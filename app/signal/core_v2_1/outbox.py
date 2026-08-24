"""Confirmed Telegram delivery for the durable Core V2.1 outbox."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import structlog

from app.notification.telegram_bot import TelegramBot
from app.signal.core_v2_1.state_store import CoreV21StateStore, OutboxLeaseLostError

logger = structlog.get_logger(__name__)


class NotificationDeliveryError(RuntimeError):
    """The delivery sink did not confirm a notification."""


class ConfirmingNotificationSink(Protocol):
    def deliver(self, message: str, *, topic_id: int | None, event_id: str) -> None:
        """Return only after confirmed delivery; raise on any failure."""


class TelegramOutboxSink:
    """Synchronous Telegram sink whose boolean response drives outbox state."""

    def __init__(self, bot: TelegramBot, *, chat_id: str | int) -> None:
        self._bot = bot
        self._chat_id = str(chat_id)

    def deliver(self, message: str, *, topic_id: int | None, event_id: str) -> None:
        # A short deterministic id makes unavoidable at-least-once recovery
        # duplicates recognizable if a process dies after Telegram accepts the
        # request but before SQLite records success.
        tagged = f"{message}\n\n<code>event:{event_id[:12]}</code>"
        succeeded = self._bot.send_message(
            tagged,
            chat_id=self._chat_id,
            message_thread_id=topic_id,
        )
        if not succeeded:
            raise NotificationDeliveryError(
                f"Telegram did not confirm Core V2.1 event {event_id}"
            )


@dataclass(frozen=True)
class DispatchSummary:
    claimed: int = 0
    sent: int = 0
    failed: int = 0


class DurableOutboxDispatcher:
    """Lease, deliver, and retry durable notification rows."""

    def __init__(
        self,
        store: CoreV21StateStore,
        sink: ConfirmingNotificationSink,
        *,
        initial_retry_seconds: float = 5.0,
        max_retry_seconds: float = 300.0,
        lease_seconds: float = 30.0,
    ) -> None:
        if initial_retry_seconds <= 0 or max_retry_seconds <= 0 or lease_seconds <= 0:
            raise ValueError("retry and lease durations must be positive")
        if initial_retry_seconds > max_retry_seconds:
            raise ValueError("initial retry cannot exceed maximum retry")
        self._store = store
        self._sink = sink
        self._initial_retry = initial_retry_seconds
        self._max_retry = max_retry_seconds
        self._lease = lease_seconds

    def dispatch_due(
        self,
        *,
        now: datetime | None = None,
        limit: int = 50,
    ) -> DispatchSummary:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        items = self._store.claim_due_outbox(
            now=current,
            limit=limit,
            lease_seconds=self._lease,
        )
        sent = 0
        failed = 0
        for item in items:
            try:
                self._sink.deliver(
                    item.message,
                    topic_id=item.topic_id,
                    event_id=item.event_id,
                )
            except Exception as exc:
                delay = self._retry_delay(item.attempts)
                try:
                    self._store.mark_outbox_failed(
                        item.outbox_id,
                        str(exc),
                        claim_token=item.claim_token,
                        retry_at=current + timedelta(seconds=delay),
                    )
                except OutboxLeaseLostError:
                    logger.warning(
                        "core_v2_notification_claim_lost",
                        event_id=item.event_id,
                        outcome="delivery_failed",
                    )
                    failed += 1
                    continue
                logger.warning(
                    "core_v2_notification_retry_scheduled",
                    event_id=item.event_id,
                    attempt=item.attempts + 1,
                    retry_seconds=delay,
                    error=str(exc),
                )
                failed += 1
                continue
            try:
                self._store.mark_outbox_sent(
                    item.outbox_id,
                    claim_token=item.claim_token,
                    sent_at=current,
                )
                sent += 1
            except OutboxLeaseLostError:
                # Another worker reclaimed the expired lease while this sink
                # call was in flight.  Never let the stale owner overwrite the
                # newer claim's outcome.
                logger.warning(
                    "core_v2_notification_claim_lost",
                    event_id=item.event_id,
                    outcome="delivery_confirmed_but_not_owned",
                )
                failed += 1
        return DispatchSummary(claimed=len(items), sent=sent, failed=failed)

    def _retry_delay(self, attempts: int) -> float:
        """Return capped exponential backoff without constructing huge ints."""

        if attempts < 0:
            raise ValueError("outbox attempts cannot be negative")
        delay = self._initial_retry
        for _ in range(attempts):
            if delay >= self._max_retry / 2:
                return self._max_retry
            delay *= 2
        return min(delay, self._max_retry)


class DurableOutboxWorker:
    """Small stoppable loop around :class:`DurableOutboxDispatcher`."""

    def __init__(
        self,
        dispatcher: DurableOutboxDispatcher,
        *,
        interval_seconds: float = 1.0,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._dispatcher = dispatcher
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lifecycle_lock = threading.Lock()

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._thread is not None and self._thread.is_alive():
                if self._stop.is_set():
                    raise RuntimeError("Core V2.1 outbox shutdown is still in progress")
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="core-v2-notification-outbox",
                daemon=True,
            )
            self._thread.start()

    def stop(self, *, timeout_seconds: float = 10.0) -> None:
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds cannot be negative")
        with self._lifecycle_lock:
            self._stop.set()
            thread = self._thread
            if thread is None:
                return
            thread.join(timeout=timeout_seconds)
            if thread.is_alive():
                raise TimeoutError(
                    "Core V2.1 outbox worker did not stop before the timeout"
                )
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._dispatcher.dispatch_due()
            except Exception:
                logger.exception("core_v2_outbox_cycle_failed")
            self._stop.wait(self._interval)
