"""Tests for NotificationDispatcher (M12 coverage gap)."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.core.actions import SIDE_BUY, SIDE_SELL
from app.core.events import SignalEvent
from app.trading.portfolio.notification_dispatch import NotificationDispatcher


def _make_signal():
    return SignalEvent(
        symbol="BTC/USDT",
        signal_type="BUY",
        price=Decimal("100"),
        timestamp=datetime.now(),
        tp1_price=Decimal("110"),
        tp2_price=Decimal("120"),
        sl_price=Decimal("90"),
    )


@pytest.fixture
def mock_notifier():
    return MagicMock()


@pytest.fixture
def mock_exchange():
    ex = MagicMock()
    ex._fires_entry_notification = False
    ex._fires_fill_notification = False
    return ex


class TestNullNotifierPath:
    def test_none_notification_service_entry(self):
        d = NotificationDispatcher(None, MagicMock())
        # Should return silently, no exception
        d.notify_entry("BTC/USDT", SIDE_BUY, Decimal("100"), Decimal("1"), _make_signal(), 10, Decimal("10000"))

    def test_none_notification_service_exit(self):
        d = NotificationDispatcher(None, MagicMock())
        d.notify_exit("BTC/USDT", "STOP_LOSS", Decimal("95"), Decimal("1"))


class TestNotifierFailure:
    def test_entry_failure_does_not_crash(self, mock_notifier, mock_exchange):
        mock_notifier.on_entry.side_effect = RuntimeError("Telegram down")
        d = NotificationDispatcher(mock_notifier, mock_exchange)

        # Should NOT raise
        d.notify_entry("BTC/USDT", SIDE_BUY, Decimal("100"), Decimal("1"), _make_signal(), 10, Decimal("10000"))

    def test_exit_failure_does_not_crash(self, mock_notifier, mock_exchange):
        mock_notifier.on_fill.side_effect = RuntimeError("Telegram down")
        d = NotificationDispatcher(mock_notifier, mock_exchange)

        d.notify_exit("BTC/USDT", "TP1", Decimal("110"), Decimal("1"))


class TestExchangeFiresOwn:
    def test_entry_skipped_when_exchange_fires_own(self, mock_notifier, mock_exchange):
        mock_exchange._fires_entry_notification = True
        d = NotificationDispatcher(mock_notifier, mock_exchange)

        d.notify_entry("BTC/USDT", SIDE_BUY, Decimal("100"), Decimal("1"), _make_signal(), 10, Decimal("10000"))
        mock_notifier.on_entry.assert_not_called()

    def test_exit_skipped_when_exchange_fires_own(self, mock_notifier, mock_exchange):
        mock_exchange._fires_fill_notification = True
        d = NotificationDispatcher(mock_notifier, mock_exchange)

        d.notify_exit("BTC/USDT", "TP1", Decimal("110"), Decimal("1"))
        mock_notifier.on_fill.assert_not_called()


class TestSideFormatting:
    def test_buy_becomes_long(self, mock_notifier, mock_exchange):
        d = NotificationDispatcher(mock_notifier, mock_exchange)
        d.notify_entry("BTC/USDT", SIDE_BUY, Decimal("100"), Decimal("1"), _make_signal(), 10, Decimal("10000"))
        assert mock_notifier.on_entry.call_args.kwargs["side"] == "LONG"

    def test_sell_becomes_short(self, mock_notifier, mock_exchange):
        d = NotificationDispatcher(mock_notifier, mock_exchange)
        d.notify_entry("BTC/USDT", SIDE_SELL, Decimal("100"), Decimal("1"), _make_signal(), 10, Decimal("10000"))
        assert mock_notifier.on_entry.call_args.kwargs["side"] == "SHORT"
