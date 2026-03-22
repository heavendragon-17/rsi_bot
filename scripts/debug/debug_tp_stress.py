"""
Debug Stress Test for TP Behavior
Focuses on:
1. TP1 trigger mechanisms.
2. Allocations logic (Dynamic vs Default).
3. Precision issues with partial amounts.
4. "Weird" scenarios (TP1 hitting multiple times, skipping TPs, etc.)
"""

import logging
import os
import sys
import unittest
from datetime import datetime
from decimal import Decimal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.backtest.mock_exchange import MockExchange
from app.core.events import SignalEvent
from app.trading.portfolio.manager import PortfolioManager

# Configure logging to stdout
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")


class TestTPBehavior(unittest.TestCase):
    def setUp(self):
        self.config = {
            "risk": {
                "tp1_close_pct": 0.5,
                "tp2_close_pct": 0.5,
                "leverage": 1,
            },
            "backtest": {"initial_balance": 1000},
            "symbols": ["BTC/USDT"],
        }
        self.exchange = MockExchange()
        self.pm = PortfolioManager(self.exchange, self.config)

        # Setup Balance
        self.exchange.fetch_balance = lambda: {"total": {"USDT": 1000}}
        self.exchange.update_candle(
            "BTC/USDT", Decimal("100"), Decimal("100"), Decimal("100"), Decimal("100"), datetime.now()
        )

    def create_position(self, allocations=None):
        """Helper to create a standard position"""
        signal = SignalEvent(
            symbol="BTC/USDT",
            signal_type="BUY",
            price=Decimal("100"),
            timestamp=datetime.now(),
            sl_price=Decimal("90"),
            tp_allocations=allocations,
        )
        self.pm.on_signal(signal)
        return self.pm.positions["BTC/USDT"]

    def test_default_tp1_behavior(self):
        """Normal case: Default config (50%), clean numbers."""
        print("\n--- Test Default TP1 ---")
        pos = self.create_position(allocations=None)  # Use defaults
        initial_amount = pos.amount
        print(f"Initial Amount: {initial_amount}")

        # Trigger TP1
        signal = SignalEvent(
            symbol="BTC/USDT",
            signal_type="SELL",
            price=Decimal("110"),
            reason="TP1 hit",
            timestamp=datetime.now(),
            sl_price=Decimal("100"),
        )
        self.pm.on_signal(signal)

        # Expect 50% closed
        pos = self.pm.positions.get("BTC/USDT")
        print(f"Remaining Amount: {pos.amount}")
        self.assertAlmostEqual(pos.amount, initial_amount * Decimal("0.5"))
        self.assertTrue(pos.tp1_hit)

    def test_dynamic_tp1_100_percent(self):
        """Case: TP1 closes 100% (tp_count=1 style)."""
        print("\n--- Test Dynamic TP1 100% ---")
        allocs = {"TP1": 1.0}
        self.create_position(allocations=allocs)

        signal = SignalEvent(
            symbol="BTC/USDT",
            signal_type="SELL",
            price=Decimal("110"),
            reason="TP1 hit",
            timestamp=datetime.now(),
            sl_price=Decimal("100"),
        )
        self.pm.on_signal(signal)

        # Expect 0 remaining (position removed)
        self.assertNotIn("BTC/USDT", self.pm.positions)
        print("Position closed completely at TP1.")

    def test_weird_precision_behavior(self):
        """Case: Weird amounts creating dust or infinite decimals."""
        print("\n--- Test Precision / Dust ---")
        # Force a weird amount size via mock exchange logic if possible,
        # but here we just rely on price/risk.
        # Entry 0.12345, SL 0.12000. Risk 0.00345. 2% of 1000 = $20 risk.
        # Size = 20 / 0.00345 = 5797.101449...

        self.exchange.update_candle(
            "BTC/USDT", Decimal("0.12345"), Decimal("0.12345"), Decimal("0.12345"), Decimal("0.12345"), datetime.now()
        )

        signal = SignalEvent(
            symbol="BTC/USDT",
            signal_type="BUY",
            price=Decimal("0.12345"),
            timestamp=datetime.now(),
            sl_price=Decimal("0.12000"),
            tp_allocations={"TP1": 0.3333},  # Weird allocation
        )
        self.pm.on_signal(signal)
        pos = self.pm.positions["BTC/USDT"]
        initial_amt = pos.amount
        print(f"Initial Weird Amount: {initial_amt}")

        # Trigger TP1
        signal = SignalEvent(
            symbol="BTC/USDT",
            signal_type="SELL",
            price=Decimal("0.13000"),
            reason="TP1 hit",
            timestamp=datetime.now(),
            sl_price=Decimal("0.12345"),
        )
        self.pm.on_signal(signal)

        pos = self.pm.positions.get("BTC/USDT")
        print(f"Remaining Amount after 0.3333 close: {pos.amount}")

        expected_close = initial_amt * Decimal("0.3333")
        expected_remain = initial_amt - expected_close

        # Portfolio uses whatever exchange returns, but for mock it subtracts exactly
        self.assertEqual(pos.amount, expected_remain)

    def test_tp1_retrigger_prevention(self):
        """Case: Signal firing TP1 multiple times (e.g. from multiple candles)."""
        print("\n--- Test Retrigger Prevention ---")
        pos = self.create_position()
        initial_amt = pos.amount

        # Trigger TP1 Once
        signal = SignalEvent(
            symbol="BTC/USDT",
            signal_type="SELL",
            price=Decimal("110"),
            reason="TP1 hit",
            timestamp=datetime.now(),
            sl_price=Decimal("100"),
        )
        self.pm.on_signal(signal)
        remaining = self.pm.positions["BTC/USDT"].amount
        self.assertLess(remaining, initial_amt)

        # Trigger TP1 AGAIN (Simulate strategy sending it again)
        self.pm.on_signal(signal)

        # Should stay same
        current = self.pm.positions["BTC/USDT"].amount
        self.assertEqual(current, remaining, "TP1 should not execute twice on same position")
        print("Double trigger prevented.")

    def test_missing_config_fallback(self):
        """Case: tp_allocations missing AND default config missing (should raise or weird?)."""
        print("\n--- Test Config Fallback ---")
        # Remove defaults from PM
        self.pm.tp1_close_pct = "0.5"  # Defaults are strings or decimals? usually numbers in yaml

        self.create_position(allocations={})  # Empty allocs

        pos = self.pm.positions["BTC/USDT"]
        pos.tp_allocations = None  # Force None

        signal = SignalEvent(
            symbol="BTC/USDT",
            signal_type="SELL",
            price=Decimal("110"),
            reason="TP1 hit",
            timestamp=datetime.now(),
            sl_price=Decimal("100"),
        )
        self.pm.on_signal(signal)

        pos = self.pm.positions["BTC/USDT"]
        # Should use self.tp1_close_pct (0.5)
        self.assertTrue(pos.tp1_hit)
        print("Fallback worked.")


if __name__ == "__main__":
    unittest.main()
