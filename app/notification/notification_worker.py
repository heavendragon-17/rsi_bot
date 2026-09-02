"""
Dedicated notification background thread with bounded queue.

Replaces ad-hoc `threading.Thread(target=notifier.on_entry, ...).start()` calls.
Notifications are dispatched FIFO. If the queue is full, the event is dropped
so trading logic is never blocked, but the drop is logged and reported through
the notifier's direct failure-alert hook when one exists.
"""

import queue
import threading

import structlog

logger = structlog.get_logger()


class NotificationWorker:
    """
    Single background thread processing notifications FIFO.
    Bounded queue with drop policy if full.
    """

    def __init__(self, notifier, max_queue_size: int = 100):
        self.notifier = notifier
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._stopped = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="notification-worker",
        )

    def start(self) -> None:
        """Start the background worker thread."""
        self._thread.start()

    def stop(self) -> None:
        """Signal stop and wait for the thread to exit (up to 30s) to drain queue."""
        self._stopped.set()
        self._thread.join(timeout=30.0)

    def enqueue(self, method_name: str, *args, **kwargs) -> None:
        """
        Enqueue a notification call.
        Drops if the queue is full — trading logic is never blocked, and the
        failure is reported outside this queue when the notifier supports it.
        """
        try:
            self._queue.put_nowait((method_name, args, kwargs))
        except queue.Full:
            logger.error("notification_queue_full", method=method_name)
            self._report_failure(
                method_name,
                kwargs.get("topic_id"),
                "notification queue is full; event was dropped",
            )

    def _run(self) -> None:
        while not self._stopped.is_set() or not self._queue.empty():
            try:
                method_name, args, kwargs = self._queue.get(timeout=0.5)
                method = getattr(self.notifier, method_name, None)
                if method is None:
                    logger.error("notification_method_missing", method=method_name)
                    self._report_failure(
                        method_name,
                        kwargs.get("topic_id"),
                        "notifier method is not available",
                    )
                else:
                    try:
                        result = method(*args, **kwargs)
                        if result is False:
                            logger.error(
                                "notification_delivery_failed",
                                method=method_name,
                            )
                            self._report_failure(
                                method_name,
                                kwargs.get("topic_id"),
                                "notifier returned False",
                            )
                    except Exception as exc:
                        logger.exception("notification_failed", method=method_name)
                        self._report_failure(
                            method_name,
                            kwargs.get("topic_id"),
                            f"{type(exc).__name__}: {exc}",
                        )
                self._queue.task_done()
            except queue.Empty:
                continue

    def _report_failure(
        self,
        method_name: str,
        topic_id: int | None,
        reason: str,
    ) -> None:
        """Use a direct notifier hook so failure reporting avoids this queue."""

        reporter = getattr(self.notifier, "report_notification_failure", None)
        if not callable(reporter):
            logger.error(
                "notification_failure_unreportable",
                method=method_name,
                topic_id=topic_id,
                error=reason,
            )
            return
        try:
            reporter(method_name, topic_id=topic_id, reason=reason)
        except Exception:
            logger.exception(
                "notification_failure_report_failed",
                method=method_name,
                topic_id=topic_id,
            )
