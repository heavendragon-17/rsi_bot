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

from app.core.interfaces import IExchange, INotifier
from app.notification.notification_worker import NotificationWorker


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

    def attach_exchange(self, exchange: IExchange) -> None:
        """Attach exchange to underlying notifier for command handling."""
        if hasattr(self._notifier, "attach_exchange"):
            self._notifier.attach_exchange(exchange)

    def start_command_polling(
        self,
        extra_callbacks: dict | None = None,
        update_observer=None,
    ) -> None:
        """Start the Telegram polling loop.

        ``extra_callbacks`` is forwarded to the underlying notifier so signal
        mode can register runtime-bound commands (e.g. ``/test_signal``).
        ``update_observer`` receives raw Telegram updates for lightweight
        operator inventories such as observed forum topics.
        """
        if hasattr(self._notifier, "start_command_polling"):
            self._notifier.start_command_polling(
                extra_callbacks=extra_callbacks,
                update_observer=update_observer,
            )

    def report_notification_failure(
        self,
        method_name: str,
        *,
        topic_id: int | None = None,
        reason: str,
    ) -> None:
        """Report worker failures directly through the underlying notifier."""

        reporter = getattr(self._notifier, "report_notification_failure", None)
        if callable(reporter):
            reporter(method_name, topic_id=topic_id, reason=reason)

    # ------------------------------------------------------------------
    # INotifier delegation — all calls go through the worker queue
    # ------------------------------------------------------------------

    def send_message(self, message: str, *, topic_id: int | None = None) -> None:
        self._worker.enqueue("send_message", message, topic_id=topic_id)

    def on_entry(
        self,
        symbol: str,
        side: str,
        entry_price: Decimal,
        amount: Decimal,
        sl_price: Decimal | None = None,
        tp_prices: dict[str, Decimal] | None = None,
        leverage: int = 1,
        balance: Decimal | None = None,
        indicators: dict[str, float] | None = None,
        entry_fee: Decimal | None = None,
        reason: str | None = None,
        soft_sl_price: Decimal | None = None,
        lock_profit_price: Decimal | None = None,
        tp_allocations: dict[str, float] | None = None,
        signal_class: int | None = None,
        risk_per_trade_pct: Decimal | None = None,
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
            indicators=indicators,
            entry_fee=entry_fee,
            reason=reason,
            soft_sl_price=soft_sl_price,
            lock_profit_price=lock_profit_price,
            tp_allocations=tp_allocations,
            signal_class=signal_class,
            risk_per_trade_pct=risk_per_trade_pct,
        )

    def on_fill(
        self,
        symbol: str,
        exit_reason: str,
        fill_price: Decimal,
        amount: Decimal,
        pnl_gross: Decimal | None = None,
        pnl_net: Decimal | None = None,
        fees: Decimal | None = None,
        r_multiple: Decimal | None = None,
        remaining_amount: Decimal | None = None,
        balance: Decimal | None = None,
        entry_price: Decimal | None = None,
        total_fees: Decimal | None = None,
        hold_duration: float | None = None,
        return_pct: Decimal | None = None,
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
            entry_price=entry_price,
            total_fees=total_fees,
            hold_duration=hold_duration,
            return_pct=return_pct,
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
