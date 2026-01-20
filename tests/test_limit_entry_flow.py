import unittest
import time
from decimal import Decimal
from datetime import datetime, timedelta
from app.core.portfolio import PortfolioManager
from app.backtest.mock_exchange import MockExchange
from app.core.events import SignalEvent

class TestLimitEntryFlow(unittest.TestCase):
    def setUp(self):
        self.exchange = MockExchange(initial_balance=10000)
        self.config = {
            "entry_mode": "LIMIT",
            "timeframe": "15m",
            "risk": {
                "max_position_size_pct": 1.0,
                "risk_per_trade_pct": 0.1,
                "leverage": 1
            },
            "backtest": {"initial_balance": 10000}
        }
        self.pm = PortfolioManager(self.exchange, self.config)
        self.symbol = "BTC/USDT"
        self.exchange.current_prices[self.symbol] = {"price": Decimal("50000"), "time": datetime.now()}

    def test_limit_entry_placement(self):
        signal = SignalEvent(
            timestamp=datetime.now(),
            symbol=self.symbol,
            signal_type="BUY",
            price=Decimal("49000"), # Below market
            sl_price=Decimal("48000"),
            reason="TEST"
        )

        # 1. Handle Signal
        order = self.pm.on_signal(signal)
        self.assertIsNotNone(order)
        self.assertEqual(order["type"], "limit")
        self.assertEqual(float(order["price"]), 49000.0)
        self.assertTrue(self.pm.has_pending_entry(self.symbol))

        # 2. Check Pending Entry (Immediate check)
        # Should be open
        self.pm.check_pending_entry(self.symbol, signal.timestamp)
        self.assertTrue(self.pm.has_pending_entry(self.symbol))

    def test_limit_entry_timeout(self):
        start_ts = datetime.now()
        signal = SignalEvent(
            timestamp=start_ts,
            symbol=self.symbol,
            signal_type="BUY",
            price=Decimal("49000"),
            sl_price=Decimal("48000"),
            reason="TEST"
        )

        self.pm.on_signal(signal)

        # Advance 4 candles (15m each) -> 60 mins. Less than 5 candles (which is check >= 5).
        # Wait, candles_elapsed = (curr - entry) / tf.
        # 4 candles later: elapsed = 4.

        curr_ts = start_ts + timedelta(minutes=60)
        self.pm.check_pending_entry(self.symbol, curr_ts)
        self.assertTrue(self.pm.has_pending_entry(self.symbol)) # Still pending

        # Advance 5 candles -> 75 mins
        curr_ts = start_ts + timedelta(minutes=75)
        self.pm.check_pending_entry(self.symbol, curr_ts)

        # Should be canceled and removed
        self.assertFalse(self.pm.has_pending_entry(self.symbol))

        # Verify order canceled in exchange
        self.assertEqual(len(self.exchange.pending_orders), 0)

    def test_limit_entry_fill(self):
        start_ts = datetime.now()
        # Market at 50000
        self.exchange.current_prices[self.symbol] = {"price": Decimal("50000"), "time": start_ts}

        signal = SignalEvent(
            timestamp=start_ts,
            symbol=self.symbol,
            signal_type="BUY",
            price=Decimal("49500"),
            sl_price=Decimal("48000"),
            reason="TEST"
        )

        order = self.pm.on_signal(signal)
        order_id = order["id"]

        # Update candle to trigger fill
        # Low drops to 49400
        next_ts = start_ts + timedelta(minutes=15)
        executed = self.exchange.update_candle(self.symbol, 50000, 50000, 49400, 49500, next_ts)

        self.assertEqual(len(executed), 1)
        self.assertEqual(executed[0]["id"], order_id)

        # Now check pending entry
        self.pm.check_pending_entry(self.symbol, next_ts)

        # Should be removed from pending and added to positions
        self.assertFalse(self.pm.has_pending_entry(self.symbol))
        self.assertTrue(self.pm.has_position(self.symbol))

        pos = self.pm.get_position(self.symbol)
        self.assertAlmostEqual(float(pos.amount), float(order["amount"]))

if __name__ == '__main__':
    unittest.main()
