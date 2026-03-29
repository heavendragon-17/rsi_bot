"""
WickFillMode — Candle-OHLC trigger logic for backtest fill simulation.
======================================================================
Extracted from fill_simulator.py to satisfy file-size and class-count limits.
"""

from __future__ import annotations

from decimal import Decimal

from app.trading.exchange.fill_simulator import FillMode, PendingOrder

# Phase 1.3: check if JIT fill matching is available
try:
    from app.backtest.engine.jit_functions import HAS_NUMBA as _HAS_JIT_FILLS
except ImportError:
    _HAS_JIT_FILLS = False


class WickFillMode(FillMode):
    """Candle-OHLC trigger logic (backtest).

    Trigger rules (matching real exchange wick-fill semantics):
      SELL stop_market  → low  <= trigger_price   (SL long)
      SELL limit        → high >= trigger_price    (TP long)
      SELL stop_limit   → low  <= trigger_price    (fill at limit_price)
      SELL trailing_stop→ peak tracking + callback
      BUY  limit        → low  <= trigger_price    (TP short)
      BUY  stop_market  → high >= trigger_price    (SL short)

    Phase 1.3: uses Numba JIT for the numeric comparison kernel when
    available, falling back to pure Python for trailing_stop orders
    (which require mutable peak tracking).
    """

    def check_fills(
        self,
        orders: list[PendingOrder],
        market_data: dict[str, Decimal],
    ) -> list[tuple[PendingOrder, Decimal]]:
        high = market_data["high"]
        low = market_data["low"]

        if not orders:
            return []

        # Separate trailing_stop (needs Python peak tracking) from JIT-able orders
        jit_orders: list[PendingOrder] = []
        trailing_orders: list[PendingOrder] = []
        for order in orders:
            if order.order_type == "trailing_stop":
                trailing_orders.append(order)
            else:
                jit_orders.append(order)

        fills: list[tuple[PendingOrder, Decimal]] = []

        # Phase 1.3: JIT fast path for non-trailing orders
        if jit_orders and _HAS_JIT_FILLS:
            fills.extend(self._check_fills_jit(jit_orders, high, low))
        elif jit_orders:
            fills.extend(self._check_fills_python(jit_orders, high, low))

        # Trailing stop: always Python (mutable peak tracking)
        for order in trailing_orders:
            fp = self._check_trailing(order, high, low)
            if fp is not None:
                fills.append((order, fp))

        return fills

    @staticmethod
    def _check_fills_python(
        orders: list[PendingOrder],
        high: Decimal,
        low: Decimal,
    ) -> list[tuple[PendingOrder, Decimal]]:
        """Pure-Python fill checking (fallback)."""
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
    def _check_fills_jit(
        orders: list[PendingOrder],
        high: Decimal,
        low: Decimal,
    ) -> list[tuple[PendingOrder, Decimal]]:
        """JIT-accelerated fill checking via pre-extracted float64 arrays."""
        import numpy as np

        from app.backtest.engine.jit_functions import (
            OT_MAP,
            SIDE_MAP,
            check_fills_jit,
        )

        n = len(orders)
        trigger_prices = np.empty(n, dtype=np.float64)
        limit_prices = np.empty(n, dtype=np.float64)
        sides = np.empty(n, dtype=np.int8)
        order_types = np.empty(n, dtype=np.int8)

        for i, order in enumerate(orders):
            tp = order.trigger_price or order.price
            trigger_prices[i] = float(tp) if tp is not None else 0.0
            limit_prices[i] = float(order.limit_price or tp or 0)
            sides[i] = SIDE_MAP.get(order.side, 0)
            order_types[i] = OT_MAP.get(order.order_type, 0)

        filled_mask, fill_prices = check_fills_jit(
            trigger_prices, limit_prices, sides, order_types,
            float(high), float(low),
        )

        fills: list[tuple[PendingOrder, Decimal]] = []
        for i in range(n):
            if filled_mask[i]:
                fills.append((orders[i], Decimal(str(fill_prices[i]))))
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
