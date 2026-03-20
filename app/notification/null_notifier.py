"""
Null Object pattern for notifications.
Used when Telegram is disabled or fails to initialize.
Silently discards all notification calls — bot continues normally.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Optional

from app.core.interfaces import INotifier


class NullNotifier(INotifier):
    """No-op notifier. All methods silently do nothing."""

    def send_message(self, message: str) -> None:
        pass

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
        pass

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
        pass

    def on_error(self, context: str, error: str) -> None:
        pass

    def on_funding(self, symbol: str, rate: Decimal, payment: Decimal, balance: Decimal) -> None:
        pass

    def on_toggle(self, is_paused: bool) -> None:
        pass
