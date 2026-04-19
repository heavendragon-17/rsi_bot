"""Notification dispatch for portfolio events."""

from __future__ import annotations

from decimal import Decimal

import structlog

from app.core.actions import SIDE_BUY
from app.core.constants import DEFAULT_TAKER_FEE_DECIMAL
from app.core.events import SignalEvent

logger = structlog.get_logger()


class NotificationDispatcher:
    """Dispatches entry/exit notifications, respecting exchange notification flags."""

    def __init__(self, notification_service, exchange):
        self._notification_service = notification_service
        self._exchange = exchange

    def notify_entry(
        self,
        symbol: str,
        entry_side: str,
        price: Decimal,
        amount: Decimal,
        signal: SignalEvent,
        leverage: int,
        balance: Decimal,
    ) -> None:
        """Send entry notification unless exchange fires its own."""
        if not self._notification_service:
            return
        if getattr(self._exchange, "_fires_entry_notification", False):
            return

        notif_side = "LONG" if entry_side == SIDE_BUY else "SHORT"
        tp_prices = {
            k: v
            for k, v in [("TP1", signal.tp1_price), ("TP2", signal.tp2_price), ("TP3", signal.tp3_price)]
            if v is not None
        }
        entry_fee = price * amount * DEFAULT_TAKER_FEE_DECIMAL

        # Prefer the soft SL (risk-sizing level) so the card's SL % and Risk
        # match the configured risk_per_trade_pct; fall back to the disaster
        # stop if the strategy doesn't provide a soft SL.
        display_sl = getattr(signal, "soft_sl_price", None) or signal.sl_price

        try:
            self._notification_service.on_entry(
                symbol=symbol,
                side=notif_side,
                entry_price=price,
                amount=amount,
                sl_price=display_sl,
                tp_prices=tp_prices or None,
                leverage=leverage,
                balance=balance,
                indicators=signal.indicators,
                entry_fee=entry_fee,
            )
        except Exception:
            logger.warning(f"[{symbol}] on_entry notification failed")

    def notify_exit(
        self,
        symbol: str,
        exit_reason: str,
        fill_price: Decimal,
        amount: Decimal,
    ) -> None:
        """Send exit/fill notification unless exchange fires its own."""
        if not self._notification_service:
            return
        if getattr(self._exchange, "_fires_fill_notification", False):
            return

        try:
            self._notification_service.on_fill(
                symbol=symbol,
                exit_reason=exit_reason,
                fill_price=fill_price,
                amount=amount,
            )
        except Exception:
            logger.warning(f"[{symbol}] on_fill notification failed")
