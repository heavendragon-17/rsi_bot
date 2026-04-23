"""Per-strategy worker thread for the signal bot.

One ``StrategyWorker`` runs per active strategy. The ``SignalRunner``
(slice 7) registers :meth:`enqueue` as a close-callback on the
``TimeframeMultiplexer``, spawns the worker thread on :meth:`run`, and
signals shutdown via :meth:`request_stop`.

Loop per spec §8:
  1. Mechanical exit monitor. If any event fires, apply it and skip
     ``analyze()`` for this candle.
  2. ``strategy.analyze()`` with a VP-derived ``PositionSnapshot`` and
     the per-symbol ``ContextSnapshot``.
  3. Action dispatch per spec §8 table (all five action types).

Failure policy (spec §12): ``SIGNAL_MAX_CONSECUTIVE_FAILURES`` errors on
the same symbol → post a debug-topic "strategy dead" message and exit
the thread. Successful iterations reset the counter.
"""

from __future__ import annotations

import queue
import threading
from collections import defaultdict

import structlog

from app.core.actions import (
    SIDE_BUY,
    SIDE_SELL,
    ClosePosition,
    DoNothing,
    MoveSL,
    OpenPosition,
    PartialClose,
)
from app.core.constants import (
    SIGNAL_MAX_CONSECUTIVE_FAILURES,
    SIGNAL_MAX_VP_AGE_CANDLES,
    SIGNAL_WORKER_QUEUE_SIZE,
)
from app.core.events import Candle
from app.core.interfaces import IStrategy
from app.core.snapshots import ContextSnapshot, PositionSnapshot
from app.data.multiplexer import TimeframeMultiplexer
from app.signal import exit_monitor, signal_formatter
from app.signal.strategy_config import StrategyInstanceConfig
from app.signal.virtual_position import VirtualPosition, VirtualPositionStore

logger = structlog.get_logger()

# Sentinel pushed onto the queue by ``request_stop`` to unblock ``queue.get``.
_STOP_SENTINEL: object = object()

Action = OpenPosition | ClosePosition | MoveSL | PartialClose | DoNothing


class StrategyWorker:
    """One worker thread bound to a single strategy instance."""

    def __init__(
        self,
        instance_cfg: StrategyInstanceConfig,
        strategy: IStrategy,
        multiplexer: TimeframeMultiplexer,
        vp_store: VirtualPositionStore,
        notifier,
        *,
        debug_topic_id: int,
        max_failures: int = SIGNAL_MAX_CONSECUTIVE_FAILURES,
        max_age_candles: int = SIGNAL_MAX_VP_AGE_CANDLES,
        queue_size: int = SIGNAL_WORKER_QUEUE_SIZE,
    ) -> None:
        self.instance_cfg = instance_cfg
        self.strategy = strategy
        self.multiplexer = multiplexer
        self.vp_store = vp_store
        self.notifier = notifier
        self.debug_topic_id = debug_topic_id
        self.max_failures = max_failures
        self.max_age_candles = max_age_candles

        self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._running = threading.Event()
        self._running.set()
        self._contexts: dict[str, ContextSnapshot] = {}
        self._failure_counts: dict[str, int] = defaultdict(int)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    @property
    def strategy_topic_id(self) -> int:
        return self.instance_cfg.telegram_topic_id

    def enqueue(self, symbol: str, timeframe: str, candle: Candle) -> None:
        """Multiplexer close-callback. Drops + warns on queue overflow."""
        try:
            self._queue.put_nowait((symbol, timeframe, candle))
        except queue.Full:
            logger.warning(
                "strategy_worker_queue_full",
                strategy=self.instance_cfg.name,
                symbol=symbol,
                timeframe=timeframe,
            )

    def request_stop(self) -> None:
        self._running.clear()
        try:
            self._queue.put_nowait(_STOP_SENTINEL)
        except queue.Full:
            # Queue full — worker will notice running event on next get().
            pass

    def run(self) -> None:
        logger.info(
            "strategy_worker_started",
            strategy=self.instance_cfg.name,
            targets=sorted(self.instance_cfg.targets),
        )
        while self._running.is_set():
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is _STOP_SENTINEL:
                break

            symbol, timeframe, candle = item
            if (symbol, timeframe) not in self.instance_cfg.targets:
                continue
            if self._process(symbol, timeframe, candle):
                return  # thread dies — retry budget exhausted

        logger.info("strategy_worker_stopped", strategy=self.instance_cfg.name)

    # ------------------------------------------------------------------
    # Per-candle processing
    # ------------------------------------------------------------------
    def _process(self, symbol: str, timeframe: str, candle: Candle) -> bool:
        """Process one (symbol, timeframe, candle). Returns True if the
        failure budget is exhausted and the thread should exit."""
        try:
            vp = self.vp_store.get_for_symbol(self.instance_cfg.name, symbol)

            # 1. Mechanical exit monitor
            if vp is not None:
                events = exit_monitor.check(
                    vp, candle, max_age_candles=self.max_age_candles
                )
                if events:
                    self._apply_exit_events(events)
                    self._failure_counts[symbol] = 0
                    return False

            # 2. Strategy.analyze()
            df = self.multiplexer.get_dataframe(symbol, timeframe)
            if df is None or df.empty:
                self._failure_counts[symbol] = 0
                return False

            position = self._vp_to_snapshot(vp, symbol)
            context = self._contexts.get(symbol, ContextSnapshot(state="SCANNING"))
            result = self.strategy.analyze(
                symbol, df, position=position, context=context
            )
            if result.new_context is not None:
                self._contexts[symbol] = result.new_context

            # 3. Action dispatch
            for action in result.actions:
                self._handle_action(action, vp, symbol, timeframe, candle)
            self._failure_counts[symbol] = 0
            return False

        except Exception as e:
            self._failure_counts[symbol] += 1
            attempt = self._failure_counts[symbol]
            logger.exception(
                "strategy_worker_error",
                strategy=self.instance_cfg.name,
                symbol=symbol,
                attempt=attempt,
            )
            if attempt >= self.max_failures:
                self._notify_debug(
                    signal_formatter.format_strategy_dead(
                        self.instance_cfg.name, symbol, repr(e)
                    )
                )
                return True  # thread dies
            return False

    # ------------------------------------------------------------------
    # Exit-event application
    # ------------------------------------------------------------------
    def _apply_exit_events(
        self, events: list[exit_monitor.ExitEvent]
    ) -> None:
        for event in events:
            if isinstance(event, exit_monitor.SLHit):
                self._notify_strategy(
                    signal_formatter.format_sl_hit(event.vp, event.candle)
                )
                self.vp_store.close(event.vp.strategy_name, event.vp.symbol)
                return  # SL closes the VP; nothing else applies
            if isinstance(event, exit_monitor.TPHit):
                self._notify_strategy(
                    signal_formatter.format_tp_hit(
                        event.vp, event.tp_index, event.tp_price, event.candle
                    )
                )
                self.vp_store.mark_tp_hit(
                    event.vp.strategy_name, event.vp.symbol, event.tp_index
                )
                if event.closes_vp:
                    self.vp_store.close(event.vp.strategy_name, event.vp.symbol)
                    return
                continue
            if isinstance(event, exit_monitor.Expired):
                self._notify_debug(
                    signal_formatter.format_expired(event.vp, event.age_candles)
                )
                self.vp_store.close(event.vp.strategy_name, event.vp.symbol)
                return

    # ------------------------------------------------------------------
    # Action dispatch
    # ------------------------------------------------------------------
    def _handle_action(
        self,
        action: Action,
        vp: VirtualPosition | None,
        symbol: str,
        timeframe: str,
        candle: Candle,
    ) -> None:
        if isinstance(action, OpenPosition):
            self._handle_open(action, vp, symbol, timeframe, candle)
        elif isinstance(action, ClosePosition):
            self._handle_close(action, vp, symbol)
        elif isinstance(action, MoveSL):
            self._handle_move_sl(action, vp, symbol)
        elif isinstance(action, PartialClose):
            self._handle_partial_close(action, vp, symbol)
        # DoNothing or unknown → no-op

    def _handle_open(
        self,
        action: OpenPosition,
        vp: VirtualPosition | None,
        symbol: str,
        timeframe: str,
        candle: Candle,
    ) -> None:
        if vp is not None:
            self._warn_debug(symbol, "OpenPosition emitted while VP already open (no scale-in in v1)")
            return

        signal_id = self.vp_store.next_signal_id(self.instance_cfg.name)
        side = "LONG" if action.side == SIDE_BUY else "SHORT"
        tp_allocations = action.tp_allocations or {}
        tp_close_pcts = tuple(
            float(tp_allocations.get(f"TP{i + 1}", 0.0))
            for i in range(len(action.tp_prices))
        )
        new_vp = VirtualPosition(
            signal_id=signal_id,
            strategy_name=self.instance_cfg.name,
            symbol=symbol,
            side=side,
            entry_price=action.entry_price,
            sl_price=action.sl_price,
            tp_levels=tuple(action.tp_prices),
            tp_close_pcts=tp_close_pcts,
            opened_at_candle_ts=exit_monitor.candle_ts_ms(candle),
            timeframe=timeframe,
        )
        self.vp_store.open(new_vp)
        self._notify_strategy(signal_formatter.format_entry(new_vp))

    def _handle_close(
        self,
        action: ClosePosition,
        vp: VirtualPosition | None,
        symbol: str,
    ) -> None:
        if vp is None:
            self._warn_debug(symbol, "ClosePosition emitted with no open VP")
            return
        self._notify_strategy(
            signal_formatter.format_strategy_exit(vp, action.reason, action.price)
        )
        self.vp_store.close(vp.strategy_name, vp.symbol)

    def _handle_move_sl(
        self,
        action: MoveSL,
        vp: VirtualPosition | None,
        symbol: str,
    ) -> None:
        if vp is None:
            self._warn_debug(symbol, "MoveSL emitted with no open VP")
            return
        old_sl = vp.sl_price
        self.vp_store.update_sl(vp.strategy_name, vp.symbol, action.new_sl_price)
        self._notify_strategy(
            signal_formatter.format_sl_moved(vp, old_sl, action.new_sl_price)
        )

    def _handle_partial_close(
        self,
        action: PartialClose,
        vp: VirtualPosition | None,
        symbol: str,
    ) -> None:
        if vp is None:
            self._warn_debug(symbol, "PartialClose emitted with no open VP")
            return
        self._notify_strategy(
            signal_formatter.format_partial_close(vp, action.tp_level, action.price)
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _vp_to_snapshot(
        self, vp: VirtualPosition | None, symbol: str
    ) -> PositionSnapshot:
        if vp is None:
            return PositionSnapshot(has_position=False, symbol=symbol)
        side = SIDE_BUY if vp.side == "LONG" else SIDE_SELL
        return PositionSnapshot(
            has_position=True,
            symbol=vp.symbol,
            side=side,
            entry_price=vp.entry_price,
            current_sl=vp.sl_price,
            tp1_hit=0 in vp.tp_hits,
            tp2_hit=1 in vp.tp_hits,
            tp3_hit=2 in vp.tp_hits,
        )

    def _notify_strategy(self, message: str) -> None:
        self.notifier.send_message(message, topic_id=self.strategy_topic_id)

    def _notify_debug(self, message: str) -> None:
        self.notifier.send_message(message, topic_id=self.debug_topic_id)

    def _warn_debug(self, symbol: str, reason: str) -> None:
        self._notify_debug(
            signal_formatter.format_invariant_violation(
                self.instance_cfg.name, symbol, reason
            )
        )
