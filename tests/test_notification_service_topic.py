"""End-to-end tests for topic-id plumbing through NotificationService.

Signal-bot flow:
    NotificationService.send_message(msg, topic_id=N)
        -> NotificationWorker.enqueue("send_message", msg, topic_id=N)
        -> notifier.send_message(msg, topic_id=N)
        -> TelegramBot.send_message(..., message_thread_id=N)

Live-bot callers pass no topic_id → topic_id=None → main chat.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.notification.notification_service import NotificationService
from app.notification.notification_worker import NotificationWorker
from app.notification.null_notifier import NullNotifier


def _mk_service_with_real_worker(notifier):
    """Build a NotificationService with a real worker but a mocked notifier."""
    svc = NotificationService(notifier=notifier, mode="sim")
    return svc


class TestServiceForwarding:
    def test_default_topic_is_none(self):
        notifier = MagicMock(spec=NullNotifier)
        with patch(
            "app.notification.notification_service.NotificationWorker"
        ) as MockWorker:
            worker = MagicMock()
            MockWorker.return_value = worker
            svc = NotificationService(notifier=notifier, mode="sim")

            svc.send_message("hi")

            worker.enqueue.assert_called_with("send_message", "hi", topic_id=None)

    def test_topic_id_forwarded(self):
        notifier = MagicMock(spec=NullNotifier)
        with patch(
            "app.notification.notification_service.NotificationWorker"
        ) as MockWorker:
            worker = MagicMock()
            MockWorker.return_value = worker
            svc = NotificationService(notifier=notifier, mode="sim")

            svc.send_message("hi", topic_id=42)

            worker.enqueue.assert_called_with("send_message", "hi", topic_id=42)


class TestWorkerPassthrough:
    def test_worker_invokes_notifier_with_topic(self):
        notifier = MagicMock()
        worker = NotificationWorker(notifier)
        worker.start()
        try:
            worker.enqueue("send_message", "hello", topic_id=7)
            worker._queue.join()
        finally:
            worker.stop()

        notifier.send_message.assert_called_once_with("hello", topic_id=7)


class TestTelegramNotifierTopic:
    def test_topic_reaches_telegram_bot(self):
        with patch("app.notification.telegram_notifier.TelegramBot") as MockBot, \
                patch.dict("os.environ", {"TELEGRAM_CHAT_ID": "chat-xyz"}):
            bot = MagicMock()
            MockBot.return_value = bot
            from app.notification.telegram_notifier import TelegramNotifier

            notifier = TelegramNotifier(mode="sim")
            notifier.send_message("hi", topic_id=123)

            assert bot.send_message.call_args.kwargs["message_thread_id"] == 123

    def test_no_topic_reaches_telegram_bot_as_none(self):
        with patch("app.notification.telegram_notifier.TelegramBot") as MockBot, \
                patch.dict("os.environ", {"TELEGRAM_CHAT_ID": "chat-xyz"}):
            bot = MagicMock()
            MockBot.return_value = bot
            from app.notification.telegram_notifier import TelegramNotifier

            notifier = TelegramNotifier(mode="sim")
            notifier.send_message("hi")

            assert bot.send_message.call_args.kwargs["message_thread_id"] is None


class TestTelegramBotPayload:
    @pytest.fixture
    def _env(self):
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "123"}):
            yield

    def test_topic_in_http_payload(self, _env):
        from app.notification.telegram_bot import TelegramBot
        bot = TelegramBot()
        with patch("app.notification.telegram_bot.requests") as req:
            req.post.return_value = MagicMock(status_code=200)
            bot.send_message("hi", message_thread_id=42)
            payload = req.post.call_args.kwargs["data"]
            assert payload["message_thread_id"] == "42"

    def test_no_topic_omits_field(self, _env):
        from app.notification.telegram_bot import TelegramBot
        bot = TelegramBot()
        with patch("app.notification.telegram_bot.requests") as req:
            req.post.return_value = MagicMock(status_code=200)
            bot.send_message("hi")
            payload = req.post.call_args.kwargs["data"]
            assert "message_thread_id" not in payload


class TestTypedEventsDontThreadTopic:
    def test_on_entry_has_no_topic(self):
        """Typed events (live-bot flow) never route to topics."""
        notifier = MagicMock(spec=NullNotifier)
        with patch(
            "app.notification.notification_service.NotificationWorker"
        ) as MockWorker:
            worker = MagicMock()
            MockWorker.return_value = worker
            svc = NotificationService(notifier=notifier, mode="sim")

            svc.on_entry(
                symbol="BTC",
                side="BUY",
                entry_price=Decimal("100"),
                amount=Decimal("1"),
            )

            kwargs = worker.enqueue.call_args.kwargs
            assert "topic_id" not in kwargs
