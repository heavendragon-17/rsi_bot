"""Queue-backed alert worker for the BTC RSI cross alert.

One worker per active ``btc_rsi_cross_alert`` config. The SignalRunner
registers :meth:`handle_closed_candle` as a multiplexer close callback;
M5/M15 closed candles become queued evaluation events while H4 closed
candles are confirmed synchronously under a :class:`threading.Condition`
(they never pass through the worker queue and never emit alerts).

Guarantees implemented here (spec §11):

* bootstrap gate — every callback is discarded until
  :meth:`on_history_complete`; historical closes at/before the per-timeframe
  REST watermark or the history-ready instant stay silent forever;
* point-in-time evaluation through the pure preparation/evaluator pair;
* exactly one H4 boundary settle/retry per trigger event, bounded by
  ``context_settle_seconds`` and interrupted promptly by shutdown;
* deterministic deduplication by per-timeframe cursor and emitted event
  identity — never a wall-clock cooldown;
* consecutive-failure budget with requeue-ahead semantics and a terminal
  debug-topic notification matching the existing StrategyWorker policy;
* bounded, idempotent shutdown via :meth:`request_stop`.

This component owns no virtual positions and never touches exchange order
APIs or the mechanical exit monitor.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import UTC, datetime

import structlog

from app.core.constants import (
    SIGNAL_MAX_CONSECUTIVE_FAILURES,
    SIGNAL_WORKER_QUEUE_SIZE,
)
from app.core.events import Candle
from app.data.multiplexer import TimeframeMultiplexer
from app.signal.btc_rsi_cross_alert.config import BtcRsiCrossAlertConfig
from app.signal.btc_rsi_cross_alert.formatter import format_btc_rsi_cross_alert
from app.trading.strategy.btc_rsi_cross_alert.evaluator import (
    H4_DURATION,
    RETRYABLE_PREPARATION_REASONS,
    TRIGGER_DURATION_BY_TIMEFRAME,
    candle_close_time,
    evaluate_btc_rsi_cross,
    expected_h4_close_for,
    prepare_btc_rsi_cross_input,
)
from app.trading.strategy.btc_rsi_cross_alert.models import (
    DECISION_ALERT_FRESH_BULLISH_CROSS_H4_BULLISH,
    DECISION_H4_NOT_BULLISH,
    PREPARATION_READY,
    build_event_id,
)

logger = structlog.get_logger()

UTC = UTC

_MAX_OBSERVED_H4_CLOSES = 512


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


class BtcRsiCrossAlertWorker:
    """Evaluates closed BTC trigger candles against the live H4 context."""

    def __init__(
        self,
        config: BtcRsiCrossAlertConfig,
        multiplexer: TimeframeMultiplexer,
        notifier,
        *,
        debug_topic_id: int,
        max_failures: int = SIGNAL_MAX_CONSECUTIVE_FAILURES,
        queue_size: int = SIGNAL_WORKER_QUEUE_SIZE,
    ) -> None:
        self.config = config
        self.multiplexer = multiplexer
        self.notifier = notifier
        self.debug_topic_id = debug_topic_id
        self.max_failures = max_failures

        self._queue_size = queue_size
        self._pending: deque[tuple[str, str, Candle]] = deque()
        self._queue_cond = threading.Condition()
        self._h4_cond = threading.Condition()
        self._observed_h4_closes: set[datetime] = set()

        self._running = threading.Event()
        self._running.set()
        self._history_ready = threading.Event()
        self._history_ready_at: datetime | None = None
        self._bootstrap_watermarks: dict[str, datetime | None] = {
            tf: None for tf in config.trigger_timeframes
        }
        self._last_evaluated: dict[str, datetime | None] = {
            tf: None for tf in config.trigger_timeframes
        }
        self._emitted_event_ids: set[str] = set()
        self._failure_streak = 0

    # ------------------------------------------------------------------
    # Introspection (test/ops surface)
    # ------------------------------------------------------------------
    @property
    def topic_id(self) -> int:
        return self.config.telegram_topic_id

    @property
    def last_evaluated(self) -> dict[str, datetime | None]:
        return dict(self._last_evaluated)

    @property
    def emitted_event_ids(self) -> frozenset[str]:
        return frozenset(self._emitted_event_ids)

    @property
    def is_history_ready(self) -> bool:
        return self._history_ready.is_set()

    @property
    def history_ready_at(self) -> datetime | None:
        return self._history_ready_at

    # ------------------------------------------------------------------
    # Multiplexer callback entry points
    # ------------------------------------------------------------------
    def handle_closed_candle(self, symbol: str, timeframe: str, candle: Candle) -> None:
        """Single multiplexer close-callback entry point.

        H4 events are confirmed synchronously (never enqueued); trigger
        events are queued for the worker thread. Everything else is dropped.
        """

        if symbol != self.config.symbol:
            return
        if not candle.closed:
            return
        if timeframe == self.config.trend_timeframe:
            self.observe_h4_close(symbol, timeframe, candle)
            return
        if timeframe in self.config.trigger_timeframes:
            self.enqueue(symbol, timeframe, candle)

    def observe_h4_close(self, symbol: str, timeframe: str, candle: Candle) -> None:
        """Record a live closed H4 candle and wake any waiting trigger eval."""

        if not candle.closed:
            return
        close = candle_close_time(candle.timestamp, H4_DURATION)
        with self._h4_cond:
            self._observed_h4_closes.add(close)
            if len(self._observed_h4_closes) > _MAX_OBSERVED_H4_CLOSES:
                # Keep the newest half; old confirms can never be needed
                # again because pre-ready rows are trusted unconditionally.
                keep = sorted(self._observed_h4_closes)[
                    len(self._observed_h4_closes) // 2 :
                ]
                self._observed_h4_closes = set(keep)
            self._h4_cond.notify_all()

    def enqueue(self, symbol: str, timeframe: str, candle: Candle) -> None:
        """Queue a closed trigger candle. Drops new events on overflow."""

        with self._queue_cond:
            if len(self._pending) >= self._queue_size:
                logger.warning(
                    "btc_rsi_cross_worker_queue_full",
                    timeframe=timeframe,
                    trigger_close=_iso(candle_close_time(candle.timestamp, TRIGGER_DURATION_BY_TIMEFRAME.get(timeframe, H4_DURATION))),
                )
                return
            self._pending.append((symbol, timeframe, candle))
            self._queue_cond.notify()

    # ------------------------------------------------------------------
    # Bootstrap gate
    # ------------------------------------------------------------------
    def on_history_complete(self, now: datetime | None = None) -> None:
        """Declare REST hydration finished and arm the bootstrap watermarks.

        Called exactly once by the runner's ``history_complete_callback``
        after all fetch attempts returned. Never evaluates or alerts here —
        the first eligible evaluation is a later live closed trigger candle.
        """

        ready_at = now if now is not None else datetime.now(UTC)
        for tf in self.config.trigger_timeframes:
            self._bootstrap_watermarks[tf] = self._newest_closed_close(tf)
        self._history_ready_at = ready_at.astimezone(UTC)
        self._history_ready.set()
        logger.info(
            "btc_rsi_cross_history_ready",
            targets=len(self.config.targets),
            watermarks={
                tf: _iso(wm) for tf, wm in self._bootstrap_watermarks.items()
            },
        )

    def _newest_closed_close(self, timeframe: str) -> datetime | None:
        frame = self.multiplexer.get_dataframe(self.config.symbol, timeframe)
        if frame is None or frame.empty or "closed" not in frame.columns:
            return None
        duration = TRIGGER_DURATION_BY_TIMEFRAME[timeframe]
        closed_column = frame["closed"]
        for position in range(len(frame) - 1, -1, -1):
            if bool(closed_column.iloc[position]):
                return candle_close_time(frame.index[position], duration)
        return None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def request_stop(self) -> None:
        """Bounded, idempotent shutdown signal. Wakes all waits immediately."""

        self._running.clear()
        with self._queue_cond:
            self._queue_cond.notify_all()
        with self._h4_cond:
            self._h4_cond.notify_all()

    def run(self) -> None:
        logger.info(
            "btc_rsi_cross_worker_started",
            topic=self.config.telegram_topic_id,
            targets=sorted(self.config.targets),
        )
        while self._running.is_set():
            with self._queue_cond:
                while not self._pending and self._running.is_set():
                    self._queue_cond.wait(timeout=0.5)
                if not self._pending:
                    break  # stopped with an empty queue
                symbol, timeframe, candle = self._pending.popleft()
            if self._process_safely(symbol, timeframe, candle):
                break  # failure budget exhausted — thread dies
        logger.info(
            "btc_rsi_cross_worker_stopped",
            last_evaluated={
                tf: _iso(close) for tf, close in self._last_evaluated.items()
            },
        )

    # ------------------------------------------------------------------
    # Event processing
    # ------------------------------------------------------------------
    def _process_safely(
        self, symbol: str, timeframe: str, candle: Candle
    ) -> bool:
        """Process one queued event. Returns True to terminate the thread."""

        try:
            self._process(symbol, timeframe, candle)
            self._failure_streak = 0
            return False
        except Exception as exc:  # noqa: BLE001 — budgeted per-event isolation
            self._failure_streak += 1
            attempt = self._failure_streak
            trigger_close = candle_close_time(
                candle.timestamp, TRIGGER_DURATION_BY_TIMEFRAME[timeframe]
            )
            logger.exception(
                "btc_rsi_cross_worker_error",
                timeframe=timeframe,
                trigger_close=_iso(trigger_close),
                attempt=attempt,
            )
            if attempt >= self.max_failures:
                self._advance_cursor(timeframe, trigger_close)
                self._notify_debug(
                    f"[{self.config.name}] worker dead after {attempt} consecutive "
                    f"failures ({timeframe} {_iso(trigger_close)}): {exc!r}"
                )
                return True
            # Requeue the same event ahead of newer events while attempts remain.
            with self._queue_cond:
                self._pending.appendleft((symbol, timeframe, candle))
                self._queue_cond.notify()
            return False

    def _process(self, symbol: str, timeframe: str, candle: Candle) -> None:
        duration = TRIGGER_DURATION_BY_TIMEFRAME[timeframe]
        trigger_close = candle_close_time(candle.timestamp, duration)

        # --- bootstrap gate -------------------------------------------
        if not self._history_ready.is_set() or self._history_ready_at is None:
            logger.debug(
                "btc_rsi_cross_bootstrap_discarded",
                timeframe=timeframe,
                trigger_close=_iso(trigger_close),
            )
            return
        ready_at = self._history_ready_at
        watermark = self._bootstrap_watermarks.get(timeframe)
        if (watermark is not None and trigger_close <= watermark) or (
            trigger_close <= ready_at
        ):
            logger.info(
                "btc_rsi_cross_historical_ignored",
                timeframe=timeframe,
                trigger_close=_iso(trigger_close),
            )
            return

        # --- deterministic dedupe --------------------------------------
        event_id = build_event_id(
            symbol=self.config.symbol,
            trigger_timeframe=timeframe,
            trigger_close_time=trigger_close,
        )
        last = self._last_evaluated.get(timeframe)
        if last is not None and trigger_close <= last:
            logger.info(
                "btc_rsi_cross_duplicate_ignored",
                timeframe=timeframe,
                trigger_close=_iso(trigger_close),
                event_id=event_id,
            )
            return
        if event_id in self._emitted_event_ids:
            logger.info(
                "btc_rsi_cross_duplicate_ignored",
                timeframe=timeframe,
                trigger_close=_iso(trigger_close),
                event_id=event_id,
            )
            return

        # --- first preparation ------------------------------------------
        preparation = self._prepare(timeframe, candle.timestamp, ready_at)

        # --- single H4 boundary settle/retry -----------------------------
        if preparation.reason in RETRYABLE_PREPARATION_REASONS:
            expected_h4 = expected_h4_close_for(trigger_close)
            # Do not advance last_evaluated while waiting (spec §11).
            logger.warning(
                "btc_rsi_cross_h4_retry",
                timeframe=timeframe,
                trigger_close=_iso(trigger_close),
                expected_h4_close=_iso(expected_h4),
            )
            with self._h4_cond:
                self._h4_cond.wait(timeout=self.config.context_settle_seconds)
            if not self._running.is_set():
                return  # shutting down mid-retry; process is terminating
            preparation = self._prepare(timeframe, candle.timestamp, ready_at)

        # --- terminal not-ready ------------------------------------------
        if preparation.reason != PREPARATION_READY:
            self._advance_cursor(timeframe, trigger_close)
            logger.warning(
                "btc_rsi_cross_not_ready",
                timeframe=timeframe,
                trigger_close=_iso(trigger_close),
                reason=preparation.reason,
            )
            return

        # --- decision -----------------------------------------------------
        decision = evaluate_btc_rsi_cross(preparation.input)
        self._advance_cursor(timeframe, trigger_close)
        level = (
            "info"
            if decision.reason
            in (DECISION_ALERT_FRESH_BULLISH_CROSS_H4_BULLISH, DECISION_H4_NOT_BULLISH)
            else "debug"
        )
        getattr(logger, level)(
            "btc_rsi_cross_decision",
            timeframe=timeframe,
            trigger_close=_iso(trigger_close),
            decision=decision.reason,
            event_id=decision.event_id,
        )

        if not decision.should_alert:
            return
        if decision.event_id in self._emitted_event_ids:
            logger.info(
                "btc_rsi_cross_duplicate_ignored",
                timeframe=timeframe,
                trigger_close=_iso(trigger_close),
                event_id=decision.event_id,
            )
            return

        message = format_btc_rsi_cross_alert(preparation.input, decision.event_id)
        self.notifier.send_message(message, topic_id=self.config.telegram_topic_id)
        self._emitted_event_ids.add(decision.event_id)
        logger.info(
            "btc_rsi_cross_alert_enqueued",
            timeframe=timeframe,
            trigger_close=_iso(trigger_close),
            event_id=decision.event_id,
            topic=self.config.telegram_topic_id,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _prepare(self, timeframe: str, trigger_open_time, ready_at: datetime):
        trigger_df = self.multiplexer.get_dataframe(self.config.symbol, timeframe)
        h4_df = self.multiplexer.get_dataframe(self.config.symbol, self.config.trend_timeframe)
        if (
            trigger_df is None
            or trigger_df.empty
            or h4_df is None
            or h4_df.empty
        ):
            raise RuntimeError(
                f"multiplexer frames unavailable for {timeframe} evaluation"
            )
        with self._h4_cond:
            observed = frozenset(self._observed_h4_closes)
        return prepare_btc_rsi_cross_input(
            trigger_df,
            h4_df,
            symbol=self.config.symbol,
            trigger_timeframe=timeframe,
            trigger_open_time=trigger_open_time,
            history_ready_at=ready_at,
            observed_live_h4_closes=observed,
        )

    def _advance_cursor(self, timeframe: str, trigger_close: datetime) -> None:
        current = self._last_evaluated.get(timeframe)
        if current is None or trigger_close > current:
            self._last_evaluated[timeframe] = trigger_close

    def _notify_debug(self, message: str) -> None:
        self.notifier.send_message(message, topic_id=self.debug_topic_id)
