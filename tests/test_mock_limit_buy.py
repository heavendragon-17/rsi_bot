import unittest
from decimal import Decimal
from app.backtest.mock_exchange import MockExchange

class TestMockExchangeLimitBuy(unittest.TestCase):
    def test_limit_buy_trigger(self):
        # 10000 Balance
        exchange = MockExchange(initial_balance=10000)
        symbol = "BTC/USDT"

        # Place Limit Buy at 50000
        # Current price doesn't matter for placement, but let's say it's 51000
        exchange.current_prices[symbol] = {"price": Decimal("51000"), "time": 0}

        # 0.1 BTC * 50000 = 5000 USDT. Covered by 10000.
        order = exchange.create_order(
            symbol=symbol,
            type="LIMIT",
            side="BUY",
            amount=0.1,
            price=50000
        )
        self.assertEqual(order["status"], "open")
        self.assertIn(order["id"], exchange.pending_orders)

        # 1. Update candle where Low > Limit (50000). Should NOT trigger.
        # OHLC: 51000, 51500, 50500, 51000
        executed = exchange.update_candle(symbol, 51000, 51500, 50500, 51000, 1)
        self.assertEqual(len(executed), 0)
        self.assertEqual(exchange.pending_orders[order["id"]]["status"], "open")

        # 2. Update candle where Low <= Limit (50000). Should trigger.
        # OHLC: 50500, 50500, 49000, 50000
        executed = exchange.update_candle(symbol, 50500, 50500, 49000, 50000, 2)
        self.assertEqual(len(executed), 1)
        self.assertEqual(executed[0]["id"], order["id"])
        self.assertEqual(executed[0]["status"], "closed")
        self.assertNotIn(order["id"], exchange.pending_orders)

        # Check position
        positions = exchange.fetch_positions()
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["symbol"], symbol)
        self.assertEqual(positions[0]["contracts"], 0.1)

    def test_fetch_order(self):
        exchange = MockExchange(initial_balance=10000)
        # Initialize price
        exchange.current_prices["BTC/USDT"] = {"price": Decimal("51000"), "time": 0}

        order = exchange.create_order("BTC/USDT", "LIMIT", "BUY", 0.1, 50000)

        # Fetch pending
        fetched = exchange.fetch_order(order["id"], "BTC/USDT")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["id"], order["id"])
        self.assertEqual(fetched["status"], "open")

        # Execute
        exchange.update_candle("BTC/USDT", 50000, 50000, 49000, 50000, 1)

        # Fetch closed
        fetched = exchange.fetch_order(order["id"], "BTC/USDT")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["status"], "closed")

        # Fetch non-existent
        self.assertIsNone(exchange.fetch_order("invalid", "BTC/USDT"))

if __name__ == '__main__':
    unittest.main()
