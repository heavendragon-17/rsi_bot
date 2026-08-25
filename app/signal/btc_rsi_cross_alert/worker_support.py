"""Focused helpers for the BTC RSI cross alert worker."""

from __future__ import annotations

import threading
from collections import deque
from datetime import UTC, datetime
from typing import Protocol

import structlog

from app.core.events import Candle
from app.data.multiplexer import TimeframeMultiplexer
from app.signal.btc_rsi_cross_alert.config import BtcRsiCrossAlertConfig
from app.trading.strategy.btc_rsi_cross_alert.evaluator import (
    TRIGGER_DURATION_BY_TIMEFRAME,
    candle_close_time,
    prepare_btc_rsi_cross_input,
)
from app.trading.strategy.btc_rsi_cross_alert.models import BtcRsiCrossPreparation

logger = structlog.get_logger()


def iso_timestamp(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


def newest_closed_close(
    multiplexer: TimeframeMultiplexer,
    symbol: str,
    timeframe: str,
) -> datetime | None:
    """Return the newest fully closed candle close held by the multiplexer."""

    frame = multiplexer.get_dataframe(symbol, timeframe)
    if frame is None or frame.empty or "closed" not in frame.columns:
        return None
    duration = TRIGGER_DURATION_BY_TIMEFRAME[timeframe]
    closed_column = frame["closed"]
    for position in range(len(frame) - 1, -1, -1):
        if bool(closed_column.iloc[position]):
            return candle_close_time(frame.index[position], duration)
    return None


def prepare_from_multiplexer(
    multiplexer: TimeframeMultiplexer,
    config: BtcRsiCrossAlertConfig,
    timeframe: str,
    trigger_open_time: datetime,
    ready_at: datetime,
    observed_h4_closes: frozenset[datetime],
) -> BtcRsiCrossPreparation:
    """Build one point-in-time evaluator input from synchronized frames."""

    trigger_df = multiplexer.get_dataframe(config.symbol, timeframe)
    h4_df = multiplexer.get_dataframe(config.symbol, config.trend_timeframe)
    if trigger_df is None or trigger_df.empty or h4_df is None or h4_df.empty:
        raise RuntimeError(f"multiplexer frames unavailable for {timeframe} evaluation")
    return prepare_btc_rsi_cross_input(
        trigger_df,
        h4_df,
        symbol=config.symbol,
        trigger_timeframe=timeframe,
        trigger_open_time=trigger_open_time,
        history_ready_at=ready_at,
        observed_live_h4_closes=observed_h4_closes,
    )


class WorkerProcessingContext(Protocol):
    """State and hooks required by the failure-budget wrapper."""

    config: BtcRsiCrossAlertConfig
    max_failures: int
    _failure_streak: int
    _pending: deque[tuple[str, str, Candle]]
    _queue_cond: threading.Condition

    def _process(self, symbol: str, timeframe: str, candle: Candle) -> None: ...

    def _advance_cursor(self, timeframe: str, trigger_close: datetime) -> None: ...

    def _notify_debug(self, message: str) -> None: ...


def process_safely(
    context: WorkerProcessingContext,
    symbol: str,
    timeframe: str,
    candle: Candle,
) -> bool:
    """Process one queued event and report whether its worker must terminate."""

    try:
        context._process(symbol, timeframe, candle)
        context._failure_streak = 0
        return False
    except Exception as exc:  # noqa: BLE001 - budgeted per-event isolation
        context._failure_streak += 1
        attempt = context._failure_streak
        trigger_close = candle_close_time(
            candle.timestamp,
            TRIGGER_DURATION_BY_TIMEFRAME[timeframe],
        )
        logger.exception(
            "btc_rsi_cross_worker_error",
            timeframe=timeframe,
            trigger_close=iso_timestamp(trigger_close),
            attempt=attempt,
        )
        if attempt >= context.max_failures:
            context._advance_cursor(timeframe, trigger_close)
            context._notify_debug(
                f"[{context.config.name}] worker dead after {attempt} consecutive "
                f"failures ({timeframe} {iso_timestamp(trigger_close)}): {exc!r}"
            )
            return True
        # Requeue the same event ahead of newer events while attempts remain.
        with context._queue_cond:
            context._pending.appendleft((symbol, timeframe, candle))
            context._queue_cond.notify()
        return False
