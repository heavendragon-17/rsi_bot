"""
Backtest Mock Exchange (OHLC-Based)
===================================
Simulates exchange for backtesting with wick-based SL/TP checking.
Uses Decimal for precision, supports LIMIT and STOP_LOSS/TAKE_PROFIT orders.
"""
from decimal import Decimal
from typing import Optional, Dict, Any, List
from app.core.interfaces import IExchange
from datetime import datetime


def to_decimal(val) -> Decimal:
    """Convert any numeric to Decimal."""
    if val is None:
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


class MockExchange(IExchange):
    def __init__(self, initial_balance: float = 1000.0):
        self.balance = to_decimal(initial_balance)  # Quote currency (USDT)
        self.positions: Dict[str, Decimal] = {}  # symbol -> amount
        self.entry_times: Dict[str, Any] = {}  # symbol -> entry timestamp
        self.entry_prices: Dict[str, Decimal] = {}  # symbol -> entry price
        self.trade_history: List[Dict] = []
        self.current_prices: Dict[str, Dict] = {}  # symbol -> {price, time}
        
        # Pending orders: order_id -> order details
        self.pending_orders: Dict[str, Dict] = {}
        self._order_counter = 0

    def _next_order_id(self) -> str:
        self._order_counter += 1
        return f"mock_order_{self._order_counter}"

    def update_candle(self, symbol: str, open_, high, low, close, timestamp) -> List[Dict]:
        """
        Update exchange with full OHLC candle data.
        Checks pending SL/TP orders against High/Low wicks.
        
        Returns list of executed orders (for logging).
        """
        high_dec = to_decimal(high)
        low_dec = to_decimal(low)
        close_dec = to_decimal(close)
        
        self.current_prices[symbol] = {'price': close_dec, 'time': timestamp}
        
        executed = []
        orders_to_remove = []
        
        for order_id, order in self.pending_orders.items():
            if order['symbol'] != symbol:
                continue
            
            triggered = False
            fill_price = None
            order_type = order.get('order_type', 'LIMIT')
            trigger_price = to_decimal(order.get('trigger_price') or order.get('price'))
            
            # LIMIT SELL = Stop Loss behavior (triggers when price drops)
            if order['side'] == 'SELL' and order_type in ('LIMIT', 'STOP_LOSS'):
                if low_dec <= trigger_price:
                    triggered = True
                    fill_price = trigger_price
                    order_type = 'STOP_LOSS'
                    
            # TAKE_PROFIT = triggers when price rises
            elif order_type == 'TAKE_PROFIT':
                if high_dec >= trigger_price:
                    triggered = True
                    fill_price = trigger_price
            
            if triggered:
                # Use stored exit_reason if available, otherwise use order_type
                stored_exit_reason = order.get('exit_reason') or order_type
                result = self._execute_order(
                    symbol=order['symbol'],
                    side=order['side'],
                    amount=to_decimal(order['amount']),
                    exec_price=fill_price,
                    timestamp=timestamp,
                    order_type=order_type,
                    exit_reason=stored_exit_reason
                )
                if result:
                    executed.append(result)
                    orders_to_remove.append(order_id)
        
        # Remove executed orders
        for order_id in orders_to_remove:
            del self.pending_orders[order_id]
        
        return executed

    def update_price(self, symbol: str, price, timestamp) -> None:
        """Legacy method for compatibility."""
        self.current_prices[symbol] = {'price': to_decimal(price), 'time': timestamp}

    def get_balance(self) -> Decimal:
        return self.balance

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int):
        return []

    def place_stop_loss(self, symbol: str, amount, trigger_price) -> Dict:
        """Place a stop loss order."""
        order_id = self._next_order_id()
        order = {
            'id': order_id,
            'symbol': symbol,
            'side': 'SELL',
            'amount': to_decimal(amount),
            'trigger_price': to_decimal(trigger_price),
            'order_type': 'STOP_LOSS',
            'status': 'PENDING'
        }
        self.pending_orders[order_id] = order
        return order

    def place_take_profit(self, symbol: str, amount, trigger_price, label: str = "TP") -> Dict:
        """Place a take profit order."""
        order_id = self._next_order_id()
        order = {
            'id': order_id,
            'symbol': symbol,
            'side': 'SELL',
            'amount': to_decimal(amount),
            'trigger_price': to_decimal(trigger_price),
            'order_type': 'TAKE_PROFIT',
            'status': 'PENDING',
            'label': label
        }
        self.pending_orders[order_id] = order
        return order

    def cancel_orders_for_symbol(self, symbol: str) -> int:
        """Cancel all pending orders for a symbol."""
        to_cancel = [oid for oid, o in self.pending_orders.items() if o['symbol'] == symbol]
        for oid in to_cancel:
            del self.pending_orders[oid]
        return len(to_cancel)

    def update_stop_loss(self, symbol: str, new_trigger_price) -> bool:
        """Update the trigger price of existing SL order for symbol."""
        new_price = to_decimal(new_trigger_price)
        for order_id, order in self.pending_orders.items():
            if order['symbol'] == symbol and order.get('order_type') in ('STOP_LOSS', 'LIMIT'):
                if order['side'] == 'SELL':
                    order['trigger_price'] = new_price
                    order['price'] = new_price
                    return True
        return False

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel a specific pending order."""
        if order_id in self.pending_orders:
            del self.pending_orders[order_id]
            return True
        return False

    def create_order(self, symbol: str, order_type: str, side: str, amount, 
                     price=None, exit_reason: str = None) -> Optional[Dict]:
        """Create an order. MARKET executes immediately, LIMIT goes pending."""
        amount = to_decimal(amount)
        
        current_data = self.current_prices.get(symbol)
        if not current_data:
            print(f"MockExchange: No price data for {symbol}")
            return None

        # LIMIT orders go to pending
        if order_type.upper() == 'LIMIT' and price is not None:
            order_id = self._next_order_id()
            price_dec = to_decimal(price)
            order = {
                'id': order_id,
                'symbol': symbol,
                'side': side,
                'amount': amount,
                'price': price_dec,
                'trigger_price': price_dec,
                'order_type': 'LIMIT',
                'status': 'PENDING',
                'exit_reason': exit_reason  # Store for when order fills
            }
            self.pending_orders[order_id] = order
            return {'id': order_id, 'status': 'PENDING', 'type': 'LIMIT'}

        # MARKET orders execute immediately
        exec_price = to_decimal(price) if price else current_data['price']
        timestamp = current_data['time']

        return self._execute_order(symbol, side, amount, exec_price, timestamp, exit_reason=exit_reason)

    def _execute_order(self, symbol: str, side: str, amount: Decimal, exec_price: Decimal,
                       timestamp, order_type: str = "MARKET", exit_reason: str = None) -> Optional[Dict]:
        """Internal method to execute an order."""
        cost = exec_price * amount
        entry_price = None
        entry_time = None
        hold_duration_seconds = None
        pnl = None
        pnl_pct = None

        if side == 'BUY':
            if cost > self.balance:
                print(f"MockExchange: Insufficient funds. Cost: {cost}, Bal: {self.balance}")
                return None
            self.balance -= cost
            self.positions[symbol] = self.positions.get(symbol, Decimal("0")) + amount
            # Track entry info for this position
            self.entry_times[symbol] = timestamp
            self.entry_prices[symbol] = exec_price

        elif side == 'SELL':
            current_pos = self.positions.get(symbol, Decimal("0"))
            tolerance = current_pos * Decimal("1.001")
            if amount > tolerance:
                return None  # Silently reject - insufficient position

            # Clamp to actual position
            amount = min(amount, current_pos)
            revenue = exec_price * amount
            self.balance += revenue
            self.positions[symbol] -= amount
            
            # Calculate PnL and hold duration
            entry_price = self.entry_prices.get(symbol)
            entry_time = self.entry_times.get(symbol)
            
            if entry_price is not None:
                # PnL for this sell amount
                entry_cost = entry_price * amount
                pnl = float(revenue - entry_cost)
                pnl_pct = float((exec_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
            
            if entry_time is not None and timestamp is not None:
                try:
                    # Calculate hold duration in seconds
                    if hasattr(entry_time, 'timestamp') and hasattr(timestamp, 'timestamp'):
                        hold_duration_seconds = (timestamp.timestamp() - entry_time.timestamp())
                    elif hasattr(entry_time, 'value') and hasattr(timestamp, 'value'):
                        # pandas Timestamp
                        hold_duration_seconds = (timestamp.value - entry_time.value) / 1e9
                except Exception:
                    pass
            
            # Clear entry tracking if position fully closed
            if self.positions[symbol] <= Decimal("1e-8"):
                del self.positions[symbol]
                self.entry_times.pop(symbol, None)
                self.entry_prices.pop(symbol, None)
            cost = revenue

        trade = {
            'time': timestamp,
            'symbol': symbol,
            'side': side,
            'price': float(exec_price),
            'amount': float(amount),
            'cost_or_revenue': float(cost),
            'balance_after': float(self.balance),
            'order_type': order_type,
            'exit_reason': exit_reason,
            'entry_price': float(entry_price) if entry_price else None,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'hold_duration_seconds': hold_duration_seconds
        }
        self.trade_history.append(trade)
        
        return trade

