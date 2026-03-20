"""
Backtest SSE progress streaming route.

GET /api/backtest/{run_id}/progress — SSE stream
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.backtest.service import BacktestService

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

_service = BacktestService()


@router.get("/{run_id}/progress")
async def stream_progress(run_id: int):
    """SSE endpoint. Client connects and receives progress events."""
    return StreamingResponse(
        _service.stream_progress(run_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
