"""
Null Object pattern for notifications.
Used when Telegram is disabled or fails to initialize.
Silently discards all notification calls — bot continues normally.
"""

from __future__ import annotations

from decimal import Decimal

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
        sl_price: Decimal | None = None,
        tp_prices: dict[str, Decimal] | None = None,
        leverage: int = 1,
        balance: Decimal | None = None,
        indicators: dict[str, float] | None = None,
        entry_fee: Decimal | None = None,
    ) -> None:
        pass

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
        pass

    def on_error(self, context: str, error: str) -> None:
        pass

    def on_funding(self, symbol: str, rate: Decimal, payment: Decimal, balance: Decimal) -> None:
        pass

    def on_toggle(self, is_paused: bool) -> None:
        pass
