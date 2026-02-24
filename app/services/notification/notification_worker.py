"""
Dedicated notification background thread with bounded queue.

Replaces ad-hoc `threading.Thread(target=notifier.on_entry, ...).start()` calls
in PaperExchange. Notifications are dispatched FIFO. If the queue is full,
the event is silently dropped (trading logic is never blocked).
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
        Drops silently if the queue is full — trading logic is never blocked.
        """
        try:
            self._queue.put_nowait((method_name, args, kwargs))
        except queue.Full:
            logger.warning("notification_queue_full", method=method_name)

    def _run(self) -> None:
        while not self._stopped.is_set() or not self._queue.empty():
            try:
                method_name, args, kwargs = self._queue.get(timeout=0.5)
                method = getattr(self.notifier, method_name, None)
                if method is not None:
                    try:
                        method(*args, **kwargs)
                    except Exception:
                        logger.exception("notification_failed", method=method_name)
                self._queue.task_done()
            except queue.Empty:
                continue
