# tests/test_concurrency.py
"""
Concurrency Tests for Thread-Safe MockExchange
===============================================
Tests to verify that MockExchange is thread-safe and can handle
concurrent order placements from multiple threads without race conditions.
"""
import pytest
import threading
import time
import random
from datetime import datetime
from decimal import Decimal

from app.backtest.mock_exchange import MockExchange


class TestMockExchangeThreadSafety:
    """Tests for thread-safe MockExchange operations."""
    
    def setup_method(self):
        """Set up test exchange with initial balance."""
        self.exchange = MockExchange(initial_balance=100000, leverage=10)
        
        # Set up price data for multiple symbols
        self.symbols = [f"SYM{i}/USDT" for i in range(10)]
        for symbol in self.symbols:
            self.exchange.current_prices[symbol] = {
                "price": Decimal("100"),
                "time": datetime.now()
            }
    
    def test_concurrent_order_placement(self):
        """
        Test that multiple threads can place orders concurrently
        without race conditions or negative balances.
        """
        num_threads = 10
        orders_per_thread = 50
        errors = []
        
        def place_orders(symbol: str, thread_id: int):
            """Place multiple buy/sell orders for a symbol."""
            try:
                for i in range(orders_per_thread):
                    # Buy small amounts
                    result = self.exchange.create_order(
                        symbol=symbol,
                        type='market',
                        side='BUY',
                        amount=0.1,
                        price=100
                    )
                    
                    if result:
                        # Immediately sell what we bought
                        self.exchange.create_order(
                            symbol=symbol,
                            type='market',
                            side='SELL',
                            amount=0.1,
                            price=100
                        )
                    
                    # Small random delay to increase contention
                    time.sleep(random.uniform(0, 0.001))
                    
            except Exception as e:
                errors.append((thread_id, str(e)))
        
        # Start threads
        threads = []
        for i, symbol in enumerate(self.symbols):
            t = threading.Thread(target=place_orders, args=(symbol, i))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join(timeout=30)
        
        # Verify no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"
        
        # Verify balance is non-negative
        balance = self.exchange.fetch_balance()
        usdt_balance = balance['free']['USDT']
        assert usdt_balance >= 0, f"Balance went negative: {usdt_balance}"
        
    def test_concurrent_fetch_operations(self):
        """
        Test that fetch operations are thread-safe and return
        consistent copies of data.
        """
        num_threads = 20
        results = []
        
        # First, create some positions
        for symbol in self.symbols[:3]:
            self.exchange.create_order(
                symbol=symbol,
                type='market',
                side='BUY',
                amount=1.0,
                price=100
            )
        
        def fetch_data(thread_id: int):
            """Fetch balance and positions repeatedly."""
            for _ in range(100):
                balance = self.exchange.fetch_balance()
                positions = self.exchange.fetch_positions()
                
                # Store results for verification
                results.append({
                    'thread_id': thread_id,
                    'balance': balance,
                    'positions': positions
                })
                
        # Start threads
        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=fetch_data, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join(timeout=30)
        
        # Verify all results are valid
        assert len(results) == num_threads * 100
        for r in results:
            assert 'USDT' in r['balance']['free']
            assert isinstance(r['positions'], list)
    
    def test_concurrent_stop_loss_updates(self):
        """
        Test that SL updates are thread-safe and don't corrupt order data.
        """
        symbol = "BTC/USDT"
        self.exchange.current_prices[symbol] = {
            "price": Decimal("50000"),
            "time": datetime.now()
        }
        
        # Create a position and SL
        self.exchange.create_order(
            symbol=symbol,
            type='market',
            side='BUY',
            amount=0.1,
            price=50000
        )
        self.exchange.place_stop_loss(symbol, 0.1, 48000)
        
        errors = []
        
        def update_sl(thread_id: int):
            """Update SL price repeatedly."""
            try:
                for i in range(100):
                    new_price = 48000 + (thread_id * 100) + i
                    self.exchange.update_stop_loss(symbol, new_price)
                    time.sleep(random.uniform(0, 0.001))
            except Exception as e:
                errors.append((thread_id, str(e)))
        
        # Start threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=update_sl, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join(timeout=30)
        
        # Verify no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"
        
        # Verify pending order still exists and is valid
        assert len(self.exchange.pending_orders) == 1
        for order in self.exchange.pending_orders.values():
            assert order['symbol'] == symbol
            assert order['type'] == 'stop_loss'
    
    def test_concurrent_order_cancel(self):
        """
        Test that order cancellation is thread-safe.
        """
        # Place multiple orders
        order_ids = []
        for i, symbol in enumerate(self.symbols):
            order = self.exchange.place_stop_loss(symbol, 0.1, 100 - i)
            order_ids.append((order['id'], symbol))
        
        cancelled = []
        errors = []
        
        def cancel_order(order_id: str, symbol: str, thread_id: int):
            """Try to cancel an order."""
            try:
                result = self.exchange.cancel_order(order_id, symbol)
                cancelled.append((order_id, result))
            except Exception as e:
                # OrderNotFound is expected if already cancelled
                if 'not found' not in str(e).lower():
                    errors.append((thread_id, str(e)))
        
        # Start threads to cancel orders (some will race)
        threads = []
        for i, (order_id, symbol) in enumerate(order_ids):
            # Multiple threads try to cancel the same order
            for j in range(3):
                t = threading.Thread(
                    target=cancel_order, 
                    args=(order_id, symbol, i * 3 + j)
                )
                threads.append(t)
                t.start()
        
        # Wait for all threads
        for t in threads:
            t.join(timeout=30)
        
        # Verify no unexpected errors
        assert len(errors) == 0, f"Unexpected errors: {errors}"
        
        # All orders should be cancelled
        assert len(self.exchange.pending_orders) == 0
    
    def test_lock_reentrant(self):
        """
        Test that RLock allows reentrant calls (e.g., update_stop_loss_to_entry
        calls update_stop_loss internally).
        """
        symbol = "ETH/USDT"
        self.exchange.current_prices[symbol] = {
            "price": Decimal("3000"),
            "time": datetime.now()
        }
        
        # Create position with entry price tracked
        self.exchange.create_order(
            symbol=symbol,
            type='market',
            side='BUY',
            amount=1.0,
            price=3000
        )
        self.exchange.place_stop_loss(symbol, 1.0, 2800)
        
        # This should work without deadlock (RLock allows reentrant locking)
        result = self.exchange.update_stop_loss_to_entry(symbol)
        assert result == True
        
        # Verify SL was moved to entry
        for order in self.exchange.pending_orders.values():
            if order['symbol'] == symbol:
                assert order['triggerPrice'] == Decimal("3000")


class TestMockExchangeStressTest:
    """Stress tests for MockExchange under heavy concurrent load."""
    
    def test_high_frequency_trading_simulation(self):
        """
        Simulate high-frequency trading with many symbols and threads.
        """
        exchange = MockExchange(initial_balance=1000000, leverage=20)
        
        symbols = [f"PAIR{i}/USDT" for i in range(20)]
        for symbol in symbols:
            exchange.current_prices[symbol] = {
                "price": Decimal("100"),
                "time": datetime.now()
            }
        
        trade_count = 0
        trade_lock = threading.Lock()
        
        def hft_trader(symbol: str):
            nonlocal trade_count
            for _ in range(200):
                try:
                    # Random trading activity
                    action = random.choice(['buy', 'sell', 'sl', 'tp', 'cancel'])
                    
                    if action == 'buy':
                        exchange.create_order(symbol, 'market', 'BUY', 0.01, 100)
                    elif action == 'sell':
                        if symbol in exchange.positions:
                            pos = exchange.positions[symbol]
                            if pos > Decimal("0.01"):
                                exchange.create_order(symbol, 'market', 'SELL', 0.01, 100)
                    elif action == 'sl':
                        exchange.place_stop_loss(symbol, 0.01, 90)
                    elif action == 'tp':
                        exchange.place_take_profit(symbol, 0.01, 110, "TP1")
                    elif action == 'cancel':
                        exchange.cancel_orders_for_symbol(symbol)
                    
                    with trade_lock:
                        trade_count += 1
                        
                except Exception:
                    pass  # Ignore expected exceptions like InsufficientFunds
        
        # Start many threads
        threads = []
        for symbol in symbols:
            t = threading.Thread(target=hft_trader, args=(symbol,))
            threads.append(t)
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join(timeout=60)
        
        # Verify exchange state is consistent
        balance = exchange.fetch_balance()
        assert balance['free']['USDT'] >= 0
        
        # Many trades should have executed
        assert trade_count > 1000
        
        print(f"Stress test completed: {trade_count} operations, "
              f"final balance: {balance['free']['USDT']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
