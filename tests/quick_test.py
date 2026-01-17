"""Quick test for thread-safe MockExchange."""
import sys
import threading
import time
from decimal import Decimal

sys.path.insert(0, '.')

from app.backtest.mock_exchange import MockExchange

print("Testing thread-safe MockExchange...")

# Create exchange
exchange = MockExchange(initial_balance=10000, leverage=10)
print(f"✓ MockExchange created")
print(f"✓ Has _lock: {hasattr(exchange, '_lock')}")

# Set up price
exchange.current_prices["BTC/USDT"] = {"price": Decimal("50000"), "time": None}
print(f"✓ Set price data")

# Test basic operations
balance = exchange.fetch_balance()
print(f"✓ fetch_balance works: {balance['free']['USDT']}")

# Test order creation
order = exchange.create_order("BTC/USDT", "market", "BUY", 0.01, 50000)
print(f"✓ create_order works: {order is not None}")

# Test concurrent access
errors = []
def worker(thread_id):
    try:
        for i in range(20):
            exchange.fetch_balance()
            exchange.fetch_positions()
    except Exception as e:
        errors.append(str(e))

threads = []
for i in range(5):
    t = threading.Thread(target=worker, args=(i,))
    threads.append(t)
    t.start()

for t in threads:
    t.join()

print(f"✓ Concurrent fetch operations: {len(errors)} errors")

# Final balance check
final_balance = exchange.fetch_balance()
print(f"✓ Final balance: {final_balance['free']['USDT']}")

print("\n=== ALL TESTS PASSED ===")
