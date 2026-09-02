"""Adapter from raw point-in-time market bundles to the pure Core V2.1 API."""

from __future__ import annotations

import bisect
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, TypeVar

import pandas as pd

from app.signal.core_v2_1.buffer import BundleNotReady, MarketDataIntegrityError
from app.signal.core_v2_1.coordinator import RuntimeEvaluation
from app.signal.core_v2_1.models import (
    AdvisoryEvent,
    AsOfBundle,
    ClosedCandle,
    MarketKey,
    MarketSeries,
    TriggerPlan,
    ensure_utc,
    timeframe_delta,
)
from app.trading.strategy.core_v2_1 import (
    BTC_BENCHMARK,
    CONFIG_VERSION,
    INDICATOR_VERSION,
    READINESS_COLUMN,
    AltH1Snapshot,
    BtcH1Snapshot,
    BtcH4Snapshot,
    CoreState,
    EvaluationInput,
    M15Snapshot,
    M15TrendSnapshot,
    compute_alt_h1_indicators,
    compute_btc_h1_indicators,
    compute_btc_h4_indicators,
    compute_m15_indicators,
    evaluate_core_v2_1,
    instrument_for_symbol,
)
from app.trading.strategy.core_v2_1.feature_anchor import (
    FEATURE_ANCHOR_VERSION,
    first_fully_covered_close,
)

RUNTIME_STRATEGY_VERSION = (
    f"{CONFIG_VERSION}|{INDICATOR_VERSION}|{FEATURE_ANCHOR_VERSION}"
)
SnapshotT = TypeVar("SnapshotT")


class CoreV21RuntimeEvaluator:
    """Concrete adapter with a causally safe prepared-feature cache.

    The evaluator's strategy state remains an explicit input/output value.  The
    mutable cache contains only deterministic market features.  Each feature
    row is computed by a forward-only indicator implementation, so selecting a
    historical row from a frame prepared through a later close is identical to
    computing the same indicator on that historical prefix.
    """

    def __init__(self) -> None:
        self._prepared: dict[MarketKey, _PreparedMarket] = {}
        self._prepared_lock = threading.RLock()

    def initial_state(self) -> CoreState:
        return CoreState.initial()

    def evaluate(
        self,
        bundle: AsOfBundle,
        strategy_symbol: str,
        state: CoreState,
    ) -> RuntimeEvaluation[CoreState]:
        evaluation_input = build_core_evaluation_input(bundle, strategy_symbol)
        return _runtime_evaluation(evaluation_input, state)

    def prepare_history(self, series: tuple[MarketSeries, ...]) -> None:
        """Build every recursive feature frame once and atomically publish it."""

        prepared: dict[MarketKey, _PreparedMarket] = {}
        for item in sorted(series, key=lambda value: value.key):
            if item.key in prepared:
                raise ValueError(f"Duplicate prepared series: {item.key.storage_id}")
            prepared[item.key] = _prepare_market(item)
        with self._prepared_lock:
            self._prepared = prepared

    def update_history(self, candle: ClosedCandle) -> bool:
        """Append one immutable live close and refresh only its feature frame."""

        with self._prepared_lock:
            current = self._prepared.get(candle.key)
            if current is None:
                raise MarketDataIntegrityError(
                    f"Prepared history is missing {candle.key.storage_id}"
                )
            position = bisect.bisect_left(current.close_times, candle.close_time)
            if (
                position < len(current.close_times)
                and current.close_times[position] == candle.close_time
            ):
                if current.series.candles[position] != candle:
                    raise MarketDataIntegrityError(
                        f"Conflicting prepared candle for {candle.key.storage_id} at "
                        f"{candle.close_time.isoformat()}"
                    )
                return False
            expected = current.close_times[-1] + timeframe_delta(candle.key.timeframe)
            if candle.close_time != expected:
                raise MarketDataIntegrityError(
                    f"Prepared live history gap for {candle.key.storage_id}: expected "
                    f"{expected.isoformat()}, got {candle.close_time.isoformat()}"
                )
            updated = MarketSeries(
                key=candle.key,
                candles=(*current.series.candles, candle),
            )
            self._prepared[candle.key] = _prepare_market(updated)
            return True

    def evaluate_prepared(
        self,
        trigger_plan: TriggerPlan,
        as_of: datetime,
        state: CoreState,
    ) -> RuntimeEvaluation[CoreState]:
        """Evaluate one PIT close from precomputed feature rows in O(1)."""

        with self._prepared_lock:
            evaluation_input = self._prepared_input(trigger_plan, as_of)
            return _runtime_evaluation(evaluation_input, state)

    def assert_prepared_ready(self, trigger_plan: TriggerPlan, as_of: datetime) -> None:
        """Validate that the latest close has a complete prepared PIT input."""

        with self._prepared_lock:
            self._prepared_input(trigger_plan, as_of)

    def _prepared_input(
        self,
        trigger_plan: TriggerPlan,
        as_of: datetime,
    ) -> EvaluationInput:
        as_of_utc = ensure_utc(as_of, field_name="as_of")
        instrument = instrument_for_symbol(trigger_plan.strategy_symbol)
        if trigger_plan.trigger.venue is not instrument.venue:
            raise ValueError("trigger venue does not match locked strategy instrument")
        if trigger_plan.trigger.instrument != instrument.venue_symbol:
            raise ValueError("trigger source instrument does not match locked strategy instrument")

        positions: dict[MarketKey, int] = {}
        for requirement in trigger_plan.requirements:
            history = self._prepared.get(requirement.key)
            if history is None:
                raise BundleNotReady(
                    f"Prepared history is missing {requirement.key.storage_id}"
                )
            position = bisect.bisect_right(history.close_times, as_of_utc) - 1
            available = position + 1
            if available < requirement.minimum_candles:
                raise BundleNotReady(
                    f"{requirement.key.storage_id} has {available} closed candles as of "
                    f"{as_of_utc.isoformat()}, needs {requirement.minimum_candles}"
                )
            latest = history.close_times[position]
            if requirement.key == trigger_plan.trigger and latest != as_of_utc:
                raise BundleNotReady(
                    f"Trigger {trigger_plan.trigger.storage_id} has no close at "
                    f"{as_of_utc.isoformat()}"
                )
            age = as_of_utc - latest
            if age < timedelta(0):
                raise MarketDataIntegrityError(
                    f"{requirement.key.storage_id} contains future data"
                )
            if age > requirement.max_staleness:
                raise MarketDataIntegrityError(
                    f"{requirement.key.storage_id} is stale by {age}; maximum is "
                    f"{requirement.max_staleness}"
                )
            if requirement.require_boundary_close:
                expected = _floor_utc_boundary(as_of_utc, requirement.key.timeframe)
                if latest != expected:
                    raise MarketDataIntegrityError(
                        f"{requirement.key.storage_id} boundary is incomplete: expected "
                        f"{expected.isoformat()}, got {latest.isoformat()}"
                    )
            positions[requirement.key] = position

        trigger = trigger_plan.trigger
        alt_h1_key = MarketKey(trigger.venue, trigger.instrument, "1h")
        btc_h1_key = MarketKey(
            BTC_BENCHMARK.venue,
            BTC_BENCHMARK.venue_symbol,
            "1h",
        )
        btc_h4_key = MarketKey(
            BTC_BENCHMARK.venue,
            BTC_BENCHMARK.venue_symbol,
            "4h",
        )
        m15_position = positions[trigger]
        if m15_position < 3:
            raise BundleNotReady(
                f"{trigger.storage_id} needs four candles for exact M15 snapshots"
            )
        current = _prepared_snapshot(
            self._prepared[trigger], m15_position, _PreparedM15Row, "M15"
        )
        previous = _prepared_snapshot(
            self._prepared[trigger], m15_position - 1, _PreparedM15Row, "M15"
        )
        three_bars_ago = _prepared_snapshot(
            self._prepared[trigger], m15_position - 3, _PreparedM15Row, "M15"
        )
        alt_latest = _prepared_snapshot(
            self._prepared[alt_h1_key],
            positions[alt_h1_key],
            AltH1Snapshot,
            "alt H1",
        )
        btc_h1_latest = _prepared_snapshot(
            self._prepared[btc_h1_key],
            positions[btc_h1_key],
            BtcH1Snapshot,
            "BTC H1",
        )
        btc_h4_latest = _prepared_snapshot(
            self._prepared[btc_h4_key],
            positions[btc_h4_key],
            BtcH4Snapshot,
            "BTC H4",
        )
        if current.snapshot is None:
            raise ValueError(f"M15 indicator snapshot at index {m15_position} is not ready")
        if previous.snapshot is None:
            raise ValueError(
                f"M15 indicator snapshot at index {m15_position - 1} is not ready"
            )
        return EvaluationInput(
            symbol=trigger_plan.strategy_symbol,
            venue=instrument.venue,
            current_m15=current.snapshot,
            previous_m15=previous.snapshot,
            m15_three_bars_ago=three_bars_ago.trend,
            alt_h1=alt_latest,
            btc_h1=btc_h1_latest,
            btc_h4=btc_h4_latest,
        )

    def dump_state(self, state: CoreState) -> Mapping[str, Any]:
        return state.to_dict()

    def load_state(self, payload: Mapping[str, Any]) -> CoreState:
        return CoreState.from_dict(payload)


def build_core_evaluation_input(
    bundle: AsOfBundle,
    strategy_symbol: str,
) -> EvaluationInput:
    instrument = instrument_for_symbol(strategy_symbol)
    if bundle.trigger_key.venue is not instrument.venue:
        raise ValueError("bundle venue does not match locked strategy instrument")
    if bundle.trigger_key.instrument != instrument.venue_symbol:
        raise ValueError("bundle source instrument does not match locked strategy instrument")

    trigger = bundle.trigger_key
    alt_h1_key = MarketKey(trigger.venue, trigger.instrument, "1h")
    btc_h1_key = MarketKey(BTC_BENCHMARK.venue, BTC_BENCHMARK.venue_symbol, "1h")
    btc_h4_key = MarketKey(BTC_BENCHMARK.venue, BTC_BENCHMARK.venue_symbol, "4h")

    m15 = compute_m15_indicators(_series_frame(bundle, trigger))
    alt_h1 = compute_alt_h1_indicators(_series_frame(bundle, alt_h1_key))
    btc_h1 = compute_btc_h1_indicators(_series_frame(bundle, btc_h1_key))
    btc_h4 = compute_btc_h4_indicators(_series_frame(bundle, btc_h4_key))
    _require_ready(m15, "M15", indexes=(-1, -2))
    if not pd.notna(m15.iloc[-4]["ema21"]):
        raise ValueError("M15 EMA21 trend snapshot at index -4 is not ready")
    _require_ready(alt_h1, "alt H1")
    _require_ready(btc_h1, "BTC H1")
    _require_ready(btc_h4, "BTC H4")

    current = m15.iloc[-1]
    previous = m15.iloc[-2]
    three_bars_ago = m15.iloc[-4]
    alt_latest = alt_h1.iloc[-1]
    btc_h1_latest = btc_h1.iloc[-1]
    btc_h4_latest = btc_h4.iloc[-1]

    return _evaluation_input_from_rows(
        strategy_symbol=strategy_symbol,
        venue=instrument.venue,
        current=current,
        previous=previous,
        three_bars_ago=three_bars_ago,
        alt_latest=alt_latest,
        btc_h1_latest=btc_h1_latest,
        btc_h4_latest=btc_h4_latest,
    )


@dataclass(frozen=True)
class _PreparedM15Row:
    snapshot: M15Snapshot | None
    trend: M15TrendSnapshot


@dataclass(frozen=True)
class _PreparedMarket:
    series: MarketSeries
    close_times: tuple[datetime, ...]
    frame: pd.DataFrame
    snapshots: tuple[
        _PreparedM15Row | AltH1Snapshot | BtcH1Snapshot | BtcH4Snapshot | None,
        ...,
    ]


def _prepare_market(series: MarketSeries) -> _PreparedMarket:
    if not series.candles:
        raise BundleNotReady(f"No candles for {series.key.storage_id}")
    expected_first = first_fully_covered_close(series.key.timeframe)
    if series.candles[0].close_time != expected_first:
        raise MarketDataIntegrityError(
            f"Prepared feature anchor mismatch for {series.key.storage_id}: expected "
            f"{expected_first.isoformat()}, got {series.candles[0].close_time.isoformat()}"
        )
    duration = timeframe_delta(series.key.timeframe)
    for previous, current in zip(
        series.candles,
        series.candles[1:],
        strict=False,
    ):
        if current.close_time - previous.close_time != duration:
            raise MarketDataIntegrityError(
                f"Gap in prepared {series.key.storage_id}: "
                f"{previous.close_time.isoformat()} to {current.close_time.isoformat()}"
            )
    frame = _market_series_frame(series)
    btc_key = (BTC_BENCHMARK.venue, BTC_BENCHMARK.venue_symbol)
    identity = (series.key.venue, series.key.instrument)
    if series.key.timeframe == "15m":
        enriched = compute_m15_indicators(frame)
    elif series.key.timeframe == "1h" and identity == btc_key:
        enriched = compute_btc_h1_indicators(frame)
    elif series.key.timeframe == "1h":
        enriched = compute_alt_h1_indicators(frame)
    elif series.key.timeframe == "4h" and identity == btc_key:
        enriched = compute_btc_h4_indicators(frame)
    else:
        raise ValueError(f"Unsupported Core V2.1 market: {series.key.storage_id}")
    return _PreparedMarket(
        series=series,
        close_times=tuple(candle.close_time for candle in series.candles),
        frame=enriched,
        snapshots=_prepare_snapshots(enriched, series),
    )


def _prepare_snapshots(
    frame: pd.DataFrame,
    series: MarketSeries,
) -> tuple[_PreparedM15Row | AltH1Snapshot | BtcH1Snapshot | BtcH4Snapshot | None, ...]:
    """Materialize typed immutable rows once for O(1) historical replay.

    Pandas ``iloc`` creates and coerces a Series on every access.  A full cold
    bootstrap performs hundreds of thousands of row selections, so retaining
    the already-computed values as domain snapshots avoids that repeated cost
    without changing indicator arithmetic or point-in-time selection.
    """

    ready = frame[READINESS_COLUMN].to_numpy(dtype=bool, copy=False)
    closes = tuple(candle.close_time for candle in series.candles)
    rows: list[
        _PreparedM15Row | AltH1Snapshot | BtcH1Snapshot | BtcH4Snapshot | None
    ] = [None] * len(frame)

    def values(column: str):
        return frame[column].to_numpy(copy=False)

    rsi21 = values("rsi21")
    rsi_ema9 = values("rsi_ema9")
    rsi_wma45 = values("rsi_wma45")
    identity = (series.key.venue, series.key.instrument)
    btc_key = (BTC_BENCHMARK.venue, BTC_BENCHMARK.venue_symbol)

    if series.key.timeframe == "15m":
        opens = values("open")
        highs = values("high")
        lows = values("low")
        prices = values("close")
        ema21 = values("ema21")
        ema200 = values("ema200")
        atr14 = values("atr14")
        for index, is_ready in enumerate(ready):
            snapshot = (
                M15Snapshot(
                    closed_at=closes[index],
                    is_closed=True,
                    open=_decimal(opens[index]),
                    high=_decimal(highs[index]),
                    low=_decimal(lows[index]),
                    close=_decimal(prices[index]),
                    ema21=_decimal(ema21[index]),
                    ema200=_decimal(ema200[index]),
                    atr14=_decimal(atr14[index]),
                    rsi21=_decimal(rsi21[index]),
                    rsi_ema9=_decimal(rsi_ema9[index]),
                    rsi_wma45=_decimal(rsi_wma45[index]),
                )
                if is_ready
                else None
            )
            rows[index] = _PreparedM15Row(
                snapshot=snapshot,
                trend=M15TrendSnapshot(
                    closed_at=closes[index],
                    is_closed=True,
                    ema21=_decimal(ema21[index]),
                ),
            )
        return tuple(rows)

    if series.key.timeframe == "1h" and identity != btc_key:
        for index, is_ready in enumerate(ready):
            if is_ready:
                rows[index] = AltH1Snapshot(
                    closed_at=closes[index],
                    is_closed=True,
                    rsi21=_decimal(rsi21[index]),
                    rsi_ema9=_decimal(rsi_ema9[index]),
                    rsi_wma45=_decimal(rsi_wma45[index]),
                )
        return tuple(rows)

    if series.key.timeframe == "1h" and identity == btc_key:
        prices = values("close")
        ema21 = values("ema21")
        for index, is_ready in enumerate(ready):
            if is_ready:
                rows[index] = BtcH1Snapshot(
                    closed_at=closes[index],
                    is_closed=True,
                    close=_decimal(prices[index]),
                    ema21=_decimal(ema21[index]),
                    rsi21=_decimal(rsi21[index]),
                    rsi_ema9=_decimal(rsi_ema9[index]),
                    rsi_wma45=_decimal(rsi_wma45[index]),
                )
        return tuple(rows)

    if series.key.timeframe == "4h" and identity == btc_key:
        for index, is_ready in enumerate(ready):
            if is_ready:
                rows[index] = BtcH4Snapshot(
                    closed_at=closes[index],
                    is_closed=True,
                    rsi21=_decimal(rsi21[index]),
                    rsi_ema9=_decimal(rsi_ema9[index]),
                    rsi_wma45=_decimal(rsi_wma45[index]),
                )
        return tuple(rows)

    raise ValueError(f"Unsupported Core V2.1 market: {series.key.storage_id}")


def _prepared_snapshot(
    market: _PreparedMarket,
    index: int,
    expected_type: type[SnapshotT],
    label: str,
) -> SnapshotT:
    snapshot = market.snapshots[index]
    if snapshot is None:
        raise ValueError(f"{label} indicator snapshot at index {index} is not ready")
    if not isinstance(snapshot, expected_type):
        raise TypeError(
            f"{label} prepared snapshot has unexpected type {type(snapshot).__name__}"
        )
    return snapshot


def _evaluation_input_from_rows(
    *,
    strategy_symbol: str,
    venue: Any,
    current: pd.Series,
    previous: pd.Series,
    three_bars_ago: pd.Series,
    alt_latest: pd.Series,
    btc_h1_latest: pd.Series,
    btc_h4_latest: pd.Series,
) -> EvaluationInput:
    return EvaluationInput(
        symbol=strategy_symbol,
        venue=venue,
        current_m15=_m15_snapshot(current),
        previous_m15=_m15_snapshot(previous),
        m15_three_bars_ago=M15TrendSnapshot(
            closed_at=three_bars_ago.name.to_pydatetime(),
            is_closed=True,
            ema21=_decimal(three_bars_ago["ema21"]),
        ),
        alt_h1=AltH1Snapshot(
            closed_at=alt_latest.name.to_pydatetime(),
            is_closed=True,
            rsi21=_decimal(alt_latest["rsi21"]),
            rsi_ema9=_decimal(alt_latest["rsi_ema9"]),
            rsi_wma45=_decimal(alt_latest["rsi_wma45"]),
        ),
        btc_h1=BtcH1Snapshot(
            closed_at=btc_h1_latest.name.to_pydatetime(),
            is_closed=True,
            close=_decimal(btc_h1_latest["close"]),
            ema21=_decimal(btc_h1_latest["ema21"]),
            rsi21=_decimal(btc_h1_latest["rsi21"]),
            rsi_ema9=_decimal(btc_h1_latest["rsi_ema9"]),
            rsi_wma45=_decimal(btc_h1_latest["rsi_wma45"]),
        ),
        btc_h4=BtcH4Snapshot(
            closed_at=btc_h4_latest.name.to_pydatetime(),
            is_closed=True,
            rsi21=_decimal(btc_h4_latest["rsi21"]),
            rsi_ema9=_decimal(btc_h4_latest["rsi_ema9"]),
            rsi_wma45=_decimal(btc_h4_latest["rsi_wma45"]),
        ),
    )


def _series_frame(bundle: AsOfBundle, key: MarketKey) -> pd.DataFrame:
    return _market_series_frame(bundle.for_key(key))


def _market_series_frame(series: MarketSeries) -> pd.DataFrame:
    candles = series.candles
    return pd.DataFrame(
        {
            "open": [float(candle.open) for candle in candles],
            "high": [float(candle.high) for candle in candles],
            "low": [float(candle.low) for candle in candles],
            "close": [float(candle.close) for candle in candles],
            "volume": [float(candle.volume) for candle in candles],
        },
        index=pd.DatetimeIndex([candle.close_time for candle in candles]),
    )


def _floor_utc_boundary(value: datetime, timeframe: str) -> datetime:
    seconds = int(timeframe_delta(timeframe).total_seconds())
    return datetime.fromtimestamp(
        (int(value.timestamp()) // seconds) * seconds,
        tz=UTC,
    )


def _runtime_evaluation(
    evaluation_input: EvaluationInput,
    state: CoreState,
) -> RuntimeEvaluation[CoreState]:
    result = evaluate_core_v2_1(evaluation_input, state)
    decision = result.decision
    event = _map_event(decision.event) if decision.event is not None else None
    payload: dict[str, Any] = {
        "reasons": [reason.value for reason in decision.reasons],
    }
    if decision.metrics is not None:
        payload["metrics"] = {
            "distance_atr": str(decision.metrics.distance_atr),
            "signal_range_atr": str(decision.metrics.signal_range_atr),
        }
    if decision.preferred_entry_zone is not None:
        payload["preferred_entry_zone"] = {
            "lower": str(decision.preferred_entry_zone.lower),
            "upper": str(decision.preferred_entry_zone.upper),
        }
    return RuntimeEvaluation(
        next_state=result.next_state,
        decision_kind=decision.kind.value,
        event=event,
        decision_payload=payload,
    )


def _require_ready(
    frame: pd.DataFrame,
    label: str,
    *,
    indexes: tuple[int, ...] = (-1,),
) -> None:
    for index in indexes:
        if not bool(frame.iloc[index][READINESS_COLUMN]):
            raise ValueError(f"{label} indicator snapshot at index {index} is not ready")


def _m15_snapshot(row: pd.Series) -> M15Snapshot:
    return M15Snapshot(
        closed_at=row.name.to_pydatetime(),
        is_closed=True,
        open=_decimal(row["open"]),
        high=_decimal(row["high"]),
        low=_decimal(row["low"]),
        close=_decimal(row["close"]),
        ema21=_decimal(row["ema21"]),
        ema200=_decimal(row["ema200"]),
        atr14=_decimal(row["atr14"]),
        rsi21=_decimal(row["rsi21"]),
        rsi_ema9=_decimal(row["rsi_ema9"]),
        rsi_wma45=_decimal(row["rsi_wma45"]),
    )


def _map_event(core_event: Any) -> AdvisoryEvent:
    levels = core_event.trade_levels
    zone = core_event.preferred_entry_zone
    return AdvisoryEvent(
        event_type=core_event.event_type,
        symbol=core_event.symbol,
        venue=core_event.venue,
        closed_at=core_event.closed_at,
        reasons=tuple(reason.value for reason in core_event.reasons),
        reference_entry=levels.reference_entry if levels is not None else None,
        reference_stop=levels.reference_stop if levels is not None else None,
        reference_tp1=levels.tp1 if levels is not None else None,
        reference_tp2=levels.tp2 if levels is not None else None,
        reference_tp3=levels.tp3 if levels is not None else None,
        zone_low=zone.lower if zone is not None else None,
        zone_high=zone.upper if zone is not None else None,
        wait_elapsed=core_event.wait_bars_elapsed,
    )


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))
