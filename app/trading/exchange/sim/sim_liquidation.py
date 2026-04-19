# app/trading/exchange/sim/sim_liquidation.py
"""
SimExchange liquidation logic
=============================
Mirrors the equity-based force-close from the backtest ``check_liquidation``
(``app/backtest/exchange/executor.py``) so that sim mode cannot report an
impossible negative balance — the bot should stop trading once account
equity hits zero, just like a real perpetual futures exchange.

Kept separate from ``sim_fill_handler`` to respect the 400-line-per-file cap
declared in ``CLAUDE.md``.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

from app.trading.exchange.sim.sim_fill_handler import (
    close_position_locked,
    emit_notifications,
)

if TYPE_CHECKING:
    from app.trading.exchange.sim.sim_exchange import SimExchange

logger = structlog.get_logger()


def check_liquidation(sim_ex: SimExchange) -> bool:
    """Force-close every position when account equity drops to zero or below.

    Sim mode does not reserve margin, so ``equity = balance + Σ unrealized PnL``
    across open positions (marked to the latest tick price). If equity ≤ 0,
    every position is closed at the current tick price, the balance is zeroed,
    pending orders are cancelled, and the state is paused so no further orders
    are accepted.
    """
    with sim_ex.state.lock:
        if not sim_ex.state.positions:
            return False
        total_upnl = Decimal("0")
        for symbol, pos in sim_ex.state.positions.items():
            last_price = sim_ex._last_prices.get(symbol, pos.entry_price)
            total_upnl += (last_price - pos.entry_price) * pos.amount
        equity = sim_ex.state.balance + total_upnl
        if equity > Decimal("0"):
            return False

        logger.warning(
            "sim_liquidation",
            balance=float(sim_ex.state.balance),
            unrealized_pnl=float(total_upnl),
            equity=float(equity),
            open_positions=len(sim_ex.state.positions),
        )

        notify_fills: list[tuple] = []
        filled_at = sim_ex._sim_time or time.time()
        for symbol in list(sim_ex.state.positions.keys()):
            pos = sim_ex.state.positions[symbol]
            if pos.amount <= Decimal("0"):
                continue
            fill_price = sim_ex._last_prices.get(symbol, pos.entry_price)
            sim_ex._sim.cancel_all_orders(symbol)
            notify = close_position_locked(
                sim_ex,
                order_id=f"liquidation_{symbol}",
                symbol=symbol,
                amount=pos.amount,
                fill_price=fill_price,
                order_type="market",
                reduce_only=True,
                filled_at=filled_at,
            )
            if notify is not None:
                notify_fills.append(_override_exit_reason(notify, "LIQUIDATION"))

        sim_ex.state.balance = Decimal("0")
        sim_ex.state.is_paused = True

    for notify in notify_fills:
        emit_notifications(sim_ex, None, notify)
    return True


def _override_exit_reason(notify: tuple, reason: str) -> tuple:
    """Replace the exit_reason slot in a close-notification tuple."""
    fields = list(notify)
    fields[1] = reason
    return tuple(fields)
