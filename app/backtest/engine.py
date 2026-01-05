import pandas as pd
from app.services.market_data.store import MarketDataStore
from app.core.events import Candle
from datetime import datetime

class BacktestEngine:
    def __init__(self, data_path, strategy_class, portfolio, config):
        self.data = pd.read_csv(data_path)
        self.data['timestamp'] = pd.to_datetime(self.data['timestamp'])
        self.strategy = strategy_class(config)
        self.portfolio = portfolio
        self.config = config
        self.symbol = config['symbols'][0] # Single symbol backtest for now
        self.store = MarketDataStore()

    def run(self):
        print(f"Starting backtest on {self.symbol} with {len(self.data)} candles...")

        # Pre-fill store with some data if needed (warmup)
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

            # Check SL/TP for existing positions BEFORE strategy analysis (simulating order fill during candle)
            # Actually, standard backtesting checks SL/TP against High/Low of current candle
            self.portfolio.check_sl_tp(self.symbol, candle)

            if i < warmup_period:
                continue

            # 2. Run Strategy
            # Get dataframe from store
            df = self.store.get_dataframe(self.symbol)
            signal = self.strategy.analyze(self.symbol, df)

            # 3. Execute Signal
            if signal:
                self._execute_signal(signal, candle)

    def _execute_signal(self, signal, candle):
        # User defined rules:
        # Buy on Signal
        # Sell on Signal (if strategy supports it)

        if signal.signal_type == 'BUY':
            if self.symbol not in self.portfolio.positions:
                # Calculate quantity based on risk or balance
                # Simple: Use 99% balance to avoid rounding errors or fee simulation later
                price = candle.close # Use close price of signal candle
                amount = (self.portfolio.balance * 0.99) / price

                # Logic for initial SL/TP can be enriched here
                # Example: SL = 2% below, TP = 4% above
                sl = price * 0.98

                self.portfolio.open_position(
                    self.symbol, price, amount,
                    time=candle.timestamp,
                    reason=signal.reason,
                    sl=sl
                )

        elif signal.signal_type == 'SELL':
            self.portfolio.close_position(
                self.symbol, candle.close, candle.timestamp, reason=signal.reason
            )
