"""
Portfolio Engine — multiplexed multi-symbol backtest with batch processing.

Phase 2.1: BatchCandleCloseEvents process all symbols per timestamp as a batch.
Phase 2.2: Adaptive equity curve sampling reduces recording overhead.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import structlog

from app.backtest.engine.curves import calculate_portfolio_drawdown
from app.backtest.engine.fast_frame import FastFrame
from app.backtest.engine.jit_functions import calculate_equity_jit
from app.backtest.engine.metrics import (
    build_round_trips,
    calculate_metrics,
    calculate_monthly_returns,
    calculate_risk_metrics,
)
from app.backtest.exchange.mock_exchange import MockExchange
from app.core.constants import (
    EQUITY_DRAWDOWN_THRESHOLD,
    EQUITY_SAMPLE_HIGH_RES,
    EQUITY_SAMPLE_INTERVAL,
    EQUITY_SAMPLE_LOW_RES,
)
from app.core.events import CandleCloseEvent, EngineStopEvent
from app.core.snapshots import ContextSnapshot
from app.trading.engine import Engine
from app.trading.portfolio.manager import PortfolioManager

logger = structlog.get_logger()


class PortfolioEngine(Engine):
    """
    Unified Portfolio Engine.

    Consumes chronologically ordered events from multiple symbols.
    Supports both legacy PortfolioEventSource (one event at a time)
    and Phase 2.1 BatchPortfolioEventSource (batched by timestamp).
    """

    def __init__(self, event_source, strategy_class, exchange: MockExchange, config: dict, symbols: list[str]) -> None:
        # Create a single portfolio manager tracking the global exchange
        portfolio = PortfolioManager(exchange, config)

        # Instantiate a single strategy instance used across all symbols
        strategy = strategy_class(config)

        super().__init__(
            event_source=event_source,
            strategy=strategy,
            portfolio=portfolio,
            exchange=exchange,
            symbols=symbols,
        )

        self.exchange: MockExchange = exchange
        self.config = config
        self._initial_balance = float(exchange.balance)
        self._on_progress = None

        # Pass the progress callback down to the event source
        if hasattr(self.event_source, "_on_progress"):
            # Event source wants a callable that takes a float percentage
            self.event_source._on_progress = lambda pct: self._report_progress(pct)

        # Phase 1.2: pre-build FastFrames per symbol for zero-overhead access
        self._fast_frames: dict[str, FastFrame] = {}
        if hasattr(event_source, "dfs"):
            for sym, sym_df in event_source.dfs.items():
                self._fast_frames[sym] = FastFrame.from_dataframe(sym_df)

        # Track global equity over time for the portfolio drawdown curve
        self.portfolio_equity_curve: list[dict] = []
        # Remember the last timestamp processed
        self._last_ts: datetime | None = None
        self._last_equity_ts: datetime | None = None

        # Phase 2.2: Adaptive equity curve sampling state
        self._equity_sample_counter = 0
        self._equity_sample_interval = EQUITY_SAMPLE_INTERVAL
        self._equity_peak = float(exchange.balance)
        self._force_equity_record = False  # Force on order execution

        # Detect batch mode
        from app.backtest.engine.batch_event_source import BatchPortfolioEventSource
        self._batch_mode = isinstance(event_source, BatchPortfolioEventSource)

    def _report_progress(self, pct: float) -> None:
        """Called by event source with percentage 0.0 to 1.0"""
        if self._on_progress:
            self._on_progress({"pct": int(pct * 100), "total": getattr(self.event_source, "total_events", 0)})

    def run(self, on_progress=None) -> dict:
        self._on_progress = on_progress

        logger.info(
            "portfolio_backtest_start",
            symbols=self.symbols,
            initial_balance=self._initial_balance,
            leverage=f"{self.exchange.leverage}x",
        )

        if self._batch_mode:
            self._run_batch_loop()
        else:
            super().run()

        self._close_all_positions(reason="EOD")

        if on_progress:
            on_progress({"pct": 100})

        final_bal = float(self.exchange.balance)

        # Collect total stats
        total_pnl = 0.0
        total_trades = len(self.exchange.trade_history)
        for trade in self.exchange.trade_history:
            if "pnl" in trade and trade["pnl"] is not None:
                total_pnl += trade["pnl"]

        logger.info(
            "portfolio_backtest_complete", final_balance=final_bal, total_trades=total_trades, net_profit=total_pnl
        )

        return self.compute_results()

    def _run_batch_loop(self) -> None:
        """Phase 2.1: Process BatchCandleCloseEvents from batch event source.

        For each timestamp batch: update all candles → check liquidation
        once → record equity once → dispatch all strategy analyses.
        """
        from app.backtest.engine.batch_event_source import BatchCandleCloseEvent

        for event in self.event_source.events():
            if isinstance(event, EngineStopEvent):
                logger.info("engine_stopped", reason=event.reason)
                break
            if not isinstance(event, BatchCandleCloseEvent):
                continue

            ts = event.timestamp
            self._last_ts = ts

            for candle_event in event.events:
                self._update_candle_and_sync(candle_event, ts)

            if self._check_liquidation(ts):
                return

            self.portfolio.sync_from_exchange()
            self._record_equity(ts)

            for candle_event in event.events:
                super()._handle_candle_close(candle_event)

    def _handle_candle_close(self, event: CandleCloseEvent) -> None:
        """Legacy per-event processing (used when not in batch mode)."""
        if event.df is None:
            return

        ci = event.current_index
        ts = event.df.index[ci] if ci is not None else event.df.index[-1]
        self._last_ts = event.candle.timestamp

        self._update_candle_and_sync(event, ts)

        if self._check_liquidation(ts):
            return

        self.portfolio.sync_from_exchange()
        self._record_equity(ts)
        super()._handle_candle_close(event)

    def _update_candle_and_sync(self, event: CandleCloseEvent, ts) -> None:
        """Extract OHLC from event, update exchange, and sync fills."""
        df = event.df
        ci = event.current_index
        if df is None:
            return

        if ci is not None:
            o = float(df["open"].values[ci])
            h = float(df["high"].values[ci])
            low = float(df["low"].values[ci])
            c = float(df["close"].values[ci])
        else:
            row = df.iloc[-1]
            o = float(row["open"])
            h = float(row["high"])
            low = float(row["low"])
            c = float(row["close"])

        executed = self.exchange.update_candle(event.candle.symbol, o, h, low, c, ts)
        if executed:
            self._force_equity_record = True
        self._sync_executed_orders_to_portfolio(event.candle.symbol, executed)

    def _check_liquidation(self, ts) -> bool:
        """Check global liquidation. Returns True if liquidated (halts engine)."""
        if not self.exchange.check_liquidation(ts):
            return False
        self.portfolio.positions.clear()
        for sym in self.symbols:
            self.contexts[sym] = ContextSnapshot(state="SCANNING")
        self._record_equity(ts, force=True)
        logger.warning("portfolio_liquidated_halting", timestamp=ts)
        self.stop()
        return True

    def _sync_executed_orders_to_portfolio(self, symbol: str, executed_orders: list) -> None:
        """
        Sync limit/stop order fills from update_candle() back into PortfolioManager.

        Without this, strategy.analyze() reads position.tp1_hit=False after a TP1
        limit order fires, emits a duplicate PartialClose, and sells at close price
        (variable) instead of the exact TP price — producing inconsistent TP1 PnL.
        """
        for order in executed_orders:
            if order.get("side", "").upper() != "SELL":
                continue

            exit_reason = order.get("info", {}).get("exit_reason", "").upper()
            filled_amount = order.get("filled", order.get("amount", 0))

            # Full close: clear portfolio position and reset context
            if symbol not in self.exchange.positions:
                if symbol in self.portfolio.positions:
                    del self.portfolio.positions[symbol]
                self.contexts[symbol] = ContextSnapshot(state="SCANNING")
                return

            # Partial TP fill: mark hit flag and reduce amount
            pos = self.portfolio.positions.get(symbol)
            if pos is None:
                continue

            from decimal import Decimal

            filled_dec = Decimal(str(filled_amount))

            if exit_reason in ("TP1", "TP2", "TP3"):
                flag = f"{exit_reason.lower()}_hit"
                setattr(pos, flag, True)
                pos.amount = max(Decimal("0"), pos.amount - filled_dec)
                pos.tp_order_ids.pop(exit_reason, None)

                # Move SL to breakeven after TP1 — match live sync_tp_fills() behavior
                if exit_reason == "TP1" and pos.amount > Decimal("0"):
                    self.portfolio.move_stop_loss(symbol, pos.entry_price)

    def _record_equity(self, ts, force: bool = False) -> None:
        """Phase 2.2: Adaptively sample the equity curve.

        Normal mode: record every EQUITY_SAMPLE_INTERVAL candles.
        High-res mode: record every candle when drawdown > threshold.
        Low-res mode: record every EQUITY_SAMPLE_LOW_RES candles when flat.
        Always records on forced events (order execution, liquidation, EOD).
        """
        if self._last_equity_ts == ts:
            return

        self._equity_sample_counter += 1

        # Always record on forced events (order fills, liquidation, EOD)
        if force or self._force_equity_record:
            self._force_equity_record = False
        elif self._equity_sample_counter < self._equity_sample_interval:
            return

        self._equity_sample_counter = 0
        equity = self._calculate_current_equity()

        self.portfolio_equity_curve.append(
            {"date": ts.isoformat() if hasattr(ts, "isoformat") else str(ts), "balance": float(equity)}
        )
        self._last_equity_ts = ts

        # Adapt sampling interval based on drawdown
        if equity > self._equity_peak:
            self._equity_peak = equity

        if self._equity_peak > 0:
            dd_pct = (self._equity_peak - equity) / self._equity_peak * 100
            if dd_pct >= EQUITY_DRAWDOWN_THRESHOLD:
                self._equity_sample_interval = EQUITY_SAMPLE_HIGH_RES
            elif dd_pct < EQUITY_DRAWDOWN_THRESHOLD / 2:
                self._equity_sample_interval = EQUITY_SAMPLE_LOW_RES
            else:
                self._equity_sample_interval = EQUITY_SAMPLE_INTERVAL

    def _calculate_current_equity(self) -> float:
        """Phase 1.3: JIT-accelerated equity calculation."""
        positions = self.exchange.positions
        if not positions:
            return float(self.exchange.balance)

        import numpy as np

        symbols = list(positions.keys())
        n = len(symbols)
        amounts = np.empty(n, dtype=np.float64)
        entries = np.empty(n, dtype=np.float64)
        currents = np.empty(n, dtype=np.float64)
        margins = np.empty(n, dtype=np.float64)

        for i, sym in enumerate(symbols):
            amounts[i] = float(positions[sym])
            entries[i] = float(self.exchange.entry_prices.get(sym, 0))
            curr_data = self.exchange.current_prices.get(sym, {})
            currents[i] = float(curr_data.get("price", entries[i]))
            margins[i] = float(self.exchange.margin_used.get(sym, 0))

        return calculate_equity_jit(
            amounts, entries, currents, margins, float(self.exchange.balance)
        )

    def _close_all_positions(self, reason: str = "EOD") -> None:
        """Close all open positions at final price."""
        if not self.exchange.positions:
            return
        from decimal import Decimal

        for symbol, amount in list(self.exchange.positions.items()):
            if amount > 0:
                curr_data = self.exchange.current_prices.get(symbol, {})
                final_price = curr_data.get("price", self.exchange.entry_prices.get(symbol, Decimal("0")))
                logger.info("closing_eod_position", symbol=symbol, amount=amount, price=final_price)
                self.exchange.create_order(
                    symbol=symbol, order_type="market", side="SELL",
                    amount=Decimal(str(amount)), price=Decimal(str(final_price)),
                    params={"exit_reason": reason},
                )
        if self._last_ts:
            self._record_equity(self._last_ts, force=True)

    def compute_results(self) -> dict:
        """Compute portfolio-wide aggregated metrics."""
        trades = self.exchange.trade_history
        initial = self._initial_balance
        if not trades:
            return self._empty_results(initial)

        df = pd.DataFrame(trades)
        round_trips = build_round_trips(df)
        round_trips_list = round_trips.to_dict(orient="records") if not round_trips.empty else []
        metrics = calculate_metrics(round_trips)
        drawdown_full = calculate_portfolio_drawdown(self.portfolio_equity_curve, initial)
        risk_metrics = calculate_risk_metrics(round_trips, drawdown_full, initial)
        monthly_returns = calculate_monthly_returns(round_trips)
        final_balance = float(self.exchange.balance)
        realized_pnl = float(round_trips["pnl"].sum()) if not round_trips.empty else 0.0
        net_profit_pct = (realized_pnl / initial * 100) if initial > 0 else 0.0

        return {
            "metrics": metrics, "risk_metrics": risk_metrics,
            "drawdown": {
                "max_drawdown_pct": drawdown_full.get("max_drawdown_pct", 0),
                "max_drawdown_value": drawdown_full.get("max_drawdown_value", 0),
                "max_dd_duration": drawdown_full.get("max_dd_duration", 0),
                "avg_drawdown_pct": drawdown_full.get("avg_drawdown_pct", 0),
            },
            "monthly_returns": monthly_returns,
            "equity_curve": self.portfolio_equity_curve,
            "drawdown_curve": drawdown_full.get("drawdown_curve", []),
            "round_trips": round_trips_list,
            "initial_balance": initial, "final_balance": final_balance,
            "net_profit": realized_pnl, "net_profit_pct": net_profit_pct,
        }

    @staticmethod
    def _empty_results(initial: float) -> dict:
        return {
            "metrics": {},
            "risk_metrics": {
                "sharpe_ratio": 0, "sortino_ratio": 0,
                "calmar_ratio": 0, "volatility": 0, "var_95": 0,
            },
            "drawdown": {
                "max_drawdown_pct": 0, "max_drawdown_value": 0,
                "max_dd_duration": 0, "avg_drawdown_pct": 0,
            },
            "monthly_returns": {},
            "equity_curve": [],
            "drawdown_curve": [],
            "round_trips": [],
            "initial_balance": initial,
            "final_balance": initial,
            "net_profit": 0.0,
            "net_profit_pct": 0.0,
        }
