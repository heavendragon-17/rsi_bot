"""
Unified Trading Engine (PR7: Unified Engine with Event Source Pattern)
=======================================================================
Processes EngineEvents from any IEventSource. Both live trading and
backtesting share this same event loop — the event source determines
the origin of the data, not the processing logic.

Live mode:    Engine + LiveEventSource  (wraps BinanceStreamManager)
Backtest mode: BacktestEngine + BacktestEventSource (replays CSV)
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import structlog

from app.core.actions import (
    ClosePosition,
    MoveSL,
    OpenPosition,
    PartialClose,
)
from app.core.events import CandleCloseEvent, EngineStopEvent, SignalEvent, TickEvent
from app.core.interfaces import IExchange, IStrategy
from app.core.snapshots import ContextSnapshot
from app.trading.event_source import IEventSource

logger = structlog.get_logger()


class Engine:
    """
    Unified trading engine.

    Consumes events from an IEventSource and dispatches typed actions to
    Portfolio. Centralises the action-dispatch logic that was previously
    duplicated in MultiSymbolRunner and BacktestEngine.

    Subclass to add mode-specific behaviour (e.g. BacktestEngine overrides
    _handle_candle_close to run MockExchange wick-fill checking first).
    """

    def __init__(
        self,
        event_source: IEventSource,
        strategy: IStrategy,
        portfolio,  # PortfolioManager (avoid circular import)
        exchange: IExchange,
        symbols: list[str],
        on_progress: Callable[[float], None] | None = None,
    ) -> None:
        self.event_source = event_source
        self.strategy = strategy
        self.portfolio = portfolio
        self.exchange = exchange
        self.symbols = symbols
        self.on_progress = on_progress

        # Per-symbol strategy context (stateless strategy, external state)
        self.contexts: dict[str, ContextSnapshot] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> dict | None:
        """
        Main event loop. Processes events until source is exhausted or stopped.

        Returns:
            Result dict (for backtest subclass) or None (live — runs forever).
        """
        logger.info("engine_started", symbols=self.symbols)

        for event in self.event_source.events():
            if isinstance(event, TickEvent):
                self._handle_tick(event)
            elif isinstance(event, CandleCloseEvent):
                self._handle_candle_close(event)
            elif isinstance(event, EngineStopEvent):
                logger.info("engine_stopped", reason=event.reason)
                break

        return self._compute_results()

    def stop(self) -> None:
        """Stop the engine by stopping its event source."""
        self.event_source.stop()

    # ------------------------------------------------------------------
    # Event handlers (override in subclasses for mode-specific behaviour)
    # ------------------------------------------------------------------

    def _handle_tick(self, tick: TickEvent) -> None:
        """
        Process a price tick.

        Tick mode is optional (PR7). Override in subclass if tick-based
        fill checking is needed (e.g. LiveEngine monitoring open orders).
        """
        pass

    def _handle_candle_close(self, event: CandleCloseEvent) -> None:
        """
        Process a closed candle: run strategy analysis and dispatch actions.

        The event carries either a pre-built DataFrame (backtest) or None
        (live, where the caller is expected to attach the store DataFrame).
        Subclasses may call super() after performing mode-specific setup
        (e.g. BacktestEngine calls exchange.update_candle first).
        """
        candle = event.candle
        symbol = candle.symbol
        df = event.df
        current_index = event.current_index

        effective_len = (current_index + 1) if current_index is not None else (len(df) if df is not None else 0)
        if df is None or effective_len < 50:
            return

        position = self.portfolio.get_position_snapshot(symbol)
        ctx = self.contexts.get(symbol, ContextSnapshot(state="SCANNING"))

        result = self.strategy.analyze(symbol, df, position=position, context=ctx, current_index=current_index)

        self.contexts[symbol] = result.new_context

        for action in result.actions:
            self._apply_action(action)

    # ------------------------------------------------------------------
    # Action dispatch (single canonical implementation)
    # ------------------------------------------------------------------

    def _apply_action(self, action) -> None:
        """Dispatch a typed action to the Portfolio."""
        if isinstance(action, OpenPosition):
            signal = self._action_to_signal(action)
            logger.info("open_position", symbol=action.symbol, price=str(action.entry_price))
            self.portfolio.on_signal(signal)

        elif isinstance(action, ClosePosition):
            logger.info("close_position", symbol=action.symbol, reason=action.reason)
            self.portfolio.close_position(action.symbol, reason=action.reason, price=action.price)

        elif isinstance(action, MoveSL):
            logger.info("move_sl", symbol=action.symbol, new_sl=str(action.new_sl_price), reason=action.reason)
            self.portfolio.move_stop_loss(action.symbol, action.new_sl_price)

        elif isinstance(action, PartialClose):
            logger.info("partial_close", symbol=action.symbol, tp_level=action.tp_level, price=str(action.price))
            self.portfolio.execute_partial_close(action.symbol, action.tp_level, new_sl_price=action.new_sl_price)

        # DoNothing: explicit no-op, nothing to dispatch

    def _action_to_signal(self, action: OpenPosition) -> SignalEvent:
        """Convert an OpenPosition action to a SignalEvent for PortfolioManager.

        signal_type mirrors action.side:
          "BUY"  → long  entry (PortfolioManager._handle_entry_signal BUY)
          "SELL" → short entry (PortfolioManager._handle_entry_signal SELL)
        """
        tp_prices = action.tp_prices or []
        return SignalEvent(
            symbol=action.symbol,
            signal_type=action.side,  # "BUY" for long, "SELL" for short
            price=action.entry_price,
            timestamp=datetime.now(),
            reason=action.reason,
            sl_price=action.sl_price,
            soft_sl_price=action.soft_sl_price,
            tp1_price=tp_prices[0] if len(tp_prices) > 0 else None,
            tp2_price=tp_prices[1] if len(tp_prices) > 1 else None,
            tp3_price=tp_prices[2] if len(tp_prices) > 2 else None,
            signal_class=action.signal_class,
            lock_profit_price=action.lock_profit_price,
            tp_allocations=action.tp_allocations,
        )

    # ------------------------------------------------------------------
    # Override in subclass
    # ------------------------------------------------------------------

    def _compute_results(self) -> dict | None:
        """
        Called after the event loop ends.
        Override in BacktestEngine to return metrics dict.
        """
        return None
