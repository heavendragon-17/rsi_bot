"""Regression tests: TelegramBot must not lose messages to HTML entity
rejections.

In production (2026-08/09) every ``btc_rsi_cross_alert`` card containing a
raw ``<`` was rejected by Telegram with HTTP 400 "can't parse entities" and
silently dropped — the alert worker had already logged the alert as
"enqueued", so nothing surfaced the loss. These tests lock in the
plain-text fallback: an entity-parse rejection must degrade formatting,
never delivery."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.notification.telegram_bot import TelegramBot

_ENTITY_ERROR = json.dumps(
    {
        "ok": False,
        "error_code": 400,
        "description": "Bad Request: can't parse entities: "
        'Unsupported start tag "<" at byte offset 366',
    }
)

_OTHER_BAD_REQUEST = json.dumps(
    {
        "ok": False,
        "error_code": 400,
        "description": "Bad Request: chat not found",
    }
)

_OK = json.dumps({"ok": True, "result": {"message_id": 1}})


def _make_bot() -> TelegramBot:
    with patch.dict(
        "os.environ",
        {"TELEGRAM_BOT_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "-100123"},
    ):
        return TelegramBot()


def _make_bot_with_failure_topic() -> TelegramBot:
    with patch.dict(
        "os.environ",
        {"TELEGRAM_BOT_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "-100123"},
    ):
        return TelegramBot(failure_topic_id=1006)


def _response(status_code: int, text: str) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    return response


class TestEntityRejectionFallback:
    def test_entity_rejection_retries_as_plain_text(self):
        bot = _make_bot()
        with patch("app.notification.telegram_bot.requests.post") as post:
            post.side_effect = [
                _response(400, _ENTITY_ERROR),
                _response(200, _OK),
            ]

            sent = bot.send_message(
                "M5 RSI21 < 60.00: 53.42 < 60.00", message_thread_id=1003
            )

        assert sent is True
        assert post.call_count == 2
        retried_payload = post.call_args.kwargs["data"]
        assert "parse_mode" not in retried_payload
        assert retried_payload["text"] == "M5 RSI21 < 60.00: 53.42 < 60.00"
        # Forum-topic routing and buttons must survive the fallback.
        assert retried_payload["message_thread_id"] == "1003"

    def test_fallback_payload_preserves_inline_button(self):
        bot = _make_bot()
        with patch("app.notification.telegram_bot.requests.post") as post:
            post.side_effect = [
                _response(400, _ENTITY_ERROR),
                _response(200, _OK),
            ]

            bot.send_message(
                "broken < markup",
                button_text="Chart",
                button_url="https://example.com",
            )

        assert post.call_count == 2
        retried_payload = post.call_args.kwargs["data"]
        assert "reply_markup" in retried_payload
        assert "parse_mode" not in retried_payload

    def test_fallback_failure_returns_false(self):
        bot = _make_bot()
        with patch("app.notification.telegram_bot.requests.post") as post:
            post.side_effect = [
                _response(400, _ENTITY_ERROR),
                _response(400, _OTHER_BAD_REQUEST),
            ]

            sent = bot.send_message("still < broken")

        assert sent is False
        # The failed primary + plain-text retry are followed by one direct
        # failure alert in the configured/default chat.
        assert post.call_count == 3

    def test_non_entity_rejection_does_not_retry(self):
        """A 400 that is not an entity-parse failure (e.g. chat not found)
        must not trigger the plain-text retry."""

        bot = _make_bot()
        with patch("app.notification.telegram_bot.requests.post") as post:
            post.return_value = _response(400, _OTHER_BAD_REQUEST)

            sent = bot.send_message("normal text")

        assert sent is False
        # The original failure is followed by the default error alert.
        assert post.call_count == 2

    def test_first_attempt_success_never_retries(self):
        bot = _make_bot()
        with patch("app.notification.telegram_bot.requests.post") as post:
            post.return_value = _response(200, _OK)

            sent = bot.send_message("<b>real HTML is fine</b>")

        assert sent is True
        assert post.call_count == 1
        assert post.call_args.kwargs["data"]["parse_mode"] == "HTML"


class TestDeliveryFailureAlert:
    def test_failed_message_alerts_the_debug_topic(self):
        bot = _make_bot_with_failure_topic()
        with patch("app.notification.telegram_bot.requests.post") as post:
            post.side_effect = [
                _response(400, _OTHER_BAD_REQUEST),
                _response(200, _OK),
            ]

            sent = bot.send_message("important signal", message_thread_id=1147)

        assert sent is False
        assert post.call_count == 2
        alert_payload = post.call_args.kwargs["data"]
        assert alert_payload["message_thread_id"] == "1006"
        assert "Telegram delivery failure" in alert_payload["text"]
        assert "1147" in alert_payload["text"]

    def test_debug_topic_alert_falls_back_to_main_chat(self):
        bot = _make_bot_with_failure_topic()
        with patch("app.notification.telegram_bot.requests.post") as post:
            post.side_effect = [
                _response(400, _OTHER_BAD_REQUEST),
                _response(400, _OTHER_BAD_REQUEST),
                _response(200, _OK),
            ]

            bot.send_message("important signal", message_thread_id=1147)

        assert post.call_count == 3
        fallback_payload = post.call_args.kwargs["data"]
        assert "message_thread_id" not in fallback_payload

    def test_repeated_failures_are_rate_limited(self):
        bot = _make_bot_with_failure_topic()
        with patch("app.notification.telegram_bot.requests.post") as post:
            post.side_effect = [
                _response(400, _OTHER_BAD_REQUEST),
                _response(200, _OK),
                _response(400, _OTHER_BAD_REQUEST),
            ]

            assert bot.send_message("first") is False
            assert bot.send_message("second") is False

        # The second primary failure is logged, but does not generate a second
        # developer alert during the cooldown window.
        assert post.call_count == 3
