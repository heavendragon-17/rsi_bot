"""Tests for NotificationService wrapper (queue-based dispatch)."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.notification.notification_service import NotificationService


def _mk_service():
    notifier = MagicMock()
    with patch(
        "app.notification.notification_service.NotificationWorker"
    ) as MockWorker:
        worker_instance = MagicMock()
        MockWorker.return_value = worker_instance
        svc = NotificationService(notifier=notifier, mode="sim")
        return svc, worker_instance, notifier


class TestNotificationServiceInit:
    def test_init_starts_worker(self):
        svc, worker, notifier = _mk_service()
        worker.start.assert_called_once()

    def test_stop_calls_worker_stop(self):
        svc, worker, _ = _mk_service()
        svc.stop()
        worker.stop.assert_called_once()


class TestNotificationServiceDispatch:
    def test_send_message_enqueues(self):
        svc, worker, _ = _mk_service()
        svc.send_message("hello")
        worker.enqueue.assert_called_with("send_message", "hello", topic_id=None)

    def test_send_message_forwards_topic_id(self):
        svc, worker, _ = _mk_service()
        svc.send_message("hello", topic_id=42)
        worker.enqueue.assert_called_with("send_message", "hello", topic_id=42)

    def test_on_entry_enqueues_with_kwargs(self):
        svc, worker, _ = _mk_service()
        svc.on_entry(
            symbol="BTC",
            side="BUY",
            entry_price=Decimal("100"),
            amount=Decimal("1"),
            leverage=5,
        )
        worker.enqueue.assert_called_once()
        call = worker.enqueue.call_args
        assert call[0][0] == "on_entry"
        assert call[1]["symbol"] == "BTC"
        assert call[1]["leverage"] == 5

    def test_on_fill_enqueues(self):
        svc, worker, _ = _mk_service()
        svc.on_fill(
            symbol="BTC",
            exit_reason="TP1",
            fill_price=Decimal("110"),
            amount=Decimal("1"),
        )
        call = worker.enqueue.call_args
        assert call[0][0] == "on_fill"

    def test_on_error_enqueues(self):
        svc, worker, _ = _mk_service()
        svc.on_error("context", "oops")
        worker.enqueue.assert_called_with("on_error", context="context", error="oops")

    def test_on_funding_enqueues(self):
        svc, worker, _ = _mk_service()
        svc.on_funding(
            symbol="BTC",
            rate=Decimal("0.0001"),
            payment=Decimal("-0.1"),
            balance=Decimal("1000"),
        )
        worker.enqueue.assert_called_once()
        assert worker.enqueue.call_args[0][0] == "on_funding"

    def test_on_toggle_enqueues(self):
        svc, worker, _ = _mk_service()
        svc.on_toggle(True)
        worker.enqueue.assert_called_with("on_toggle", is_paused=True)

    def test_attach_exchange_delegates(self):
        svc, _, notifier = _mk_service()
        notifier.attach_exchange = MagicMock()
        exchange = MagicMock()
        svc.attach_exchange(exchange)
        notifier.attach_exchange.assert_called_once_with(exchange)

    def test_attach_exchange_noop_when_missing_method(self):
        svc, _, notifier = _mk_service()
        # Delete attach_exchange from notifier and ensure it doesn't crash
        del notifier.attach_exchange
        svc.attach_exchange(MagicMock())  # should no-op

    def test_start_command_polling_delegates(self):
        svc, _, notifier = _mk_service()
        notifier.start_command_polling = MagicMock()
        svc.start_command_polling()
        notifier.start_command_polling.assert_called_once()

    def test_start_command_polling_noop_when_missing(self):
        svc, _, notifier = _mk_service()
        del notifier.start_command_polling
        svc.start_command_polling()  # should no-op
