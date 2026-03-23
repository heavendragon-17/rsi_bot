"""
Quick test to verify lock_profit_price is passed correctly from SignalEvent to Position.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from decimal import Decimal

from app.backtest.exchange.mock_exchange import MockExchange
from app.core.events import SignalEvent
from app.trading.portfolio.manager import PortfolioManager


def test_lock_profit_price():
    """Test that lock_profit_price flows from BUY signal to Position."""
    config = {
        "risk": {
            "leverage": 10,
            "risk_per_trade_pct": 0.02,
            "use_risk_based_sizing": True,
            "tp1_close_pct": 0.50,
            "tp2_close_pct": 0.50,
        },
        "backtest": {"initial_balance": 10000},
    }

    exchange = MockExchange(initial_balance=10000, leverage=10)
    portfolio = PortfolioManager(exchange, config)

    symbol = "DOGE/USDT"
    entry_price = Decimal("0.15244")
    soft_sl_price = Decimal("0.14744")  # ~3.3% below entry
    disaster_sl_price = Decimal("0.14244")  # Further below

    # Calculate 0.2R lock profit price manually
    risk = entry_price - soft_sl_price  # 0.005
    lock_profit_price = entry_price + (risk * Decimal("0.2"))  # 0.15244 + 0.001 = 0.15344

    tp1_price = entry_price + (risk * Decimal("1.0"))  # 0.15744

    print(f"Entry: {entry_price}")
    print(f"Soft SL: {soft_sl_price}")
    print(f"Risk: {risk}")
    print(f"Lock Profit Price (0.2R): {lock_profit_price}")
    print(f"TP1 (1R): {tp1_price}")
    print()

    # Set up mock price
    exchange.update_candle(symbol, entry_price, entry_price, entry_price, entry_price, datetime.now())

    # Create BUY signal with all the prices
    signal = SignalEvent(
        symbol=symbol,
        signal_type="BUY",
        price=entry_price,
        timestamp=datetime.now(),
        reason="TEST BUY",
        tp1_price=tp1_price,
        tp2_price=None,
        tp3_price=None,
        sl_price=disaster_sl_price,
        soft_sl_price=soft_sl_price,
        lock_profit_price=lock_profit_price,
    )

    # Process the BUY signal
    portfolio.on_signal(signal)

    # Check if Position was created with lock_profit_price
    pos = portfolio.get_position(symbol)
    if pos is None:
        print("ERROR: Position was not created!")
        return False

    print("Position created:")
    print(f"  amount: {pos.amount}")
    print(f"  entry_price: {pos.entry_price}")
    print(f"  lock_profit_price: {pos.lock_profit_price}")
    print(f"  sl_price: {pos.sl_price}")
    print()

    if pos.lock_profit_price is None:
        print("ERROR: lock_profit_price is None in Position!")
        return False

    if pos.lock_profit_price != lock_profit_price:
        print(f"ERROR: lock_profit_price mismatch! Expected {lock_profit_price}, got {pos.lock_profit_price}")
        return False

    print("SUCCESS: lock_profit_price is correctly stored in Position!")
    return True


if __name__ == "__main__":
    success = test_lock_profit_price()
    sys.exit(0 if success else 1)
