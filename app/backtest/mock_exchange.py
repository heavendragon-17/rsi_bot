# app/backtest/mock_exchange.py
"""
Backtest Mock Exchange (Futures with Leverage)
==============================================
Simulates a futures exchange for backtesting with:
- Leverage support (margin-based trading)
- Normalized order type vocabulary (market, limit, stop_market, stop_limit, trailing_stop)
- reduceOnly enforcement
- Wick-based SL/TP checking
- Decimal precision
- CCXT-compliant order structure
"""

from __future__ import annotations

import threading
import structlog
from typing import Dict, List, Optional, Any, Sequence
from decimal import Decimal
from app.core.exceptions import InsufficientFundsError, OrderNotFoundError
from app.core.interfaces import IExchange
from app.core.utils import to_decimal

logger = structlog.get_logger()


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


class MockExchange(IExchange):
    """
    Thread-safe mock exchange for backtesting and paper trading.
    Uses RLock to protect all internal state for concurrent access.
    Supports the normalized order type vocabulary shared with BinanceAdapter.
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

    def fetch_balance(self, params: Optional[Dict] = None) -> Dict:
        """
        CCXT-compliant balance fetch. Thread-safe.
        Returns: {'free': {}, 'used': {}, 'total': {}, 'USDT': {...}}
        """
        with self._lock:
            usdt_balance = self.balance
            used_usdt = sum(self.margin_used.values())
            total_usdt = usdt_balance + used_usdt

            return {
                'free': {'USDT': usdt_balance},
                'used': {'USDT': used_usdt},
                'total': {'USDT': total_usdt},
                'USDT': {'free': usdt_balance, 'used': used_usdt, 'total': total_usdt}
            }

    # ============================================================
    # Market data update (OHLC) — Trigger logic for pending orders
    # ============================================================

    def update_candle(self, symbol: str, open_, high, low, close, timestamp) -> List[Dict]:
        """
        Update exchange with full OHLC candle data. Thread-safe.
        Checks pending orders against High/Low wicks using proper trigger logic:

        - limit (TP, SELL side): triggers when high >= price (price reached target)
        - stop_market (SL, SELL side): triggers when low <= stopPrice (price fell to stop)
        - stop_limit: triggers at stopPrice → becomes limit order at limit_price
        - trailing_stop: tracks peak, triggers when price drops by callback_rate% from peak

        Returns list of executed orders.
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

                order_subtype = order.get("order_subtype", "limit")
                side = order.get("side", "").upper()
                trigger_price = to_decimal(order.get("triggerPrice") or order.get("price"))
                reduce_only = order.get("reduce_only", False)

                triggered = False
                fill_price: Optional[Decimal] = None

                if side == "SELL":
                    if order_subtype == "stop_market":
                        # SL: triggers when low <= stopPrice
                        if low_dec <= trigger_price:
                            triggered = True
                            fill_price = trigger_price
                    elif order_subtype == "limit":
                        # TP: triggers when high >= price
                        if high_dec >= trigger_price:
                            triggered = True
                            fill_price = trigger_price
                    elif order_subtype == "stop_limit":
                        limit_price = to_decimal(order.get("limit_price", trigger_price))
                        if low_dec <= trigger_price:
                            # Convert to limit order (simplified: fill at limit_price)
                            triggered = True
                            fill_price = limit_price
                    elif order_subtype == "trailing_stop":
                        callback_rate = to_decimal(order.get("callback_rate", Decimal("1")))
                        peak = to_decimal(order.get("peak_price", high_dec))
                        # Update peak
                        if high_dec > peak:
                            order["peak_price"] = high_dec
                            peak = high_dec
                        # Check if price dropped by callback_rate% from peak
                        trigger_level = peak * (Decimal("1") - callback_rate / Decimal("100"))
                        if low_dec <= trigger_level:
                            triggered = True
                            fill_price = trigger_level

                elif side == "BUY":
                    if order_subtype == "limit":
                        # BUY limit: triggers when low <= price
                        if low_dec <= trigger_price:
                            triggered = True
                            fill_price = trigger_price
                    elif order_subtype == "stop_market":
                        # BUY stop: triggers when high >= stopPrice
                        if high_dec >= trigger_price:
                            triggered = True
                            fill_price = trigger_price

                if triggered and fill_price is not None:
                    # reduceOnly enforcement
                    if reduce_only:
                        current_pos = self.positions.get(symbol, Decimal("0"))
                        if current_pos <= Decimal("0"):
                            # No position to reduce — cancel order
                            orders_to_remove.append(order_id)
                            continue
                        # Cap amount at current position
                        fill_amount = min(to_decimal(order["amount"]), current_pos)
                    else:
                        fill_amount = to_decimal(order["amount"])

                    exit_reason = order.get("info", {}).get("exit_reason") or order_subtype.upper()
                    result = self._execute_order(
                        symbol=order["symbol"],
                        side=side,
                        amount=fill_amount,
                        exec_price=fill_price,
                        timestamp=timestamp,
                        order_type=order_subtype.upper(),
                        exit_reason=exit_reason,
                    )
                    if result:
                        # Mark the order as filled in trade history reference
                        result["triggering_order_id"] = order_id
                        executed.append(result)
                        orders_to_remove.append(order_id)

            for oid in orders_to_remove:
                self.pending_orders.pop(oid, None)

            return executed

    # ============================================================
    # IExchange methods
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
            return pos_list.copy()

    # ============================================================
    # Order Management — Normalized Order Type Vocabulary
    # ============================================================

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> Sequence[Sequence[Any]]:
        return []  # not used in push-based backtest

    def create_order(
        self,
        symbol: str,
        order_type: str = None,
        side: str = None,
        amount=None,
        price=None,
        params: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """
        Create an order using normalized order types. Thread-safe.

        Supported types:
        - market: immediate fill at current/signal price
        - limit: pending, fill when price crosses (TP for SELL side)
        - stop_market: pending, trigger when price crosses stop (SL for SELL side)
        - stop_limit: pending, trigger at stopPrice → fill at price
        - trailing_stop: pending, dynamic trigger based on callbackRate

        Params:
        - stopPrice: trigger price for stop_market/stop_limit
        - reduceOnly: if True, caps sell at current position, skips if no position
        - callbackRate: percentage for trailing_stop
        - exit_reason: label for trade history
        """
        with self._lock:
            params = params or {}
            actual_type = (order_type or "market").lower()
            amount = to_decimal(amount)
            reduce_only = params.get("reduceOnly", False)
            exit_reason = params.get("exit_reason", "")

            current_data = self.current_prices.get(symbol)
            if not current_data:
                logger.warning(f"MockExchange: No price data for {symbol}")
                return None

            # ----------------------------------------------------------
            # MARKET → immediate fill
            # ----------------------------------------------------------
            if actual_type == "market":
                if reduce_only:
                    current_pos = self.positions.get(symbol, Decimal("0"))
                    if current_pos <= Decimal("0") and (side or "").upper() == "SELL":
                        return None  # No position to reduce
                    if (side or "").upper() == "SELL":
                        amount = min(amount, current_pos)

                exec_price = to_decimal(price) if price is not None else to_decimal(current_data["price"])
                timestamp = current_data["time"]
                return self._execute_order(
                    symbol, side, amount, exec_price, timestamp,
                    order_type="MARKET", exit_reason=exit_reason,
                )

            # ----------------------------------------------------------
            # LIMIT → pending order
            # ----------------------------------------------------------
            if actual_type == "limit":
                order_id = self._next_order_id()
                price_dec = to_decimal(price)
                order = {
                    "id": order_id,
                    "symbol": symbol,
                    "side": (side or "BUY").upper(),
                    "amount": amount,
                    "price": price_dec,
                    "triggerPrice": price_dec,
                    "type": "limit",
                    "order_subtype": "limit",
                    "status": "open",
                    "reduce_only": reduce_only,
                    "info": {"exit_reason": exit_reason},
                }
                self.pending_orders[order_id] = order
                return {"id": order_id, "status": "open", "type": "limit"}

            # ----------------------------------------------------------
            # STOP_MARKET → pending, triggers at stopPrice
            # ----------------------------------------------------------
            if actual_type == "stop_market":
                stop_price = to_decimal(params.get("stopPrice", price))
                order_id = self._next_order_id()
                order = {
                    "id": order_id,
                    "symbol": symbol,
                    "side": (side or "SELL").upper(),
                    "amount": amount,
                    "price": stop_price,
                    "triggerPrice": stop_price,
                    "type": "stop_market",
                    "order_subtype": "stop_market",
                    "status": "open",
                    "reduce_only": reduce_only,
                    "info": {"exit_reason": exit_reason or "STOP_LOSS"},
                }
                self.pending_orders[order_id] = order
                return {"id": order_id, "status": "open", "type": "stop_market"}

            # ----------------------------------------------------------
            # STOP_LIMIT → pending, triggers at stopPrice → limit at price
            # ----------------------------------------------------------
            if actual_type == "stop_limit":
                stop_price = to_decimal(params.get("stopPrice"))
                limit_price = to_decimal(price)
                order_id = self._next_order_id()
                order = {
                    "id": order_id,
                    "symbol": symbol,
                    "side": (side or "SELL").upper(),
                    "amount": amount,
                    "price": limit_price,
                    "triggerPrice": stop_price,
                    "limit_price": limit_price,
                    "type": "stop_limit",
                    "order_subtype": "stop_limit",
                    "status": "open",
                    "reduce_only": reduce_only,
                    "info": {"exit_reason": exit_reason},
                }
                self.pending_orders[order_id] = order
                return {"id": order_id, "status": "open", "type": "stop_limit"}

            # ----------------------------------------------------------
            # TRAILING_STOP → pending, dynamic trigger
            # ----------------------------------------------------------
            if actual_type == "trailing_stop":
                callback_rate = Decimal(str(params.get("callbackRate", 1)))
                current_price = to_decimal(current_data["price"])
                order_id = self._next_order_id()
                order = {
                    "id": order_id,
                    "symbol": symbol,
                    "side": (side or "SELL").upper(),
                    "amount": amount,
                    "type": "trailing_stop",
                    "order_subtype": "trailing_stop",
                    "status": "open",
                    "reduce_only": reduce_only,
                    "callback_rate": callback_rate,
                    "peak_price": current_price,
                    "info": {"exit_reason": exit_reason or "TRAILING_STOP"},
                }
                self.pending_orders[order_id] = order
                return {"id": order_id, "status": "open", "type": "trailing_stop"}

            logger.warning(f"MockExchange: Unknown order type '{actual_type}'")
            return None

    # ============================================================
    # Order Query & Cancellation
    # ============================================================

    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Fetch order status. Checks pending orders first, then trade history."""
        with self._lock:
            # Check pending orders
            if order_id in self.pending_orders:
                order = self.pending_orders[order_id]
                return {
                    "id": order_id,
                    "symbol": order.get("symbol"),
                    "status": "open",
                    "type": order.get("type"),
                    "side": order.get("side"),
                    "amount": float(order.get("amount", 0)),
                    "filled": 0,
                    "info": order.get("info", {}),
                }

            # Check trade history for filled orders
            for trade in self.trade_history:
                if trade.get("triggering_order_id") == order_id:
                    return {
                        "id": order_id,
                        "symbol": trade.get("symbol"),
                        "status": "closed",
                        "type": trade.get("type"),
                        "side": trade.get("side"),
                        "amount": trade.get("amount", 0),
                        "filled": trade.get("filled", 0),
                        "price": trade.get("price", 0),
                        "info": trade.get("info", {}),
                    }

            return {"id": order_id, "symbol": symbol, "status": "unknown"}

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel a specific pending order. Thread-safe."""
        with self._lock:
            if order_id in self.pending_orders:
                self.pending_orders.pop(order_id, None)
                return True
            raise OrderNotFoundError(f"Order {order_id} not found")

    def cancel_all_orders(self, symbol: str) -> int:
        """Cancel all pending orders for a symbol. Thread-safe."""
        with self._lock:
            to_cancel = [oid for oid, o in self.pending_orders.items() if o.get("symbol") == symbol]
            for oid in to_cancel:
                self.pending_orders.pop(oid)
            return len(to_cancel)

    def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all open/pending orders, optionally filtered by symbol."""
        with self._lock:
            orders = []
            for oid, o in self.pending_orders.items():
                if symbol and o.get("symbol") != symbol:
                    continue
                orders.append({
                    "id": oid,
                    "symbol": o.get("symbol"),
                    "side": o.get("side"),
                    "type": o.get("type"),
                    "amount": float(o.get("amount", 0)),
                    "price": float(o.get("triggerPrice", 0)),
                    "status": "open",
                    "info": o.get("info", {}),
                })
            return orders

    # ============================================================
    # SL Convenience Methods
    # ============================================================

    def update_stop_loss(self, symbol: str, new_trigger_price, new_amount=None, exit_reason: str = None) -> bool:
        """
        Cancel existing SL + re-create as stop_market order.
        Thread-safe (RLock allows reentrant calls from create_order).
        """
        with self._lock:
            new_price = to_decimal(new_trigger_price)
            new_amt = to_decimal(new_amount) if new_amount is not None else None

            # Find and cancel existing stop_market orders for this symbol
            sl_order_ids = [
                oid for oid, o in self.pending_orders.items()
                if o.get("symbol") == symbol
                and o.get("side") == "SELL"
                and o.get("order_subtype") in ("stop_market", "stop_loss")
            ]

            for oid in sl_order_ids:
                self.pending_orders.pop(oid, None)

            if not sl_order_ids and new_amt is None:
                # No existing SL to update, and no amount specified
                current_pos = self.positions.get(symbol, Decimal("0"))
                if current_pos <= 0:
                    return False
                new_amt = current_pos

            # Determine amount
            if new_amt is None:
                current_pos = self.positions.get(symbol, Decimal("0"))
                new_amt = current_pos

            if new_amt <= 0:
                return False

            # Place new stop_market order
            result = self.create_order(
                symbol=symbol,
                order_type="stop_market",
                side="SELL",
                amount=new_amt,
                params={
                    "stopPrice": new_price,
                    "reduceOnly": True,
                    "exit_reason": exit_reason or "STOP_LOSS",
                },
            )
            return result is not None

    def update_stop_loss_to_entry(self, symbol: str) -> bool:
        """Move existing SL order to entry price for this symbol. Thread-safe."""
        with self._lock:
            entry = self.entry_prices.get(symbol)
            if entry is None:
                return False
            return self.update_stop_loss(symbol, entry, exit_reason="BREAKEVEN")

    # ============================================================
    # Internal Execution
    # ============================================================

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
        side = (side or "BUY").upper()
        notional = exec_price * amount
        margin = notional / self.leverage

        entry_price = None
        entry_time = None
        hold_duration_seconds = None
        pnl = None
        pnl_pct = None
        margin_used = Decimal("0")

        # Calculate fees early so we can include them in pnl
        fee_rate = self.taker_fee if order_type.upper() in ('MARKET', 'STOP_MARKET') else self.maker_fee
        fee_cost = notional * fee_rate

        if side == "BUY":
            if margin > self.balance:
                raise InsufficientFundsError(
                    f"Insufficient balance for {symbol}. Required: {margin:.2f}, Available: {self.balance:.2f}"
                )

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
                raise InsufficientFundsError(f"Insufficient position for {symbol}: have {current_pos}, want {amount}")

            amount = min(amount, current_pos)

            entry_price = self.entry_prices.get(symbol)
            entry_time = self.entry_times.get(symbol)

            close_ratio = amount / current_pos if current_pos > 0 else Decimal("1")

            position_margin = self.margin_used.get(symbol, Decimal("0"))
            margin_to_return = position_margin * close_ratio

            # Recalculate exit notional & fee after potential amount adjustment
            notional = exec_price * amount
            fee_cost = notional * fee_rate

            if entry_price is not None:
                price_diff = exec_price - entry_price
                gross_pnl = price_diff * amount
                # Approximate entry fee for this portion of the position
                entry_notional = entry_price * amount
                entry_fee_rate = self.taker_fee  # entries are always market (taker)
                entry_fee = entry_notional * entry_fee_rate
                # Net PnL = gross - entry fee - exit fee
                pnl = float(gross_pnl - entry_fee - fee_cost)
                pnl_pct = float((exec_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0
            else:
                pnl = 0.0

            self.balance += margin_to_return + Decimal(str(pnl or 0))

            self.positions[symbol] = current_pos - amount
            self.margin_used[symbol] = position_margin - margin_to_return

            if entry_time is not None and timestamp is not None:
                try:
                    if hasattr(entry_time, "timestamp") and hasattr(timestamp, "timestamp"):
                        hold_duration_seconds = (timestamp.timestamp() - entry_time.timestamp())
                    elif hasattr(entry_time, "value") and hasattr(timestamp, "value"):
                        hold_duration_seconds = (timestamp.value - entry_time.value) / 1e9
                except Exception:
                    pass

            if self.positions[symbol] <= Decimal("1e-8"):
                self.positions.pop(symbol, None)
                self.margin_used.pop(symbol, None)
                self.entry_times.pop(symbol, None)
                self.entry_prices.pop(symbol, None)

            margin_used = margin_to_return

            # Exit fee already included in pnl, no separate deduction needed

        # Recalculate notional after potential amount adjustment
        if side == "BUY":
            notional = exec_price * amount

        order_id = self._next_order_id()

        order = {
            # CCXT standard fields
            "id": order_id,
            "clientOrderId": f"client_{order_id}",
            "status": "closed",
            "type": order_type.lower(),
            "side": side,
            "symbol": symbol,
            "price": float(exec_price),
            "amount": float(amount),
            "filled": float(amount),
            "remaining": 0.0,
            "cost": float(notional),
            "average": float(exec_price),
            "fee": {"currency": "USDT", "cost": float(fee_cost), "rate": float(fee_rate)},
            "info": {"exit_reason": exit_reason or ""},

            # Extended fields for reporting
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
