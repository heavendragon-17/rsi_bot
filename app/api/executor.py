"""
Job executor — ThreadPoolExecutor + per-run SSE progress queues.

Thread-to-async bridge: BacktestEngine.run(on_progress=callback) runs in a
worker thread. The callback pushes events onto an asyncio.Queue via
loop.call_soon_threadsafe so the async SSE generator can stream them.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from app.core.constants import DEFAULT_MAX_WORKERS, MAX_WORKERS_UPPER_BOUND

_executor = ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS)
_max_workers: int = DEFAULT_MAX_WORKERS
_jobs: dict[int, Future] = {}
_progress_queues: dict[int, asyncio.Queue] = {}


def get_max_workers() -> int:
    return _max_workers


def has_running_jobs() -> bool:
    return any(not f.done() for f in _jobs.values())


def set_max_workers(n: int) -> None:
    """Rebuild the thread pool with a new worker count.

    Must NOT be called while jobs are running — caller is responsible
    for checking ``has_running_jobs()`` first.
    """
    global _executor, _max_workers
    clamped = max(1, min(n, MAX_WORKERS_UPPER_BOUND))
    _executor.shutdown(wait=False)
    _executor = ThreadPoolExecutor(max_workers=clamped)
    _max_workers = clamped


def submit_backtest(run_id: int, fn: Callable, *args, **kwargs) -> Future:
    """Submit a backtest job to the thread pool."""
    future = _executor.submit(fn, *args, **kwargs)
    _jobs[run_id] = future
    return future


def cancel_job(run_id: int) -> bool:
    """Attempt to cancel a pending job. Returns True if cancelled."""
    future = _jobs.get(run_id)
    if future is None:
        return False
    cancelled = future.cancel()
    if cancelled:
        cleanup_job(run_id)
    return cancelled


def create_progress_queue(run_id: int) -> asyncio.Queue:
    """Create (or reset) the SSE queue for a run."""
    q: asyncio.Queue = asyncio.Queue()
    _progress_queues[run_id] = q
    return q


def get_progress_queue(run_id: int) -> asyncio.Queue | None:
    return _progress_queues.get(run_id)


def cleanup_job(run_id: int) -> None:
    """Remove job and queue from registries."""
    _jobs.pop(run_id, None)
    _progress_queues.pop(run_id, None)


def make_progress_callback(run_id: int, loop: asyncio.AbstractEventLoop) -> Callable[[dict[str, Any]], None]:
    """
    Return a thread-safe callback that pushes progress events onto the
    asyncio.Queue so the async SSE generator can yield them.

    Called from a worker thread — must NOT await or call async functions.
    """

    def callback(data: dict[str, Any]) -> None:
        q = _progress_queues.get(run_id)
        if q is not None:
            loop.call_soon_threadsafe(q.put_nowait, {"event": "progress", **data})

    return callback


def publish_event(run_id: int, loop: asyncio.AbstractEventLoop, event: str, data: dict[str, Any]) -> None:
    """Push a named event (e.g. 'complete', 'error') onto the queue from any thread."""
    q = _progress_queues.get(run_id)
    if q is not None:
        payload = {"event": event, **data}
        loop.call_soon_threadsafe(q.put_nowait, payload)
