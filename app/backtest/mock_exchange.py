# app/backtest/mock_exchange.py
"""
Backtest Mock Exchange (Futures with Leverage)
==============================================
Simulates a futures exchange for backtesting with:
- Leverage support (margin-based trading)
- Normalized order type vocabulary (market, limit, stop_market, stop_limit, trailing_stop)
- reduceOnly enforcement
- Wick-based SL/TP checking via FillSimulator(WickFillMode)
- Decimal precision
- CCXT-compliant order structure
- SHORT support: negative position amounts, BUY-side exit orders, signed PnL
"""
from __future__ import annotations

import threading
import structlog
from typing import Dict, List, Optional, Any, Sequence
from decimal import Decimal
from app.core.exceptions import InsufficientFundsError, OrderNotFoundError
from app.core.interfaces import IExchange
from app.core.utils import to_decimal
from app.core.actions import SIDE_BUY, SIDE_SELL, EXIT_STOP_LOSS, EXIT_LIQUIDATION
from app.trading.exchange.fill_simulator import (
    FillSimulator, WickFillMode, PendingOrder,
)

logger = structlog.get_logger()


class MockExchange(IExchange):
    """
    Thread-safe mock exchange for backtesting.
    Delegates order management and fill detection to FillSimulator(WickFillMode).
    Owns position/margin/balance state internally.
    """

    def __init__(
        self,
        initial_balance: float = 1000.0,
        leverage: int = 1,
        maker_fee: float = 0.0,
        taker_fee: float = 0.0,
    ) -> None:
        self._lock = threading.RLock()

        self.balance: Decimal = to_decimal(initial_balance)
        self.leverage: Decimal = Decimal(str(leverage))
        self.maker_fee: Decimal = Decimal(str(maker_fee))
        self.taker_fee: Decimal = Decimal(str(taker_fee))

        # Positions: symbol → signed amount (+long, -short)
        self.positions: Dict[str, Decimal] = {}
        self.margin_used: Dict[str, Decimal] = {}
        self.entry_times: Dict[str, Any] = {}
        self.entry_prices: Dict[str, Decimal] = {}

        self.trade_history: List[Dict] = []
        self.current_prices: Dict[str, Dict] = {}

        # Fill simulator owns pending orders and fill detection
        self._sim = FillSimulator(
            WickFillMode(),
            maker_fee=self.maker_fee,
            taker_fee=self.taker_fee,
        )

    # ── Backward-compat property ─────────────────────────────────

    @property
    def pending_orders(self) -> Dict[str, Dict]:
        """Dict view of pending orders for backward compatibility with tests."""
        result: Dict[str, Dict] = {}
        for oid, o in self._sim.pending_orders.items():
            result[oid] = {
                "id": o.id,
                "symbol": o.symbol,
                "side": o.side,
                "amount": o.amount,
                "price": o.price,
                "triggerPrice": o.trigger_price or o.price,
                "type": o.order_type,
                "order_subtype": o.order_type,
                "status": "open",
                "reduce_only": o.reduce_only,
                "info": dict(o.info),
                "limit_price": o.limit_price,
                "callback_rate": o.callback_rate,
                "peak_price": o.peak_price,
            }
        return result

    # ── Position amount callback for FillSimulator ───────────────

    def _get_position_amount(self, symbol: str) -> Decimal:
        return self.positions.get(symbol, Decimal("0"))

    # ── IExchange: balance ───────────────────────────────────────

    def fetch_balance(self, params: Optional[Dict] = None) -> Dict:
        with self._lock:
            used = sum(self.margin_used.values())
            total = self.balance + used
            return {
                "free": {"USDT": self.balance},
                "used": {"USDT": used},
                "total": {"USDT": total},
                "USDT": {"free": self.balance, "used": used, "total": total},
            }

    # ── Liquidation ──────────────────────────────────────────────

    def check_liquidation(self, timestamp: Any) -> bool:
        with self._lock:
            if not self.positions:
                return False
            used = sum(self.margin_used.values())
            total_upnl = Decimal("0")
            for symbol, amt in self.positions.items():
                if amt == 0:
                    continue
                entry = self.entry_prices.get(symbol, Decimal("0"))
                curr = to_decimal(self.current_prices.get(symbol, {}).get("price", entry))
                total_upnl += (curr - entry) * amt
            equity = self.balance + used + total_upnl
            if equity <= Decimal("0"):
                logger.warning("portfolio_liquidated", equity=float(equity), timestamp=timestamp)
                for symbol in list(self.positions.keys()):
                    signed = self.positions.get(symbol, Decimal("0"))
                    if signed == 0:
                        continue
                    exit_side = SIDE_BUY if signed < 0 else SIDE_SELL
                    abs_amt = abs(signed)
                    price = to_decimal(self.current_prices.get(symbol, {}).get("price", Decimal("0")))
                    if price <= 0:
                        price = self.entry_prices.get(symbol, Decimal("0"))
                    try:
                        self._execute_order(symbol, exit_side, abs_amt, price,
                                            timestamp, "MARKET", EXIT_LIQUIDATION,
                                            fee_override=Decimal("0.005"))
                    except Exception as e:
                        logger.error("liquidation_error", symbol=symbol, error=str(e))
                self.balance = Decimal("0")
                return True
            return False

    # ── Candle update → fill detection ───────────────────────────

    def update_candle(
        self,
        symbol: str,
        open_: Any,
        high: Any,
        low: Any,
        close: Any,
        timestamp: Any,
    ) -> List[Dict]:
        with self._lock:
            high_dec = to_decimal(high)
            low_dec = to_decimal(low)
            close_dec = to_decimal(close)
            self.current_prices[symbol] = {"price": close_dec, "time": timestamp}

            candle_data = {"high": high_dec, "low": low_dec}
            fill_results = self._sim.process_market_data(
                symbol, candle_data, self._get_position_amount,
            )

            executed: List[Dict] = []
            for fr in fill_results:
                exit_reason = fr.info.get("exit_reason") or fr.order_type.upper()
                result = self._execute_order(
                    symbol=fr.symbol,
                    side=fr.side,
                    amount=fr.fill_amount,
                    exec_price=fr.fill_price,
                    timestamp=timestamp,
                    order_type=fr.order_type.upper(),
                    exit_reason=exit_reason,
                )
                if result:
                    result["triggering_order_id"] = fr.order_id
                    executed.append(result)
            return executed

    # ── IExchange: leverage / positions / ohlcv ──────────────────

    def set_leverage(self, leverage: int, symbol: str) -> bool:
        with self._lock:
            self.leverage = Decimal(str(leverage))
            return True

    def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict]:
        with self._lock:
            pos_list = []
            for s, amt in self.positions.items():
                if symbols and s not in symbols:
                    continue
                if amt == 0:
                    continue
                entry = self.entry_prices.get(s, Decimal("0"))
                curr = to_decimal(self.current_prices.get(s, {}).get("price", entry))
                upnl = (curr - entry) * amt
                pos_list.append({
                    "symbol": s,
                    "contracts": float(amt),
                    "contractSize": 1.0,
                    "unrealizedPnl": float(upnl),
                    "leverage": float(self.leverage),
                    "entryPrice": float(entry),
                    "side": "long" if amt > 0 else "short",
                    "notional": float(amt * curr),
                    "info": {"marginUsed": float(self.margin_used.get(s, 0))},
                })
            return pos_list.copy()

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> Sequence[Sequence[Any]]:
        return []

    # ── Order creation ───────────────────────────────────────────

    def create_order(
        self,
        symbol: str,
        order_type: str = None,
        side: str = None,
        amount: Any = None,
        price: Any = None,
        params: Optional[Dict] = None,
    ) -> Optional[Dict]:
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

            # ── MARKET → immediate fill ─────────────────────────
            if actual_type == "market":
                if reduce_only:
                    current_pos = self.positions.get(symbol, Decimal("0"))
                    s = (side or "").upper()
                    if s == "SELL":
                        if current_pos <= Decimal("0"):
                            return None
                        amount = min(amount, current_pos)
                    elif s == "BUY":
                        if current_pos >= Decimal("0"):
                            return None
                        amount = min(amount, abs(current_pos))
                exec_price = to_decimal(price) if price is not None else to_decimal(current_data["price"])
                return self._execute_order(
                    symbol, side, amount, exec_price,
                    current_data["time"], "MARKET", exit_reason,
                )

            # ── Pending order types ─────────────────────────────
            order_id = self._sim.next_order_id(prefix="mock")
            order_side = (side or "SELL").upper()

            if actual_type == "limit":
                price_dec = to_decimal(price)
                order = PendingOrder(
                    id=order_id, symbol=symbol, order_type="limit",
                    side=order_side, amount=amount, price=price_dec,
                    trigger_price=price_dec, reduce_only=reduce_only,
                    info={"exit_reason": exit_reason},
                )
                self._sim.add_order(order)
                return {"id": order_id, "status": "open", "type": "limit"}

            if actual_type == "stop_market":
                stop_price = to_decimal(params.get("stopPrice", price))
                order = PendingOrder(
                    id=order_id, symbol=symbol, order_type="stop_market",
                    side=order_side, amount=amount, trigger_price=stop_price,
                    price=stop_price, reduce_only=reduce_only,
                    info={"exit_reason": exit_reason or "STOP_LOSS"},
                )
                self._sim.add_order(order)
                return {"id": order_id, "status": "open", "type": "stop_market"}

            if actual_type == "stop_limit":
                stop_price = to_decimal(params.get("stopPrice"))
                limit_p = to_decimal(price)
                order = PendingOrder(
                    id=order_id, symbol=symbol, order_type="stop_limit",
                    side=order_side, amount=amount, trigger_price=stop_price,
                    price=limit_p, limit_price=limit_p, reduce_only=reduce_only,
                    info={"exit_reason": exit_reason},
                )
                self._sim.add_order(order)
                return {"id": order_id, "status": "open", "type": "stop_limit"}

            if actual_type == "trailing_stop":
                cb_rate = Decimal(str(params.get("callbackRate", 1)))
                curr_price = to_decimal(current_data["price"])
                order = PendingOrder(
                    id=order_id, symbol=symbol, order_type="trailing_stop",
                    side=order_side, amount=amount, reduce_only=reduce_only,
                    callback_rate=cb_rate, peak_price=curr_price,
                    info={"exit_reason": exit_reason or "TRAILING_STOP"},
                )
                self._sim.add_order(order)
                return {"id": order_id, "status": "open", "type": "trailing_stop"}

            logger.warning(f"MockExchange: Unknown order type '{actual_type}'")
            return None

    # ── Order query & cancellation ───────────────────────────────

    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        with self._lock:
            po = self._sim.get_order(order_id)
            if po:
                return {
                    "id": order_id, "symbol": po.symbol, "status": "open",
                    "type": po.order_type, "side": po.side,
                    "amount": float(po.amount), "filled": 0,
                    "info": dict(po.info),
                }
            for trade in self.trade_history:
                if trade.get("triggering_order_id") == order_id:
                    return {
                        "id": order_id, "symbol": trade.get("symbol"),
                        "status": "closed", "type": trade.get("type"),
                        "side": trade.get("side"),
                        "amount": trade.get("amount", 0),
                        "filled": trade.get("filled", 0),
                        "price": trade.get("price", 0),
                        "info": trade.get("info", {}),
                    }
            return {"id": order_id, "symbol": symbol, "status": "unknown"}

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        with self._lock:
            if self._sim.cancel_order(order_id):
                return True
            raise OrderNotFoundError(f"Order {order_id} not found")

    def cancel_all_orders(self, symbol: str) -> int:
        with self._lock:
            return self._sim.cancel_all_orders(symbol)

    def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            orders = []
            for o in self._sim.get_pending_orders(symbol):
                orders.append({
                    "id": o.id, "symbol": o.symbol, "side": o.side,
                    "type": o.order_type, "amount": float(o.amount),
                    "price": float(o.trigger_price or Decimal("0")),
                    "status": "open", "info": dict(o.info),
                })
            return orders

    # ── SL convenience ───────────────────────────────────────────

    def update_stop_loss(
        self, symbol: str, new_trigger_price: Any,
        new_amount: Any = None, exit_reason: Optional[str] = None,
    ) -> bool:
        with self._lock:
            new_price = to_decimal(new_trigger_price)
            new_amt = to_decimal(new_amount) if new_amount is not None else None
            current_pos = self.positions.get(symbol, Decimal("0"))
            exit_side = SIDE_BUY if current_pos < 0 else SIDE_SELL

            sl_ids = [
                oid for oid, o in self._sim.pending_orders.items()
                if o.symbol == symbol and o.side == exit_side
                and o.order_type in ("stop_market", "stop_loss")
            ]
            for oid in sl_ids:
                self._sim.cancel_order(oid)

            if not sl_ids and new_amt is None and current_pos == 0:
                return False
            if new_amt is None:
                new_amt = abs(current_pos)
            if new_amt <= 0:
                return False

            result = self.create_order(
                symbol=symbol, order_type="stop_market", side=exit_side,
                amount=new_amt,
                params={"stopPrice": new_price, "reduceOnly": True,
                        "exit_reason": exit_reason or EXIT_STOP_LOSS},
            )
            return result is not None

    def update_stop_loss_to_entry(self, symbol: str) -> bool:
        with self._lock:
            entry = self.entry_prices.get(symbol)
            if entry is None:
                return False
            return self.update_stop_loss(symbol, entry, exit_reason="BREAKEVEN")

    # ── Internal execution (position / margin / balance) ─────────

    def _execute_order(
        self, symbol: str, side: str, amount: Decimal, exec_price: Decimal,
        timestamp: Any, order_type: str = "MARKET",
        exit_reason: Optional[str] = None, fee_override: Optional[Decimal] = None,
    ) -> Optional[Dict]:
        side = (side or SIDE_BUY).upper()
        notional = exec_price * amount
        fee_rate = fee_override if fee_override is not None else (
            self.taker_fee if order_type.upper() in ("MARKET", "STOP_MARKET") else self.maker_fee)
        fee_cost = notional * fee_rate
        current_signed = self.positions.get(symbol, Decimal("0"))

        entry_price = None
        hold_secs = None
        pnl = None
        pnl_pct = None
        margin_used = Decimal("0")

        is_opening = (side == "BUY" and current_signed >= 0) or (side == "SELL" and current_signed <= 0)
        if is_opening:
            margin = notional / self.leverage
            if margin > self.balance:
                raise InsufficientFundsError(
                    f"Insufficient balance for {symbol}. Required: {margin:.2f}, Available: {self.balance:.2f}")
            self.balance -= margin
            delta = amount if side == "BUY" else -amount
            self.positions[symbol] = current_signed + delta
            self.margin_used[symbol] = self.margin_used.get(symbol, Decimal("0")) + margin
            self.entry_times[symbol] = timestamp
            self.entry_prices[symbol] = exec_price
            margin_used = margin
        else:
            # Closing: unified for LONG exit (SELL) and SHORT exit (BUY)
            pos_size = abs(current_signed)
            if amount > pos_size * Decimal("1.001"):
                raise InsufficientFundsError(
                    f"Insufficient position for {symbol}: have {pos_size}, want {amount}")
            amount = min(amount, pos_size)
            entry_price = self.entry_prices.get(symbol)
            entry_time = self.entry_times.get(symbol)
            close_ratio = amount / pos_size if pos_size > 0 else Decimal("1")
            pos_margin = self.margin_used.get(symbol, Decimal("0"))
            margin_to_return = pos_margin * close_ratio
            notional = exec_price * amount
            fee_cost = notional * fee_rate
            if entry_price is not None:
                # Unified PnL: (exit - entry) * signed_amount for shorts,
                # (exit - entry) * amount for longs
                if current_signed < 0:
                    gross_pnl = (exec_price - entry_price) * current_signed
                    pnl_pct = float((entry_price - exec_price) / entry_price * 100) if entry_price > 0 else 0.0
                else:
                    gross_pnl = (exec_price - entry_price) * amount
                    pnl_pct = float((exec_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0
                entry_fee = entry_price * amount * self.taker_fee
                pnl = float(gross_pnl - entry_fee - fee_cost)
            else:
                pnl = 0.0
            self.balance += margin_to_return + Decimal(str(pnl or 0))
            delta = amount if side == "BUY" else -amount
            self.positions[symbol] = current_signed + delta
            self.margin_used[symbol] = pos_margin - margin_to_return
            hold_secs = self._calc_hold_duration(entry_time, timestamp)
            if abs(self.positions.get(symbol, Decimal("0"))) <= Decimal("1e-8"):
                for d in (self.positions, self.margin_used, self.entry_times, self.entry_prices):
                    d.pop(symbol, None)
            margin_used = margin_to_return
            notional = exec_price * amount

        order_id = self._sim.next_order_id(prefix="mock")
        order = {
            "id": order_id, "clientOrderId": f"client_{order_id}",
            "status": "closed", "type": order_type.lower(),
            "side": side, "symbol": symbol,
            "price": float(exec_price), "amount": float(amount),
            "filled": float(amount), "remaining": 0.0,
            "cost": float(notional), "average": float(exec_price),
            "fee": {"currency": "USDT", "cost": float(fee_cost), "rate": float(fee_rate)},
            "info": {"exit_reason": exit_reason or ""},
            "time": timestamp, "notional": float(notional),
            "margin": float(margin_used), "leverage": float(self.leverage),
            "balance_after": float(self.balance),
            "entry_price": float(entry_price) if entry_price is not None else None,
            "pnl": pnl, "pnl_pct": pnl_pct, "hold_duration_seconds": hold_secs,
        }
        self.trade_history.append(order)
        return order

    @staticmethod
    def _calc_hold_duration(entry_time: Any, exit_time: Any) -> Optional[float]:
        if entry_time is None or exit_time is None:
            return None
        try:
            if hasattr(entry_time, "timestamp") and hasattr(exit_time, "timestamp"):
                return exit_time.timestamp() - entry_time.timestamp()
            if hasattr(entry_time, "value") and hasattr(exit_time, "value"):
                return (exit_time.value - entry_time.value) / 1e9
        except Exception:
            return None
