"""
Backtest Engine (NO COOLDOWN / NO WAITING / NO SL LOCK)
=======================================================
Runs strategy on historical data.

Key:
- SL limit fills happen inside MockExchange.update_price()
- We must sync those fills into PortfolioManager and StrategyContext.
"""
import pandas as pd
from decimal import Decimal
from app.services.market_data.store import MarketDataStore
from app.core.events import Candle
from app.core.portfolio import PortfolioManager
from app.backtest.mock_exchange import MockExchange
from app.core.context import SCANNING


class BacktestEngine:
    def __init__(self, data_path: str, strategy_class, config: dict):
        self.data = pd.read_csv(data_path)
        self.data["timestamp"] = pd.to_datetime(self.data["timestamp"])
        self.config = config
        self.symbol = config["symbols"][0]
        self.store = MarketDataStore()

        initial_balance = config.get("backtest", {}).get("initial_balance", 1000.0)
        self.exchange = MockExchange(initial_balance=initial_balance)
        self.portfolio = PortfolioManager(self.exchange, config)
        self.strategy = strategy_class(config)

        self._last_trade_count = 0

    def _sync_exchange_fills(self) -> None:
        trades = self.exchange.trade_history
        while self._last_trade_count < len(trades):
            trade = trades[self._last_trade_count]
            self._last_trade_count += 1

            # Sync portfolio
            self.portfolio.on_fill(trade)

            # Sync strategy context (remove active trade on exchange SELL)
            symbol = trade.get("symbol")
            side = trade.get("side")
            now_ts = trade.get("time")

            if not symbol or not side:
                continue

            if side == "SELL" and hasattr(self.strategy, "context") and self.strategy.context:
                ctx = self.strategy.context
                tf = getattr(self.strategy, "timeframe", "")
                key = f"{symbol}:{tf}" if tf else f"{symbol}:"

                ctx.close_trade(symbol)
                ctx.transition(key, SCANNING, reason="Exchange SELL fill", now_ts=now_ts)

    def run(self) -> None:
        print(f"Starting backtest on {self.symbol} with {len(self.data)} candles...")
        print(f"Initial balance: {self.exchange.get_balance()}")

        warmup_period = 220

        for i, row in self.data.iterrows():
            candle = Candle(
                symbol=self.symbol,
                timestamp=row["timestamp"],
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row["volume"])),
                closed=True,
            )

            self.store.update_candle(candle)

            # Update price (may fill SL)
            self.exchange.update_price(self.symbol, candle.close, candle.timestamp)
            self.portfolio.sync_from_exchange()

            if i < warmup_period:
                continue

            df = self.store.get_dataframe(self.symbol)
            signal = self.strategy.analyze(self.symbol, df)

            if signal:
                self.portfolio.on_signal(signal)

        print("\nBacktest complete!")
        print(f"Final balance: {self.exchange.get_balance()}")
        print(f"Open positions: {self.exchange.positions}")
        print(f"Total trades: {len(self.exchange.trade_history)}")
