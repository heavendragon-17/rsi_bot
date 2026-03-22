"""Tests for NotificationWorker (M16 coverage gap)."""

import time
from unittest.mock import MagicMock, call

from app.notification.notification_worker import NotificationWorker
from app.notification.null_notifier import NullNotifier


class TestQueueOrder:
    def test_processes_in_fifo_order(self):
        notifier = MagicMock()
        worker = NotificationWorker(notifier, max_queue_size=10)
        worker.start()

        worker.enqueue("send_message", "first")
        worker.enqueue("send_message", "second")
        worker.enqueue("send_message", "third")

        worker.stop()

        calls = notifier.send_message.call_args_list
        assert len(calls) == 3
        assert calls[0] == call("first")
        assert calls[1] == call("second")
        assert calls[2] == call("third")


class TestExceptionHandling:
    def test_worker_continues_after_exception(self):
        notifier = MagicMock()
        notifier.on_entry.side_effect = RuntimeError("boom")
        worker = NotificationWorker(notifier, max_queue_size=10)
        worker.start()

        worker.enqueue("on_entry", "BTC/USDT")
        worker.enqueue("send_message", "after error")

        worker.stop()

        notifier.on_entry.assert_called_once()
        notifier.send_message.assert_called_once_with("after error")


class TestNullNotifier:
    def test_null_notifier_completes_cleanly(self):
        notifier = NullNotifier()
        worker = NotificationWorker(notifier, max_queue_size=10)
        worker.start()

        worker.enqueue("send_message", "hello")
        worker.enqueue("on_entry", symbol="BTC/USDT", side="LONG", entry_price=100, amount=1)

        worker.stop()
        # No exception = pass


class TestFullQueue:
    def test_full_queue_drops_silently(self):
        notifier = MagicMock()
        # Slow method to keep queue full
        notifier.send_message.side_effect = lambda msg: time.sleep(0.1)
        worker = NotificationWorker(notifier, max_queue_size=1)
        worker.start()

        # Rapidly enqueue more than capacity
        for i in range(5):
            worker.enqueue("send_message", f"msg-{i}")

        worker.stop()

        # Some messages were processed, some dropped — no exception raised
        assert notifier.send_message.call_count >= 1
        assert notifier.send_message.call_count < 5
