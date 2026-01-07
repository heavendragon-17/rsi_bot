import pandas as pd
from app.services.market_data.store import MarketDataStore
from app.core.events import Candle, SignalEvent
from app.core.portfolio import PortfolioManager
from app.backtest.mock_exchange import MockExchange
from datetime import datetime

class BacktestEngine:
    def __init__(self, data_path, strategy_class, config):
        self.data = pd.read_csv(data_path)
        self.data['timestamp'] = pd.to_datetime(self.data['timestamp'])
        self.config = config
        self.symbol = config['symbols'][0]
        self.store = MarketDataStore()

        # 1. Initialize Mock Exchange
        initial_balance = config.get('backtest', {}).get('initial_balance', 1000.0)
        self.exchange = MockExchange(initial_balance=initial_balance)

        # 2. Initialize Real Portfolio Manager (injected with Mock Exchange)
        self.portfolio = PortfolioManager(self.exchange, config)

        # 3. Initialize Strategy
        self.strategy = strategy_class(config)

    def run(self):
        print(f"Starting backtest on {self.symbol} with {len(self.data)} candles...")

        warmup_period = 50

        for i, row in self.data.iterrows():
            # 1. Update Market Data
            candle = Candle(
                symbol=self.symbol,
                timestamp=row['timestamp'],
                open=row['open'],
                high=row['high'],
                low=row['low'],
                close=row['close'],
                volume=row['volume'],
                closed=True
            )
            self.store.update_candle(candle)

            # 2. Update Exchange Price (Mark-to-Market)
            self.exchange.update_price(self.symbol, candle.close, candle.timestamp)

            # Check SL/TP (Portfolio responsibility? or Strategy?)
            # In this architecture, PortfolioManager manages risk on signals.
            # Continuous monitoring (SL/TP) would typically happen here via `portfolio.on_tick(candle)`
            # but for this iteration, we rely on Strategy to emit EXIT signals.

            if i < warmup_period:
                continue

            # 3. Run Strategy
            df = self.store.get_dataframe(self.symbol)
            signal = self.strategy.analyze(self.symbol, df)

            # 4. Process Signal via Portfolio
            if signal:
                self.portfolio.on_signal(signal)
