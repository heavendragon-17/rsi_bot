"""
Backtest Routes
===============
REST + SSE endpoints for running backtests and streaming progress.

POST /api/backtest/run          — start backtest, returns run_id immediately
GET  /api/backtest/{run_id}     — get run details + metrics from DB
GET  /api/backtest/{run_id}/progress  — SSE stream of execution progress
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Any
from sse_starlette.sse import EventSourceResponse

from app.engine.executor import run_backtest
from app.api.sse import subscribe, format_sse
from app.db.connection import get_connection
from app.db.repositories import run_repo

router = APIRouter()


# ─────────────────────────────────────────────
# Request / Response models
# ─────────────────────────────────────────────

class RunBacktestRequest(BaseModel):
    session_id: str
    config: dict[str, Any]


class RunBacktestResponse(BaseModel):
    run_id: int
    status: str = "pending"


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@router.post("/backtest/run", response_model=RunBacktestResponse)
async def start_backtest(req: RunBacktestRequest):
    """
    Start a backtest run. Returns run_id immediately.
    Connect to GET /api/backtest/{run_id}/progress for SSE progress stream.
    """
    run_id = await run_backtest(req.session_id, req.config)
    return RunBacktestResponse(run_id=run_id, status="pending")


@router.get("/backtest/{run_id}")
def get_run(run_id: int):
    """
    Get run details and results from the database.
    Poll this after the SSE stream reports 'done'.
    """
    with get_connection() as conn:
        run = run_repo.get_run(conn, run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

        # Fetch results if completed
        metrics = None
        if run["status"] == "completed":
            cursor = conn.execute(
                """
                SELECT net_profit, net_profit_pct, win_rate, profit_factor,
                       sharpe_ratio, sortino_ratio, calmar_ratio, max_drawdown_pct,
                       total_trades, winning_trades, losing_trades, avg_hold_time_hours
                FROM run_results WHERE run_id = ?
                """,
                (run_id,),
            )
            row = cursor.fetchone()
            if row:
                metrics = {
                    "net_profit": row[0],
                    "net_profit_pct": row[1],
                    "win_rate": row[2],
                    "profit_factor": row[3],
                    "sharpe_ratio": row[4],
                    "sortino_ratio": row[5],
                    "calmar_ratio": row[6],
                    "max_drawdown_pct": row[7],
                    "total_trades": row[8],
                    "winning_trades": row[9],
                    "losing_trades": row[10],
                    "avg_hold_time_hours": row[11],
                }

    return {
        "run": run,
        "metrics": metrics,
    }


@router.get("/backtest/{run_id}/progress")
async def stream_progress(run_id: int):
    """
    SSE endpoint. Streams progress events until the backtest completes or fails.

    Event types:
        progress  — { pct: 0-100, message: str }
        done      — { run_id, status, metrics }
        error     — { message: str, run_id: int }
    """
    async def event_generator():
        async for event in subscribe(run_id):
            yield format_sse(event)

    return EventSourceResponse(event_generator())
