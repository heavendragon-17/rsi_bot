"""
Backtest Engine
================
Runs strategy on historical data with Decimal support.
"""
import pandas as pd
from decimal import Decimal
from app.services.market_data.store import MarketDataStore
from app.core.events import Candle, SignalEvent
from app.core.portfolio import PortfolioManager
from app.backtest.mock_exchange import MockExchange
from datetime import datetime


class BacktestEngine:
    """Engine to run backtests on historical data."""
    
    def __init__(self, data_path: str, strategy_class, config: dict):
        self.data = pd.read_csv(data_path)
        self.data['timestamp'] = pd.to_datetime(self.data['timestamp'])
        self.config = config
        self.symbol = config['symbols'][0]
        self.store = MarketDataStore()

        # 1. Initialize Mock Exchange
        initial_balance = config.get('backtest', {}).get('initial_balance', 1000.0)
        self.exchange = MockExchange(initial_balance=initial_balance)

        # 2. Initialize Portfolio Manager
        self.portfolio = PortfolioManager(self.exchange, config)

        # 3. Initialize Strategy
        self.strategy = strategy_class(config)

    def run(self) -> None:
        """Run the backtest simulation."""
        print(f"Starting backtest on {self.symbol} with {len(self.data)} candles...")
        print(f"Initial balance: {self.exchange.get_balance()}")

        warmup_period = 220  # Need enough data for indicators

        for i, row in self.data.iterrows():
            # 1. Update Market Data with Decimal types
            candle = Candle(
                symbol=self.symbol,
                timestamp=row['timestamp'],
                open=Decimal(str(row['open'])),
                high=Decimal(str(row['high'])),
                low=Decimal(str(row['low'])),
                close=Decimal(str(row['close'])),
                volume=Decimal(str(row['volume'])),
                closed=True
            )
            self.store.update_candle(candle)

            # 2. Update Exchange Price (for SL order checking)
            self.exchange.update_price(
                self.symbol,
                candle.close,
                candle.timestamp
            )

            if i < warmup_period:
                continue

            # 3. Run Strategy
            df = self.store.get_dataframe(self.symbol)
            signal = self.strategy.analyze(self.symbol, df)

            # 4. Process Signal via Portfolio
            if signal:
                self.portfolio.on_signal(signal)

        # Final summary
        print(f"\nBacktest complete!")
        print(f"Final balance: {self.exchange.get_balance()}")
        print(f"Open positions: {self.exchange.positions}")
        print(f"Total trades: {len(self.exchange.trade_history)}")
