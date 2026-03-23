"""SL/TP placement, movement, tracking, and partial close logic."""

from __future__ import annotations

from decimal import Decimal

import structlog

from app.core.actions import (
    EXIT_BREAKEVEN,
    EXIT_LOCK_PROFIT,
    EXIT_STOP_LOSS,
    SIDE_BUY,
    opposite_side,
)
from app.core.events import SignalEvent
from app.core.exceptions import ExchangeError
from app.core.interfaces import IExchange
from app.core.utils import to_decimal
from app.trading.portfolio.models import Position

logger = structlog.get_logger()


class SLTPManager:
    """Manages SL/TP order placement, movement, fill sync, and partial closes."""

    def __init__(self, exchange: IExchange, config: dict):
        self.exchange = exchange

        risk_cfg = config.get("risk", {})
        self.tp1_close_pct = Decimal(str(risk_cfg.get("tp1_close_pct", 0.50)))
        self.tp2_close_pct = Decimal(str(risk_cfg.get("tp2_close_pct", 0.50)))

    def place_tp_orders(
        self, signal: SignalEvent, total_amount: Decimal, position_side: str = SIDE_BUY
    ) -> dict[str, str]:
        """Place TP1/TP2/TP3 as limit orders with reduceOnly=True."""
        tp_order_ids: dict[str, str] = {}
        remaining = total_amount
        exit_side = opposite_side(position_side)
        allocs = signal.tp_allocations or {}

        levels = [
            ("TP1", signal.tp1_price, Decimal(str(allocs.get("TP1", self.tp1_close_pct)))),
            ("TP2", signal.tp2_price, Decimal(str(allocs.get("TP2", self.tp2_close_pct)))),
            ("TP3", signal.tp3_price, Decimal("1.0")),
        ]

        for label, tp_price, pct in levels:
            if tp_price is None or remaining <= Decimal("0"):
                continue

            close_amount = remaining * pct
            if close_amount <= Decimal("0"):
                continue

            try:
                order = self.exchange.create_order(
                    symbol=signal.symbol,
                    order_type="limit",
                    side=exit_side,
                    amount=close_amount,
                    price=tp_price,
                    params={"reduceOnly": True, "exit_reason": label},
                )
                if order and order.get("id"):
                    tp_order_ids[label] = order["id"]
            except Exception as e:
                logger.error(f"Failed to place {label} order for {signal.symbol}: {e}")

            remaining -= close_amount

        return tp_order_ids

    def move_sl(
        self,
        symbol: str,
        positions: dict[str, Position],
        new_price: Decimal = None,
        new_amount: Decimal = None,
    ) -> bool:
        """Cancel existing SL and replace with stop_market at target price."""
        if symbol not in positions:
            return False

        pos = positions[symbol]
        if abs(pos.amount) <= Decimal("0"):
            return False

        target_price = new_price if new_price is not None else pos.entry_price
        amount = new_amount if new_amount is not None else abs(pos.amount)

        if pos.sl_order_id:
            try:
                self.exchange.cancel_order(pos.sl_order_id, symbol)
            except Exception:
                pass
            pos.sl_order_id = None

        try:
            sl_order = self.exchange.create_order(
                symbol=symbol,
                order_type="stop_market",
                side=pos.exit_side,
                amount=amount,
                params={
                    "stopPrice": target_price,
                    "reduceOnly": True,
                    "exit_reason": self.sl_exit_reason(target_price, pos.entry_price, pos.side),
                },
            )
            if sl_order:
                pos.sl_order_id = sl_order.get("id")
                logger.info(f"[{symbol}] SL moved to {target_price} (stop_market, reduceOnly, side={pos.exit_side})")
                return True
        except Exception as e:
            logger.error(f"Failed to place SL for {symbol}: {e}")

        return False

    @staticmethod
    def sl_exit_reason(sl_price: Decimal, entry_price: Decimal, position_side: str = SIDE_BUY) -> str:
        if sl_price == entry_price:
            return EXIT_BREAKEVEN
        in_profit = sl_price > entry_price if position_side == SIDE_BUY else sl_price < entry_price
        return EXIT_LOCK_PROFIT if in_profit else EXIT_STOP_LOSS

    def sync_tp_fills(self, symbol: str, positions: dict[str, Position]) -> None:
        """Check if any TP orders have filled. Update position accordingly."""
        if symbol not in positions:
            return

        pos = positions[symbol]

        for tp_level, order_id in list(pos.tp_order_ids.items()):
            try:
                order = self.exchange.fetch_order(order_id, symbol)
                if order.get("status") in ("closed", "filled"):
                    filled_amount = to_decimal(order.get("filled", order.get("amount", 0)))
                    if pos.is_long():
                        pos.amount -= filled_amount
                    else:
                        pos.amount += filled_amount
                    setattr(pos, f"{tp_level.lower()}_hit", True)
                    del pos.tp_order_ids[tp_level]

                    logger.info(f"[{symbol}] {tp_level} filled: {filled_amount}, remaining: {pos.amount}")

                    has_remaining = abs(pos.amount) > Decimal("0")
                    if tp_level == "TP1" and has_remaining:
                        self.move_sl(symbol, positions)
            except Exception as e:
                logger.warning(f"Failed to check {tp_level} order {order_id}: {e}")

        if abs(pos.amount) <= Decimal("1e-8"):
            self.cleanup_position(symbol, positions)

    def cleanup_position(self, symbol: str, positions: dict[str, Position]) -> None:
        """Cancel remaining orders and remove position from tracking."""
        pos = positions.get(symbol)
        if not pos:
            return

        if pos.sl_order_id:
            try:
                self.exchange.cancel_order(pos.sl_order_id, symbol)
            except Exception:
                pass

        for _tp_level, order_id in list(pos.tp_order_ids.items()):
            try:
                self.exchange.cancel_order(order_id, symbol)
            except Exception:
                pass

        positions.pop(symbol, None)

    def execute_partial_close(
        self,
        symbol: str,
        positions: dict[str, Position],
        tp_level: str,
        new_sl_price: Decimal | None = None,
        exchange_sync_fn=None,
    ):
        """Execute partial close for TP levels (manual override)."""
        if exchange_sync_fn:
            exchange_sync_fn()

        if symbol not in positions:
            return None

        pos = positions[symbol]
        tp_level = tp_level.upper().strip()

        if tp_level == "TP1" and pos.tp1_hit:
            if new_sl_price and abs(pos.amount) > Decimal("0"):
                self.move_sl(symbol, positions, new_sl_price)
            return None
        if tp_level == "TP2" and pos.tp2_hit:
            return None
        if tp_level == "TP3" and pos.tp3_hit:
            return None

        allocs = pos.tp_allocations or {}
        abs_amount = abs(pos.amount)
        close_amount = Decimal("0")

        if tp_level == "TP1":
            pct = Decimal(str(allocs.get("TP1", self.tp1_close_pct)))
            close_amount = abs_amount * pct
            pos.tp1_hit = True
        elif tp_level == "TP2":
            pct = Decimal(str(allocs.get("TP2", self.tp2_close_pct)))
            close_amount = abs_amount * pct
            pos.tp2_hit = True
        elif tp_level == "TP3":
            pct = Decimal(str(allocs.get("TP3", "1.0")))
            close_amount = abs_amount * pct
            pos.tp3_hit = True

        if close_amount <= Decimal("0"):
            return None

        tp_order_id = pos.tp_order_ids.pop(tp_level, None)
        if tp_order_id:
            try:
                self.exchange.cancel_order(tp_order_id, symbol)
            except Exception:
                pass

        try:
            order = self.exchange.create_order(
                symbol=symbol,
                order_type="market",
                side=pos.exit_side,
                amount=close_amount,
                params={"reduceOnly": True, "exit_reason": tp_level},
            )
            if not order:
                return None
        except ExchangeError as e:
            logger.error(f"Failed to execute partial close {tp_level} for {symbol}: {e}")
            return None

        if pos.is_long():
            pos.amount -= close_amount
        else:
            pos.amount += close_amount

        if abs(pos.amount) > Decimal("0"):
            self.move_sl(symbol, positions, new_price=new_sl_price)

        if abs(pos.amount) <= Decimal("1e-8"):
            self.cleanup_position(symbol, positions)

        return order
