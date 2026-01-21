
import unittest
import sys
import os
from decimal import Decimal
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from app.core.portfolio import PortfolioManager
from app.backtest.mock_exchange import MockExchange
from app.core.events import SignalEvent

class TestSLBehavior(unittest.TestCase):
    def setUp(self):
        self.config = {
            "risk": {
                "max_position_size_pct": 0.99,
                "risk_per_trade_pct": 0.02,
                "leverage": 1,
                "min_sl_distance_pct": 0.01,
            },
            "backtest": {"initial_balance": 10000}
        }
        self.exchange = MockExchange()
        self.portfolio = PortfolioManager(self.exchange, self.config)

        # Seed price
        self.symbol = "BTC/USDT"
        self.exchange.current_prices[self.symbol] = {
            "price": Decimal("10000"),
            "time": datetime.now()
        }

    def test_disaster_sl_trigger(self):
        """
        Verify that Disaster SL is placed on exchange and triggers on Wick.
        """
        entry_price = Decimal("10000")
        soft_sl_price = Decimal("9800")
        disaster_sl_price = Decimal("9400")

        signal = SignalEvent(
            symbol=self.symbol,
            signal_type="BUY",
            price=entry_price,
            timestamp=datetime.now(),
            sl_price=disaster_sl_price,
            soft_sl_price=soft_sl_price
        )

        # 1. Execute Buy
        self.portfolio.on_signal(signal)

        # Verify Position
        pos = self.portfolio.positions.get(self.symbol)
        self.assertIsNotNone(pos)
        self.assertIsNotNone(pos.sl_order_id, "Disaster SL ID missing")
        # Ensure Soft SL order is NOT placed
        self.assertFalse(hasattr(pos, 'soft_sl_order_id'), "Soft SL ID should not exist")

        # Verify only ONE pending order (Disaster SL)
        # Note: Depending on implementation, there might be other artifacts, but we check count
        # Pending orders: 1 (Disaster SL)
        pending_orders = self.exchange.pending_orders
        self.assertEqual(len(pending_orders), 1, "Only Disaster SL should be pending")

        # Verify Disaster SL Price
        order = list(pending_orders.values())[0]
        self.assertEqual(order["triggerPrice"], disaster_sl_price)

        # 2. Simulate Wick Trigger
        # Low=9300 < 9400.
        executed = self.exchange.update_candle(
            symbol=self.symbol,
            open_=10000,
            high=10000,
            low=9300,
            close=9700,
            timestamp=datetime.now()
        )

        # Verify Execution
        self.assertTrue(len(executed) > 0, "Disaster SL should trigger")
        self.assertEqual(executed[0]["price"], 9400.0)

    def test_soft_sl_strategy_exit(self):
        """
        Verify that if Strategy sends SELL signal (Soft SL hit),
        Portfolio closes position and cancels Disaster SL.
        """
        entry_price = Decimal("10000")
        soft_sl_price = Decimal("9800")
        disaster_sl_price = Decimal("9400")

        # 1. Open Position
        signal = SignalEvent(
            symbol=self.symbol,
            signal_type="BUY",
            price=entry_price,
            timestamp=datetime.now(),
            sl_price=disaster_sl_price,
            soft_sl_price=soft_sl_price
        )
        self.portfolio.on_signal(signal)

        pos = self.portfolio.positions.get(self.symbol)
        sl_id = pos.sl_order_id

        # Verify SL order exists
        self.assertIn(sl_id, self.exchange.pending_orders)

        # 2. Simulate Soft SL Hit (Strategy Logic would emit SELL)
        exit_signal = SignalEvent(
            symbol=self.symbol,
            signal_type="SELL",
            price=Decimal("9700"), # Triggered at Close
            timestamp=datetime.now(),
            reason="CLOSE_BY_CANDLE_SL"
        )

        # Execute Sell
        self.portfolio.on_signal(exit_signal)

        # 3. Verify Position Closed
        self.assertNotIn(self.symbol, self.portfolio.positions, "Position should be closed")

        # 4. Verify Disaster SL Canceled
        self.assertNotIn(sl_id, self.exchange.pending_orders, "Disaster SL should be canceled")

if __name__ == '__main__':
    unittest.main()
