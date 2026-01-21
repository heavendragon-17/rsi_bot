
import unittest
import sys
import os
from decimal import Decimal
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.getcwd())

from app.backtest.mock_exchange import MockExchange

class TestSoftSLMock(unittest.TestCase):
    def setUp(self):
        self.exchange = MockExchange()
        self.symbol = "BTC/USDT"
        self.exchange.positions[self.symbol] = Decimal("1.0")
        self.exchange.entry_prices[self.symbol] = Decimal("10000")
        self.exchange.entry_times[self.symbol] = datetime.now()
        # Seed current price data so create_order works
        self.exchange.current_prices[self.symbol] = {
            "price": Decimal("10000"),
            "time": datetime.now()
        }

    def test_soft_sl_wick_ignore(self):
        """
        Test that Soft SL is NOT triggered by a Wick if Close is safe.
        """
        # Place Soft SL at 9500
        order = self.exchange.create_order(
            symbol=self.symbol,
            type="limit", # Must use limit for MockExchange to treat as pending via create_order
            side="SELL",
            amount=Decimal("1.0"),
            price=Decimal("9500"),
            params={"is_soft_sl": True}
        )

        # Candle: Low 9000 (below SL), but Close 9600 (above SL)
        # Should NOT trigger
        self.exchange.update_candle(
            symbol=self.symbol,
            open_=10000,
            high=10000,
            low=9000,
            close=9600,
            timestamp=datetime.now()
        )

        # Verify order is still open
        pending = self.exchange.pending_orders.get(order["id"])
        self.assertIsNotNone(pending, "Soft SL should remain open (wick ignored)")

    def test_soft_sl_close_trigger(self):
        """
        Test that Soft SL IS triggered by Close, and fills at Close price.
        """
        # Place Soft SL at 9500
        order = self.exchange.create_order(
            symbol=self.symbol,
            type="limit",
            side="SELL",
            amount=Decimal("1.0"),
            price=Decimal("9500"),
            params={"is_soft_sl": True}
        )

        # Candle: Low 9000, Close 9400 (both below SL)
        # Should trigger on Close
        executed = self.exchange.update_candle(
            symbol=self.symbol,
            open_=10000,
            high=10000,
            low=9000,
            close=9400,
            timestamp=datetime.now()
        )

        # Verify order executed
        self.assertEqual(len(executed), 1, "Soft SL should trigger")
        filled_order = executed[0]

        # Verify fill price is Close Price (9400), not Trigger Price (9500)
        self.assertEqual(filled_order["price"], 9400.0, "Soft SL should fill at Close Price")

    def test_disaster_sl_wick_trigger(self):
        """
        Test that Disaster SL (no flag) IS triggered by Wick.
        """
        # Place Disaster SL at 8000
        order = self.exchange.create_order(
            symbol=self.symbol,
            type="limit",
            side="SELL",
            amount=Decimal("1.0"),
            price=Decimal("8000"),
            params={} # No flag
        )

        # Candle: Low 7000 (below SL), Close 9000 (above SL)
        # Should trigger immediately on Wick
        executed = self.exchange.update_candle(
            symbol=self.symbol,
            open_=10000,
            high=10000,
            low=7000,
            close=9000,
            timestamp=datetime.now()
        )

        # Verify order executed
        self.assertEqual(len(executed), 1, "Disaster SL should trigger on Wick")
        filled_order = executed[0]

        # Verify fill price is Trigger Price (8000), not Close (9000) or Low (7000)
        # MockExchange normally fills Limit orders at limit price if gap is crossed?
        # Actually MockExchange logic: fill_price = trigger_price.
        self.assertEqual(filled_order["price"], 8000.0, "Disaster SL should fill at Trigger Price")

if __name__ == '__main__':
    unittest.main()
