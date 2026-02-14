"""
SSE Event Bus
=============
Per-run asyncio queues for Server-Sent Events progress streaming.

Usage (from async context):
    queue = get_queue(run_id)
    await publish(run_id, "progress", {"pct": 10, "message": "Starting..."})
    async for event in subscribe(run_id):
        yield event

Usage (from a thread via run_in_executor):
    publish_from_thread(run_id, "progress", {"pct": 10, "message": "..."}, loop)
"""
import asyncio
import json
from typing import AsyncGenerator

# Global registry: run_id -> asyncio.Queue
_queues: dict[int, asyncio.Queue] = {}


def get_queue(run_id: int) -> asyncio.Queue:
    """Get or create the queue for a run_id."""
    if run_id not in _queues:
        _queues[run_id] = asyncio.Queue()
    return _queues[run_id]


async def publish(run_id: int, event_type: str, data: dict) -> None:
    """Publish an event to the run's queue (from async context)."""
    queue = get_queue(run_id)
    await queue.put({"event": event_type, "data": data})


def publish_from_thread(run_id: int, event_type: str, data: dict, loop: asyncio.AbstractEventLoop) -> None:
    """
    Publish an event from a background thread.
    The event loop must be passed in (captured before entering the thread).
    """
    queue = get_queue(run_id)
    loop.call_soon_threadsafe(queue.put_nowait, {"event": event_type, "data": data})


async def subscribe(run_id: int) -> AsyncGenerator[dict, None]:
    """
    Async generator that yields events for a run until "done" or "error".
    Cleans up the queue when finished.
    """
    queue = get_queue(run_id)
    try:
        while True:
            event = await queue.get()
            yield event
            if event["event"] in ("done", "error"):
                break
    finally:
        # Clean up queue after SSE stream closes
        _queues.pop(run_id, None)


def format_sse(event: dict) -> dict:
    """Format event dict for sse-starlette EventSourceResponse."""
    return {
        "event": event["event"],
        "data": json.dumps(event["data"]),
    }
