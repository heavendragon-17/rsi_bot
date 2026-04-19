# app/trading/exchange/sim/sim_notifications.py
"""
SimExchange notification capture & dispatch
============================================
Pure functions that build entry-notification payloads from sim state and
forward entry/fill notifications to the configured ``INotifier``.

Extracted from ``sim_fill_handler`` to keep that module under the 400-line
arch-lint limit and to isolate the side-effecting dispatch path from fill
execution logic.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.trading.exchange.sim.sim_exchange import SimExchange

logger = structlog.get_logger()


def capture_entry_notification(
    sim_ex: SimExchange,
    symbol: str,
    fill_price: Decimal,
    amount: Decimal,
) -> dict | None:
    """Build an entry notification payload (caller holds the lock)."""
    signal_meta = (
        sim_ex._pending_signal_meta.pop(symbol, {})
        if hasattr(sim_ex, "_pending_signal_meta")
        else {}
    )

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
