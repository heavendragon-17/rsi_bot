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
from app.services.execution.exchange_factory import create_exchange
from app.core.context import SCANNING
from app.utils.indicators import Indicators


class BacktestEngine:
    def __init__(self, data_path: str, strategy_class, config: dict):
        self.data = pd.read_csv(data_path)
        self.data["timestamp"] = pd.to_datetime(self.data["timestamp"])
        self.config = config
        self.symbol = config["symbols"][0]

        # Get backtest and risk settings
        leverage = config.get("risk", {}).get("leverage", 1)
        
        # Initialize exchange with leverage
        self.exchange = create_exchange(config)
        self.exchange.set_leverage(self.symbol, leverage)

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
        print(f"Leverage: {self.exchange.leverage}x")

        warmup_period = 220
        n_rows = len(self._full_df)

        for i in range(warmup_period, n_rows):
            row = self._full_df.iloc[i]
            ts = self._full_df.index[i]
            o, h, l, c = row["open"], row["high"], row["low"], row["close"]
            v = row.get("volume", 0)

            # 1. Update Portfolio on candle close
            candle = Candle(
                symbol=self.symbol,
                timestamp=ts,
                open=Decimal(str(o)),
                high=Decimal(str(h)),
                low=Decimal(str(l)),
                close=Decimal(str(c)),
                volume=Decimal(str(v)),
                closed=True
            )
            self.portfolio.on_candle(candle)

            # 2. Update exchange with full OHLC (checks pending SL/TP against wicks)
            # Only if exchange supports update_candle (MockExchange)
            executed_orders = []
            if hasattr(self.exchange, "update_candle"):
                executed_orders = self.exchange.update_candle(
                    self.symbol, float(o), float(h), float(l), float(c), ts
                )
            else:
                # Fallback or stub for adapters that don't simulate matching
                pass

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

            # Pass pre-computed slice (indicators already calculated)
            df_slice = self._full_df.iloc[:i+1]
            signal = self.strategy.analyze(self.symbol, df_slice)

            if signal:
                risk_params = self.strategy.get_risk_params(signal)
                self.portfolio.on_signal(signal, risk_params)

        # Close any open positions at final price for accurate reporting
        self._close_open_positions()

        print("\nBacktest complete!")
        print(f"Final balance: {self.exchange.get_balance()}")
        print(f"Open positions: {dict(self.exchange.positions)}")
        print(f"Total trades: {len(self.exchange.trade_history)}")

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
                    order_type='MARKET',
                    side='SELL',
                    amount=float(amount),
                    price=final_price,
                    exit_reason='EOD'  # End of Data
                )

