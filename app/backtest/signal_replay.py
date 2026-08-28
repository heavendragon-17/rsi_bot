"""Offline historical replay for the BTC RSI cross alert.

This module deliberately sits beside the ordinary order-oriented backtest
engine. ``btc_rsi_cross_alert`` is a multi-timeframe, Telegram-only signal
component, so replaying it requires M5, M15, and H4 data to be available at
each trigger close but does not require an exchange, portfolio, database, or
Telegram connection.

The replay uses the same pure preparation, timeframe-specific decision
functions, event identity, and Telegram card formatter as the live alert
worker. Its Markdown output is intended for manual chart review; it never
assigns a win/loss outcome or calculates a performance metric.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Final

import structlog

from app.backtest.signal_replay_data import (
    all_h4_close_times as _all_h4_close_times,
)
from app.backtest.signal_replay_data import (
    events_for_frame as _events_for_frame,
)
from app.backtest.signal_replay_data import (
    load_ohlcv_csv as _load_ohlcv_csv,
)
from app.backtest.signal_replay_models import (
    ReplayCounts,
    ReplayResult,
    ReplaySignal,
    ReplayTriggerEvent,
)
from app.backtest.signal_replay_models import (
    SignalReplayInputError as SignalReplayInputError,
)
from app.backtest.signal_replay_preparation import ReplayPreparationCache
from app.signal.btc_rsi_cross_alert.formatter import format_btc_rsi_cross_alert
from app.trading.strategy.btc_rsi_cross_alert.m5_checker import M5_TIMEFRAME
from app.trading.strategy.btc_rsi_cross_alert.m15_checker import M15_TIMEFRAME
from app.trading.strategy.btc_rsi_cross_alert.models import (
    M5_ALERT_COOLDOWN,
    BtcRsiCrossDecision,
    BtcRsiCrossInput,
)

logger = structlog.get_logger()

UTC_PLUS_7: Final[timezone] = timezone(timedelta(hours=7), name="UTC+7")
SYMBOL: Final[str] = "BTC/USDT"
DEFAULT_DATA_DIR: Final[Path] = Path("app/backtest/data")
DEFAULT_REPORT_DIR: Final[Path] = Path("app/backtest/report")
HISTORICAL_READY_AT: Final[datetime] = datetime(1970, 1, 1, tzinfo=UTC)
TIMEFRAME_ORDER: Final[dict[str, int]] = {M5_TIMEFRAME: 0, M15_TIMEFRAME: 1}


def _as_utc(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime or None")
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=UTC_PLUS_7)
    return value.astimezone(UTC)


def _as_utc7(value: datetime) -> datetime:
    return value.astimezone(UTC_PLUS_7)


def _format_utc7(value: datetime) -> str:
    return _as_utc7(value).strftime("%Y-%m-%d %H:%M:%S UTC+7")


def _format_window_boundary(value: datetime | None, *, is_start: bool) -> str:
    if value is None:
        return "earliest available" if is_start else "latest available"
    return _format_utc7(value)


def _prepare_and_evaluate(
    event: ReplayTriggerEvent,
    replay_cache: ReplayPreparationCache,
) -> tuple[BtcRsiCrossInput | None, BtcRsiCrossDecision | None, str]:
    return replay_cache.prepare_and_evaluate(event, symbol=SYMBOL)


def _scan_event(
    event: ReplayTriggerEvent,
    replay_cache: ReplayPreparationCache,
) -> tuple[bool | None, str]:
    return replay_cache.scan(event)


def _render_signal(signal: ReplaySignal, *, sequence: int | None = None) -> str:
    label = "M5" if signal.timeframe == M5_TIMEFRAME else "M15"
    return "\n".join(
        (
            "=" * 60,
            f"Signal {(sequence or signal.sequence):04d} — CONFIRMED — {label}",
            "",
            "Manual review: UNREVIEWED",
            "Chart result: [ ] WIN   [ ] LOSS   [ ] SKIP",
            "",
            signal.telegram_card,
            "",
            "Reviewer notes:",
            "_" * 60,
            "",
        )
    )


def render_replay_markdown(
    result: ReplayResult,
    *,
    generated_at: datetime | None = None,
    timeframe: str | None = None,
) -> str:
    """Render a combined or timeframe-specific chart-review Markdown document."""

    if timeframe not in (None, M5_TIMEFRAME, M15_TIMEFRAME):
        raise ValueError(f"unsupported replay report timeframe: {timeframe}")

    generated = _as_utc(generated_at, "generated_at") or result.generated_at_utc7.astimezone(UTC)
    signals = tuple(
        signal
        for signal in result.signals
        if timeframe is None or signal.timeframe == timeframe
    )
    counts = (
        result.counts
        if timeframe is None
        else _counts_for_timeframe(result.counts, timeframe)
    )
    lines = [
        "# BTC RSI Cross Alert — Historical Replay",
        "",
        "Strategy: btc_rsi_cross_alert",
        f"Symbol: {SYMBOL}",
        *(
            (f"Timeframe: {timeframe}",)
            if timeframe is not None
            else ()
        ),
        "Data window: "
        f"{_format_window_boundary(result.start_utc7, is_start=True)} → "
        f"{_format_window_boundary(result.end_utc7, is_start=False)}",
        f"Generated: {_format_utc7(generated)}",
        "",
        f"Confirmed signals: {len(signals)}",
        *(
            [
                f"M5 signals: {sum(signal.timeframe == M5_TIMEFRAME for signal in signals)}",
                f"M15 signals: {sum(signal.timeframe == M15_TIMEFRAME for signal in signals)}",
            ]
            if timeframe is None
            else [f"{timeframe} signals: {len(signals)}"]
        ),
        "",
        f"Trigger candles evaluated: {counts.candidates}",
        f"Warmup candles skipped: {counts.warmup_skipped}",
        f"M5 warmup skipped: {counts.m5_warmup_skipped}",
        f"M15 warmup skipped: {counts.m15_warmup_skipped}",
        f"Not ready: {counts.not_ready}",
        f"Rejected by signal rules: {counts.rejected}",
        f"M5 cooldown suppressed: {counts.m5_cooldown_suppressed}",
        f"Duplicate events suppressed: {counts.duplicate_suppressed}",
        "",
        "Automated win rate: NOT CALCULATED",
        "Review each signal against the historical chart.",
        "",
    ]
    for sequence, signal in enumerate(signals, start=1):
        lines.append(_render_signal(signal, sequence=sequence))
    return "\n".join(lines).rstrip() + "\n"


def _counts_for_timeframe(counts: ReplayCounts, timeframe: str) -> ReplayCounts:
    """Keep only counters relevant to one split report."""

    is_m5 = timeframe == M5_TIMEFRAME
    return ReplayCounts(
        m5_candidates=counts.m5_candidates if is_m5 else 0,
        m15_candidates=counts.m15_candidates if not is_m5 else 0,
        m5_not_ready=counts.m5_not_ready if is_m5 else 0,
        m15_not_ready=counts.m15_not_ready if not is_m5 else 0,
        m5_rejected=counts.m5_rejected if is_m5 else 0,
        m15_rejected=counts.m15_rejected if not is_m5 else 0,
        m5_cooldown_suppressed=counts.m5_cooldown_suppressed if is_m5 else 0,
        duplicate_suppressed=counts.duplicate_suppressed if is_m5 else 0,
        m5_warmup_skipped=counts.m5_warmup_skipped if is_m5 else 0,
        m15_warmup_skipped=counts.m15_warmup_skipped if not is_m5 else 0,
    )


def _default_paths() -> tuple[Path, Path, Path]:
    return (
        DEFAULT_DATA_DIR / "BTCUSDT_5m.csv",
        DEFAULT_DATA_DIR / "BTCUSDT_15m.csv",
        DEFAULT_DATA_DIR / "BTCUSDT_4h.csv",
    )


def _default_output_path(
    start_utc: datetime | None,
    end_utc: datetime | None,
) -> Path:
    start_label = _as_utc7(start_utc).strftime("%Y-%m-%d") if start_utc else "earliest"
    end_label = _as_utc7(end_utc).strftime("%Y-%m-%d") if end_utc else "latest"
    return DEFAULT_REPORT_DIR / f"signal_replay_{start_label}_{end_label}.md"


def _default_split_output_paths(
    start_utc: datetime | None,
    end_utc: datetime | None,
) -> tuple[Path, Path]:
    """Return the default M5 and M15 report paths."""

    combined_path = _default_output_path(start_utc, end_utc)
    return (
        combined_path.with_name(f"{combined_path.stem}_m5{combined_path.suffix}"),
        combined_path.with_name(f"{combined_path.stem}_m15{combined_path.suffix}"),
    )


def run_btc_alert_replay(
    m5_path: str | Path,
    m15_path: str | Path,
    h4_path: str | Path,
    start_utc7: datetime | None = None,
    end_utc7: datetime | None = None,
    output_path: str | Path | None = None,
    *,
    output_m5_path: str | Path | None = None,
    output_m15_path: str | Path | None = None,
    generated_at_utc7: datetime | None = None,
) -> ReplayResult:
    """Replay historical BTC M5/M15 alerts and write a Markdown log.

    ``start_utc7`` and ``end_utc7`` are inclusive trigger-candle close
    boundaries. Naive datetime values are interpreted as UTC+7. The full CSV
    frames remain available to the pure evaluator so indicator warmup is
    included before the requested window, while only in-window confirmations
    are written to the output.
    """

    start_utc = _as_utc(start_utc7, "start_utc7")
    end_utc = _as_utc(end_utc7, "end_utc7")
    if start_utc is not None and end_utc is not None and start_utc > end_utc:
        raise ValueError("start_utc7 must be before or equal to end_utc7")
    if output_path is not None and (
        output_m5_path is not None or output_m15_path is not None
    ):
        raise ValueError("choose output_path or output_m5_path/output_m15_path, not both")
    if (output_m5_path is None) != (output_m15_path is None):
        raise ValueError("output_m5_path and output_m15_path must be provided together")

    m5_frame = _load_ohlcv_csv(m5_path, M5_TIMEFRAME)
    m15_frame = _load_ohlcv_csv(m15_path, M15_TIMEFRAME)
    h4_frame = _load_ohlcv_csv(h4_path, "4h")
    observed_h4_closes = _all_h4_close_times(h4_frame)
    replay_cache = ReplayPreparationCache(
        m5_frame,
        m15_frame,
        h4_frame,
        history_ready_at=HISTORICAL_READY_AT,
        observed_h4_closes=observed_h4_closes,
    )
    warmup_ready_at = replay_cache.warmup_ready_at_by_timeframe

    events = _events_for_frame(m5_frame, M5_TIMEFRAME, start_utc, end_utc)
    events.extend(_events_for_frame(m15_frame, M15_TIMEFRAME, start_utc, end_utc))
    events.sort(key=lambda event: (event.close_time, TIMEFRAME_ORDER[event.timeframe]))

    m5_candidates = sum(event.timeframe == M5_TIMEFRAME for event in events)
    m15_candidates = len(events) - m5_candidates
    m5_not_ready = 0
    m15_not_ready = 0
    m5_rejected = 0
    m15_rejected = 0
    m5_cooldown_suppressed = 0
    duplicate_suppressed = 0
    m5_warmup_skipped = 0
    m15_warmup_skipped = 0
    emitted_event_ids: set[str] = set()
    last_m5_alert_close: datetime | None = None
    confirmed: list[ReplaySignal] = []

    for event in events:
        event_warmup_ready_at = warmup_ready_at[event.timeframe]
        if event_warmup_ready_at is not None and event.close_time < event_warmup_ready_at:
            if event.timeframe == M5_TIMEFRAME:
                m5_warmup_skipped += 1
            else:
                m15_warmup_skipped += 1
            continue

        is_candidate, preparation_reason = _scan_event(event, replay_cache)
        if is_candidate is None:
            if event.timeframe == M5_TIMEFRAME:
                m5_not_ready += 1
            else:
                m15_not_ready += 1
            logger.debug(
                "btc_signal_replay_not_ready",
                timeframe=event.timeframe,
                trigger_close=_format_utc7(event.close_time),
                reason=preparation_reason,
            )
            continue

        if not is_candidate:
            if event.timeframe == M5_TIMEFRAME:
                m5_rejected += 1
            else:
                m15_rejected += 1
            continue

        data, decision, preparation_reason = _prepare_and_evaluate(
            event, replay_cache
        )
        if data is None or decision is None:
            if event.timeframe == M5_TIMEFRAME:
                m5_not_ready += 1
            else:
                m15_not_ready += 1
            logger.debug(
                "btc_signal_replay_not_ready",
                timeframe=event.timeframe,
                trigger_close=_format_utc7(event.close_time),
                reason=preparation_reason,
            )
            continue
        if not decision.should_alert:
            if event.timeframe == M5_TIMEFRAME:
                m5_rejected += 1
            else:
                m15_rejected += 1
            continue

        if decision.event_id in emitted_event_ids:
            duplicate_suppressed += 1
            continue

        if (
            event.timeframe == M5_TIMEFRAME
            and last_m5_alert_close is not None
            and event.close_time < last_m5_alert_close + M5_ALERT_COOLDOWN
        ):
            m5_cooldown_suppressed += 1
            continue

        emitted_event_ids.add(decision.event_id)
        if event.timeframe == M5_TIMEFRAME:
            last_m5_alert_close = event.close_time
        confirmed.append(
            ReplaySignal(
                sequence=len(confirmed) + 1,
                timeframe=event.timeframe,
                data=data,
                decision=decision,
                telegram_card=format_btc_rsi_cross_alert(data, decision.event_id),
            )
        )

    generated_at = _as_utc(generated_at_utc7, "generated_at_utc7") or datetime.now(UTC)
    split_paths = (
        (Path(output_m5_path), Path(output_m15_path))
        if output_m5_path is not None and output_m15_path is not None
        else _default_split_output_paths(start_utc, end_utc)
        if output_path is None
        else (None, None)
    )
    result = ReplayResult(
        signals=tuple(confirmed),
        counts=ReplayCounts(
            m5_candidates=m5_candidates,
            m15_candidates=m15_candidates,
            m5_not_ready=m5_not_ready,
            m15_not_ready=m15_not_ready,
            m5_rejected=m5_rejected,
            m15_rejected=m15_rejected,
            m5_cooldown_suppressed=m5_cooldown_suppressed,
            duplicate_suppressed=duplicate_suppressed,
            m5_warmup_skipped=m5_warmup_skipped,
            m15_warmup_skipped=m15_warmup_skipped,
        ),
        start_utc7=start_utc.astimezone(UTC_PLUS_7) if start_utc else None,
        end_utc7=end_utc.astimezone(UTC_PLUS_7) if end_utc else None,
        generated_at_utc7=generated_at.astimezone(UTC_PLUS_7),
        output_path=Path(output_path) if output_path is not None else None,
        output_m5_path=split_paths[0],
        output_m15_path=split_paths[1],
    )

    if result.output_path is not None:
        result.output_path.parent.mkdir(parents=True, exist_ok=True)
        result.output_path.write_text(render_replay_markdown(result), encoding="utf-8")
    else:
        for path, timeframe in (
            (result.output_m5_path, M5_TIMEFRAME),
            (result.output_m15_path, M15_TIMEFRAME),
        ):
            if path is None:
                raise RuntimeError(f"missing output path for {timeframe} report")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                render_replay_markdown(result, timeframe=timeframe),
                encoding="utf-8",
            )
    logger.info(
        "btc_signal_replay_completed",
        output_paths=[str(path) for path in result.output_paths],
        confirmed_signals=len(result.signals),
        m5_signals=sum(signal.timeframe == M5_TIMEFRAME for signal in result.signals),
        m15_signals=sum(signal.timeframe == M15_TIMEFRAME for signal in result.signals),
    )
    return result


def main(argv: list[str] | None = None) -> int:
    """Load the CLI lazily so the replay API stays lightweight to import."""

    from app.backtest.signal_replay_cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
