"""Durable inventory of Telegram forum topics observed by the bot.

The Telegram Bot API includes a forum topic id on incoming messages and topic
service messages, but it does not expose a method for listing every existing
forum topic.  This registry records the topics the bot has actually seen so
operators can identify topic ids that have no application configuration.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_TOPIC_REGISTRY_PATH = Path("data/telegram_topics.json")


@dataclass(frozen=True)
class ObservedForumTopic:
    """One Telegram forum topic discovered from an incoming bot update."""

    topic_id: int
    name: str | None = None


class ForumTopicRegistry:
    """Persist topic ids/names observed in one configured Telegram chat.

    The registry is intentionally observation-based.  It never claims that a
    topic absent from the file does not exist because the Bot API cannot
    backfill the complete forum topic list for a bot.
    """

    def __init__(self, path: str | Path | None = DEFAULT_TOPIC_REGISTRY_PATH) -> None:
        self._path = Path(path) if path is not None else None
        self._lock = threading.RLock()
        self._topics: dict[int, ObservedForumTopic] = self._load()

    def observe_update(
        self,
        update: dict[str, Any],
        *,
        expected_chat_id: str | int | None = None,
    ) -> None:
        """Record a forum topic carried by a Telegram message update.

        Both ordinary messages and forum-topic service messages arrive under
        the ``message`` update key for this polling bot.  Edited messages are
        accepted as well so a topic rename can be learned after creation.
        """

        message = (
            update.get("message")
            or update.get("edited_message")
            or update.get("channel_post")
            or update.get("edited_channel_post")
        )
        if not isinstance(message, dict):
            return

        chat = message.get("chat")
        if not isinstance(chat, dict):
            return
        chat_id = chat.get("id")
        if expected_chat_id is not None and str(chat_id) != str(expected_chat_id):
            return

        raw_topic_id = message.get("message_thread_id")
        if raw_topic_id is None:
            return
        try:
            topic_id = int(str(raw_topic_id))
        except (TypeError, ValueError):
            return
        if topic_id <= 0:
            return

        name: str | None = None
        for field in ("forum_topic_created", "forum_topic_edited"):
            service = message.get(field)
            if isinstance(service, dict) and service.get("name") is not None:
                candidate = str(service["name"]).strip()
                if candidate:
                    name = candidate
                    break
        self.observe(topic_id, name=name)

    def observe(self, topic_id: int, *, name: str | None = None) -> None:
        """Record or update one topic without rewriting unchanged state."""

        if topic_id <= 0:
            raise ValueError("forum topic ids must be positive")
        clean_name = str(name).strip() if name is not None else None
        if clean_name == "":
            clean_name = None

        with self._lock:
            previous = self._topics.get(topic_id)
            if previous is not None and (clean_name is None or clean_name == previous.name):
                return
            self._topics[topic_id] = ObservedForumTopic(topic_id, clean_name or (previous.name if previous else None))
            self._persist()

    def all_topics(self) -> list[ObservedForumTopic]:
        """Return all observed topics in deterministic id order."""

        with self._lock:
            return sorted(self._topics.values(), key=lambda topic: topic.topic_id)

    def unconfigured_topics(
        self,
        configured_topic_ids: Iterable[int],
    ) -> list[ObservedForumTopic]:
        """Return observed topics with no configured route, sorted by id."""

        configured = {int(topic_id) for topic_id in configured_topic_ids}
        return [
            topic
            for topic in self.all_topics()
            if topic.topic_id not in configured
        ]

    def _load(self) -> dict[int, ObservedForumTopic]:
        if self._path is None or not self._path.is_file():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise ValueError("registry root must be a list")
            topics: dict[int, ObservedForumTopic] = {}
            for item in raw:
                if not isinstance(item, dict):
                    continue
                try:
                    topic_id = int(item["topic_id"])
                except (KeyError, TypeError, ValueError):
                    continue
                if topic_id <= 0:
                    continue
                name = item.get("name")
                topics[topic_id] = ObservedForumTopic(
                    topic_id,
                    str(name).strip() if name is not None and str(name).strip() else None,
                )
            return topics
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.warning(
                "telegram_topic_registry_load_failed",
                path=str(self._path),
                error=str(exc),
            )
            return {}

    def _persist(self) -> None:
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = [
                {"topic_id": topic.topic_id, "name": topic.name}
                for topic in self.all_topics()
            ]
            temporary = self._path.with_name(f".{self._path.name}.tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self._path)
        except OSError as exc:
            logger.warning(
                "telegram_topic_registry_persist_failed",
                path=str(self._path),
                error=str(exc),
            )
