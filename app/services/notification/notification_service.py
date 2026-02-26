"""
NotificationService
===================
Thin wrapper around an INotifier that:
  1. Routes all calls through a background NotificationWorker queue
     so trading threads are never blocked.
  2. Exposes .stop() for graceful queue drain on shutdown.

Usage:
    ns = NotificationService(TelegramNotifier(mode="sim"), mode="sim")
    ns.on_entry(...)      # non-blocking, enqueued
    ns.stop()             # drain & join worker thread
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Optional

from app.core.interfaces import INotifier
from app.services.notification.notification_worker import NotificationWorker


class NotificationService(INotifier):
    """
    Wraps an INotifier with a background worker queue.
    All notification calls are enqueued and dispatched asynchronously.
    """

    def __init__(self, notifier: INotifier, mode: str = "sim"):
        self._notifier = notifier
        self._mode = mode
        self._worker = NotificationWorker(notifier)
        self._worker.start()

    def stop(self) -> None:
        """Stop the background worker (drains queue up to 30 s)."""
        self._worker.stop()

    # ------------------------------------------------------------------
    # INotifier delegation — all calls go through the worker queue
    # ------------------------------------------------------------------

    def send_message(self, message: str) -> None:
        self._worker.enqueue("send_message", message)

    def on_entry(
        self,
        symbol: str,
        side: str,
        entry_price: Decimal,
        amount: Decimal,
        sl_price: Optional[Decimal] = None,
        tp_prices: Optional[Dict[str, Decimal]] = None,
        leverage: int = 1,
        balance: Optional[Decimal] = None,
    ) -> None:
        self._worker.enqueue(
            "on_entry",
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            amount=amount,
            sl_price=sl_price,
            tp_prices=tp_prices,
            leverage=leverage,
            balance=balance,
        )

    def on_fill(
        self,
        symbol: str,
        exit_reason: str,
        fill_price: Decimal,
        amount: Decimal,
        pnl_gross: Optional[Decimal] = None,
        pnl_net: Optional[Decimal] = None,
        fees: Optional[Decimal] = None,
        r_multiple: Optional[Decimal] = None,
        remaining_amount: Optional[Decimal] = None,
        balance: Optional[Decimal] = None,
    ) -> None:
        self._worker.enqueue(
            "on_fill",
            symbol=symbol,
            exit_reason=exit_reason,
            fill_price=fill_price,
            amount=amount,
            pnl_gross=pnl_gross,
            pnl_net=pnl_net,
            fees=fees,
            r_multiple=r_multiple,
            remaining_amount=remaining_amount,
            balance=balance,
        )

    def on_error(self, context: str, error: str) -> None:
        self._worker.enqueue("on_error", context=context, error=error)

    def on_funding(
        self,
        symbol: str,
        rate: Decimal,
        payment: Decimal,
        balance: Decimal,
    ) -> None:
        self._worker.enqueue(
            "on_funding",
            symbol=symbol,
            rate=rate,
            payment=payment,
            balance=balance,
        )

    def on_toggle(self, is_paused: bool) -> None:
        self._worker.enqueue("on_toggle", is_paused=is_paused)
