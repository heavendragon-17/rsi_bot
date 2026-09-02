from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from app.backtest.core_v2_1.data import (
    build_point_in_time_context,
    resample_closed_candles,
)
from app.backtest.core_v2_1.replay import _to_core_evaluation_input
from app.signal.core_v2_1.buffer import ClosedCandleBuffer, MarketDataIntegrityError, PointInTimeBundleBuilder
from app.signal.core_v2_1.coordinator import RuntimeEvaluation
from app.signal.core_v2_1.core_adapter import (
    RUNTIME_STRATEGY_VERSION,
    CoreV21RuntimeEvaluator,
    build_core_evaluation_input,
)
from app.signal.core_v2_1.hyperliquid_export import PUMP_FILENAME
from app.signal.core_v2_1.live_runtime import CoreV21LiveSignalRuntime
from app.signal.core_v2_1.market_data import (
    CompositeMarketDataRouter,
    MarketDataSourceError,
)
from app.signal.core_v2_1.market_plan import build_core_v2_1_market_plan
from app.signal.core_v2_1.models import (
    BundleRequirement,
    ClosedCandle,
    MarketKey,
    MarketPlan,
    TriggerPlan,
    Venue,
    timeframe_delta,
)
from app.signal.core_v2_1.state_store import CoreV21StateStore
from app.trading.strategy.core_v2_1 import (
    FEATURE_ANCHOR_M15_OPEN,
    FEATURE_ANCHOR_VERSION,
    compute_alt_h1_indicators,
    compute_btc_h1_indicators,
    compute_btc_h4_indicators,
    compute_m15_indicators,
    first_fully_covered_close,
)


def _history(
    key: MarketKey,
    *,
    count: int,
    ending: datetime,
    start_price: Decimal,
) -> tuple[ClosedCandle, ...]:
    duration = {
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
    }[key.timeframe]
    result = []
    for index in range(count):
        close_time = ending - duration * (count - index - 1)
        close = start_price + Decimal(index) / Decimal("10")
        result.append(
            ClosedCandle(
                key=key,
                open_time=close_time - duration,
                close_time=close_time,
                open=close - Decimal("0.05"),
                high=close + Decimal("0.2"),
                low=close - Decimal("0.2"),
                close=close,
                volume=Decimal("100"),
            )
        )
    return tuple(result)


def test_runtime_adapter_builds_closed_exact_cadence_core_input() -> None:
    full_plan = build_core_v2_1_market_plan()
    eth_plan = next(item for item in full_plan.triggers if item.strategy_symbol == "ETHUSDT")
    plan = MarketPlan((eth_plan,))
    anchor = datetime(2026, 1, 10, 12, tzinfo=UTC)
    buffer = ClosedCandleBuffer(max_candles_per_market=1000)

    for requirement in eth_plan.requirements:
        count = requirement.minimum_candles
        start_price = Decimal("2000") if requirement.key.instrument.startswith("ETH") else Decimal("90000")
        buffer.add_many(
            _history(
                requirement.key,
                count=count,
                ending=anchor,
                start_price=start_price,
            )
        )

    bundle = PointInTimeBundleBuilder(buffer).build(plan.triggers[0], anchor)
    adapter = CoreV21RuntimeEvaluator()
    result = adapter.evaluate(bundle, "ETHUSDT", adapter.initial_state())

    assert result.next_state.last_processed_at == anchor
    payload = adapter.dump_state(result.next_state)
    assert adapter.load_state(payload) == result.next_state
    assert result.decision_kind


class _GeneratedBinanceSource:
    venue = Venue.BINANCE_FUTURES

    def fetch_closed(self, key, start_close, end_close):
        duration = timeframe_delta(key.timeframe)
        seconds = int(duration.total_seconds())
        start_seconds = int(start_close.timestamp())
        quotient, remainder = divmod(start_seconds, seconds)
        if remainder:
            quotient += 1
        current = datetime.fromtimestamp(quotient * seconds, tz=UTC)
        last_seconds = (int(end_close.timestamp()) // seconds) * seconds
        last = datetime.fromtimestamp(last_seconds, tz=UTC)
        candles = []
        while current <= last:
            base = Decimal(int((current - datetime(2025, 1, 1, tzinfo=UTC)).total_seconds()))
            close = Decimal("1000") + base / Decimal("100000")
            candles.append(
                ClosedCandle(
                    key=key,
                    open_time=current - duration,
                    close_time=current,
                    open=close - Decimal("0.05"),
                    high=close + Decimal("0.2"),
                    low=close - Decimal("0.2"),
                    close=close,
                    volume=Decimal("100"),
                )
            )
            current += duration
        return tuple(candles)


class _TruncatedGeneratedSource(_GeneratedBinanceSource):
    def __init__(
        self,
        *,
        drop_first: bool = False,
        drop_middle: bool = False,
        drop_last: bool = False,
        drop_all: bool = False,
    ) -> None:
        self._drop_first = drop_first
        self._drop_middle = drop_middle
        self._drop_last = drop_last
        self._drop_all = drop_all

    def fetch_closed(self, key, start_close, end_close):
        candles = super().fetch_closed(key, start_close, end_close)
        if self._drop_all:
            return ()
        if self._drop_first and candles:
            candles = candles[1:]
        if self._drop_middle and len(candles) >= 3:
            middle = len(candles) // 2
            candles = candles[:middle] + candles[middle + 1 :]
        if self._drop_last and candles:
            candles = candles[:-1]
        return candles


class _RetentionLimitedHyperliquidSource(_GeneratedBinanceSource):
    venue = Venue.HYPERLIQUID_PERP

    def __init__(self, *, maximum_m15_candles: int) -> None:
        self.maximum_m15_candles = maximum_m15_candles
        self.m15_calls: list[tuple[datetime, datetime]] = []

    def fetch_closed(self, key, start_close, end_close):
        if key.timeframe == "15m":
            self.m15_calls.append((start_close, end_close))
            duration = timeframe_delta(key.timeframe)
            requested = int((end_close - start_close) / duration) + 1
            if requested > self.maximum_m15_candles:
                raise MarketDataSourceError(
                    f"retained coverage is limited to {self.maximum_m15_candles} candles"
                )
        return super().fetch_closed(key, start_close, end_close)


def _canonical_frame(candles: tuple[ClosedCandle, ...]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_at": [candle.open_time for candle in candles],
            "open": [float(candle.open) for candle in candles],
            "high": [float(candle.high) for candle in candles],
            "low": [float(candle.low) for candle in candles],
            "close": [float(candle.close) for candle in candles],
            "volume": [float(candle.volume) for candle in candles],
        },
        index=pd.DatetimeIndex(
            [candle.close_time for candle in candles],
            name="closed_at",
        ),
    )


def _frame_candles(key: MarketKey, frame: pd.DataFrame) -> tuple[ClosedCandle, ...]:
    return tuple(
        ClosedCandle(
            key=key,
            open_time=row["open_at"].to_pydatetime(),
            close_time=closed_at.to_pydatetime(),
            open=Decimal(str(row["open"])),
            high=Decimal(str(row["high"])),
            low=Decimal(str(row["low"])),
            close=Decimal(str(row["close"])),
            volume=Decimal(str(row["volume"])),
        )
        for closed_at, row in frame.iterrows()
    )


def test_native_dependency_adapter_matches_m15_resampled_replay_input() -> None:
    full_plan = build_core_v2_1_market_plan()
    eth_plan = next(
        item for item in full_plan.triggers if item.strategy_symbol == "ETHUSDT"
    )
    through = datetime(2026, 7, 17, 16, tzinfo=UTC)
    source = _GeneratedBinanceSource()
    alt_m15_candles = source.fetch_closed(
        eth_plan.trigger,
        first_fully_covered_close("15m"),
        through,
    )
    btc_m15_key = MarketKey(
        Venue.BINANCE_FUTURES,
        "BTC/USDT:USDT",
        "15m",
    )
    btc_m15_candles = source.fetch_closed(
        btc_m15_key,
        first_fully_covered_close("15m"),
        through,
    )
    alt_m15 = _canonical_frame(alt_m15_candles)
    btc_m15 = _canonical_frame(btc_m15_candles)
    alt_h1_raw = resample_closed_candles(alt_m15, "1h")
    btc_h1_raw = resample_closed_candles(btc_m15, "1h")
    btc_h4_raw = resample_closed_candles(btc_m15, "4h")

    replay_m15 = compute_m15_indicators(alt_m15)
    replay_alt_h1 = compute_alt_h1_indicators(alt_h1_raw)
    replay_btc_h1 = compute_btc_h1_indicators(btc_h1_raw)
    replay_btc_h4 = compute_btc_h4_indicators(btc_h4_raw)
    context = build_point_in_time_context(
        symbol=eth_plan.strategy_symbol,
        as_of=through,
        m15=replay_m15,
        alt_h1=replay_alt_h1,
        btc_h1=replay_btc_h1,
        btc_h4=replay_btc_h4,
    )
    assert context is not None
    replay_input = _to_core_evaluation_input(context)

    alt_h1_key = next(
        requirement.key
        for requirement in eth_plan.requirements
        if requirement.key.instrument == eth_plan.trigger.instrument
        and requirement.key.timeframe == "1h"
    )
    btc_h1_key = next(
        requirement.key
        for requirement in eth_plan.requirements
        if requirement.key.instrument == "BTC/USDT:USDT"
        and requirement.key.timeframe == "1h"
    )
    btc_h4_key = next(
        requirement.key
        for requirement in eth_plan.requirements
        if requirement.key.instrument == "BTC/USDT:USDT"
        and requirement.key.timeframe == "4h"
    )
    live_histories = (
        alt_m15_candles,
        _frame_candles(alt_h1_key, alt_h1_raw),
        _frame_candles(btc_h1_key, btc_h1_raw),
        _frame_candles(btc_h4_key, btc_h4_raw),
    )
    buffer = ClosedCandleBuffer(max_candles_per_market=None)
    for candles in live_histories:
        buffer.add_many(candles)
    live_bundle = PointInTimeBundleBuilder(buffer).build(eth_plan, through)
    live_input = build_core_evaluation_input(
        live_bundle,
        eth_plan.strategy_symbol,
    )
    assert live_input == replay_input


def _write_pump_seed(path, candles: tuple[ClosedCandle, ...]) -> None:
    pd.DataFrame(
        {
            "timestamp": [
                (pd.Timestamp(candle.open_time) + pd.Timedelta(hours=7)).tz_localize(None)
                for candle in candles
            ],
            "open": [str(candle.open) for candle in candles],
            "high": [str(candle.high) for candle in candles],
            "low": [str(candle.low) for candle in candles],
            "close": [str(candle.close) for candle in candles],
            "volume": [str(candle.volume) for candle in candles],
        }
    ).to_csv(path, index=False)


class _NoopSink:
    def deliver(self, message, *, topic_id, event_id):
        return None


def test_live_signal_runtime_composes_hydrate_bootstrap_poll_and_outbox(tmp_path) -> None:
    full_plan = build_core_v2_1_market_plan()
    eth_plan = next(item for item in full_plan.triggers if item.strategy_symbol == "ETHUSDT")
    runtime = CoreV21LiveSignalRuntime(
        state_database=tmp_path / "live.sqlite3",
        market_router=CompositeMarketDataRouter((_GeneratedBinanceSource(),)),
        notification_sink=_NoopSink(),
        market_plan=MarketPlan((eth_plan,)),
        poll_interval_seconds=60,
        clock=lambda: datetime(2026, 7, 17, 16, 7, tzinfo=UTC),
    )

    result = runtime.start()
    try:
        assert result.hydrated_candles > 0
        assert result.bootstrap.ready
        health = runtime.health()
        assert health.started
        assert health.coordinator_ready
        assert health.poller_alive
    finally:
        runtime.stop()
    assert not runtime.health().started


def test_live_cold_start_seeds_pump_csv_then_fetches_only_retained_tail(
    monkeypatch,
    tmp_path,
) -> None:
    full_plan = build_core_v2_1_market_plan()
    locked_pump = next(
        item for item in full_plan.triggers if item.strategy_symbol == "PUMP"
    )
    pump_plan = TriggerPlan(
        strategy_symbol=locked_pump.strategy_symbol,
        trigger=locked_pump.trigger,
        requirements=tuple(
            BundleRequirement(
                key=requirement.key,
                minimum_candles=1,
                max_staleness=requirement.max_staleness,
                require_contiguous=requirement.require_contiguous,
                require_boundary_close=requirement.require_boundary_close,
            )
            for requirement in locked_pump.requirements
        ),
    )
    plan = MarketPlan((pump_plan,))
    boundary = FEATURE_ANCHOR_M15_OPEN + timedelta(hours=6, minutes=15)
    seed_last_close = boundary - timedelta(minutes=15)
    seed = _GeneratedBinanceSource().fetch_closed(
        pump_plan.trigger,
        first_fully_covered_close("15m"),
        seed_last_close,
    )
    data_dir = tmp_path / "candles"
    data_dir.mkdir()
    _write_pump_seed(data_dir / PUMP_FILENAME, seed)
    hyperliquid = _RetentionLimitedHyperliquidSource(maximum_m15_candles=2)

    def quiet_evaluation(self, bundle, strategy_symbol, state):
        return RuntimeEvaluation(
            next_state=state,
            decision_kind="QUIET",
            event=None,
            decision_payload={},
        )

    def quiet_prepared_evaluation(self, trigger_plan, as_of, state):
        return RuntimeEvaluation(
            next_state=state,
            decision_kind="QUIET",
            event=None,
            decision_payload={},
        )

    monkeypatch.setattr(CoreV21RuntimeEvaluator, "evaluate", quiet_evaluation)
    monkeypatch.setattr(
        CoreV21RuntimeEvaluator,
        "evaluate_prepared",
        quiet_prepared_evaluation,
    )
    monkeypatch.setattr(
        CoreV21RuntimeEvaluator,
        "assert_prepared_ready",
        lambda self, trigger_plan, as_of: None,
    )
    database = tmp_path / "pump-live.sqlite3"
    runtime = CoreV21LiveSignalRuntime(
        state_database=database,
        market_router=CompositeMarketDataRouter(
            (_GeneratedBinanceSource(), hyperliquid)
        ),
        notification_sink=_NoopSink(),
        market_plan=plan,
        bootstrap_data_dir=data_dir,
        poll_interval_seconds=60,
        clock=lambda: boundary + timedelta(seconds=5),
    )

    result = runtime.start()
    try:
        assert result.bootstrap.ready
    finally:
        runtime.stop()

    assert hyperliquid.m15_calls[0] == (seed_last_close, boundary)
    stored = CoreV21StateStore(database).load_market_candles(pump_plan.trigger)
    assert stored[0] == seed[0]
    assert stored[-1].close_time == boundary
    assert stored[0].key.venue is Venue.HYPERLIQUID_PERP


def test_restart_uses_persisted_indicator_anchor_and_matches_uninterrupted_state(tmp_path) -> None:
    full_plan = build_core_v2_1_market_plan()
    eth_plan = next(item for item in full_plan.triggers if item.strategy_symbol == "ETHUSDT")
    plan = MarketPlan((eth_plan,))
    source = _GeneratedBinanceSource()
    router = CompositeMarketDataRouter((source,))
    original_db = tmp_path / "original.sqlite3"
    restart_db = tmp_path / "restart.sqlite3"
    def first_clock() -> datetime:
        return datetime(2026, 7, 17, 16, 7, tzinfo=UTC)
    original = CoreV21LiveSignalRuntime(
        state_database=original_db,
        market_router=router,
        notification_sink=_NoopSink(),
        market_plan=plan,
        poll_interval_seconds=60,
        clock=first_clock,
    )
    original.start()
    original.stop()
    shutil.copy2(original_db, restart_db)

    next_candle = source.fetch_closed(
        eth_plan.trigger,
        datetime(2026, 7, 17, 16, 15, tzinfo=UTC),
        datetime(2026, 7, 17, 16, 22, tzinfo=UTC),
    )[-1]
    original.coordinator.on_closed_candle(next_candle)
    uninterrupted_cursor = CoreV21StateStore(original_db).load_cursor(
        RUNTIME_STRATEGY_VERSION,
        eth_plan.trigger,
    )
    assert uninterrupted_cursor is not None
    uninterrupted_input = build_core_evaluation_input(
        original.coordinator.build_as_of_bundle(
            eth_plan.trigger,
            uninterrupted_cursor.last_processed_at,
        ),
        "ETHUSDT",
    )

    restarted = CoreV21LiveSignalRuntime(
        state_database=restart_db,
        market_router=router,
        notification_sink=_NoopSink(),
        market_plan=plan,
        poll_interval_seconds=60,
        clock=lambda: datetime(2026, 7, 17, 16, 22, tzinfo=UTC),
    )
    restarted.start()
    restarted.stop()
    restarted_cursor = CoreV21StateStore(restart_db).load_cursor(
        RUNTIME_STRATEGY_VERSION,
        eth_plan.trigger,
    )
    assert restarted_cursor is not None
    assert restarted_cursor.last_processed_at == uninterrupted_cursor.last_processed_at
    assert restarted_cursor.state_payload == uninterrupted_cursor.state_payload
    assert restarted_cursor.feature_anchor_version == FEATURE_ANCHOR_VERSION
    assert restarted_cursor.feature_anchor_open == FEATURE_ANCHOR_M15_OPEN
    restarted_input = build_core_evaluation_input(
        restarted.coordinator.build_as_of_bundle(
            eth_plan.trigger,
            restarted_cursor.last_processed_at,
        ),
        "ETHUSDT",
    )
    assert restarted_input == uninterrupted_input
    assert restarted_input.current_m15.ema21 == uninterrupted_input.current_m15.ema21
    assert restarted_input.current_m15.ema200 == uninterrupted_input.current_m15.ema200
    assert restarted_input.current_m15.rsi_wma45 == uninterrupted_input.current_m15.rsi_wma45


def test_locked_feature_anchor_has_exact_native_bucket_contract() -> None:
    assert FEATURE_ANCHOR_M15_OPEN == datetime(2026, 6, 29, 11, 15, tzinfo=UTC)
    assert first_fully_covered_close("15m") == datetime(
        2026, 6, 29, 11, 30, tzinfo=UTC
    )
    assert first_fully_covered_close("1h") == datetime(
        2026, 6, 29, 13, 0, tzinfo=UTC
    )
    assert first_fully_covered_close("4h") == datetime(
        2026, 6, 29, 16, 0, tzinfo=UTC
    )


def test_hydrate_fails_closed_when_locked_anchor_is_no_longer_available(tmp_path) -> None:
    full_plan = build_core_v2_1_market_plan()
    eth_plan = next(item for item in full_plan.triggers if item.strategy_symbol == "ETHUSDT")
    runtime = CoreV21LiveSignalRuntime(
        state_database=tmp_path / "missing-anchor.sqlite3",
        market_router=CompositeMarketDataRouter(
            (_TruncatedGeneratedSource(drop_first=True),)
        ),
        notification_sink=_NoopSink(),
        market_plan=MarketPlan((eth_plan,)),
        clock=lambda: datetime(2026, 7, 17, 16, 7, tzinfo=UTC),
    )

    with pytest.raises(MarketDataIntegrityError, match="incomplete"):
        runtime.start()


def test_hydrate_fails_closed_on_partial_latest_tail(tmp_path) -> None:
    full_plan = build_core_v2_1_market_plan()
    eth_plan = next(item for item in full_plan.triggers if item.strategy_symbol == "ETHUSDT")
    runtime = CoreV21LiveSignalRuntime(
        state_database=tmp_path / "partial-tail.sqlite3",
        market_router=CompositeMarketDataRouter(
            (_TruncatedGeneratedSource(drop_last=True),)
        ),
        notification_sink=_NoopSink(),
        market_plan=MarketPlan((eth_plan,)),
        clock=lambda: datetime(2026, 7, 17, 16, 7, tzinfo=UTC),
    )

    with pytest.raises(MarketDataIntegrityError, match="incomplete"):
        runtime.start()


def test_hydrate_rejects_interior_gap_before_candles_become_immutable(tmp_path) -> None:
    full_plan = build_core_v2_1_market_plan()
    eth_plan = next(item for item in full_plan.triggers if item.strategy_symbol == "ETHUSDT")
    database = tmp_path / "interior-gap.sqlite3"
    runtime = CoreV21LiveSignalRuntime(
        state_database=database,
        market_router=CompositeMarketDataRouter(
            (_TruncatedGeneratedSource(drop_middle=True),)
        ),
        notification_sink=_NoopSink(),
        market_plan=MarketPlan((eth_plan,)),
        clock=lambda: datetime(2026, 7, 17, 16, 7, tzinfo=UTC),
    )

    with pytest.raises(MarketDataIntegrityError, match="incomplete"):
        runtime.start()
    assert CoreV21StateStore(database).load_market_candles(eth_plan.trigger) == ()


def test_restart_fails_closed_when_venue_returns_empty_catchup(tmp_path) -> None:
    full_plan = build_core_v2_1_market_plan()
    eth_plan = next(item for item in full_plan.triggers if item.strategy_symbol == "ETHUSDT")
    plan = MarketPlan((eth_plan,))
    database = tmp_path / "empty-tail.sqlite3"
    first = CoreV21LiveSignalRuntime(
        state_database=database,
        market_router=CompositeMarketDataRouter((_GeneratedBinanceSource(),)),
        notification_sink=_NoopSink(),
        market_plan=plan,
        clock=lambda: datetime(2026, 7, 17, 16, 7, tzinfo=UTC),
    )
    first.start()
    first.stop()

    restarted = CoreV21LiveSignalRuntime(
        state_database=database,
        market_router=CompositeMarketDataRouter(
            (_TruncatedGeneratedSource(drop_all=True),)
        ),
        notification_sink=_NoopSink(),
        market_plan=plan,
        clock=lambda: datetime(2026, 7, 17, 16, 22, tzinfo=UTC),
    )
    with pytest.raises(MarketDataIntegrityError, match="incomplete"):
        restarted.start()
