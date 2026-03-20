"""
Backtest SSE progress streaming route.

GET /api/backtest/{run_id}/progress — SSE stream
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api import executor as exc_mod

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


# ---------------------------------------------------------------------------
# GET /api/backtest/{run_id}/progress  — SSE
# ---------------------------------------------------------------------------


@router.get("/{run_id}/progress")
async def stream_progress(run_id: int):
    """SSE endpoint. Client connects and receives progress events."""
    q = exc_mod.get_progress_queue(run_id)
    if q is None:
        # Run already finished or doesn't exist — send synthetic complete
        async def _done():
            yield f"event: complete\ndata: {json.dumps({'run_id': run_id, 'status': 'completed'})}\n\n"

        return StreamingResponse(
            _done(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def _generate():
        try:
            while True:
                event = await asyncio.wait_for(q.get(), timeout=300.0)
                evt_name = event.pop("event", "progress")
                yield f"event: {evt_name}\ndata: {json.dumps(event)}\n\n"
                if evt_name in ("complete", "error"):
                    break
        except asyncio.TimeoutError:
            yield f"event: error\ndata: {json.dumps({'message': 'timeout'})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
