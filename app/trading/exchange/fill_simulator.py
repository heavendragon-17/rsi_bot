"""
Pluggable FillSimulator — shared order management and fill detection.

Extracted from MockExchange (wick-based) and SimExchange (tick-based)
to eliminate duplicated order matching logic.  Each exchange composes
a FillSimulator with the appropriate FillMode and delegates trigger
detection + order storage, while retaining its own position/balance model.

Architecture:
    FillMode (ABC)
      ├── WickFillMode   — candle OHLC triggers (backtest)
      └── TickFillMode   — single-price triggers (paper trading)

    FillSimulator
      ├── order storage  (add / cancel / query)
      ├── fill detection (delegates to FillMode)
      └── reduceOnly enforcement (via callback)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.core.utils import to_decimal

# ── Data classes ─────────────────────────────────────────────────────


@dataclass
class PendingOrder:
    """Unified pending-order representation shared by both exchanges."""

    id: str
    symbol: str
    order_type: str  # market, limit, stop_market, stop_limit, trailing_stop
    side: str  # BUY | SELL
    amount: Decimal
    price: Decimal | None = None  # limit price (TP target)
    trigger_price: Decimal | None = None  # stop / SL trigger price
    reduce_only: bool = False
    status: str = "open"  # open | pending | pending_open | filled | cancelled
    callback_rate: Decimal | None = None  # trailing_stop callback %
    peak_price: Decimal | None = None  # trailing_stop peak tracker
    limit_price: Decimal | None = None  # stop_limit final fill price
    info: dict[str, Any] = field(default_factory=dict)


@dataclass
class FillResult:
    """Describes a single triggered fill returned by process_market_data."""

    order_id: str
    symbol: str
    side: str
    order_type: str
    fill_price: Decimal
    fill_amount: Decimal
    fee_rate: Decimal
    reduce_only: bool
    info: dict[str, Any] = field(default_factory=dict)


# ── FillMode ABC ─────────────────────────────────────────────────────


class FillMode(ABC):
    """Determines *when* and *at what price* a pending order triggers."""

    @abstractmethod
    def check_fills(
        self,
        orders: list[PendingOrder],
        market_data: Any,
    ) -> list[tuple[PendingOrder, Decimal]]:
        """Return (order, fill_price) pairs for orders that trigger.

        Must NOT mutate *orders* list — caller handles removal.
        """
        ...


class WickFillMode(FillMode):
    """Candle-OHLC trigger logic (backtest).

    Trigger rules (matching real exchange wick-fill semantics):
      SELL stop_market  → low  <= trigger_price   (SL long)
      SELL limit        → high >= trigger_price    (TP long)
      SELL stop_limit   → low  <= trigger_price    (fill at limit_price)
      SELL trailing_stop→ peak tracking + callback
      BUY  limit        → low  <= trigger_price    (TP short)
      BUY  stop_market  → high >= trigger_price    (SL short)
    """

    def check_fills(
        self,
        orders: list[PendingOrder],
        market_data: dict[str, Decimal],
    ) -> list[tuple[PendingOrder, Decimal]]:
        high = market_data["high"]
        low = market_data["low"]

        fills: list[tuple[PendingOrder, Decimal]] = []

        for order in orders:
            tp = order.trigger_price or order.price
            if tp is None:
                continue

            fill_price: Decimal | None = None

            if order.side == "SELL":
                if order.order_type == "stop_market":
                    if low <= tp:
                        fill_price = tp
                elif order.order_type == "limit":
                    if high >= tp:
                        fill_price = tp
                elif order.order_type == "stop_limit":
                    if low <= tp:
                        fill_price = order.limit_price or tp
                elif order.order_type == "trailing_stop":
                    fill_price = self._check_trailing(order, high, low)
            elif order.side == "BUY":
                if order.order_type == "limit":
                    if low <= tp:
                        fill_price = tp
                elif order.order_type == "stop_market":
                    if high >= tp:
                        fill_price = tp

            if fill_price is not None:
                fills.append((order, fill_price))

        return fills

    @staticmethod
    def _check_trailing(
        order: PendingOrder,
        high: Decimal,
        low: Decimal,
    ) -> Decimal | None:
        cb = order.callback_rate or Decimal("1")
        peak = order.peak_price or high
        if high > peak:
            order.peak_price = high
            peak = high
        trigger_level = peak * (Decimal("1") - cb / Decimal("100"))
        if low <= trigger_level:
            return trigger_level
        return None


class TickFillMode(FillMode):
    """Single-tick trigger logic (paper trading).

    Trigger rules:
      SELL stop_market → price <= stop_price   (SL)
      SELL limit       → price >= limit_price  (TP)
      BUY  stop_market → price >= stop_price   (SL short)
      BUY  limit       → price <= limit_price  (TP short)
    """

    def check_fills(
        self,
        orders: list[PendingOrder],
        market_data: Decimal,
    ) -> list[tuple[PendingOrder, Decimal]]:
        price = market_data
        fills: list[tuple[PendingOrder, Decimal]] = []

        for order in orders:
            fill_price: Decimal | None = None

            if order.order_type == "stop_market" and order.side == "SELL":
                if order.trigger_price and price <= order.trigger_price:
                    fill_price = order.trigger_price
            elif order.order_type == "limit" and order.side == "SELL":
                if order.price and price >= order.price:
                    fill_price = order.price
            elif order.order_type == "stop_market" and order.side == "BUY":
                if order.trigger_price and price >= order.trigger_price:
                    fill_price = order.trigger_price
            elif order.order_type == "limit" and order.side == "BUY":
                if order.price and price <= order.price:
                    fill_price = order.price

            if fill_price is not None:
                fills.append((order, fill_price))

        return fills


# ── FillSimulator ────────────────────────────────────────────────────

# Type alias: callback returns signed position amount for a symbol.
# Positive = long, negative = short, 0 = no position.
PositionAmountFn = Callable[[str], Decimal]


class FillSimulator:
    """Shared order management and fill detection.

    Owns pending-order storage and delegates trigger logic to a FillMode.
    Does NOT own position or balance state — the composing exchange handles
    those via the FillResult objects returned by process_market_data().

    Args:
        fill_mode:  WickFillMode or TickFillMode instance.
        maker_fee:  Maker fee rate as Decimal (e.g. 0.0002).
        taker_fee:  Taker fee rate as Decimal (e.g. 0.0005).
    """

    def __init__(
        self,
        fill_mode: FillMode,
        maker_fee: Decimal,
        taker_fee: Decimal,
    ) -> None:
        self._fill_mode = fill_mode
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self._pending: dict[str, PendingOrder] = {}
        self._order_counter: int = 0

    # ── Order ID generation ──────────────────────────────────────

    def next_order_id(self, prefix: str = "sim") -> str:
        self._order_counter += 1
        return f"{prefix}_order_{self._order_counter}"

    # ── Order storage ────────────────────────────────────────────

    @property
    def pending_orders(self) -> dict[str, PendingOrder]:
        """Direct access to the pending orders dict (read-only intent)."""
        return self._pending

    def add_order(self, order: PendingOrder) -> None:
        self._pending[order.id] = order

    def remove_order(self, order_id: str) -> PendingOrder | None:
        return self._pending.pop(order_id, None)

    def cancel_order(self, order_id: str) -> bool:
        order = self._pending.pop(order_id, None)
        if order is not None:
            order.status = "cancelled"
            return True
        return False

    def cancel_all_orders(self, symbol: str) -> int:
        ids = [oid for oid, o in self._pending.items() if o.symbol == symbol]
        for oid in ids:
            self._pending[oid].status = "cancelled"
            del self._pending[oid]
        return len(ids)

    def get_pending_orders(self, symbol: str | None = None) -> list[PendingOrder]:
        if symbol is None:
            return list(self._pending.values())
        return [o for o in self._pending.values() if o.symbol == symbol]

    def get_order(self, order_id: str) -> PendingOrder | None:
        return self._pending.get(order_id)

    # ── Fee helpers ──────────────────────────────────────────────

    def fee_rate_for(self, order_type: str) -> Decimal:
        """Taker for market/stop_market, maker for limit."""
        if order_type.lower() in ("market", "stop_market"):
            return self.taker_fee
        return self.maker_fee

    # ── Fill detection ───────────────────────────────────────────

    def process_market_data(
        self,
        symbol: str,
        market_data: Any,
        get_position_amount: PositionAmountFn,
    ) -> list[FillResult]:
        """Check pending orders for *symbol* against *market_data*.

        1. Filters orders for the symbol (status in "open"/"pending").
        2. Delegates to fill_mode.check_fills().
        3. Enforces reduceOnly (caps amount, cancels if no position).
        4. Removes filled orders from storage.
        5. Returns FillResult list for the exchange to process.

        Args:
            symbol: Trading pair to scan.
            market_data: Candle dict (WickFillMode) or Decimal price (TickFillMode).
            get_position_amount: Callback returning signed position size.
        """
        eligible = [o for o in self._pending.values() if o.symbol == symbol and o.status in ("open", "pending")]
        if not eligible:
            return []

        triggered = self._fill_mode.check_fills(eligible, market_data)

        results: list[FillResult] = []
        orders_to_remove: list[str] = []

        for order, fill_price in triggered:
            fill_amount = order.amount

            if order.reduce_only:
                current_pos = get_position_amount(symbol)
                if order.side == "SELL":
                    if current_pos <= Decimal("0"):
                        orders_to_remove.append(order.id)
                        continue
                    fill_amount = min(to_decimal(order.amount), current_pos)
                elif order.side == "BUY":
                    if current_pos >= Decimal("0"):
                        orders_to_remove.append(order.id)
                        continue
                    fill_amount = min(to_decimal(order.amount), abs(current_pos))

            fee_rate = self.fee_rate_for(order.order_type)

            results.append(
                FillResult(
                    order_id=order.id,
                    symbol=order.symbol,
                    side=order.side,
                    order_type=order.order_type,
                    fill_price=fill_price,
                    fill_amount=fill_amount,
                    fee_rate=fee_rate,
                    reduce_only=order.reduce_only,
                    info=dict(order.info),
                )
            )
            orders_to_remove.append(order.id)

        for oid in orders_to_remove:
            self._pending.pop(oid, None)

        return results
