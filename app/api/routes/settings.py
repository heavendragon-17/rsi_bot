"""
Settings routes.

GET /api/settings/concurrency  — current max_workers
PUT /api/settings/concurrency  — update max_workers (409 if jobs running)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.executor import get_max_workers, has_running_jobs, set_max_workers
from app.core.constants import MAX_WORKERS_UPPER_BOUND

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ConcurrencyResponse(BaseModel):
    max_workers: int


class ConcurrencyUpdate(BaseModel):
    max_workers: int = Field(ge=1, le=MAX_WORKERS_UPPER_BOUND)


@router.get("/concurrency", response_model=ConcurrencyResponse)
def get_concurrency():
    return ConcurrencyResponse(max_workers=get_max_workers())


@router.put("/concurrency", response_model=ConcurrencyResponse)
def update_concurrency(body: ConcurrencyUpdate):
    if has_running_jobs():
        raise HTTPException(
            status_code=409,
            detail="Cannot change concurrency while backtests are running",
        )
    set_max_workers(body.max_workers)
    return ConcurrencyResponse(max_workers=get_max_workers())
