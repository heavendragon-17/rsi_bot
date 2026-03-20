"""
Portfolio Engine
================
Subclasses the unified Engine to support multiplexed events from PortfolioEventSource.
Adds global liquidation checks per candle and aggregate metrics calculation.
"""
from __future__ import annotations

import pandas as pd
import structlog

from app.trading.engine import Engine
from app.core.events import CandleCloseEvent
from app.core.snapshots import ContextSnapshot
from app.backtest.mock_exchange import MockExchange
from app.trading.portfolio.manager import PortfolioManager
from app.backtest.engine import BacktestEngine

logger = structlog.get_logger()

class PortfolioEngine(Engine):
    """
    Unified Portfolio Engine.

    Consumes chronologically ordered CandleCloseEvents from multiple symbols.
    For each candle, it updates MockExchange with the wicks, checks for specific
    SL/TP fills, checks global liquidation, and then dispatches strategy actions.
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

        self.config = config
        self._initial_balance = float(exchange.balance)
        self._on_progress = None

        # Pass the progress callback down to the event source
        if hasattr(self.event_source, '_on_progress'):
            # Event source wants a callable that takes a float percentage
            self.event_source._on_progress = lambda pct: self._report_progress(pct)

        # Track global equity over time for the portfolio drawdown curve
        self.portfolio_equity_curve = []
        # Remember the last timestamp processed
        self._last_ts = None

    def _report_progress(self, pct: float) -> None:
        """Called by event source with percentage 0.0 to 1.0"""
        if self._on_progress:
            self._on_progress({
                "pct": int(pct * 100),
                "total": getattr(self.event_source, 'total_events', 0)
            })

    def run(self, on_progress=None) -> dict:
        self._on_progress = on_progress

        logger.info(
            "portfolio_backtest_start",
            symbols=self.symbols,
            initial_balance=self._initial_balance,
            leverage=f"{self.exchange.leverage}x",
        )

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
            "portfolio_backtest_complete",
            final_balance=final_bal,
            total_trades=total_trades,
            net_profit=total_pnl
        )

        return self.compute_results()

    def _handle_candle_close(self, event: CandleCloseEvent) -> None:
        candle = event.candle
        df = event.df

        if df is None:
            return
            
        # Update last timestamp
        self._last_ts = candle.timestamp

        # 1. Update MockExchange wicks for THIS specific symbol
        row = df.iloc[-1]
        ts = df.index[-1]
        o = float(row["open"])
        h = float(row["high"])
        l = float(row["low"])
        c = float(row["close"])

        executed_orders = self.exchange.update_candle(candle.symbol, o, h, l, c, ts)

        # Sync exchange-executed orders back into portfolio state.
        # This covers two cases:
        #  1. PARTIAL TP fill (limit order fired by update_candle): mark tp1/2/3_hit
        #     and reduce pos.amount so strategy.analyze() won't emit a duplicate
        #     PartialClose on the same candle (variable-PnL double-sell bug).
        #  2. Full position close (SL or final TP): clear portfolio position and
        #     reset context to SCANNING so new entries can fire immediately.
        self._sync_executed_orders_to_portfolio(candle.symbol, executed_orders)

        # 2. Check Global Liquidation
        liquidated = self.exchange.check_liquidation(ts)
        if liquidated:
            # If liquidated, clear all portfolio tracking and reset all contexts
            self.portfolio.positions.clear()
            for sym in self.symbols:
                self.contexts[sym] = ContextSnapshot(state="SCANNING")
            
            # Record equity curve drop
            self._record_equity(ts)
            
            # Since we blew up, we stop processing (optional: we could just wait to recover, but let's halt)
            logger.warning("portfolio_liquidated_halting", timestamp=ts)
            self.stop()
            return
            
        self.portfolio.sync_from_exchange()
        
        # 3. Record Equity curve periodically (e.g., at the end of each day or every candle)
        # For a truly accurate portfolio curve, we document equity as it changes.
        # To avoid massive arrays for tick data, we sample once per day or when orders execute.
        # But for M15, storing every candle isn't too terrible. 
        self._record_equity(ts)

        # 4. Strategy Analysis (Unified base Engine handles this seamlessly)
        super()._handle_candle_close(event)

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
                    self.portfolio._move_sl_to_entry(symbol)

    def _record_equity(self, ts) -> None:
        """Calculate and store the current total portfolio equity"""
        if not hasattr(self, '_last_equity_ts') or self._last_equity_ts != ts:
            equity = self._calculate_current_equity()
            self.portfolio_equity_curve.append({
                "date": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "balance": float(equity)
            })
            self._last_equity_ts = ts

    def _calculate_current_equity(self) -> float:
        usdt_balance = float(self.exchange.balance)
        used_usdt = float(sum(self.exchange.margin_used.values()))
        
        total_upnl = 0.0
        for symbol, amt_dec in self.exchange.positions.items():
            if amt_dec == 0:
                continue
            entry = float(self.exchange.entry_prices.get(symbol, 0))
            curr_data = self.exchange.current_prices.get(symbol, {})
            curr = float(curr_data.get("price", entry))
            upnl = (curr - entry) * float(amt_dec)
            total_upnl += upnl

        return usdt_balance + used_usdt + total_upnl

    def _close_all_positions(self, reason: str = "EOD") -> None:
        """Close all open positions at final price."""
        if not self.exchange.positions:
            return

        ts = self._last_ts
        for symbol, amount in list(self.exchange.positions.items()):
            if amount > 0:
                curr_data = self.exchange.current_prices.get(symbol, {})
                # If we don't have a current price for some reason, use entry
                final_price = float(curr_data.get("price", self.exchange.entry_prices.get(symbol, 0)))
                
                logger.info(
                    "closing_eod_position",
                    symbol=symbol,
                    amount=amount,
                    price=final_price,
                )
                self.exchange.create_order(
                    symbol=symbol,
                    order_type="market",
                    side="SELL",
                    amount=float(amount),
                    price=final_price,
                    params={"exit_reason": reason},
                )
        
        # Record final equity
        if ts:
             self._record_equity(ts)

    def compute_results(self) -> dict:
        """
        Compute portfolio-wide aggregated metrics.
        Borrows heavy lifting from BacktestEngine static helpers.
        """
        trades = self.exchange.trade_history
        initial = self._initial_balance

        if not trades:
            return self._empty_results(initial)

        df = pd.DataFrame(trades)
        round_trips = BacktestEngine._build_round_trips(df)
        round_trips_list = (
            round_trips.to_dict(orient="records") if not round_trips.empty else []
        )

        metrics = BacktestEngine._calculate_metrics(round_trips)
        
        # Drawdown: use the recorded portfolio equity curve rather than simply summing closed trade PnLs
        # Because we multiplexed time, unrealized drawdown during holding periods matters
        drawdown_full = self._calculate_portfolio_drawdown(initial)
        risk_metrics = BacktestEngine._calculate_risk_metrics(round_trips, drawdown_full, initial)
        monthly_returns = BacktestEngine._calculate_monthly_returns(round_trips)

        final_balance = float(self.exchange.balance)
        realized_pnl = float(round_trips["pnl"].sum()) if not round_trips.empty else 0.0
        net_profit_pct = (realized_pnl / initial * 100) if initial > 0 else 0.0

        return {
            "metrics": metrics,
            "risk_metrics": risk_metrics,
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
            "initial_balance": initial,
            "final_balance": final_balance,
            "net_profit": realized_pnl,
            "net_profit_pct": net_profit_pct,
        }

    def _calculate_portfolio_drawdown(self, initial_balance: float) -> dict:
        if not self.portfolio_equity_curve:
            return {
                "max_drawdown_pct": 0, "max_drawdown_value": 0,
                "drawdown_curve": [], "max_dd_duration": 0, "avg_drawdown_pct": 0,
            }

        peak = initial_balance
        max_dd = 0.0
        max_dd_value = 0.0
        current_dd_duration = 0
        max_dd_duration = 0
        all_drawdowns = []
        dd_curve = []

        for point in self.portfolio_equity_curve:
            val = point["balance"]
            date_str = point["date"]
            
            if val > peak:
                peak = val
                if current_dd_duration > 0:
                    max_dd_duration = max(max_dd_duration, current_dd_duration)
                current_dd_duration = 0
            else:
                dd = (peak - val) / peak if peak > 0 else 0
                if dd > 0:
                     all_drawdowns.append(dd * 100)
                     current_dd_duration += 1
                if dd > max_dd:
                     max_dd = dd
                     max_dd_value = peak - val
            
            dd_curve.append({"date": date_str, "drawdown": round(dd * 100, 4) if val <= peak else 0.0})

        if current_dd_duration > 0:
             max_dd_duration = max(max_dd_duration, current_dd_duration)

        avg_drawdown = sum(all_drawdowns) / len(all_drawdowns) if all_drawdowns else 0

        return {
            "max_drawdown_pct": max_dd * 100,
            "max_drawdown_value": max_dd_value,
            "drawdown_curve": dd_curve,
            "max_dd_duration": max_dd_duration,
            "avg_drawdown_pct": avg_drawdown,
        }

    def _empty_results(self, initial: float) -> dict:
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
