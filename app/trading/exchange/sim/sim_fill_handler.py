# app/trading/exchange/sim/sim_fill_handler.py
"""SimExchange fill execution: order fills, position open/close, notification capture.

All functions take the SimExchange instance as the first argument so they can
access ``sim_ex.state`` and ``sim_ex._sim``. Liquidation lives in
``sim_liquidation.py`` to respect the 400-line cap.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog

from app.core.constants import DEFAULT_MAKER_FEE_DECIMAL, DEFAULT_TAKER_FEE_DECIMAL
from app.trading.exchange.fill_simulator import PendingOrder
from app.trading.exchange.sim.sim_notifications import (
    capture_entry_notification,
    emit_notifications,
)
from app.trading.exchange.sim.sim_state import ClosedTrade, SimPosition

if TYPE_CHECKING:
    from app.trading.exchange.sim.sim_exchange import SimExchange

__all__ = [
    "execute_fill_from_order",
    "execute_fill_from_result",
    "open_position_locked",
    "close_position_locked",
    "capture_entry_notification",
    "emit_notifications",
    "link_sl_to_position",
    "link_tp_to_position",
    "post_fill_hook",
    "exit_reason_from_fields",
]

logger = structlog.get_logger()

TAKER_FEE = DEFAULT_TAKER_FEE_DECIMAL
MAKER_FEE = DEFAULT_MAKER_FEE_DECIMAL


def execute_fill_from_order(
    sim_ex: SimExchange,
    order: PendingOrder,
    fill_price: Decimal,
) -> None:
    """Fill a PendingOrder directly (market entries, soft SL, kline_open)."""
    notify_entry = None
    notify_fill = None

    with sim_ex.state.lock:
        if order.status in ("filled", "cancelled"):
            return
        if order.id not in sim_ex._sim.pending_orders:
            return

        order.status = "filled"
        filled_at = sim_ex._sim_time or time.time()
        sim_ex._sim.remove_order(order.id)

        if order.side == "BUY":
            fee = fill_price * order.amount * TAKER_FEE
            sim_ex.state.balance -= fee
            sim_ex.state.total_fees_paid += fee
            open_position_locked(
                sim_ex,
                order.id,
                order.symbol,
                order.amount,
                fill_price,
                filled_at,
                fee,
            )
            if getattr(sim_ex, "_fires_entry_notification", False):
                notify_entry = capture_entry_notification(
                    sim_ex, order.symbol, fill_price, order.amount
                )
        elif order.side == "SELL":
            notify_fill = close_position_locked(
                sim_ex,
                order.id,
                order.symbol,
                order.amount,
                fill_price,
                order.order_type,
                order.reduce_only,
                filled_at,
            )

    emit_notifications(sim_ex, notify_entry, notify_fill)


def execute_fill_from_result(sim_ex: SimExchange, fr: Any) -> None:
    """Fill from a FillResult produced by process_market_data."""
    notify_entry = None
    notify_fill = None

    with sim_ex.state.lock:
        filled_at = sim_ex._sim_time or time.time()

        if fr.side == "BUY":
            fee = fr.fill_price * fr.fill_amount * TAKER_FEE
            sim_ex.state.balance -= fee
            sim_ex.state.total_fees_paid += fee
            open_position_locked(
                sim_ex,
                fr.order_id,
                fr.symbol,
                fr.fill_amount,
                fr.fill_price,
                filled_at,
                fee,
            )
            if getattr(sim_ex, "_fires_entry_notification", False):
                notify_entry = capture_entry_notification(
                    sim_ex, fr.symbol, fr.fill_price, fr.fill_amount
                )
        elif fr.side == "SELL":
            notify_fill = close_position_locked(
                sim_ex,
                fr.order_id,
                fr.symbol,
                fr.fill_amount,
                fr.fill_price,
                fr.order_type,
                fr.reduce_only,
                filled_at,
            )
            post_fill_hook(
                sim_ex,
                fr.order_id,
                fr.symbol,
                fr.order_type,
                fr.reduce_only,
            )

    emit_notifications(sim_ex, notify_entry, notify_fill)


def open_position_locked(
    sim_ex: SimExchange,
    order_id: str,
    symbol: str,
    amount: Decimal,
    fill_price: Decimal,
    filled_at: float,
    entry_fee: Decimal,
) -> None:
    """Create a new SimPosition in state (caller holds the lock)."""
    pending = getattr(sim_ex, "_pending_indicators", {})
    indicators = pending.pop(symbol, None) if pending else None
    pos = SimPosition(
        symbol=symbol,
        side="long",
        amount=amount,
        entry_price=fill_price,
        initial_amount=amount,
        initial_risk=Decimal("0"),
        indicators=indicators,
        entry_fee=entry_fee,
        opened_at=filled_at,
    )
    sim_ex.state.positions[symbol] = pos
    logger.info(f"[SimExchange] Position opened — {symbol} {amount} @ {fill_price}")


def close_position_locked(
    sim_ex: SimExchange,
    order_id: str,
    symbol: str,
    amount: Decimal,
    fill_price: Decimal,
    order_type: str,
    reduce_only: bool,
    filled_at: float,
) -> tuple | None:
    """Close (fully or partially) an existing position (caller holds the lock)."""
    position = sim_ex.state.positions.get(symbol)
    if not position:
        return None

    close_amount = min(amount, position.amount)
    if close_amount <= 0:
        return None

    fee = fill_price * close_amount * (MAKER_FEE if order_type == "limit" else TAKER_FEE)
    pnl_gross = (fill_price - position.entry_price) * close_amount
    # Entry fee was debited from balance at open. Pro-rate it for partial closes
    # so the displayed Net P&L matches the *true* lifecycle net (gross − entry − exit fees),
    # which is the figure ``compute_price_at_rr`` targets when pricing TPs/lock-profit.
    entry_fee_slice = (
        position.entry_fee * (close_amount / position.initial_amount) if position.initial_amount > 0 else Decimal("0")
    )
    pnl_net = pnl_gross - fee - entry_fee_slice

    # Balance only changes by (gross − exit fee) at close: the entry fee was
    # already taken out at open, so don't double-charge it here.
    sim_ex.state.balance += pnl_gross - fee
    sim_ex.state.total_fees_paid += fee

    exit_reason = exit_reason_from_fields(order_id, order_type, reduce_only, position)

    r_multiple = (pnl_net / position.initial_risk) if position.initial_risk else Decimal("0")
    # Pro-rate entry fee for this close slice so partial-close notifications
    # show the true fee cost of the portion being closed (not the full position).
    total_fees = entry_fee_slice + fee
    hold_duration = (filled_at - position.opened_at) if position.opened_at > 0 else 0.0
    notional = position.entry_price * close_amount
    return_pct = (pnl_net / notional * 100) if notional else Decimal("0")

    trade = ClosedTrade(
        symbol=symbol,
        entry_price=position.entry_price,
        exit_price=fill_price,
        amount=close_amount,
        side="long",
        pnl_gross=pnl_gross,
        fees_paid=fee,
        funding_paid=Decimal("0"),
        pnl_net=pnl_net,
        r_multiple=r_multiple,
        exit_reason=exit_reason,
        opened_at=position.opened_at,
        closed_at=filled_at,
    )

    position.amount -= close_amount
    remaining = position.amount
    if position.amount <= Decimal("0.000001"):
        del sim_ex.state.positions[symbol]
    sim_ex.state.closed_trades.append(trade)

    balance_after = sim_ex.state.balance
    return (
        symbol,
        exit_reason,
        fill_price,
        close_amount,
        pnl_gross,
        pnl_net,
        fee,
        r_multiple,
        remaining if remaining > Decimal("0.000001") else Decimal("0"),
        balance_after,
        position.entry_price,
        total_fees,
        hold_duration,
        return_pct,
    )


# Notification capture / emit live in sim_notifications.py — imported at top.


def link_sl_to_position(
    sim_ex: SimExchange,
    symbol: str,
    sl_order_id: str,
    sl_price: Decimal,
    risk_sl_price: Decimal | None = None,
) -> None:
    """Attach SL order ID and compute initial_risk on the position.

    ``risk_sl_price`` should be the *soft* SL used for position sizing (so
    ``initial_risk ≈ risk_per_trade_pct × capital`` and R-multiples are
    correct); if ``None``, falls back to the stop_market trigger (``sl_price``).
    A replacement SL order marks ``moved_sl=True`` so later exits are labelled
    MOVED_SL(_PROFIT) rather than HARD_SL.
    """
    with sim_ex.state.lock:
        pos = sim_ex.state.positions.get(symbol)
        if not pos:
            return
        if pos.sl_order_id is not None and pos.sl_order_id != sl_order_id:
            pos.moved_sl = True
        pos.sl_order_id = sl_order_id
        if pos.initial_risk == Decimal("0"):
            risk_ref = risk_sl_price if risk_sl_price is not None else sl_price
            pos.initial_risk = abs(pos.entry_price - risk_ref) * pos.initial_amount


def link_tp_to_position(
    sim_ex: SimExchange,
    symbol: str,
    tp_label: str,
    tp_order_id: str,
) -> None:
    """Attach TP order ID to the position."""
    with sim_ex.state.lock:
        pos = sim_ex.state.positions.get(symbol)
        if pos:
            pos.tp_order_ids[tp_label] = tp_order_id


def post_fill_hook(
    sim_ex: SimExchange,
    order_id: str,
    symbol: str,
    order_type: str,
    reduce_only: bool,
) -> None:
    """Mark TP1/TP2 hit flags on the position after a partial close."""
    pos = sim_ex.state.positions.get(symbol)
    if not pos:
        return
    exit_reason = exit_reason_from_fields(order_id, order_type, reduce_only, pos)
    if exit_reason == "TP1":
        pos.tp1_hit = True
    elif exit_reason == "TP2":
        pos.tp2_hit = True


def exit_reason_from_fields(
    order_id: str,
    order_type: str,
    reduce_only: bool,
    position: SimPosition,
) -> str:
    """Resolve exit reason from order fields and position state.

    A stop_market fill after the SL has been replaced (``position.moved_sl``) is
    reported as MOVED_SL — the strategy only moves the stop to a lock-profit
    level, so such an exit is always at or above entry by construction.
    """
    if order_type == "stop_market":
        return "MOVED_SL" if position.moved_sl else "HARD_SL"
    if order_type == "market" and reduce_only:
        return "CANDLE_SL"
    for label, oid in position.tp_order_ids.items():
        if oid == order_id:
            return label
    if not position.tp1_hit:
        return "TP1"
    if not position.tp2_hit:
        return "TP2"
    return "TP3"
