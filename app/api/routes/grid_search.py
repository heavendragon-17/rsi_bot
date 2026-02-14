"""
Grid Search Routes
==================
REST + SSE endpoints for parallel grid search execution.

POST /api/grid-search/run              — start grid search, returns run_id immediately
GET  /api/grid-search/{run_id}         — get results for a completed run
GET  /api/grid-search/{run_id}/progress — SSE stream of execution progress
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Optional
from sse_starlette.sse import EventSourceResponse

from app.engine.grid_search_executor import run_grid_search
from app.api.sse import subscribe, format_sse
from app.db.connection import get_connection
from app.db.repositories import run_repo, grid_search_repo

router = APIRouter()


# ─────────────────────────────────────────────
# Request / Response models
# ─────────────────────────────────────────────

class GridConfig(BaseModel):
    x_param: str
    x_min: float
    x_max: float
    x_step: float
    y_param: str
    y_min: float
    y_max: float
    y_step: float
    metric: str = "net_pnl"


class RunGridSearchRequest(BaseModel):
    session_id: str
    config: dict[str, Any]
    grid: GridConfig


class RunGridSearchResponse(BaseModel):
    run_id: int
    status: str = "pending"
    total_combinations: int


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@router.post("/grid-search/run", response_model=RunGridSearchResponse)
async def start_grid_search(req: RunGridSearchRequest):
    """
    Start a grid search run. Returns run_id immediately.
    Connect to GET /api/grid-search/{run_id}/progress for SSE progress.
    """
    grid_config = req.grid.model_dump()
    run_id, total_combinations = await run_grid_search(
        req.session_id,
        req.config,
        grid_config,
    )
    return RunGridSearchResponse(
        run_id=run_id,
        status="pending",
        total_combinations=total_combinations,
    )


@router.get("/grid-search/{run_id}")
def get_grid_search_results(run_id: int):
    """
    Get all grid search results for a completed run.
    Also returns the best result based on the metric used.

    Returns:
        {
            results: list of grid_search_results rows,
            best: { x_param, x_value, y_param, y_value, metric_value } | null,
            run_status: str,
        }
    """
    with get_connection() as conn:
        run = run_repo.get_run(conn, run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

        results = grid_search_repo.get_results(conn, run_id)

    # Find best result (highest net_pnl_pct by default)
    best = None
    if results:
        valid = [r for r in results if r.get("sharpe_ratio") is not None]
        if valid:
            best_r = max(valid, key=lambda r: r.get("net_pnl_pct") or 0)
            best = {
                "x_param": best_r["x_param"],
                "x_value": best_r["x_value"],
                "y_param": best_r["y_param"],
                "y_value": best_r["y_value"],
                "metric_value": best_r.get("net_pnl_pct") or 0,
            }

    return {
        "results": results,
        "best": best,
        "run_status": run["status"],
    }


@router.get("/grid-search/{run_id}/progress")
async def stream_grid_search_progress(run_id: int):
    """
    SSE endpoint. Streams progress events until grid search completes or fails.

    Event types:
        progress  — { pct: 0-100, completed: N, total: M, message: str }
        done      — { run_id, status, total_combos, valid_combos, best }
        error     — { message: str, run_id: int }
    """
    async def event_generator():
        async for event in subscribe(run_id):
            yield format_sse(event)

    return EventSourceResponse(event_generator())
