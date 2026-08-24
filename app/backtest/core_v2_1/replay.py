"""Chronological six-symbol, point-in-time replay for Core V2.1."""

from __future__ import annotations

import hashlib
import heapq
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd

from app.backtest.core_v2_1.audit import AuditLedger, ReplayAuditRecord
from app.backtest.core_v2_1.coverage import (
    CORE_V2_1_UNIVERSE,
    EXPECTED_LOCAL_SIX,
    CoverageReport,
    assert_pre_download_local_six,
    data_identity_for_symbol,
    data_path_for_symbol,
    normalize_symbol,
    scan_local_coverage,
    venue_for_symbol,
)
from app.backtest.core_v2_1.data import (
    CandleDataError,
    PointInTimeContext,
    build_point_in_time_context,
    load_stored_candles,
    resample_closed_candles,
)
from app.trading.strategy.core_v2_1 import (
    CONFIG_VERSION,
    FEATURE_ANCHOR_M15_OPEN,
    FEATURE_ANCHOR_VERSION,
    INDICATOR_SEED_CONVENTION,
    INDICATOR_VERSION,
    STRATEGY_VERSION,
    first_fully_covered_close,
)


class Evaluator(Protocol):
    def __call__(self, evaluation_input: Any, state: Any) -> Any: ...


@dataclass(frozen=True)
class LocalReplayData:
    alt_m15: Mapping[str, pd.DataFrame]
    btc_m15: pd.DataFrame
    coverage: CoverageReport
    common_start: pd.Timestamp
    common_end: pd.Timestamp
    input_manifest: tuple[ReplayInputMetadata, ...]


@dataclass(frozen=True)
class ReplayInputMetadata:
    role: str
    strategy_symbol: str
    venue: str
    venue_instrument: str
    path: str
    sha256: str
    retained_rows: int
    first_open_at: str
    last_closed_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "strategy_symbol": self.strategy_symbol,
            "venue": self.venue,
            "venue_instrument": self.venue_instrument,
            "path": self.path,
            "sha256": self.sha256,
            "retained_rows": self.retained_rows,
            "first_open_at": self.first_open_at,
            "last_closed_at": self.last_closed_at,
        }


@dataclass(frozen=True)
class ReplayFrames:
    """Indicator-enriched frames used by the pure state-machine evaluator."""

    alt_m15: Mapping[str, pd.DataFrame]
    alt_h1: Mapping[str, pd.DataFrame]
    btc_h1: pd.DataFrame
    btc_h4: pd.DataFrame


@dataclass(frozen=True)
class ReplayResult:
    ledger: AuditLedger
    processed_events: int
    evaluated_events: int
    not_ready_events: int
    emitted_events: int
    states: Mapping[str, Any]
    warmup_processed_events: int = 0
    warmup_evaluated_events: int = 0
    warmup_not_ready_events: int = 0


def load_pre_download_six(
    data_dir: str | Path,
    *,
    now: pd.Timestamp | str | None = None,
    assert_exact_six: bool = True,
) -> LocalReplayData:
    """Load the audited six-symbol stepping-stone plus the real BTC benchmark.

    ``assert_exact_six`` is only appropriate before the task-5 acquisition; it
    may be disabled after the directory contains the full approved universe.
    The returned common window includes only times visible for every source.
    """

    coverage = scan_local_coverage(data_dir, validate=False)
    if assert_exact_six:
        assert_pre_download_local_six(coverage)
    return load_available_universe(
        data_dir,
        symbols=EXPECTED_LOCAL_SIX,
        now=now,
        coverage=coverage,
    )


def load_available_universe(
    data_dir: str | Path,
    *,
    symbols: tuple[str, ...] | list[str] | None = None,
    require_all: bool = False,
    now: pd.Timestamp | str | None = None,
    coverage: CoverageReport | None = None,
) -> LocalReplayData:
    """Load an explicit or discovered subset without cross-venue substitution.

    ``require_all=True`` requires all 25 locked trade candidates and BTC.
    Otherwise omitted ``symbols`` means every currently available approved
    source.  PUMP always resolves to the structural Hyperliquid filename and
    can never fall back to a similarly named Binance ticker.
    """

    coverage = coverage or scan_local_coverage(data_dir, validate=False)
    if require_all:
        requested = CORE_V2_1_UNIVERSE
    elif symbols is None:
        requested = coverage.available_symbols
    else:
        requested = tuple(normalize_symbol(symbol) for symbol in symbols)
    if not requested:
        raise CandleDataError("No approved Core V2.1 source files are available")
    unknown = tuple(symbol for symbol in requested if symbol not in CORE_V2_1_UNIVERSE)
    if unknown:
        raise CandleDataError(f"Unknown Core V2.1 strategy symbol(s): {', '.join(unknown)}")
    if len(set(requested)) != len(requested):
        raise CandleDataError("Replay symbol selection contains duplicates")
    missing_paths = [
        (symbol, data_identity_for_symbol(symbol), data_path_for_symbol(data_dir, symbol))
        for symbol in requested
        if not data_path_for_symbol(data_dir, symbol).is_file()
    ]
    btc_path = data_path_for_symbol(data_dir, "BTCUSDT")
    if not btc_path.is_file():
        identity = data_identity_for_symbol("BTCUSDT")
        missing_paths.append(("BTCUSDT", identity, btc_path))
    if missing_paths:
        rendered = "; ".join(
            f"{symbol} [{identity.venue} {identity.venue_instrument}] -> {path.name}"
            for symbol, identity, path in missing_paths
        )
        raise CandleDataError(f"Missing required point-in-time source(s); no substitution allowed: {rendered}")

    alt_m15: dict[str, pd.DataFrame] = {}
    manifest: list[ReplayInputMetadata] = []
    for symbol in requested:
        path = data_path_for_symbol(data_dir, symbol)
        loaded = load_stored_candles(path, now=now, strict=True)
        anchored = _anchor_m15_frame(loaded.frame, symbol=symbol)
        alt_m15[symbol] = anchored
        manifest.append(_input_metadata("alt_trigger", symbol, path, anchored))
    btc_loaded = load_stored_candles(btc_path, now=now, strict=True)
    btc_m15 = _anchor_m15_frame(btc_loaded.frame, symbol="BTCUSDT")
    manifest.append(_input_metadata("btc_benchmark", "BTCUSDT", btc_path, btc_m15))
    frames = [*alt_m15.values(), btc_m15]
    if any(frame.empty for frame in frames):
        raise CandleDataError("Six-symbol replay requires non-empty alt and BTC M15 frames")
    common_start = max(frame.index[0] for frame in frames)
    common_end = min(frame.index[-1] for frame in frames)
    if common_start > common_end:
        raise CandleDataError("Six-symbol alt/BTC data has no common point-in-time window")
    return LocalReplayData(
        alt_m15=alt_m15,
        btc_m15=btc_m15,
        coverage=coverage,
        common_start=common_start,
        common_end=common_end,
        input_manifest=tuple(manifest),
    )


def build_replay_frames(
    source: LocalReplayData,
    *,
    m15_indicator_builder: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
    alt_h1_indicator_builder: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
    btc_h1_indicator_builder: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
    btc_h4_indicator_builder: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
) -> ReplayFrames:
    """Derive UTC H1/H4 candles and calculate dedicated Core indicators.

    Each role uses its dedicated, locked indicator function.  Optional builder
    injection is retained for isolated tests.  Resampling always occurs before
    indicator calculation.
    """

    from app.trading.strategy.core_v2_1 import (
        compute_alt_h1_indicators,
        compute_btc_h1_indicators,
        compute_btc_h4_indicators,
        compute_m15_indicators,
    )

    m15_builder = m15_indicator_builder or compute_m15_indicators
    alt_h1_builder = alt_h1_indicator_builder or compute_alt_h1_indicators
    btc_h1_builder = btc_h1_indicator_builder or compute_btc_h1_indicators
    btc_h4_builder = btc_h4_indicator_builder or compute_btc_h4_indicators
    alt_m15 = {symbol: m15_builder(frame.copy()) for symbol, frame in source.alt_m15.items()}
    alt_h1 = {
        symbol: alt_h1_builder(resample_closed_candles(frame, "1h"))
        for symbol, frame in source.alt_m15.items()
    }
    btc_h1 = btc_h1_builder(resample_closed_candles(source.btc_m15, "1h"))
    btc_h4 = btc_h4_builder(resample_closed_candles(source.btc_m15, "4h"))
    return ReplayFrames(alt_m15=alt_m15, alt_h1=alt_h1, btc_h1=btc_h1, btc_h4=btc_h4)


class CoreV21PointInTimeReplay:
    """Replay all symbol closes in stable global chronological order."""

    def __init__(
        self,
        frames: ReplayFrames,
        *,
        evaluator: Evaluator | None = None,
        state_factory: Callable[[], Any] | None = None,
    ) -> None:
        if not frames.alt_m15:
            raise CandleDataError("Replay requires at least one trigger symbol")
        if set(frames.alt_m15) != set(frames.alt_h1):
            raise CandleDataError("M15 and Alt H1 symbol sets must match")
        for frame in frames.alt_m15.values():
            _validate_replay_frame(frame, expected_cadence=pd.Timedelta(minutes=15))
        for frame in [*frames.alt_h1.values(), frames.btc_h1]:
            _validate_replay_frame(frame, expected_cadence=pd.Timedelta(hours=1))
        _validate_replay_frame(frames.btc_h4, expected_cadence=pd.Timedelta(hours=4))
        if evaluator is None or state_factory is None:
            from app.trading.strategy.core_v2_1 import CoreState, evaluate_core_v2_1

            evaluator = evaluator or evaluate_core_v2_1
            state_factory = state_factory or CoreState.initial
        self.frames = frames
        self.evaluator = evaluator
        self.state_factory = state_factory

    def run(
        self,
        *,
        start: pd.Timestamp | str | None = None,
        end: pd.Timestamp | str | None = None,
    ) -> ReplayResult:
        start_at = _optional_utc(start)
        end_at = _optional_utc(end)
        if start_at is not None and end_at is not None and start_at > end_at:
            raise ValueError("Replay start must be at or before end")

        states = {symbol: self.state_factory() for symbol in self.frames.alt_m15}
        ledger = AuditLedger()
        evaluated = 0
        not_ready = 0
        emitted = 0
        warmup_processed = 0
        warmup_evaluated = 0
        warmup_not_ready = 0
        ledger_sequence = 0
        # Always traverse pre-start history.  This warms each independent state
        # machine without exporting its decisions, so a WAIT/DISARMED cycle at
        # the requested left boundary is carried in rather than fabricated.
        for closed_at, symbol in _chronological_events(self.frames.alt_m15, start=None, end=end_at):
            in_output_window = start_at is None or closed_at >= start_at
            state_before = states[symbol]
            context = build_point_in_time_context(
                symbol=symbol,
                as_of=closed_at,
                m15=self.frames.alt_m15[symbol],
                alt_h1=self.frames.alt_h1[symbol],
                btc_h1=self.frames.btc_h1,
                btc_h4=self.frames.btc_h4,
            )
            readiness_reasons = _readiness_reasons(context)
            if readiness_reasons:
                if in_output_window:
                    not_ready += 1
                    ledger_sequence += 1
                    ledger.append(
                        ReplayAuditRecord(
                            sequence=ledger_sequence,
                            trigger_closed_at=closed_at,
                            symbol=symbol,
                            venue=venue_for_symbol(symbol),
                            context_closed_at=context.context_closed_at if context is not None else {},
                            state_before=state_before,
                            decision={"kind": "NOT_READY", "reasons": readiness_reasons},
                            state_after=state_before,
                            status="not_ready",
                        )
                    )
                else:
                    warmup_processed += 1
                    warmup_not_ready += 1
                continue

            assert context is not None
            evaluation_input = _to_core_evaluation_input(context)
            result = self.evaluator(evaluation_input, state_before)
            decision = result.decision
            states[symbol] = result.next_state
            if in_output_window:
                evaluated += 1
                if getattr(decision, "event", None) is not None:
                    emitted += 1
                ledger_sequence += 1
                ledger.append(
                    ReplayAuditRecord(
                        sequence=ledger_sequence,
                        trigger_closed_at=closed_at,
                        symbol=symbol,
                        venue=venue_for_symbol(symbol),
                        context_closed_at=context.context_closed_at,
                        state_before=state_before,
                        decision=decision,
                        state_after=result.next_state,
                    )
                )
            else:
                warmup_processed += 1
                warmup_evaluated += 1

        return ReplayResult(
            ledger=ledger,
            processed_events=len(ledger.records),
            evaluated_events=evaluated,
            not_ready_events=not_ready,
            emitted_events=emitted,
            states=states,
            warmup_processed_events=warmup_processed,
            warmup_evaluated_events=warmup_evaluated,
            warmup_not_ready_events=warmup_not_ready,
        )


def replay_metadata(
    *,
    result: ReplayResult,
    coverage: CoverageReport | None = None,
    source: LocalReplayData | None = None,
    strategy_version: str = STRATEGY_VERSION,
    config_version: str = CONFIG_VERSION,
    indicator_version: str = INDICATOR_VERSION,
    indicator_seed_convention: str = INDICATOR_SEED_CONVENTION,
    window_mode: str = "custom",
    requested_start: pd.Timestamp | str | None = None,
    requested_end: pd.Timestamp | str | None = None,
) -> dict[str, Any]:
    """Build the portable run metadata stored next to an audit ledger."""

    event_counts: dict[str, int] = {}
    for record in result.ledger.records:
        decision = getattr(record.decision, "event", None)
        event_type = getattr(decision, "event_type", None)
        if event_type is not None:
            key = str(getattr(event_type, "value", event_type))
            event_counts[key] = event_counts.get(key, 0) + 1
    first = result.ledger.records[0].trigger_closed_at.isoformat() if result.ledger.records else None
    last = result.ledger.records[-1].trigger_closed_at.isoformat() if result.ledger.records else None
    return {
        "schema_version": 1,
        "engine": "core_v2_1_point_in_time",
        "strategy_version": strategy_version,
        "config_version": config_version,
        "indicator_version": indicator_version,
        "indicator_seed_convention": indicator_seed_convention,
        "feature_anchor_version": FEATURE_ANCHOR_VERSION,
        "feature_anchor_m15_open": FEATURE_ANCHOR_M15_OPEN.isoformat(),
        "feature_first_close_by_timeframe": {
            timeframe: first_fully_covered_close(timeframe).isoformat()
            for timeframe in ("15m", "1h", "4h")
        },
        "timestamp_contract": "timezone-aware UTC candle close",
        "storage_timestamp_conversion": "timezone-naive UTC+7 open -> subtract 7h -> aware UTC open -> add timeframe",
        "as_of_join": "exact expected fully-closed UTC H1/H4 bucket at or before trigger",
        "initialization_semantics": (
            "independent CoreState.initial() per strategy symbol at the locked feature anchor; "
            "all pre-start candles are processed chronologically with ledger/events suppressed; "
            "not-ready warmup leaves state unchanged"
        ),
        "window_mode": window_mode,
        "requested_start": _metadata_timestamp(requested_start),
        "requested_end": _metadata_timestamp(requested_end),
        "run_start": first,
        "run_end": last,
        "processed_events": result.processed_events,
        "evaluated_events": result.evaluated_events,
        "skipped_events": result.not_ready_events,
        "not_ready_events": result.not_ready_events,
        "emitted_events": result.emitted_events,
        "event_counts": dict(sorted(event_counts.items())),
        "warmup_processed_events": result.warmup_processed_events,
        "warmup_evaluated_events": result.warmup_evaluated_events,
        "warmup_not_ready_events": result.warmup_not_ready_events,
        "inputs": [entry.to_dict() for entry in source.input_manifest] if source is not None else [],
        "coverage": coverage.to_dict() if coverage is not None else None,
    }


def _chronological_events(
    frames: Mapping[str, pd.DataFrame],
    *,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> Iterator[tuple[pd.Timestamp, str]]:
    """Heap-merge trigger indices with deterministic symbol-order ties."""

    canonical = {symbol: position for position, symbol in enumerate(CORE_V2_1_UNIVERSE)}
    ordered_symbols = sorted(frames, key=lambda symbol: (canonical.get(symbol, len(canonical)), symbol))
    symbol_order = {symbol: position for position, symbol in enumerate(ordered_symbols)}
    positions: dict[str, int] = {}
    queue: list[tuple[pd.Timestamp, int, str]] = []
    for symbol in ordered_symbols:
        frame = frames[symbol]
        position = int(frame.index.searchsorted(start, side="left")) if start is not None else 0
        positions[symbol] = position
        if position < len(frame) and (end is None or frame.index[position] <= end):
            heapq.heappush(queue, (frame.index[position], symbol_order[symbol], symbol))

    while queue:
        closed_at, _, symbol = heapq.heappop(queue)
        yield closed_at, symbol
        position = positions[symbol] + 1
        positions[symbol] = position
        frame = frames[symbol]
        if position < len(frame) and (end is None or frame.index[position] <= end):
            heapq.heappush(queue, (frame.index[position], symbol_order[symbol], symbol))


def _readiness_reasons(context: PointInTimeContext | None) -> list[str]:
    if context is None:
        return ["missing_expected_closed_context_or_m15_history"]
    required = {
        "m15.open": context.current_m15.values.get("open"),
        "m15.high": context.current_m15.values.get("high"),
        "m15.low": context.current_m15.values.get("low"),
        "m15.close": context.current_m15.values.get("close"),
        "m15.ema21": context.current_m15.values.get("ema21"),
        "m15.ema200": context.current_m15.values.get("ema200"),
        "m15.atr14": context.current_m15.values.get("atr14"),
        "m15.rsi21": context.current_m15.values.get("rsi21"),
        "m15.rsi_ema9": context.current_m15.values.get("rsi_ema9"),
        "m15.rsi_wma45": context.current_m15.values.get("rsi_wma45"),
        "previous_m15.rsi_ema9": context.previous_m15.values.get("rsi_ema9"),
        "previous_m15.rsi_wma45": context.previous_m15.values.get("rsi_wma45"),
        "m15_three_bars_ago.ema21": context.m15_three_bars_ago.values.get("ema21"),
        "alt_h1.rsi21": context.alt_h1.values.get("rsi21"),
        "alt_h1.rsi_ema9": context.alt_h1.values.get("rsi_ema9"),
        "alt_h1.rsi_wma45": context.alt_h1.values.get("rsi_wma45"),
        "btc_h1.close": context.btc_h1.values.get("close"),
        "btc_h1.ema21": context.btc_h1.values.get("ema21"),
        "btc_h1.rsi21": context.btc_h1.values.get("rsi21"),
        "btc_h1.rsi_ema9": context.btc_h1.values.get("rsi_ema9"),
        "btc_h1.rsi_wma45": context.btc_h1.values.get("rsi_wma45"),
        "btc_h4.rsi21": context.btc_h4.values.get("rsi21"),
        "btc_h4.rsi_ema9": context.btc_h4.values.get("rsi_ema9"),
        "btc_h4.rsi_wma45": context.btc_h4.values.get("rsi_wma45"),
    }
    return [name for name, value in required.items() if value is None or not np.isfinite(float(value))]


def _to_core_evaluation_input(context: PointInTimeContext) -> Any:
    from app.trading.strategy.core_v2_1.config import VENUE_BY_SYMBOL
    from app.trading.strategy.core_v2_1.models import (
        AltH1Snapshot,
        BtcH1Snapshot,
        BtcH4Snapshot,
        EvaluationInput,
        M15Snapshot,
        M15TrendSnapshot,
    )

    current = context.current_m15.values
    previous = context.previous_m15.values
    alt_h1 = context.alt_h1.values
    btc_h1 = context.btc_h1.values
    btc_h4 = context.btc_h4.values
    return EvaluationInput(
        symbol=context.symbol,
        venue=VENUE_BY_SYMBOL[context.symbol],
        current_m15=M15Snapshot(
            closed_at=context.current_m15.closed_at,
            is_closed=True,
            open=_decimal(current["open"]),
            high=_decimal(current["high"]),
            low=_decimal(current["low"]),
            close=_decimal(current["close"]),
            ema21=_decimal(current["ema21"]),
            ema200=_decimal(current["ema200"]),
            atr14=_decimal(current["atr14"]),
            rsi21=_decimal(current["rsi21"]),
            rsi_ema9=_decimal(current["rsi_ema9"]),
            rsi_wma45=_decimal(current["rsi_wma45"]),
        ),
        previous_m15=M15Snapshot(
            closed_at=context.previous_m15.closed_at,
            is_closed=True,
            open=_decimal(previous["open"]),
            high=_decimal(previous["high"]),
            low=_decimal(previous["low"]),
            close=_decimal(previous["close"]),
            ema21=_decimal(previous["ema21"]),
            ema200=_decimal(previous["ema200"]),
            atr14=_decimal(previous["atr14"]),
            rsi21=_decimal(previous["rsi21"]),
            rsi_ema9=_decimal(previous["rsi_ema9"]),
            rsi_wma45=_decimal(previous["rsi_wma45"]),
        ),
        m15_three_bars_ago=M15TrendSnapshot(
            closed_at=context.m15_three_bars_ago.closed_at,
            is_closed=True,
            ema21=_decimal(context.m15_three_bars_ago.values["ema21"]),
        ),
        alt_h1=AltH1Snapshot(
            closed_at=context.alt_h1.closed_at,
            is_closed=True,
            rsi21=_decimal(alt_h1["rsi21"]),
            rsi_ema9=_decimal(alt_h1["rsi_ema9"]),
            rsi_wma45=_decimal(alt_h1["rsi_wma45"]),
        ),
        btc_h1=BtcH1Snapshot(
            closed_at=context.btc_h1.closed_at,
            is_closed=True,
            close=_decimal(btc_h1["close"]),
            ema21=_decimal(btc_h1["ema21"]),
            rsi21=_decimal(btc_h1["rsi21"]),
            rsi_ema9=_decimal(btc_h1["rsi_ema9"]),
            rsi_wma45=_decimal(btc_h1["rsi_wma45"]),
        ),
        btc_h4=BtcH4Snapshot(
            closed_at=context.btc_h4.closed_at,
            is_closed=True,
            rsi21=_decimal(btc_h4["rsi21"]),
            rsi_ema9=_decimal(btc_h4["rsi_ema9"]),
            rsi_wma45=_decimal(btc_h4["rsi_wma45"]),
        ),
    )


def _validate_replay_frame(frame: pd.DataFrame, *, expected_cadence: pd.Timedelta) -> None:
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise CandleDataError("Replay frames require timezone-aware close-time indices")
    if str(frame.index.tz) not in {"UTC", "UTC+00:00"}:
        raise CandleDataError("Replay frames must use UTC close times")
    if not frame.index.is_monotonic_increasing or not frame.index.is_unique:
        raise CandleDataError("Replay frame indices must be chronological and unique")
    if len(frame) > 1 and bool(((frame.index[1:] - frame.index[:-1]) != expected_cadence).any()):
        raise CandleDataError(f"Replay frame must have exact {expected_cadence} closed-candle cadence")


def _anchor_m15_frame(frame: pd.DataFrame, *, symbol: str) -> pd.DataFrame:
    """Trim a canonical source before any recursive indicator is computed."""

    if "open_at" not in frame.columns:
        raise CandleDataError(f"{symbol} canonical M15 frame has no open_at column")
    anchor_open = pd.Timestamp(FEATURE_ANCHOR_M15_OPEN)
    anchored = frame.loc[frame["open_at"] >= anchor_open].copy()
    if anchored.empty:
        raise CandleDataError(
            f"{symbol} has no M15 data at the locked feature anchor "
            f"{anchor_open.isoformat()}"
        )
    actual_open = pd.Timestamp(anchored.iloc[0]["open_at"])
    expected_close = pd.Timestamp(first_fully_covered_close("15m"))
    if actual_open != anchor_open or anchored.index[0] != expected_close:
        raise CandleDataError(
            f"{symbol} feature anchor is incomplete: expected open "
            f"{anchor_open.isoformat()} / close {expected_close.isoformat()}, got "
            f"{actual_open.isoformat()} / {anchored.index[0].isoformat()}"
        )
    _validate_replay_frame(anchored, expected_cadence=pd.Timedelta(minutes=15))
    return anchored


def _optional_utc(value: pd.Timestamp | str | None) -> pd.Timestamp | None:
    if value is None:
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("Replay bounds must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _input_metadata(role: str, symbol: str, path: Path, frame: pd.DataFrame) -> ReplayInputMetadata:
    identity = data_identity_for_symbol(symbol)
    return ReplayInputMetadata(
        role=role,
        strategy_symbol=symbol,
        venue=identity.venue,
        venue_instrument=identity.venue_instrument,
        path=str(path.resolve()),
        sha256=_sha256(path),
        retained_rows=len(frame),
        first_open_at=frame["open_at"].iloc[0].isoformat(),
        last_closed_at=frame.index[-1].isoformat(),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _metadata_timestamp(value: pd.Timestamp | str | None) -> str | None:
    if value is None:
        return None
    return _optional_utc(value).isoformat()  # type: ignore[union-attr]
