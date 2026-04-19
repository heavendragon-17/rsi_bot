# app/trading/exchange/sim/sim_fill_handler.py
"""
SimExchange fill execution logic
=================================
Module-level functions extracted from SimExchange that handle order fills,
position open/close, notification capture, and position linking helpers.

All functions receive the SimExchange instance (``sim_ex``) as their first
parameter so they can access ``sim_ex.state``, ``sim_ex._sim``, etc.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog

from app.core.constants import DEFAULT_MAKER_FEE_DECIMAL, DEFAULT_TAKER_FEE_DECIMAL
from app.trading.exchange.fill_simulator import PendingOrder
from app.trading.exchange.sim.sim_state import ClosedTrade, SimPosition

if TYPE_CHECKING:
    from app.trading.exchange.sim.sim_exchange import SimExchange

logger = structlog.get_logger()

TAKER_FEE = DEFAULT_TAKER_FEE_DECIMAL
MAKER_FEE = DEFAULT_MAKER_FEE_DECIMAL


# ── Fill entry points ─────────────────────────────────────────


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
            notify_entry = capture_entry_notification(
                sim_ex,
                order.symbol,
                fill_price,
                order.amount,
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
            notify_entry = capture_entry_notification(
                sim_ex,
                fr.symbol,
                fr.fill_price,
                fr.fill_amount,
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


# ── Position open / close (must be called under state.lock) ───


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
    pnl_net = pnl_gross - fee

    sim_ex.state.balance += pnl_net
    sim_ex.state.total_fees_paid += fee

    exit_reason = exit_reason_from_fields(order_id, order_type, reduce_only, position)

    r_multiple = (pnl_net / position.initial_risk) if position.initial_risk else Decimal("0")
    total_fees = position.entry_fee + fee
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


# ── Notification capture / emit ───────────────────────────────


def capture_entry_notification(
    sim_ex: SimExchange,
    symbol: str,
    fill_price: Decimal,
    amount: Decimal,
) -> dict | None:
    """Build an entry notification payload (caller holds the lock)."""
    signal_meta = sim_ex._pending_signal_meta.pop(symbol, {}) if hasattr(sim_ex, "_pending_signal_meta") else {}

    # Determine actual position side: prefer stashed signal side, fall back to position state.
    pos = sim_ex.state.positions.get(symbol)
    entry_side_raw = signal_meta.get("side") or (pos.side if pos else "BUY")
    side_label = "LONG" if str(entry_side_raw).upper() in ("BUY", "LONG") else "SHORT"

    # Prefer SL/TP from the originating signal (reliable: available before the SL/TP
    # orders have been placed on the exchange). Fall back to scanning pending orders
    # for callers that create_order the entry without routing through trade_executor.
    _sl_price: Decimal | None = signal_meta.get("sl_price")
    _tp_prices: dict[str, Decimal] | None = signal_meta.get("tp_prices")

    if _sl_price is None or not _tp_prices:
        exit_side = "SELL" if side_label == "LONG" else "BUY"
        scanned_tp: list[Decimal] = []
        for o in sim_ex._sim.get_pending_orders(symbol):
            if o.side != exit_side:
                continue
            if _sl_price is None and o.order_type == "stop_market" and o.trigger_price:
                _sl_price = o.trigger_price
            elif o.order_type == "limit" and o.price:
                scanned_tp.append(o.price)
        if not _tp_prices and scanned_tp:
            # Sort by distance from entry so TP1 is the nearest target.
            scanned_tp.sort(reverse=(side_label == "SHORT"))
            _tp_prices = {f"TP{i + 1}": p for i, p in enumerate(scanned_tp[:3])}

    indicators = pos.indicators if pos else None
    entry_fee = pos.entry_fee if pos else Decimal("0")

    return {
        "symbol": symbol,
        "side": side_label,
        "entry_price": fill_price,
        "amount": amount,
        "balance": sim_ex.state.balance,
        "sl_price": _sl_price,
        "tp_prices": _tp_prices,
        "indicators": indicators,
        "entry_fee": entry_fee,
        "reason": signal_meta.get("reason"),
        "soft_sl_price": signal_meta.get("soft_sl_price"),
        "lock_profit_price": signal_meta.get("lock_profit_price"),
        "tp_allocations": signal_meta.get("tp_allocations"),
        "signal_class": signal_meta.get("signal_class"),
        "risk_per_trade_pct": signal_meta.get("risk_per_trade_pct"),
    }


def emit_notifications(
    sim_ex: SimExchange,
    notify_entry: dict | None,
    notify_fill: tuple | None,
) -> None:
    """Dispatch entry/fill notifications to the notification service."""
    if notify_entry and sim_ex._notification_service:
        leverage = sim_ex._config.get("risk", {}).get("leverage", 1)
        try:
            sim_ex._notification_service.on_entry(
                symbol=notify_entry["symbol"],
                side=notify_entry["side"],
                entry_price=notify_entry["entry_price"],
                amount=notify_entry["amount"],
                sl_price=notify_entry["sl_price"],
                tp_prices=notify_entry["tp_prices"],
                leverage=leverage,
                balance=notify_entry["balance"],
                indicators=notify_entry["indicators"],
                entry_fee=notify_entry["entry_fee"],
                reason=notify_entry.get("reason"),
                soft_sl_price=notify_entry.get("soft_sl_price"),
                lock_profit_price=notify_entry.get("lock_profit_price"),
                tp_allocations=notify_entry.get("tp_allocations"),
                signal_class=notify_entry.get("signal_class"),
                risk_per_trade_pct=notify_entry.get("risk_per_trade_pct"),
            )
        except Exception:
            logger.exception("notification on_entry failed")

    if notify_fill and sim_ex._notification_service:
        (
            sym, reason, fp, amt, pnl_g, pnl_n, fees, r_mult, rem, bal,
            entry_price, total_fees, hold_duration, return_pct,
        ) = notify_fill
        try:
            sim_ex._notification_service.on_fill(
                symbol=sym,
                exit_reason=reason,
                fill_price=fp,
                amount=amt,
                pnl_gross=pnl_g,
                pnl_net=pnl_n,
                fees=fees,
                r_multiple=r_mult,
                remaining_amount=rem,
                balance=bal,
                entry_price=entry_price,
                total_fees=total_fees,
                hold_duration=hold_duration,
                return_pct=return_pct,
            )
        except Exception:
            logger.exception("notification on_fill failed")


# ── Position metadata helpers ─────────────────────────────────


def link_sl_to_position(
    sim_ex: SimExchange,
    symbol: str,
    sl_order_id: str,
    sl_price: Decimal,
) -> None:
    """Attach SL order ID and compute initial_risk on the position."""
    with sim_ex.state.lock:
        pos = sim_ex.state.positions.get(symbol)
        if pos:
            pos.sl_order_id = sl_order_id
            if pos.initial_risk == Decimal("0"):
                pos.initial_risk = abs(pos.entry_price - sl_price) * pos.initial_amount


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
    """Determine the exit reason string from order fields and position state."""
    if order_type == "stop_market":
        return "HARD_SL"
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
