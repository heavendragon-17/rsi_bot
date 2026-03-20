"""
Backtest result retrieval routes.

GET /api/backtest/{run_id}            — run detail (metrics + trades)
GET /api/backtest/{run_id}/timeseries — equity/drawdown curves (lazy)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import RunDetail, TimeseriesResponse
from app.backtest.service import BacktestService
from app.repository.backtest.database import SessionLocal

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

_service = BacktestService()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/{run_id}", response_model=RunDetail)
def get_run_detail(run_id: int, db: Session = Depends(get_db)):
    try:
        return _service.get_run_detail(run_id, db)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{run_id}/timeseries", response_model=TimeseriesResponse)
def get_timeseries(run_id: int, db: Session = Depends(get_db)):
    try:
        return _service.get_timeseries(run_id, db)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
