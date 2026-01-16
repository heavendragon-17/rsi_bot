# app/backtest/mock_exchange.py
"""
Backtest Mock Exchange (Futures with Leverage)
==============================================
Simulates a futures exchange for backtesting with:
- Leverage support (margin-based trading)
- Wick-based SL/TP checking
- Decimal precision
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Dict, Any, List, Sequence

from app.core.interfaces import IFuturesExchange


def to_decimal(val) -> Decimal:
    """Convert any numeric to Decimal."""
    if val is None:
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


def _base_asset(symbol: str) -> str:
    """
    Extract base asset from pair.
    Examples:
      "BTC/USDT" -> "BTC"
      "RIVER/USDT" -> "RIVER"
      "BTCUSDT" -> "BTCUSDT" (fallback)
    """
    if not symbol:
        return ""
    s = str(symbol).upper()
    if "/" in s:
        return s.split("/")[0].strip()
    return s.strip()


class MockExchange(IFuturesExchange):
    def __init__(self, initial_balance: float = 1000.0, leverage: int = 1):
        self.balance = to_decimal(initial_balance)  # Quote currency (USDT)
        self.leverage = Decimal(str(leverage))  # Futures leverage

        # positions: symbol -> amount (base amount, notional position)
        self.positions: Dict[str, Decimal] = {}
        
        # Margin tracking for futures
        self.margin_used: Dict[str, Decimal] = {}  # symbol -> margin locked

        # entry tracking
        self.entry_times: Dict[str, Any] = {}        # symbol -> entry timestamp
        self.entry_prices: Dict[str, Decimal] = {}   # symbol -> entry price

        self.trade_history: List[Dict] = []
        self.current_prices: Dict[str, Dict] = {}  # symbol -> {price, time}

        # Pending orders: order_id -> order details
        self.pending_orders: Dict[str, Dict] = {}
        self._order_counter = 0

    def _next_order_id(self) -> str:
        self._order_counter += 1
        return f"mock_order_{self._order_counter}"

    # ============================================================
    # IExchange required balance methods
    # ============================================================

    def get_balance(self) -> Decimal:
        """Return quote balance (USDT)."""
        return self.balance

    def get_balances(self, coins: Optional[List[str]] = None) -> Dict[str, Decimal]:
        """
        Return balances by asset.

        - USDT balance is tracked in self.balance
        - Base asset balances are derived from open positions (self.positions)
          (since this mock exchange stores positions as base amount).
        """
        out: Dict[str, Decimal] = {"USDT": self.balance}

        # include base assets from positions
        for sym, amt in self.positions.items():
            base = _base_asset(sym)
            if not base:
                continue
            out[base] = out.get(base, Decimal("0")) + to_decimal(amt)

        if coins:
            wanted = [c.strip().upper() for c in coins if c and c.strip()]
            return {c: out.get(c, Decimal("0")) for c in wanted}

        # default: return non-zero assets
        return {k: v for k, v in out.items() if v != 0}

    def get_balance_of(self, assets: List[str]) -> Dict[str, Decimal]:
        """
        Required by IExchange.
        Example:
          get_balance_of(["USDT", "BTC", "ETH"])
        """
        wanted = [a.strip().upper() for a in assets if a and a.strip()]
        if not wanted:
            return {}
        all_bal = self.get_balances(None)
        return {a: all_bal.get(a, Decimal("0")) for a in wanted}

    # ============================================================
    # Market data update (OHLC)
    # ============================================================

    def update_candle(self, symbol: str, open_, high, low, close, timestamp) -> List[Dict]:
        """
        Update exchange with full OHLC candle data.
        Checks pending SL/TP orders against High/Low wicks.

        Returns list of executed orders (for logging).
        """
        high_dec = to_decimal(high)
        low_dec = to_decimal(low)
        close_dec = to_decimal(close)

        self.current_prices[symbol] = {"price": close_dec, "time": timestamp}

        executed: List[Dict] = []
        orders_to_remove: List[str] = []

        for order_id, order in list(self.pending_orders.items()):
            if order.get("symbol") != symbol:
                continue

            triggered = False
            fill_price: Optional[Decimal] = None
            order_type = order.get("order_type", "LIMIT")
            trigger_price = to_decimal(order.get("trigger_price") or order.get("price"))

            # SL behavior: SELL and (LIMIT or STOP_LOSS) triggers when low <= trigger
            if order.get("side") == "SELL" and order_type in ("LIMIT", "STOP_LOSS"):
                if low_dec <= trigger_price:
                    triggered = True
                    fill_price = trigger_price
                    order_type = "STOP_LOSS"

            # TP behavior: TAKE_PROFIT triggers when high >= trigger
            elif order_type == "TAKE_PROFIT":
                if high_dec >= trigger_price:
                    triggered = True
                    fill_price = trigger_price

            if triggered and fill_price is not None:
                stored_exit_reason = order.get("exit_reason") or order_type
                result = self._execute_order(
                    symbol=order["symbol"],
                    side=order["side"],
                    amount=to_decimal(order["amount"]),
                    exec_price=fill_price,
                    timestamp=timestamp,
                    order_type=order_type,
                    exit_reason=stored_exit_reason,
                )
                if result:
                    executed.append(result)
                    orders_to_remove.append(order_id)

        for oid in orders_to_remove:
            self.pending_orders.pop(oid, None)

        return executed

    def update_price(self, symbol: str, price, timestamp) -> None:
        """Legacy method for compatibility."""
        self.current_prices[symbol] = {"price": to_decimal(price), "time": timestamp}

    # ============================================================
    # IExchange trading methods
    # ============================================================

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> Sequence[Sequence[Any]]:
        return []  # not used in push-based backtest

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        self.leverage = Decimal(str(leverage))
        return True

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        amount = self.positions.get(symbol, Decimal("0"))
        if amount <= 0:
            return None
        return {
            "symbol": symbol,
            "amount": amount,
            "entry_price": self.entry_prices.get(symbol),
            "leverage": self.leverage
        }

    def place_stop_loss(self, symbol: str, amount, trigger_price) -> Dict:
        """Place a stop loss order."""
        order_id = self._next_order_id()
        order = {
            "id": order_id,
            "symbol": symbol,
            "side": "SELL",
            "amount": to_decimal(amount),
            "trigger_price": to_decimal(trigger_price),
            "order_type": "STOP_LOSS",
            "status": "PENDING",
        }
        self.pending_orders[order_id] = order
        return order

    def place_take_profit(self, symbol: str, amount, trigger_price, label: str = "TP") -> Dict:
        """Place a take profit order."""
        order_id = self._next_order_id()
        order = {
            "id": order_id,
            "symbol": symbol,
            "side": "SELL",
            "amount": to_decimal(amount),
            "trigger_price": to_decimal(trigger_price),
            "order_type": "TAKE_PROFIT",
            "status": "PENDING",
            "label": label,
        }
        self.pending_orders[order_id] = order
        return order

    def cancel_orders_for_symbol(self, symbol: str) -> int:
        """Cancel all pending orders for a symbol."""
        to_cancel = [oid for oid, o in self.pending_orders.items() if o.get("symbol") == symbol]
        for oid in to_cancel:
            self.pending_orders.pop(oid, None)
        return len(to_cancel)

    def update_stop_loss(self, symbol: str, new_trigger_price) -> bool:
        """Update the trigger price of existing SL order(s) for symbol."""
        new_price = to_decimal(new_trigger_price)
        updated = False

        for order in self.pending_orders.values():
            if (
                order.get("symbol") == symbol
                and order.get("side") == "SELL"
                and order.get("order_type") in ("STOP_LOSS", "LIMIT")
            ):
                order["trigger_price"] = new_price
                order["price"] = new_price
                updated = True

        if updated:
            print(f"[MockExchange] Updated SL for {symbol} -> {new_price}")
        return updated

    def update_stop_loss_to_entry(self, symbol: str) -> bool:
        """
        Move existing SL order to entry price for this symbol.
        Uses stored entry price from self.entry_prices[symbol].
        """
        entry = self.entry_prices.get(symbol)
        if entry is None:
            return False

        ok = self.update_stop_loss(symbol, entry)
        if ok:
            print(f"[MockExchange] Move SL to ENTRY for {symbol}: new_sl={entry}")
        return ok

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel a specific pending order."""
        if order_id in self.pending_orders:
            self.pending_orders.pop(order_id, None)
            return True
        return False

    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount,
        price=None,
        exit_reason: str = None,
    ) -> Optional[Dict]:
        """
        Create an order.
        - MARKET executes immediately
        - LIMIT goes pending (and will be triggered in update_candle via wick checks)
        """
        amount = to_decimal(amount)
        current_data = self.current_prices.get(symbol)
        if not current_data:
            print(f"MockExchange: No price data for {symbol}")
            return None

        # Pending LIMIT
        if order_type.upper() == "LIMIT" and price is not None:
            order_id = self._next_order_id()
            price_dec = to_decimal(price)
            order = {
                "id": order_id,
                "symbol": symbol,
                "side": side,
                "amount": amount,
                "price": price_dec,
                "trigger_price": price_dec,
                "order_type": "LIMIT",
                "status": "PENDING",
                "exit_reason": exit_reason,
            }
            self.pending_orders[order_id] = order
            return {"id": order_id, "status": "PENDING", "type": "LIMIT"}

        # MARKET executes
        exec_price = to_decimal(price) if price is not None else to_decimal(current_data["price"])
        timestamp = current_data["time"]
        return self._execute_order(symbol, side, amount, exec_price, timestamp, order_type="MARKET", exit_reason=exit_reason)

    def _execute_order(
        self,
        symbol: str,
        side: str,
        amount: Decimal,
        exec_price: Decimal,
        timestamp,
        order_type: str = "MARKET",
        exit_reason: str = None,
    ) -> Optional[Dict]:
        """
        Execute an order with futures leverage support.
        
        For BUY:
          - notional = amount * price
          - margin = notional / leverage
          - Deduct margin from balance, not full notional
          
        For SELL:
          - Calculate PnL = (exit_price - entry_price) * amount
          - Return margin + PnL to balance
        """
        notional = exec_price * amount
        margin = notional / self.leverage
        
        entry_price = None
        entry_time = None
        hold_duration_seconds = None
        pnl = None
        pnl_pct = None
        margin_used = Decimal("0")

        if side == "BUY":
            # Check if we have enough margin
            if margin > self.balance:
                # print(f"MockExchange: Insufficient margin. Required: {margin:.2f}, Available: {self.balance:.2f}")
                return None
            
            # Deduct margin from balance
            self.balance -= margin
            self.positions[symbol] = self.positions.get(symbol, Decimal("0")) + amount
            self.margin_used[symbol] = self.margin_used.get(symbol, Decimal("0")) + margin
            self.entry_times[symbol] = timestamp
            self.entry_prices[symbol] = exec_price
            margin_used = margin

        elif side == "SELL":
            current_pos = self.positions.get(symbol, Decimal("0"))

            # tolerance for floating rounding
            tolerance = current_pos * Decimal("1.001")
            if amount > tolerance:
                return None  # insufficient position -> reject silently

            amount = min(amount, current_pos)
            
            # Get entry info for PnL calculation
            entry_price = self.entry_prices.get(symbol)
            entry_time = self.entry_times.get(symbol)
            
            # Calculate proportion of position being closed
            close_ratio = amount / current_pos if current_pos > 0 else Decimal("1")
            
            # Get proportional margin to return
            position_margin = self.margin_used.get(symbol, Decimal("0"))
            margin_to_return = position_margin * close_ratio
            
            # Calculate PnL
            if entry_price is not None:
                price_diff = exec_price - entry_price
                pnl = float(price_diff * amount)  # PnL on the notional
                pnl_pct = float((exec_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0
            else:
                pnl = 0.0
            
            # Return margin + PnL to balance
            self.balance += margin_to_return + Decimal(str(pnl or 0))
            
            # Update position and margin
            self.positions[symbol] = current_pos - amount
            self.margin_used[symbol] = position_margin - margin_to_return

            # Calculate hold duration
            if entry_time is not None and timestamp is not None:
                try:
                    if hasattr(entry_time, "timestamp") and hasattr(timestamp, "timestamp"):
                        hold_duration_seconds = (timestamp.timestamp() - entry_time.timestamp())
                    elif hasattr(entry_time, "value") and hasattr(timestamp, "value"):
                        hold_duration_seconds = (timestamp.value - entry_time.value) / 1e9
                except Exception:
                    pass

            # Cleanup if position fully closed
            if self.positions[symbol] <= Decimal("1e-8"):
                self.positions.pop(symbol, None)
                self.margin_used.pop(symbol, None)
                self.entry_times.pop(symbol, None)
                self.entry_prices.pop(symbol, None)

            margin_used = margin_to_return

        trade = {
            "time": timestamp,
            "symbol": symbol,
            "side": side,
            "price": float(exec_price),
            "amount": float(amount),
            "notional": float(notional),
            "margin": float(margin_used),
            "leverage": float(self.leverage),
            "balance_after": float(self.balance),
            "order_type": order_type,
            "exit_reason": exit_reason,
            "entry_price": float(entry_price) if entry_price is not None else None,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "hold_duration_seconds": hold_duration_seconds,
        }
        self.trade_history.append(trade)
        return trade

