"""
Backtest Engine
================
Runs strategy on historical data with Decimal support.

IMPORTANT:
- SL limit orders can be executed inside MockExchange without creating a SignalEvent.
- Therefore we must "sync fills" from exchange -> portfolio to clear positions correctly.
"""
import pandas as pd
from decimal import Decimal
from app.services.market_data.store import MarketDataStore
from app.core.events import Candle
from app.core.portfolio import PortfolioManager
from app.backtest.mock_exchange import MockExchange
from app.core.context import SCANNING

class BacktestEngine:
    """Engine to run backtests on historical data."""

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

        # Track fills that happen inside exchange (SL pending orders)
        self._last_trade_count = 0

    def _sync_exchange_fills(self) -> None:
        """
        Sync fills that happen inside exchange (SL limit fills, etc.)

        Why:
        - MockExchange executes SL internally (pending order) -> Portfolio position is closed,
            but strategy context may still think trade is active -> it can emit SELL later.
        - This keeps Portfolio + StrategyContext consistent with Exchange.
        """
        trades = self.exchange.trade_history
        while self._last_trade_count < len(trades):
            trade = trades[self._last_trade_count]
            self._last_trade_count += 1

            # 1) Sync Portfolio (removes self.positions[symbol] on SELL)
            self.portfolio.on_fill(trade)

            symbol = trade.get("symbol")
            side = trade.get("side")
            now_ts = trade.get("time")  # datetime from MockExchange

            if not symbol or not side:
                continue

            # 2) Sync StrategyContext when exchange closes a position
            if side == "SELL" and hasattr(self.strategy, "context") and self.strategy.context:
                ctx = self.strategy.context

                # Build the same key as strategy uses
                tf = getattr(self.strategy, "timeframe", "")
                key = f"{symbol}:{tf}" if tf else f"{symbol}:"

                # Stop tracking this trade inside strategy immediately
                ctx.close_trade(symbol)

                # Exit WAITING (if any) and reset state machine
                ctx.clear_waiting(key, now_ts=now_ts)
                ctx.transition(key, SCANNING, reason="Exchange SELL fill (SL/TP)", now_ts=now_ts)

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

            # Update exchange price (this may trigger pending SL orders)
            self.exchange.update_price(self.symbol, candle.close, candle.timestamp)

            # IMPORTANT: sync fills after update_price
            self._sync_exchange_fills()

            if i < warmup_period:
                continue

            df = self.store.get_dataframe(self.symbol)
            signal = self.strategy.analyze(self.symbol, df)

            if signal:
                self.portfolio.on_signal(signal)

                # In case orders executed immediately (market orders)
                self._sync_exchange_fills()

        print("\nBacktest complete!")
        print(f"Final balance: {self.exchange.get_balance()}")
        print(f"Open positions: {self.exchange.positions}")
        print(f"Total trades: {len(self.exchange.trade_history)}")
            