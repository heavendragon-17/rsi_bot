"""Backtest Mock Exchange — simulates a futures exchange for backtesting."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

import structlog

from app.backtest.exchange.executor import (
    check_liquidation as _check_liquidation,
)
from app.backtest.exchange.executor import (
    execute_order,
)
from app.backtest.exchange.executor import (
    update_stop_loss as _update_stop_loss,
)
from app.core.exceptions import OrderNotFoundError
from app.core.interfaces import IExchange
from app.core.utils import to_decimal
from app.trading.exchange.fill_simulator import (
    FillSimulator,
    PendingOrder,
    WickFillMode,
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

        self.positions: dict[str, Decimal] = {}
        self.margin_used: dict[str, Decimal] = {}
        self.entry_times: dict[str, Any] = {}
        self.entry_prices: dict[str, Decimal] = {}

        self.trade_history: list[dict] = []
        self.current_prices: dict[str, dict] = {}

        self._sim = FillSimulator(
            WickFillMode(),
            maker_fee=self.maker_fee,
            taker_fee=self.taker_fee,
        )

    @property
    def pending_orders(self) -> dict[str, dict]:
        """Dict view of pending orders for backward compatibility with tests."""
        result: dict[str, dict] = {}
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

    def _get_position_amount(self, symbol: str) -> Decimal:
        return self.positions.get(symbol, Decimal("0"))

    def fetch_balance(self, params: dict | None = None) -> dict:
        with self._lock:
            used = sum(self.margin_used.values())
            total = self.balance + used
            return {
                "free": {"USDT": self.balance},
                "used": {"USDT": used},
                "total": {"USDT": total},
                "USDT": {"free": self.balance, "used": used, "total": total},
            }

    def check_liquidation(self, timestamp: Any) -> bool:
        with self._lock:
            return _check_liquidation(self, timestamp)

    def update_candle(
        self,
        symbol: str,
        open_: Any,
        high: Any,
        low: Any,
        close: Any,
        timestamp: Any,
    ) -> list[dict]:
        with self._lock:
            high_dec, low_dec, close_dec = to_decimal(high), to_decimal(low), to_decimal(close)
            self.current_prices[symbol] = {"price": close_dec, "time": timestamp}

            candle_data = {"high": high_dec, "low": low_dec}
            fill_results = self._sim.process_market_data(
                symbol,
                candle_data,
                self._get_position_amount,
            )

            executed: list[dict] = []
            for fr in fill_results:
                exit_reason = fr.info.get("exit_reason") or fr.order_type.upper()

                # Re-clamp reduce_only fills against actual position.
                # When multiple orders trigger on the same candle, earlier
                # fills change the position but FillSimulator used a stale
                # snapshot.  Skip if position is already closed.
                fill_amount = fr.fill_amount
                if fr.reduce_only:
                    current_pos = abs(self.positions.get(fr.symbol, Decimal("0")))
                    if current_pos <= Decimal("0"):
                        continue
                    fill_amount = min(fill_amount, current_pos)

                result = self._execute_order(
                    symbol=fr.symbol,
                    side=fr.side,
                    amount=fill_amount,
                    exec_price=fr.fill_price,
                    timestamp=timestamp,
                    order_type=fr.order_type.upper(),
                    exit_reason=exit_reason,
                )
                if result:
                    result["triggering_order_id"] = fr.order_id
                    executed.append(result)
            return executed

    def set_leverage(self, leverage: int, symbol: str) -> bool:
        with self._lock:
            self.leverage = Decimal(str(leverage))
            return True

    def fetch_positions(self, symbols: list[str] | None = None) -> list[dict]:
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
                pos_list.append(
                    {
                        "symbol": s,
                        "contracts": float(amt),
                        "contractSize": 1.0,
                        "unrealizedPnl": float(upnl),
                        "leverage": float(self.leverage),
                        "entryPrice": float(entry),
                        "side": "long" if amt > 0 else "short",
                        "notional": float(amt * curr),
                        "info": {"marginUsed": float(self.margin_used.get(s, 0))},
                    }
                )
            return pos_list.copy()

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> Sequence[Sequence[Any]]:
        return []

    def create_order(
        self,
        symbol: str,
        order_type: str = None,
        side: str = None,
        amount: Any = None,
        price: Any = None,
        params: dict | None = None,
    ) -> dict | None:
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
                    symbol,
                    side or "SELL",
                    amount,
                    exec_price,
                    current_data["time"],
                    "MARKET",
                    exit_reason,
                )

            order_id = self._sim.next_order_id(prefix="mock")
            order_side = (side or "SELL").upper()

            if actual_type == "limit":
                price_dec = to_decimal(price)
                order = PendingOrder(
                    id=order_id,
                    symbol=symbol,
                    order_type="limit",
                    side=order_side,
                    amount=amount,
                    price=price_dec,
                    trigger_price=price_dec,
                    reduce_only=reduce_only,
                    info={"exit_reason": exit_reason},
                )
                self._sim.add_order(order)
                return {"id": order_id, "status": "open", "type": "limit"}

            if actual_type == "stop_market":
                stop_price = to_decimal(params.get("stopPrice", price))
                order = PendingOrder(
                    id=order_id,
                    symbol=symbol,
                    order_type="stop_market",
                    side=order_side,
                    amount=amount,
                    trigger_price=stop_price,
                    price=stop_price,
                    reduce_only=reduce_only,
                    info={"exit_reason": exit_reason or "STOP_LOSS"},
                )
                self._sim.add_order(order)
                return {"id": order_id, "status": "open", "type": "stop_market"}

            if actual_type == "stop_limit":
                stop_price = to_decimal(params.get("stopPrice"))
                limit_p = to_decimal(price)
                order = PendingOrder(
                    id=order_id,
                    symbol=symbol,
                    order_type="stop_limit",
                    side=order_side,
                    amount=amount,
                    trigger_price=stop_price,
                    price=limit_p,
                    limit_price=limit_p,
                    reduce_only=reduce_only,
                    info={"exit_reason": exit_reason},
                )
                self._sim.add_order(order)
                return {"id": order_id, "status": "open", "type": "stop_limit"}

            if actual_type == "trailing_stop":
                cb_rate = Decimal(str(params.get("callbackRate", 1)))
                curr_price = to_decimal(current_data["price"])
                order = PendingOrder(
                    id=order_id,
                    symbol=symbol,
                    order_type="trailing_stop",
                    side=order_side,
                    amount=amount,
                    reduce_only=reduce_only,
                    callback_rate=cb_rate,
                    peak_price=curr_price,
                    info={"exit_reason": exit_reason or "TRAILING_STOP"},
                )
                self._sim.add_order(order)
                return {"id": order_id, "status": "open", "type": "trailing_stop"}

            logger.warning(f"MockExchange: Unknown order type '{actual_type}'")
            return None

    def fetch_order(self, order_id: str, symbol: str) -> dict[str, Any]:
        with self._lock:
            po = self._sim.get_order(order_id)
            if po:
                return {
                    "id": order_id,
                    "symbol": po.symbol,
                    "status": "open",
                    "type": po.order_type,
                    "side": po.side,
                    "amount": float(po.amount),
                    "filled": 0,
                    "info": dict(po.info),
                }
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
        with self._lock:
            if self._sim.cancel_order(order_id):
                return True
            raise OrderNotFoundError(f"Order {order_id} not found")

    def cancel_all_orders(self, symbol: str) -> int:
        with self._lock:
            return self._sim.cancel_all_orders(symbol)

    def fetch_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            orders = []
            for o in self._sim.get_pending_orders(symbol):
                orders.append(
                    {
                        "id": o.id,
                        "symbol": o.symbol,
                        "side": o.side,
                        "type": o.order_type,
                        "amount": float(o.amount),
                        "price": float(o.trigger_price or Decimal("0")),
                        "status": "open",
                        "info": dict(o.info),
                    }
                )
            return orders

    def update_stop_loss(
        self,
        symbol: str,
        new_trigger_price: Any,
        new_amount: Any = None,
        exit_reason: str | None = None,
    ) -> bool:
        with self._lock:
            return _update_stop_loss(self, symbol, new_trigger_price, new_amount, exit_reason)

    def update_stop_loss_to_entry(self, symbol: str) -> bool:
        with self._lock:
            entry = self.entry_prices.get(symbol)
            if entry is None:
                return False
            return self.update_stop_loss(symbol, entry, exit_reason="BREAKEVEN")

    def _execute_order(
        self,
        symbol: str,
        side: str,
        amount: Decimal,
        exec_price: Decimal,
        timestamp: Any,
        order_type: str = "MARKET",
        exit_reason: str | None = None,
        fee_override: Decimal | None = None,
    ) -> dict | None:
        return execute_order(
            self, symbol, side, amount, exec_price,
            timestamp, order_type, exit_reason, fee_override,
        )
