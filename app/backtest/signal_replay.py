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

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd
import structlog

from app.backtest.signal_replay_models import (
    ReplayCounts,
    ReplayResult,
    ReplaySignal,
    SignalReplayInputError,
)
from app.signal.btc_rsi_cross_alert.formatter import format_btc_rsi_cross_alert
from app.trading.strategy.btc_rsi_cross_alert.evaluator import (
    H4_DURATION,
    TRIGGER_DURATION_BY_TIMEFRAME,
    candle_close_time,
    normalize_candle_open,
)
from app.trading.strategy.btc_rsi_cross_alert.m5_checker import (
    M5_TIMEFRAME,
    evaluate_m5_cross,
    prepare_m5_cross_input,
)
from app.trading.strategy.btc_rsi_cross_alert.m15_checker import (
    M15_TIMEFRAME,
    evaluate_m15_cross,
    prepare_m15_cross_input,
)
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
REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
)
TIMEFRAME_ORDER: Final[dict[str, int]] = {M5_TIMEFRAME: 0, M15_TIMEFRAME: 1}


@dataclass(frozen=True)
class _TriggerEvent:
    timeframe: str
    open_time: datetime
    close_time: datetime


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


def _load_ohlcv_csv(path: str | Path, timeframe: str) -> pd.DataFrame:
    """Load, normalize, and validate one historical OHLCV frame."""

    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Historical {timeframe} CSV not found: {csv_path}")
    if not csv_path.is_file():
        raise SignalReplayInputError(f"Historical {timeframe} path is not a file: {csv_path}")

    try:
        raw = pd.read_csv(csv_path)
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise SignalReplayInputError(
            f"Could not read historical {timeframe} CSV {csv_path}: {exc}"
        ) from exc

    missing = [column for column in REQUIRED_COLUMNS if column not in raw.columns]
    if missing:
        raise SignalReplayInputError(
            f"Historical {timeframe} CSV {csv_path} is missing columns: {', '.join(missing)}"
        )
    if raw.empty:
        raise SignalReplayInputError(f"Historical {timeframe} CSV is empty: {csv_path}")

    normalized_opens: list[datetime] = []
    for position, raw_timestamp in enumerate(raw["timestamp"]):
        try:
            parsed = pd.Timestamp(raw_timestamp)
            if pd.isna(parsed):
                raise ValueError("timestamp is NaT")
            normalized_opens.append(normalize_candle_open(parsed))
        except (TypeError, ValueError, OverflowError) as exc:
            raise SignalReplayInputError(
                f"Invalid timestamp at row {position} in {csv_path}: {raw_timestamp!r}"
            ) from exc

    frame = raw.loc[:, list(REQUIRED_COLUMNS)].copy()
    frame["timestamp"] = normalized_opens
    for column in REQUIRED_COLUMNS[1:]:
        numeric = pd.to_numeric(frame[column], errors="coerce")
        values = numeric.to_numpy(dtype="float64", na_value=np.nan)
        if not np.isfinite(values).all():
            bad_position = int(np.flatnonzero(~np.isfinite(values))[0])
            raise SignalReplayInputError(
                f"Invalid {column} at row {bad_position} in {csv_path}; "
                "OHLCV values must be finite numbers"
            )
        frame[column] = values

    frame = frame.set_index("timestamp").sort_index()
    if not frame.index.is_unique:
        duplicate = frame.index[frame.index.duplicated(keep=False)][0]
        duplicate_time = duplicate.to_pydatetime()
        raise SignalReplayInputError(
            f"Historical {timeframe} CSV contains duplicate candle opens: "
            f"{_format_utc7(duplicate_time)}"
        )

    frame["closed"] = True
    frame["timeframe"] = timeframe
    return frame


def _events_for_frame(
    frame: pd.DataFrame,
    timeframe: str,
    start_utc: datetime | None,
    end_utc: datetime | None,
) -> list[_TriggerEvent]:
    duration = TRIGGER_DURATION_BY_TIMEFRAME[timeframe]
    events: list[_TriggerEvent] = []
    for raw_open in frame.index:
        open_time = normalize_candle_open(raw_open)
        close_time = open_time + duration
        if start_utc is not None and close_time < start_utc:
            continue
        if end_utc is not None and close_time > end_utc:
            continue
        events.append(
            _TriggerEvent(
                timeframe=timeframe,
                open_time=open_time,
                close_time=close_time,
            )
        )
    return events


def _all_h4_close_times(frame: pd.DataFrame) -> frozenset[datetime]:
    return frozenset(
        candle_close_time(raw_open, H4_DURATION) for raw_open in frame.index
    )


def _prepare_and_evaluate(
    event: _TriggerEvent,
    m5_frame: pd.DataFrame,
    m15_frame: pd.DataFrame,
    h4_frame: pd.DataFrame,
    observed_h4_closes: frozenset[datetime],
) -> tuple[BtcRsiCrossInput | None, BtcRsiCrossDecision | None, str]:
    trigger_frame = m5_frame if event.timeframe == M5_TIMEFRAME else m15_frame
    if event.timeframe == M5_TIMEFRAME:
        preparation = prepare_m5_cross_input(
            trigger_frame,
            h4_frame,
            symbol=SYMBOL,
            trigger_open_time=event.open_time,
            history_ready_at=HISTORICAL_READY_AT,
            observed_live_h4_closes=observed_h4_closes,
        )
        if preparation.input is None:
            return None, None, preparation.reason
        return preparation.input, evaluate_m5_cross(preparation.input), preparation.reason

    preparation = prepare_m15_cross_input(
        trigger_frame,
        h4_frame,
        symbol=SYMBOL,
        trigger_open_time=event.open_time,
        history_ready_at=HISTORICAL_READY_AT,
        observed_live_h4_closes=observed_h4_closes,
    )
    if preparation.input is None:
        return None, None, preparation.reason
    return preparation.input, evaluate_m15_cross(preparation.input), preparation.reason


def _render_signal(signal: ReplaySignal) -> str:
    label = "M5" if signal.timeframe == M5_TIMEFRAME else "M15"
    return "\n".join(
        (
            "=" * 60,
            f"Signal {signal.sequence:04d} — CONFIRMED — {label}",
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
) -> str:
    """Render a replay result as a chart-review Markdown document."""

    generated = _as_utc(generated_at, "generated_at") or result.generated_at_utc7.astimezone(UTC)
    counts = result.counts
    lines = [
        "# BTC RSI Cross Alert — Historical Replay",
        "",
        "Strategy: btc_rsi_cross_alert",
        f"Symbol: {SYMBOL}",
        "Data window: "
        f"{_format_window_boundary(result.start_utc7, is_start=True)} → "
        f"{_format_window_boundary(result.end_utc7, is_start=False)}",
        f"Generated: {_format_utc7(generated)}",
        "",
        f"Confirmed signals: {len(result.signals)}",
        f"M5 signals: {sum(signal.timeframe == M5_TIMEFRAME for signal in result.signals)}",
        f"M15 signals: {sum(signal.timeframe == M15_TIMEFRAME for signal in result.signals)}",
        "",
        f"Trigger candles evaluated: {counts.candidates}",
        f"Not ready: {counts.not_ready}",
        f"Rejected by signal rules: {counts.rejected}",
        f"M5 cooldown suppressed: {counts.m5_cooldown_suppressed}",
        f"Duplicate events suppressed: {counts.duplicate_suppressed}",
        "",
        "Automated win rate: NOT CALCULATED",
        "Review each signal against the historical chart.",
        "",
    ]
    for signal in result.signals:
        lines.append(_render_signal(signal))
    return "\n".join(lines).rstrip() + "\n"


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


def run_btc_alert_replay(
    m5_path: str | Path,
    m15_path: str | Path,
    h4_path: str | Path,
    start_utc7: datetime | None = None,
    end_utc7: datetime | None = None,
    output_path: str | Path | None = None,
    *,
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

    m5_frame = _load_ohlcv_csv(m5_path, M5_TIMEFRAME)
    m15_frame = _load_ohlcv_csv(m15_path, M15_TIMEFRAME)
    h4_frame = _load_ohlcv_csv(h4_path, "4h")
    observed_h4_closes = _all_h4_close_times(h4_frame)

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
    emitted_event_ids: set[str] = set()
    last_m5_alert_close: datetime | None = None
    confirmed: list[ReplaySignal] = []

    for event in events:
        data, decision, preparation_reason = _prepare_and_evaluate(
            event,
            m5_frame,
            m15_frame,
            h4_frame,
            observed_h4_closes,
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
        ),
        start_utc7=start_utc.astimezone(UTC_PLUS_7) if start_utc else None,
        end_utc7=end_utc.astimezone(UTC_PLUS_7) if end_utc else None,
        generated_at_utc7=generated_at.astimezone(UTC_PLUS_7),
        output_path=(
            Path(output_path)
            if output_path is not None
            else _default_output_path(start_utc, end_utc)
        ),
    )

    result.output_path.parent.mkdir(parents=True, exist_ok=True)
    result.output_path.write_text(render_replay_markdown(result), encoding="utf-8")
    logger.info(
        "btc_signal_replay_completed",
        output_path=str(result.output_path),
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
