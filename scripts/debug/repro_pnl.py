"""
Reproduction script for PnL Discrepancy (DOGE case).
User reports $93.97 profit where $120 ($100+$20) was expected.
Hypothesis: Fees or execution price mismatch.
"""

import os
import sys
from datetime import datetime
from decimal import Decimal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.backtest.exchange.mock_exchange import MockExchange
from app.core.events import SignalEvent
from app.trading.portfolio.manager import PortfolioManager


def test_pnl_calculation():
    print("--- Simulating DOGE Trade ---")

    # 1. Setup
    # Guessing config based on $200 risk per trade
    config = {
        "risk": {
            "risk_per_trade_pct": 0.02,  # 2% risk
            "leverage": 1,
            "tp1_close_pct": 0.5,
        },
        "backtest": {"initial_balance": 10000},
        "bot": {"timeframe": "15m"},
    }

    exchange = MockExchange(initial_balance=10000, maker_fee=0.001, taker_fee=0.001)  # Standard 0.1% fees?
    pm = PortfolioManager(exchange, config)

    # User Data
    # Entry: 0.171920
    entry_price = Decimal("0.171920")

    # We need SL to calculate Risk Amount.
    # User didn't give SL. But said "max loss is 200".
    # And "tp half at 1R".
    # IF TP1 is at 1R... we assume TP1 filled at some price.
    # But let's reverse engineer Position Size first.
    # Risk Amount = $200.
    # Size * (Entry - SL) = 200.
    # Size * R_dist = 200.
    # Size = 200 / R_dist.

    # User said expected profit is 120.
    # TP1 Profit (1R) = 0.5 * Size * R_dist = 0.5 * 200 = 100. (Correct).
    # Lock Profit (0.2R) = 0.5 * Size * 0.2 * R_dist = 0.5 * 200 * 0.2 = 20. (Correct).

    # So any SL distance works for the math, as long as Size scales.
    # Let's pick an arbitrary SL distance, say 1%.
    sl_price = entry_price * Decimal("0.99")
    r_dist = entry_price - sl_price

    # TP1 Price = Entry + R
    tp1_price = entry_price + r_dist
    # Profit Lock = Entry + 0.2R
    lock_price = entry_price + (r_dist * Decimal("0.2"))

    print(f"Entry: {entry_price}")
    print(f"SL: {sl_price}")
    print(f"TP1: {tp1_price}")
    print(f"Lock: {lock_price}")

    # Seed Exchange
    exchange.update_candle("DOGE/USDT", entry_price, entry_price, entry_price, entry_price, datetime.now())

    # 2. Execute BUY
    buy_signal = SignalEvent(
        symbol="DOGE/USDT",
        signal_type="BUY",
        price=entry_price,
        timestamp=datetime.now(),
        sl_price=sl_price,
        tp1_price=tp1_price,
        lock_profit_price=lock_price,
        tp_allocations={"TP1": 0.5},
    )
    pm.on_signal(buy_signal)

    pos = pm.positions["DOGE/USDT"]
    print(f"Position Size: {pos.amount}")

    # 3. Execute TP1
    # Trigger TP1
    tp1_signal = SignalEvent(
        symbol="DOGE/USDT",
        signal_type="SELL",
        price=tp1_price,
        reason="TP1 hit",
        timestamp=datetime.now(),
        sl_price=lock_price,  # Move SL
    )
    pm.on_signal(tp1_signal)

    # 4. Execute Lock Profit hit
    # Simulate price drop to Lock Price
    # Exchange executes SL Limit/Stop
    exchange.update_candle("DOGE/USDT", lock_price, lock_price, lock_price, lock_price, datetime.now())

    # 5. Analyze Results
    history = exchange.trade_history
    print(f"\nTrade History ({len(history)} trades):")

    total_pnl = 0
    total_fee = 0

    for t in history:
        print(
            f"Type: {t['type']}, Side: {t['side']}, Amt: {t['amount']}, Price: {t['price']}, PnL: {t['pnl']}, Fee: {t.get('fee', {}).get('cost', 0)}"
        )
        if t["pnl"]:
            total_pnl += t["pnl"]
        if t["fee"]:
            total_fee += t["fee"]["cost"]

    print(f"\nTotal Gross PnL: {total_pnl}")
    print(f"Total Fees: {total_fee}")
    print(f"Net PnL: {total_pnl - total_fee}")

    print("\nUser Reported: ~$93.97")


if __name__ == "__main__":
    test_pnl_calculation()
