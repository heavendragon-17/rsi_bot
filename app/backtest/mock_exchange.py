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

from app.core.interfaces import IExchange, IFuturesExchange


def to_decimal(val) -> Decimal:
    """Convert any numeric to Decimal."""
    if val is None:
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


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
                side = order.get("side", "").upper()

                # Check stored trigger/stop price in params or direct fields
                # CCXT stores these in different places depending on impl, here we check common fields
                trigger_price = to_decimal(order.get("triggerPrice") or order.get("stopPrice") or order.get("price"))

                # 1. STOP LOSS (Sell trigger when Low <= Price)
                #    CCXT: params={'stopPrice': ...} usually implies a Stop Market or Stop Limit
                if side == "SELL" and (order_type in ("STOP_LOSS", "STOP_MARKET") or order.get("params", {}).get("stopPrice")):
                    # Explicit Stop Loss order type OR implicit via stopPrice param
                    if low_dec <= trigger_price:
                        triggered = True
                        fill_price = trigger_price
                        # Treat as Stop Loss execution
                        if order_type not in ("STOP_LOSS", "STOP_MARKET"):
                             order["type"] = "stop_loss" # internal upgrade for reporting

                # 2. TAKE PROFIT (Sell trigger when High >= Price)
                elif side == "SELL" and (order_type in ("TAKE_PROFIT", "TAKE_PROFIT_MARKET")):
                     if high_dec >= trigger_price:
                        triggered = True
                        fill_price = trigger_price

                # 3. LIMIT SELL (Sell trigger when High >= Price)
                #    Standard Limit Sell acts like TP if above price
                elif side == "SELL" and order_type == "LIMIT":
                    if high_dec >= trigger_price:
                        triggered = True
                        fill_price = trigger_price

                # 4. LIMIT BUY (Buy trigger when Low <= Price)
                elif side == "BUY" and order_type == "LIMIT":
                    if low_dec <= trigger_price:
                        triggered = True
                        fill_price = trigger_price

                if triggered and fill_price is not None:
                    # Get exit_reason from info dict (CCXT standard)
                    stored_exit_reason = order.get("info", {}).get("exit_reason") or order.get("type")

                    # Check reduceOnly constraint if present
                    is_reduce_only = order.get("params", {}).get("reduceOnly", False) or order.get("reduceOnly", False)

                    result = self._execute_order(
                        symbol=order["symbol"],
                        side=order["side"],
                        amount=to_decimal(order["amount"]),
                        exec_price=fill_price,
                        timestamp=timestamp,
                        order_type=order["type"],
                        exit_reason=stored_exit_reason,
                        reduce_only=is_reduce_only
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
                side = order.get("side", "BUY")
                order_type = order.get("type", "").upper()
                params = order.get("params", {})

                # Check if it's a SL order (either Type=STOP_LOSS or has stopPrice)
                is_sl = (side == "SELL") and (
                    order_type in ("STOP_LOSS", "STOP_MARKET") or
                    params.get("stopPrice") is not None
                )

                if order.get("symbol") == symbol and is_sl:
                    # Update trigger/stop price
                    if params.get("stopPrice") is not None:
                        order["params"]["stopPrice"] = float(new_price)
                    order["triggerPrice"] = new_price
                    order["price"] = new_price # For limit

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
                print(f"[MockExchange] Updated SL for {symbol} -> price={new_price}{amt_str}{reason_str}")
            return updated

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
        type: str,
        side: str,
        amount: Decimal,
        price: Optional[Decimal] = None,
        params: Optional[Dict] = {}
    ) -> Optional[Dict]:
        """
        Create an order. Thread-safe. CCXT Compatible.
        
        Args:
            symbol: Pair
            type: 'market' or 'limit'
            side: 'buy' or 'sell'
            amount: Quantity
            price: Price (required for limit)
            params: Dict with 'stopPrice', 'triggerPrice', 'reduceOnly', etc.
        """
        with self._lock:
            type = type.lower()
            side = side.upper()
            amount = to_decimal(amount)
            params = params or {}
            
            current_data = self.current_prices.get(symbol)
            if not current_data:
                print(f"MockExchange: No price data for {symbol}")
                return None

            order_id = self._next_order_id()

            # Check if it's a conditional order (Stop Loss / Take Profit)
            # CCXT usually passes 'stopPrice' or 'triggerPrice' in params
            stop_price = params.get('stopPrice') or params.get('triggerPrice')

            # Construct internal order object
            order = {
                "id": order_id,
                "symbol": symbol,
                "side": side,
                "amount": amount,
                "price": to_decimal(price) if price else None,
                "type": type,
                "status": "open",
                "params": params, # Store params for later check
                "info": {"exit_reason": params.get("exit_reason", "")},
                "reduceOnly": params.get("reduceOnly", False)
            }

            # If it has a stop price, it's a pending conditional order
            if stop_price is not None:
                order["triggerPrice"] = to_decimal(stop_price)
                # If type is 'market', it's a STOP_MARKET (executes at market when triggered)
                # If type is 'limit', it's a STOP_LIMIT (places limit when triggered - simplified here to execute)
                self.pending_orders[order_id] = order
                return {"id": order_id, "status": "open", "type": type}

            # Pending LIMIT order (standard)
            if type == "limit" and price is not None:
                order["triggerPrice"] = to_decimal(price) # Limit triggers at price
                self.pending_orders[order_id] = order
                return {"id": order_id, "status": "open", "type": "limit"}

            # MARKET executes immediately
            exec_price = to_decimal(price) if price is not None else to_decimal(current_data["price"])
            timestamp = current_data["time"]
            return self._execute_order(
                symbol, side, amount, exec_price, timestamp,
                order_type=type,
                exit_reason=params.get("exit_reason"),
                reduce_only=params.get("reduceOnly", False)
            )

    def _execute_order(
        self,
        symbol: str,
        side: str,
        amount: Decimal,
        exec_price: Decimal,
        timestamp,
        order_type: str = "MARKET",
        exit_reason: str = None,
        reduce_only: bool = False
    ) -> Optional[Dict]:
        """
        Execute an order with futures leverage support.
        
        NOTE: This method assumes the lock is already held by the caller (RLock).
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

            # If trying to sell more than we have
            if amount > tolerance:
                # If Reduce Only (or implied by context like SL/TP triggering), clamp to position
                # In this system, any automated SELL execution during backtest is treated as a Close
                # if it exceeds position (to prevent crashes on double triggers).
                is_system_exit = exit_reason in ("STOP_LOSS", "TAKE_PROFIT", "TP1", "TP2", "TP3", "SL", "BREAKEVEN")

                if reduce_only or is_system_exit:
                    # Log warning but proceed with max available
                    # print(f"[MockExchange] Warning: Capping exit order for {symbol} from {amount} to {current_pos}")
                    amount = current_pos
                else:
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
