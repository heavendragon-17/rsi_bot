"""Tests for observed Telegram forum-topic discovery and rendering."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from app.notification.command_handlers import handle_topics
from app.notification.forum_topics import ForumTopicRegistry, ObservedForumTopic


def _message_update(
    topic_id: int,
    *,
    chat_id: int = -100123,
    text: str = "hello",
    service: dict | None = None,
) -> dict:
    message = {
        "chat": {"id": chat_id},
        "message_thread_id": topic_id,
        "text": text,
    }
    if service is not None:
        message.update(service)
    return {"update_id": topic_id, "message": message}


class TestForumTopicRegistry:
    def test_observes_created_topic_and_persists_it(self, tmp_path):
        path = tmp_path / "telegram_topics.json"
        registry = ForumTopicRegistry(path)

        registry.observe_update(
            _message_update(
                1576,
                service={"forum_topic_created": {"name": "Long V2"}},
            ),
            expected_chat_id=-100123,
        )

        assert registry.all_topics()[0].topic_id == 1576
        assert registry.all_topics()[0].name == "Long V2"
        assert json.loads(path.read_text(encoding="utf-8"))[0] == {
            "topic_id": 1576,
            "name": "Long V2",
        }

        reloaded = ForumTopicRegistry(path)
        assert reloaded.all_topics() == registry.all_topics()

    def test_learns_name_from_edit_and_ignores_other_chats(self, tmp_path):
        registry = ForumTopicRegistry(tmp_path / "topics.json")
        registry.observe_update(
            _message_update(44, chat_id=-100999, text="not our group"),
            expected_chat_id=-100123,
        )
        registry.observe_update(
            _message_update(44, service={"forum_topic_edited": {"name": "Momentum"}}),
            expected_chat_id=-100123,
        )

        assert registry.all_topics() == [ObservedForumTopic(44, "Momentum")]

    def test_filters_configured_ids(self, tmp_path):
        registry = ForumTopicRegistry(tmp_path / "topics.json")
        registry.observe(43, name="Configured")
        registry.observe(1576, name="Long V2")
        registry.observe(2000)

        assert registry.unconfigured_topics({43, 1576})[0].topic_id == 2000


class TestTopicsRendering:
    def test_renders_unconfigured_observed_topic_separately(self):
        send = MagicMock()

        handle_topics(
            [("rsi_no_retest", 43, "inactive")],
            "P",
            send,
            chat_id="c",
            unconfigured_topics=[ObservedForumTopic(2000, "New < topic")],
        )

        message = send.call_args.args[0]
        assert "Unconfigured Telegram topics observed:" in message
        assert "topic ID: 2000 — New &lt; topic" in message
        assert "Strategy definitions without a route:" not in message
