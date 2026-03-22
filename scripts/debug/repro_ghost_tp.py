"""
Reproduction of 'Ghost TP' Issue.
Demonstrates that if Strategy updates state BEFORE confirmation, a failed order results in missed TP.
"""

import os
import sys
from decimal import Decimal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Mock Strategy Logic (simplified from rsi_no_retest.py)
class MockStrategy:
    def __init__(self):
        self.meta = {"tp1_price": Decimal("110"), "tp1_hit": False}

    def on_candle(self, high_price):
        """Simulate analyze() method"""
        if not self.meta["tp1_hit"] and high_price >= self.meta["tp1_price"]:
            # ISSUE: Optimistic Update
            # self.meta["tp1_hit"] = True  <-- FIX: Removed
            return "SIGNAL_TP1"
        return None


# Mock Portfolio
class MockPortfolio:
    def __init__(self):
        self.tp1_executed = False
        self.simulate_failure = True

    def on_signal(self, signal):
        if signal == "SIGNAL_TP1":
            if self.simulate_failure:
                print("Portfolio: Order Failed (Network/API Error)")
                return False
            self.tp1_executed = True
            print("Portfolio: Order Executed")
            return True
        return False


def test_ghost_tp():
    strat = MockStrategy()
    port = MockPortfolio()

    # 1. Price hits TP1
    print("Candle High: 112 (TP1: 110)")
    signal = strat.on_candle(Decimal("112"))
    print(f"Strategy Signal: {signal}")

    # 2. Portfolio attempts exe but fails
    if signal:
        port.on_signal(signal)

    # 3. Next Candle (Price still high)
    print("\nCandle High: 115")
    signal_retry = strat.on_candle(Decimal("115"))
    print(f"Strategy Signal: {signal_retry}")

    if signal_retry:
        port.on_signal(signal_retry)
    else:
        print("Strategy: Silent (Thought it already hit)")

    # Result check
    if not port.tp1_executed:
        print("\nRESULT: TP1 Missed forever! (Ghost TP)")
        return False
    return True


if __name__ == "__main__":
    test_ghost_tp()
