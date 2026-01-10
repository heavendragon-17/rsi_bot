"""
Backtest Mock Exchange
=======================
Simulates exchange for backtesting with Decimal support.
"""
from decimal import Decimal
from typing import Optional, Dict, Any, Sequence
from app.core.interfaces import IExchange


class MockExchange(IExchange):
    def __init__(self, initial_balance: float = 1000.0):
        self.balance = Decimal(str(initial_balance))
        self.positions: Dict[str, Decimal] = {}
        self.trade_history = []
        self.current_prices: Dict[str, Dict] = {}
        self.pending_orders: Dict[str, Dict] = {}
        self._order_counter = 0

    def update_price(self, symbol: str, price, timestamp) -> None:
        self.current_prices[symbol] = {
            "price": Decimal(str(price)) if not isinstance(price, Decimal) else price,
            "time": timestamp,
        }
        self._check_pending_orders(symbol)

    def _check_pending_orders(self, symbol: str) -> None:
        current_data = self.current_prices.get(symbol)
        if not current_data:
            return

        current_price = current_data["price"]
        ts = current_data["time"]

        orders_to_execute = []

        for order_id, order in list(self.pending_orders.items()):
            if order["symbol"] != symbol:
                continue

            # SELL limit (SL): trigger when price <= limit
            if order["side"] == "SELL" and current_price <= order["price"]:
                orders_to_execute.append((order_id, order))

        for order_id, order in orders_to_execute:
            fill_price = order["price"]  # fill at limit price for deterministic backtest
            self._execute_order(
                symbol=order["symbol"],
                side=order["side"],
                amount=order["amount"],
                exec_price=fill_price,
                timestamp=ts,
            )
            del self.pending_orders[order_id]
            print(f"Limit SL triggered at {float(current_price)} (filled @ {float(fill_price)})")

    def get_balance(self) -> Decimal:
        return self.balance

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> Sequence[Sequence[Any]]:
        return []

    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: Decimal,
        price: Optional[Decimal] = None,
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))

        current_data = self.current_prices.get(symbol)
        if not current_data:
            return None

        if order_type.upper() == "LIMIT" and price is not None:
            self._order_counter += 1
            order_id = f"mock_order_{self._order_counter}"

            if not isinstance(price, Decimal):
                price = Decimal(str(price))

            self.pending_orders[order_id] = {
                "id": order_id,
                "symbol": symbol,
                "side": side,
                "amount": amount,
                "price": price,
                "type": "LIMIT",
                "status": "PENDING",
            }
            return {"id": order_id, "status": "PENDING", "type": "LIMIT"}

        exec_price = current_data["price"]
        ts = current_data["time"]
        return self._execute_order(symbol, side, amount, exec_price, ts)

    def _execute_order(self, symbol: str, side: str, amount: Decimal, exec_price: Decimal, timestamp) -> Optional[Dict[str, Any]]:
        cost = exec_price * amount

        if side == "BUY":
            if cost > self.balance:
                return None
            self.balance -= cost
            self.positions[symbol] = self.positions.get(symbol, Decimal("0")) + amount

        elif side == "SELL":
            current_pos = self.positions.get(symbol, Decimal("0"))
            if amount > current_pos:
                return None

            revenue = exec_price * amount
            self.balance += revenue
            self.positions[symbol] -= amount
            if self.positions[symbol] <= Decimal("0"):
                del self.positions[symbol]
            cost = revenue

        trade = {
            "time": timestamp,
            "symbol": symbol,
            "side": side,
            "price": float(exec_price),
            "amount": float(amount),
            "cost_or_revenue": float(cost),
            "balance_after": float(self.balance),
        }
        self.trade_history.append(trade)
        return trade

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        if order_id in self.pending_orders:
            del self.pending_orders[order_id]
            return True
        return False
