# app/backtest/mock_exchange.py
"""
Backtest Mock Exchange (Futures with Leverage)
==============================================
Simulates a futures exchange for backtesting with:
- Leverage support (margin-based trading)
- Wick-based SL/TP checking
- Decimal precision
- CCXT-compliant order structure
"""

from __future__ import annotations

import logging
import random
import threading
from typing import Dict, List, Optional, Any, Tuple, Union, Sequence
from datetime import datetime, timedelta
from decimal import Decimal
import ccxt

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
    """
    Thread-safe mock exchange for backtesting and paper trading.
    Uses RLock to protect all internal state for concurrent access.
    """
    
    def __init__(self, initial_balance: float = 1000.0, leverage: int = 1, maker_fee: float = 0.0, taker_fee: float = 0.0):
        # Thread safety lock (RLock allows reentrant calls)
        self._lock = threading.RLock()
        
        self.balance = to_decimal(initial_balance)  # Quote currency (USDT)
        self.leverage = Decimal(str(leverage))  # Futures leverage
        
        # Fee configuration (rates as float, e.g. 0.0002 for 0.02%)
        self.maker_fee = Decimal(str(maker_fee))
        self.taker_fee = Decimal(str(taker_fee))

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
        """Generate next order ID. Assumes lock is held by caller."""
        self._order_counter += 1
        return f"mock_order_{self._order_counter}"

    # ============================================================
    # IExchange required balance methods
    # ============================================================

    def fetch_balance(self, params: Dict = {}) -> Dict:
        """
        CCXT-compliant balance fetch. Thread-safe.
        Returns: {'free': {}, 'used': {}, 'total': {}, 'USDT': {...}}
        Keep as Decimal for backtest parity.
        """
        with self._lock:
            usdt_balance = self.balance  # This is FREE balance
            used_usdt = sum(self.margin_used.values())
            total_usdt = usdt_balance + used_usdt  # Total = Free + Used
            
            # Return a copy to prevent external modification
            return {
                'free': {'USDT': usdt_balance},
                'used': {'USDT': used_usdt},
                'total': {'USDT': total_usdt},
                'USDT': {'free': usdt_balance, 'used': used_usdt, 'total': total_usdt}
            }

    # ============================================================
    # Market data update (OHLC)
    # ============================================================

    def update_candle(self, symbol: str, open_, high, low, close, timestamp) -> List[Dict]:
        """
        Update exchange with full OHLC candle data. Thread-safe.
        Checks pending SL/TP orders against High/Low wicks.

        Returns list of executed orders (for logging).
        """
        with self._lock:
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
                order_type = order.get("type", "limit").upper()
                trigger_price = to_decimal(order.get("triggerPrice") or order.get("price"))

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
                    # Get exit_reason from info dict (CCXT standard)
                    stored_exit_reason = order.get("info", {}).get("exit_reason") or order_type
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

    # ============================================================
    # IFuturesExchange methods
    # ============================================================

    def set_leverage(self, leverage: int, symbol: str) -> bool:
        """Set leverage for a symbol (mock uses global leverage). Thread-safe."""
        with self._lock:
            self.leverage = Decimal(str(leverage))
            return True

    def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict]:
        """Fetch open positions in CCXT format. Thread-safe."""
        with self._lock:
            pos_list = []
            for s, amt in self.positions.items():
                if symbols and s not in symbols:
                    continue
                amt_dec = to_decimal(amt)
                if amt_dec == 0:
                    continue
                
                entry = self.entry_prices.get(s, Decimal("0"))
                curr_data = self.current_prices.get(s, {})
                curr = to_decimal(curr_data.get("price", entry))
                
                # Simple PnL calc for display
                upnl = (curr - entry) * amt_dec
                
                p = {
                    "symbol": s,
                    "contracts": float(amt_dec),
                    "contractSize": 1.0,
                    "unrealizedPnl": float(upnl),
                    "leverage": float(self.leverage),
                    "entryPrice": float(entry),
                    "side": "long" if amt_dec > 0 else "short",
                    "notional": float(amt_dec * curr),
                    "info": {"marginUsed": float(self.margin_used.get(s, 0))}
                }
                pos_list.append(p)
            # Return a copy of the list
            return pos_list.copy()

    # ============================================================
    # IExchange trading methods
    # ============================================================

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> Sequence[Sequence[Any]]:
        return []  # not used in push-based backtest

    def place_stop_loss(self, symbol: str, amount, trigger_price) -> Dict:
        """Place a stop loss order. Thread-safe."""
        with self._lock:
            order_id = self._next_order_id()
            order = {
                "id": order_id,
                "symbol": symbol,
                "side": "SELL",
                "amount": to_decimal(amount),
                "triggerPrice": to_decimal(trigger_price),
                "price": to_decimal(trigger_price),
                "type": "stop_loss",
                "status": "open",
                "info": {"exit_reason": "STOP_LOSS"},
            }
            self.pending_orders[order_id] = order
            return order

    def place_take_profit(self, symbol: str, amount, trigger_price, label: str = "TP") -> Dict:
        """Place a take profit order. Thread-safe."""
        with self._lock:
            order_id = self._next_order_id()
            order = {
                "id": order_id,
                "symbol": symbol,
                "side": "SELL",
                "amount": to_decimal(amount),
                "triggerPrice": to_decimal(trigger_price),
                "price": to_decimal(trigger_price),
                "type": "take_profit",
                "status": "open",
                "info": {"exit_reason": label},
                "label": label,
            }
            self.pending_orders[order_id] = order
            return order

    def cancel_orders_for_symbol(self, symbol: str) -> int:
        """Cancel all pending orders for a symbol. Thread-safe."""
        with self._lock:
            to_cancel = [oid for oid, o in self.pending_orders.items() if o.get("symbol") == symbol]
            for oid in to_cancel:
                self.pending_orders.pop(oid, None)
            return len(to_cancel)

    def update_stop_loss(self, symbol: str, new_trigger_price, new_amount=None, exit_reason: str = None) -> bool:
        """
        Update the trigger price and/or amount of existing SL order(s) for symbol.
        Thread-safe.
        
        Args:
            symbol: Trading symbol
            new_trigger_price: New SL trigger price
            new_amount: Optional new amount for the SL order (for partial TP scenarios)
            exit_reason: Optional new exit reason (e.g., "BREAKEVEN")
        """
        with self._lock:
            new_price = to_decimal(new_trigger_price)
            new_amt = to_decimal(new_amount) if new_amount is not None else None
            updated = False

            for order in self.pending_orders.values():
                if (
                    order.get("symbol") == symbol
                    and order.get("side") == "SELL"
                    and order.get("type", "").upper() in ("STOP_LOSS", "LIMIT")
                ):
                    order["triggerPrice"] = new_price
                    order["price"] = new_price
                    # Update amount if provided
                    if new_amt is not None:
                        order["amount"] = new_amt
                    # Update exit_reason if provided
                    if exit_reason:
                        if "info" not in order:
                            order["info"] = {}
                        order["info"]["exit_reason"] = exit_reason
                    updated = True

            if updated:
                amt_str = f", amount={new_amt}" if new_amt is not None else ""
                reason_str = f" (reason={exit_reason})" if exit_reason else ""
                # print(f"[MockExchange] Updated SL for {symbol} -> price={new_price}{amt_str}{reason_str}")
            return updated

    def update_stop_loss_to_entry(self, symbol: str) -> bool:
        """
        Move existing SL order to entry price for this symbol. Thread-safe.
        Uses stored entry price from self.entry_prices[symbol].
        Note: This calls update_stop_loss which also acquires the lock (RLock allows this).
        """
        with self._lock:
            entry = self.entry_prices.get(symbol)
            if entry is None:
                return False

            ok = self.update_stop_loss(symbol, entry)
            return ok

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel a specific pending order. Thread-safe."""
        with self._lock:
            if order_id in self.pending_orders:
                self.pending_orders.pop(order_id, None)
                return True
            
            raise ccxt.OrderNotFound(f"Order {order_id} not found for {symbol}")

    def create_order(
        self,
        symbol: str,
        type: str = None,  # CCXT param name
        side: str = None,
        amount = None,
        price = None,
        params: Dict = None,
        # Legacy param name (for backward compatibility)
        order_type: str = None,
        exit_reason: str = None,
    ) -> Optional[Dict]:
        """
        Create an order. Thread-safe.
        - MARKET executes immediately
        - LIMIT goes pending (and will be triggered in update_candle via wick checks)
        
        Uses CCXT param names: type, params.
        """
        with self._lock:
            # Handle CCXT 'type' vs legacy 'order_type'
            actual_type = (type or order_type or 'market').upper()
            
            # Handle CCXT params dict for exit_reason
            params = params or {}
            exit_reason = params.get('exit_reason', exit_reason)
            
            amount = to_decimal(amount)
            current_data = self.current_prices.get(symbol)
            if not current_data:
                print(f"MockExchange: No price data for {symbol}")
                return None

            order_id = self._next_order_id()

            # Pending LIMIT
            if actual_type == "LIMIT" and price is not None:
                price_dec = to_decimal(price)
                order = {
                    "id": order_id,
                    "symbol": symbol,
                    "side": side.upper() if side else 'BUY',
                    "amount": amount,
                    "price": price_dec,
                    "triggerPrice": price_dec,
                    "type": "limit",
                    "status": "open",
                    "info": {"exit_reason": exit_reason or ""},
                }
                self.pending_orders[order_id] = order
                return {"id": order_id, "status": "open", "type": "limit"}

            # MARKET executes
            exec_price = to_decimal(price) if price is not None else to_decimal(current_data["price"])
            timestamp = current_data["time"]
            return self._execute_order(symbol, side, amount, exec_price, timestamp, order_type=actual_type, exit_reason=exit_reason)

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
        
        NOTE: This method assumes the lock is already held by the caller (RLock).
        
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
                raise ccxt.InsufficientFunds(
                    f"Insufficient balance for {symbol}. Required: {margin:.2f}, Available: {self.balance:.2f}"
                )
            
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
                raise ccxt.InsufficientFunds(f"Insufficient position for {symbol}: have {current_pos}, want {amount}")

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

        # Calculate fees
        fee_rate = self.taker_fee if order_type.upper() == 'MARKET' else self.maker_fee
        fee_cost = notional * fee_rate
        
        # Deduct fee from balance
        self.balance -= fee_cost

        # Generate order ID
        order_id = self._next_order_id()

        # Build CCXT-compliant order structure
        order = {
            # CCXT standard fields
            "id": order_id,
            "clientOrderId": f"client_{order_id}",
            "status": "closed",
            "type": order_type.lower(),
            "side": side,  # Keep uppercase for legacy compatibility
            "symbol": symbol,
            "price": float(exec_price),
            "amount": float(amount),
            "filled": float(amount),
            "remaining": 0.0,
            "cost": float(notional),
            "average": float(exec_price),
            "fee": {"currency": "USDT", "cost": float(fee_cost), "rate": float(fee_rate)},
            "info": {"exit_reason": exit_reason or ""},
            
            # Extended fields for reporting (kept for backward compat in reporting.py)
            "time": timestamp,
            "notional": float(notional),
            "margin": float(margin_used),
            "leverage": float(self.leverage),
            "balance_after": float(self.balance),
            "entry_price": float(entry_price) if entry_price is not None else None,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "hold_duration_seconds": hold_duration_seconds,
        }
        self.trade_history.append(order)
        return order
