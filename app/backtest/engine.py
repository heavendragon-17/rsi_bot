"""
Backtest Engine (Vectorized)
============================
Runs strategy on historical data with wick-based SL/TP checking.
Pre-computes all indicators once for O(n) performance.
"""
import pandas as pd
import numpy as np
from decimal import Decimal
from app.core.events import Candle, SignalEvent
from app.core.portfolio import PortfolioManager
from app.backtest.mock_exchange import MockExchange
from app.core.context import SCANNING
from app.utils.indicators import Indicators


class BacktestEngine:
    def __init__(self, data_path: str, strategy_class, config: dict):
        self.data = pd.read_csv(data_path)
        self.data["timestamp"] = pd.to_datetime(self.data["timestamp"])
        self.config = config
        self.symbol = config["symbols"][0]

        # Get backtest and risk settings
        initial_balance = config.get("backtest", {}).get("initial_balance", 1000.0)
        leverage = config.get("risk", {}).get("leverage", 1)
        
        # Initialize exchange with leverage
        self.exchange = MockExchange(initial_balance=initial_balance, leverage=leverage)
        self.portfolio = PortfolioManager(self.exchange, config)
        self.strategy = strategy_class(config)
        
        # Pre-compute all indicators ONCE
        self._full_df = self._prepare_dataframe()

    def _prepare_dataframe(self) -> pd.DataFrame:
        """Pre-process data and compute all indicators once."""
        df = self.data.copy()
        df.set_index("timestamp", inplace=True)
        df["closed"] = True
        df["ts"] = df.index.astype(np.int64) // 10**6
        
        # Pre-compute indicators using strategy's indicator config
        indicators = self.strategy.indicators
        df = indicators.compute(df, symbol=self.symbol, timeframe="backtest")
        
        return df

    def run(self) -> None:
        print(f"Starting backtest on {self.symbol} with {len(self.data)} candles...")
        initial_bal = self.exchange.fetch_balance().get("total", {}).get("USDT", 0)
        print(f"Initial balance: {initial_bal}")
        print(f"Leverage: {self.exchange.leverage}x")

        warmup_period = 220
        n_rows = len(self._full_df)

        for i in range(warmup_period, n_rows):
            row = self._full_df.iloc[i]
            ts = self._full_df.index[i]
            o, h, l, c = row["open"], row["high"], row["low"], row["close"]

            # Update exchange with full OHLC (checks pending SL/TP against wicks)
            executed_orders = self.exchange.update_candle(
                self.symbol, float(o), float(h), float(l), float(c), ts
            )

            # Let Portfolio Manager update its state based on executions (TPs, SLs)
            self.portfolio.process_executions(executed_orders)

            # Sync Portfolio state back to Strategy Context to avoid double execution
            self._sync_strategy_state()

            # Handle Strategy Context transitions for any Full Exits (SL or TP3)
            if self.symbol not in self.portfolio.positions:
                closed_reason = None
                for order in executed_orders:
                    reason = order.get("info", {}).get("exit_reason", "").upper()
                    if "STOP_LOSS" in reason or "SL" in reason:
                        closed_reason = "SL hit"
                    elif "TP3" in reason:
                        closed_reason = "TP3 hit"

                if closed_reason and hasattr(self.strategy, 'context') and self.strategy.context:
                    if self.strategy.context.has_active_trade(self.symbol):
                        self.strategy.context.close_trade(self.symbol)
                        tf = getattr(self.strategy, 'timeframe', '')
                        key = f"{self.symbol}:{tf}"
                        self.strategy.context.transition(key, SCANNING, reason=closed_reason, now_ts=ts)

            self.portfolio.sync_from_exchange()

            # Pass pre-computed slice (indicators already calculated)
            df_slice = self._full_df.iloc[:i+1]
            signal = self.strategy.analyze(self.symbol, df_slice)

            if signal:
                self.portfolio.on_signal(signal)

        # Close any open positions at final price for accurate reporting
        self._close_open_positions()

        print("\nBacktest complete!")
        final_bal = self.exchange.fetch_balance().get("total", {}).get("USDT", 0)
        print(f"Final balance: {final_bal}")
        print(f"Open positions: {dict(self.exchange.positions)}")
        print(f"Total trades: {len(self.exchange.trade_history)}")

    def _sync_strategy_state(self) -> None:
        """Sync PortfolioManager execution state to StrategyContext to prevent double execution."""
        if not hasattr(self.strategy, 'context') or not self.strategy.context:
            return

        for symbol, pos in self.portfolio.positions.items():
            if self.strategy.context.has_active_trade(symbol):
                trade = self.strategy.context.get_trade(symbol)
                meta = trade.meta

                # Sync TP1
                if pos.tp1_hit and not meta.get('tp1_hit'):
                    meta['tp1_hit'] = True
                    # Emulate strategy logic for TP1 hit: move SL to lock profit
                    meta['moved_sl_to_entry'] = True
                    if pos.lock_profit_price:
                        meta['sl_price'] = pos.lock_profit_price
                        meta['soft_sl_price'] = pos.lock_profit_price

                # Sync TP2
                if pos.tp2_hit and not meta.get('tp2_hit'):
                    meta['tp2_hit'] = True

                # Sync TP3
                if pos.tp3_hit and not meta.get('tp3_hit'):
                    meta['tp3_hit'] = True

    def _close_open_positions(self) -> None:
        """Close all open positions at the last available price for accurate final reporting."""
        if not self.exchange.positions:
            return
        
        last_row = self._full_df.iloc[-1]
        final_ts = self._full_df.index[-1]
        final_price = float(last_row["close"])
        
        positions_to_close = list(self.exchange.positions.items())
        for symbol, amount in positions_to_close:
            if amount > 0:
                print(f"Closing open position: {symbol} {amount} @ {final_price} (EOD)")
                self.exchange.create_order(
                    symbol=symbol,
                    type='market',
                    side='SELL',
                    amount=float(amount),
                    price=final_price,
                    params={'exit_reason': 'EOD'}  # End of Data
                )
