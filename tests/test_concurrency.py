"""
Test Concurrency for MockExchange
=================================
Validates that MockExchange is thread-safe by spawning multiple threads
that concurrently place orders for different symbols.
"""
import pytest
import threading
import random
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.backtest.mock_exchange import MockExchange


class TestMockExchangeThreadSafety:
    """Test thread safety of MockExchange."""

    def test_concurrent_order_placement(self):
        """
        Spawn 10 threads, each placing random buy/sell orders.
        Assert no race conditions occur (no exceptions, balance consistent).
        """
        exchange = MockExchange(initial_balance=100000.0, leverage=10)
        symbols = [f"TOKEN{i}/USDT" for i in range(10)]
        
        # Initialize prices for all symbols
        for sym in symbols:
            exchange.update_candle(sym, 100.0, 100.0, 100.0, 100.0, None)
        
        errors = []
        completed_orders = []
        lock = threading.Lock()
        
        def worker(symbol: str, iterations: int):
            """Worker that places buy/sell orders for a symbol."""
            for _ in range(iterations):
                try:
                    # Random price movement
                    price = 100.0 + random.uniform(-10, 10)
                    exchange.update_candle(symbol, price, price + 1, price - 1, price, None)
                    
                    # Place a small buy order
                    amount = random.uniform(0.1, 1.0)
                    order = exchange.create_order(
                        symbol=symbol,
                        order_type="market",
                        side="BUY",
                        amount=amount,
                        price=price
                    )
                    if order:
                        with lock:
                            completed_orders.append(order)
                    
                    # Immediately sell some
                    pos = exchange.positions.get(symbol, Decimal("0"))
                    if pos > 0:
                        sell_amt = min(float(pos), amount * 0.5)
                        sell_order = exchange.create_order(
                            symbol=symbol,
                            order_type="market",
                            side="SELL",
                            amount=sell_amt,
                            price=price
                        )
                        if sell_order:
                            with lock:
                                completed_orders.append(sell_order)
                
                except Exception as e:
                    with lock:
                        errors.append((symbol, str(e)))
        
        # Run workers in parallel
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(worker, sym, 20)
                for sym in symbols
            ]
            # Wait for all to complete
            for f in as_completed(futures):
                pass
        
        # Assertions
        assert len(errors) == 0, f"Errors occurred: {errors[:5]}"
        assert len(completed_orders) > 0, "No orders were completed"
        
        # Balance should be non-negative
        balance = exchange.fetch_balance()
        total_balance = balance.get("total", {}).get("USDT", 0)
        assert float(total_balance) >= 0, f"Negative balance: {total_balance}"
        
        print(f"✓ {len(completed_orders)} orders completed")
        print(f"✓ Final balance: {total_balance}")

    def test_concurrent_sl_updates(self):
        """Test that SL updates don't cause race conditions."""
        exchange = MockExchange(initial_balance=10000.0, leverage=5)
        symbol = "BTC/USDT"
        
        # Setup position
        exchange.update_candle(symbol, 50000, 50100, 49900, 50000, None)
        exchange.create_order(symbol, order_type="market", side="BUY", amount=0.1, price=50000)
        exchange.create_order(
            symbol, order_type="stop_market", side="SELL", amount=Decimal("0.1"),
            params={"stopPrice": Decimal("49000"), "reduceOnly": True},
        )
        
        errors = []
        
        def update_sl():
            for _ in range(50):
                try:
                    new_sl = 49000 + random.uniform(-500, 500)
                    exchange.update_stop_loss(symbol, new_sl)
                except Exception as e:
                    errors.append(str(e))
        
        threads = [threading.Thread(target=update_sl) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"SL update errors: {errors[:3]}"
        print("✓ Concurrent SL updates passed")


if __name__ == "__main__":
    # Run tests directly
    test = TestMockExchangeThreadSafety()
    test.test_concurrent_order_placement()
    test.test_concurrent_sl_updates()
    print("\n✓ All concurrency tests passed!")
