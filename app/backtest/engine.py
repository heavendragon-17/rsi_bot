"""
Backtest Engine (Vectorized)
============================
Runs strategy on historical data with candle-close based SL/TP checking.
Pre-computes all indicators once for O(n) performance.

v2: Uses DI for exchange, on_candle() for SL/TP management.
"""
import pandas as pd
import numpy as np
from decimal import Decimal
from datetime import datetime

from app.core.events import Candle, SignalEvent
from app.core.portfolio import PortfolioManager
from app.core.interfaces import IFuturesExchange
from app.core.context import SCANNING
from app.utils.indicators import Indicators
from app.services.execution.exchange_factory import create_exchange


class BacktestEngine:
    """
    Backtest engine with dependency injection support.
    
    The engine:
    1. Pre-computes all indicators
    2. Loops through candles
    3. Calls portfolio.on_candle() to check SL/TP on close
    4. Calls strategy.analyze() for new signals
    5. Executes signals via portfolio.on_signal()
    """
    
    def __init__(
        self, 
        data_path: str, 
        strategy_class, 
        config: dict,
        exchange: IFuturesExchange = None  # DI: inject exchange
    ):
        self.data = pd.read_csv(data_path)
        self.data["timestamp"] = pd.to_datetime(self.data["timestamp"])
        self.config = config
        self.symbol = config["symbols"][0]

        # Use injected exchange or create via factory
        if exchange is None:
            exchange = create_exchange(config)
        self.exchange = exchange
        
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
        if hasattr(self.exchange, 'leverage'):
            print(f"Leverage: {self.exchange.leverage}x")

        warmup_period = 220
        n_rows = len(self._full_df)

        for i in range(warmup_period, n_rows):
            row = self._full_df.iloc[i]
            ts = self._full_df.index[i]
            o, h, l, c = row["open"], row["high"], row["low"], row["close"]

            # Create Candle event for this bar
            candle = Candle(
                symbol=self.symbol,
                timestamp=ts if isinstance(ts, datetime) else pd.Timestamp(ts).to_pydatetime(),
                open=Decimal(str(o)),
                high=Decimal(str(h)),
                low=Decimal(str(l)),
                close=Decimal(str(c)),
                volume=Decimal(str(row.get("volume", 0))),
                closed=True
            )

            # 1. Portfolio checks SL/TP on candle close
            executions = self.portfolio.on_candle(candle)
            
            # 2. Handle any executions (update strategy context)
            for exec_event in executions:
                if exec_event.get('type') == 'SL':
                    if hasattr(self.strategy, 'context') and self.strategy.context:
                        self.strategy.context.close_trade(self.symbol)
                        tf = getattr(self.strategy, 'timeframe', '')
                        key = f"{self.symbol}:{tf}"
                        self.strategy.context.transition(key, SCANNING, reason="SL hit", now_ts=ts)

            # 3. Update exchange price (for disaster SL checking only)
            self.exchange.update_price(self.symbol, float(c), ts)
            
            # 4. Sync portfolio state
            self.portfolio.sync_from_exchange()

            # 5. Strategy analyzes for new entry signals
            df_slice = self._full_df.iloc[:i+1]
            signal = self.strategy.analyze(self.symbol, df_slice)

            if signal:
                # Attach risk params to signal for position creation
                risk_params = self.strategy.get_risk_params(signal)
                self.portfolio.on_signal(signal, risk_params=risk_params)

        # Close any open positions at final price for accurate reporting
        self._close_open_positions()

        print("\nBacktest complete!")
        print(f"Final balance: {self.exchange.get_balance()}")
        if hasattr(self.exchange, 'positions'):
            print(f"Open positions: {dict(self.exchange.positions)}")
        if hasattr(self.exchange, 'trade_history'):
            print(f"Total trades: {len(self.exchange.trade_history)}")

    def _close_open_positions(self) -> None:
        """Close all open positions at the last available price for accurate final reporting."""
        if not hasattr(self.exchange, 'positions') or not self.exchange.positions:
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


