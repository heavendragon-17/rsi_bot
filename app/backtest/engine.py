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

# Limit the lookback window passed to strategies to prevent O(N^2) behavior
# when strategies resample or copy the dataframe.
# 50,000 candles is sufficient for almost any lookback or resampling (e.g. 1m -> 4h is ~240x)
MAX_LOOKBACK_WINDOW = 50000

class BacktestEngine:
    def __init__(self, data_path: str, strategy_class, config: dict):
        self.data = pd.read_csv(data_path)
        self.data["timestamp"] = pd.to_datetime(self.data["timestamp"])
        self.config = config
        self.symbol = config["symbols"][0]

        initial_balance = config.get("backtest", {}).get("initial_balance", 1000.0)
        self.exchange = MockExchange(initial_balance=initial_balance)
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
        print(f"Initial balance: {self.exchange.get_balance()}")

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

            # Handle executed SL orders
            for order in executed_orders:
                if order['order_type'] == 'STOP_LOSS':
                    if self.symbol in self.portfolio.positions:
                        del self.portfolio.positions[self.symbol]
                    if hasattr(self.strategy, 'context') and self.strategy.context:
                        self.strategy.context.close_trade(self.symbol)
                        tf = getattr(self.strategy, 'timeframe', '')
                        key = f"{self.symbol}:{tf}"
                        self.strategy.context.transition(key, SCANNING, reason="SL hit", now_ts=ts)

            self.portfolio.sync_from_exchange()

            # Pass windowed slice to prevent O(N^2) memory/copying behavior
            # Strategy only needs recent history (lookback).
            start_idx = max(0, i - MAX_LOOKBACK_WINDOW)
            df_slice = self._full_df.iloc[start_idx:i+1]
            signal = self.strategy.analyze(self.symbol, df_slice)

            if signal:
                self.portfolio.on_signal(signal)

        print("\nBacktest complete!")
        print(f"Final balance: {self.exchange.get_balance()}")
        print(f"Open positions: {dict(self.exchange.positions)}")
        print(f"Total trades: {len(self.exchange.trade_history)}")
