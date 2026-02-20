"""
Data availability + download routes.

GET  /api/data/status           — check if CSV exists
POST /api/data/download         — start download (SSE-streamed)
GET  /api/data/download/{job_id}/progress — SSE progress for download
"""
from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import pandas as pd
import structlog
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.schemas import DataStatusResponse, DownloadStartResponse

logger = structlog.get_logger()

router = APIRouter(prefix="/api/data", tags=["data"])

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "app", "backtest", "data")
DATA_DIR = os.path.normpath(DATA_DIR)

# In-memory download job registry {job_id: asyncio.Queue}
_download_queues: dict[str, asyncio.Queue] = {}


def _csv_path(symbol: str, timeframe: str) -> str:
    safe = symbol.replace("/", "")
    return os.path.join(DATA_DIR, f"{safe}_{timeframe}.csv")


@router.get("/status", response_model=DataStatusResponse)
def check_data_status(symbol: str, timeframe: str):
    path = _csv_path(symbol, timeframe)
    if not os.path.exists(path):
        return DataStatusResponse(
            symbol=symbol,
            timeframe=timeframe,
            available=False,
            file_path=None,
            candle_count=None,
            date_range=None,
        )

    try:
        df = pd.read_csv(path, usecols=["timestamp"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        date_range = {
            "start": df["timestamp"].iloc[0].isoformat(),
            "end": df["timestamp"].iloc[-1].isoformat(),
        }
        return DataStatusResponse(
            symbol=symbol,
            timeframe=timeframe,
            available=True,
            file_path=path,
            candle_count=len(df),
            date_range=date_range,
        )
    except Exception as exc:
        logger.warning("data_status_read_error", path=path, error=str(exc))
        return DataStatusResponse(
            symbol=symbol,
            timeframe=timeframe,
            available=True,
            file_path=path,
            candle_count=None,
            date_range=None,
        )


@router.post("/download", response_model=DownloadStartResponse)
async def start_download(body: dict[str, Any]):
    """
    Start a data download in the background and stream progress via SSE.
    Body: {symbol, timeframe, limit}
    """
    symbol: str = body.get("symbol", "BTC/USDT")
    timeframe: str = body.get("timeframe", "1h")
    limit: int = int(body.get("limit", 5000))

    job_id = str(uuid.uuid4())
    q: asyncio.Queue = asyncio.Queue()
    _download_queues[job_id] = q

    loop = asyncio.get_event_loop()

    def _run_download():
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            from app.backtest.download_data import download_data

            safe = symbol.replace("/", "")
            download_data(safe, timeframe, limit, DATA_DIR)
            loop.call_soon_threadsafe(
                q.put_nowait, {"event": "complete", "pct": 100}
            )
        except Exception as exc:
            loop.call_soon_threadsafe(
                q.put_nowait, {"event": "error", "message": str(exc)}
            )

    import threading
    t = threading.Thread(target=_run_download, daemon=True)
    t.start()

    return DownloadStartResponse(job_id=job_id, status="downloading")


@router.get("/download/{job_id}/progress")
async def download_progress(job_id: str):
    """SSE stream for a download job."""
    q = _download_queues.get(job_id)
    if q is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Download job not found")

    async def _generate():
        try:
            while True:
                event = await asyncio.wait_for(q.get(), timeout=60.0)
                evt_name = event.pop("event", "progress")
                import json
                yield f"event: {evt_name}\ndata: {json.dumps(event)}\n\n"
                if evt_name in ("complete", "error"):
                    _download_queues.pop(job_id, None)
                    break
        except asyncio.TimeoutError:
            yield "event: error\ndata: {\"message\": \"Download timed out\"}\n\n"
            _download_queues.pop(job_id, None)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
