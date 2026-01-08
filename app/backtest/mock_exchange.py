"""
Backtest Mock Exchange
=======================
Simulates exchange for backtesting with Decimal support.
"""
from decimal import Decimal
from typing import Optional, Dict, Any, Sequence
from app.core.interfaces import IExchange
from datetime import datetime


class MockExchange(IExchange):
    """Mock exchange for backtesting with Decimal support."""
    
    def __init__(self, initial_balance: float = 1000.0):
        self.balance = Decimal(str(initial_balance))
        self.positions: Dict[str, Decimal] = {}
        self.trade_history = []
        self.current_prices: Dict[str, Dict] = {}
        self.pending_orders: Dict[str, Dict] = {}  # order_id -> order details
        self._order_counter = 0

    def update_price(self, symbol: str, price, timestamp) -> None:
        """Called by BacktestEngine to update current market price."""
        self.current_prices[symbol] = {
            'price': Decimal(str(price)) if not isinstance(price, Decimal) else price,
            'time': timestamp
        }
        
        # Check pending limit orders
        self._check_pending_orders(symbol)

    def _check_pending_orders(self, symbol: str) -> None:
        """Check if any pending limit orders should be executed."""
        current_data = self.current_prices.get(symbol)
        if not current_data:
            return
        
        current_price = current_data['price']
        orders_to_execute = []
        
        for order_id, order in list(self.pending_orders.items()):
            if order['symbol'] != symbol:
                continue
            
            # SELL limit order executes when price drops to or below limit price
            if order['side'] == 'SELL' and current_price <= order['price']:
                orders_to_execute.append((order_id, order, current_price))
        
        for order_id, order, exec_price in orders_to_execute:
            self._execute_order(
                symbol=order['symbol'],
                side=order['side'],
                amount=order['amount'],
                exec_price=exec_price,
                timestamp=current_data['time']
            )
            del self.pending_orders[order_id]
            print(f"Limit SL triggered at {exec_price}")

    def get_balance(self) -> Decimal:
        return self.balance

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> Sequence[Sequence[Any]]:
        return []  # Not used in push-based backtest

    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: Decimal,
        price: Optional[Decimal] = None
    ) -> Optional[Dict[str, Any]]:
        """Create market or limit order."""
        # Convert amount to Decimal if needed
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
        
        current_data = self.current_prices.get(symbol)
        if not current_data:
            print(f"MockExchange: No price data for {symbol}")
            return None

        if order_type.upper() == 'LIMIT' and price is not None:
            # Store as pending order
            self._order_counter += 1
            order_id = f"mock_order_{self._order_counter}"
            
            if not isinstance(price, Decimal):
                price = Decimal(str(price))
            
            self.pending_orders[order_id] = {
                'id': order_id,
                'symbol': symbol,
                'side': side,
                'amount': amount,
                'price': price,
                'type': 'LIMIT',
                'status': 'PENDING'
            }
            return {'id': order_id, 'status': 'PENDING', 'type': 'LIMIT'}
        
        # Market order - execute immediately
        exec_price = current_data['price']
        timestamp = current_data['time']
        
        return self._execute_order(symbol, side, amount, exec_price, timestamp)

    def _execute_order(
        self,
        symbol: str,
        side: str,
        amount: Decimal,
        exec_price: Decimal,
        timestamp
    ) -> Optional[Dict[str, Any]]:
        """Execute an order at given price."""
        cost = exec_price * amount

        if side == 'BUY':
            if cost > self.balance:
                print(f"MockExchange: Insufficient funds. Cost: {cost}, Bal: {self.balance}")
                return None
            self.balance -= cost
            self.positions[symbol] = self.positions.get(symbol, Decimal("0")) + amount

        elif side == 'SELL':
            current_pos = self.positions.get(symbol, Decimal("0"))
            if amount > current_pos:
                print(f"MockExchange: Insufficient position. Has: {current_pos}, Want: {amount}")
                return None

            revenue = exec_price * amount
            self.balance += revenue
            self.positions[symbol] -= amount
            if self.positions[symbol] <= Decimal("0"):
                del self.positions[symbol]
            cost = revenue  # For logging

        trade = {
            'time': timestamp,
            'symbol': symbol,
            'side': side,
            'price': float(exec_price),
            'amount': float(amount),
            'cost_or_revenue': float(cost),
            'balance_after': float(self.balance)
        }
        self.trade_history.append(trade)
        return trade

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel a pending order."""
        if order_id in self.pending_orders:
            del self.pending_orders[order_id]
            return True
        return False
