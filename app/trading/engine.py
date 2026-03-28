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

        Phase 1.1: When ``event.current_index`` is set, ``event.df`` is the
        *full* pre-computed DataFrame (zero-copy). We pass a slice
        ``df.iloc[:current_index+1]`` only when actually calling strategy.analyze()
        to maintain the same contract.  This slice is cheap because strategies
        are updated to use current_index for direct access instead of scanning
        from the end.
        """
        candle = event.candle
        symbol = candle.symbol
        df = event.df
        ci = event.current_index

        if df is None:
            return

        # For backtest fast-path (current_index set), check length via index
        effective_len = (ci + 1) if ci is not None else len(df)
        if effective_len < 50:
            return

        position = self.portfolio.get_position_snapshot(symbol)
        ctx = self.contexts.get(symbol, ContextSnapshot(state="SCANNING"))

        # Phase 1.2: use FastFrame when available (zero pandas overhead)
        fast_frames = getattr(self, "_fast_frames", None)
        fast_frame = getattr(self, "_fast_frame", None)

        if ci is not None and fast_frames and symbol in fast_frames:
            # Portfolio mode: per-symbol FastFrame
            df_view = fast_frames[symbol]._subview(0, ci + 1)
        elif ci is not None and fast_frame is not None:
            # Single-symbol mode
            df_view = fast_frame._subview(0, ci + 1)
        elif ci is not None:
            df_view = df.iloc[: ci + 1]
        else:
            df_view = df

        result = self.strategy.analyze(symbol, df_view, position=position, context=ctx)

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
