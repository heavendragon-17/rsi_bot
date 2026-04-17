"""
Backtest result retrieval routes.

GET /api/backtest/{run_id}            — run detail (metrics + trades)
GET /api/backtest/{run_id}/timeseries — equity/drawdown curves (lazy)
GET /api/backtest/{run_id}/debug      — raw DB state for diagnosing UI issues
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import RunDetail, TimeseriesResponse
from app.backtest.service import BacktestService
from app.repository.backtest.database import SessionLocal
from app.repository.backtest.models import Run, RunConfig, RunResult, RunTimeseries, Trade

router = APIRouter(prefix="/api/backtest", tags=["backtest"])
logger = structlog.get_logger()

_service = BacktestService()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/{run_id}", response_model=RunDetail)
def get_run_detail(run_id: int, db: Session = Depends(get_db)):
    logger.info("api_get_run_detail", run_id=run_id)
    try:
        detail = _service.get_run_detail(run_id, db)
        logger.info(
            "api_get_run_detail_response",
            run_id=run_id,
            status=detail.status,
            has_results=detail.results is not None,
            trade_count=len(detail.trades) if detail.trades else 0,
            net_profit=detail.results.get("net_profit") if detail.results else None,
            total_trades=detail.results.get("total_trades") if detail.results else None,
        )
        return detail
    except LookupError as exc:
        logger.warning("api_get_run_detail_not_found", run_id=run_id)
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get("/{run_id}/timeseries", response_model=TimeseriesResponse)
def get_timeseries(run_id: int, db: Session = Depends(get_db)):
    logger.info("api_get_timeseries", run_id=run_id)
    try:
        ts = _service.get_timeseries(run_id, db)
        logger.info(
            "api_get_timeseries_response",
            run_id=run_id,
            equity_points=len(ts.equity_curve) if ts.equity_curve else 0,
            drawdown_points=len(ts.drawdown_curve) if ts.drawdown_curve else 0,
            monthly_returns_count=len(ts.monthly_returns) if ts.monthly_returns else 0,
        )
        return ts
    except LookupError as exc:
        logger.warning("api_get_timeseries_not_found", run_id=run_id)
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get("/{run_id}/debug")
def debug_run(run_id: int, db: Session = Depends(get_db)):
    """Raw DB state for diagnosing backend vs frontend issues.

    Returns what exists in the DB without any transformation.
    If this endpoint returns complete data but the UI shows nothing,
    the problem is in the frontend. If data is missing here, it's backend.
    """
    run = db.query(Run).filter_by(id=run_id).first()
    if run is None:
        return {"error": "run_not_found", "run_id": run_id}

    cfg = db.query(RunConfig).filter_by(run_id=run_id).first()
    result = db.query(RunResult).filter_by(run_id=run_id).first()
    ts = db.query(RunTimeseries).filter_by(run_id=run_id).first()
    trade_count = db.query(Trade).filter_by(run_id=run_id).count()

    return {
        "run_id": run_id,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "has_config": cfg is not None,
        "config_symbol": cfg.symbol if cfg else None,
        "has_results": result is not None,
        "results_summary": {
            "net_profit": str(result.net_profit) if result else None,
            "net_profit_pct": result.net_profit_pct if result else None,
            "total_trades": result.total_trades if result else None,
            "win_rate": result.win_rate if result else None,
        } if result else None,
        "has_timeseries": ts is not None,
        "timeseries_summary": {
            "equity_curve_bytes": len(ts.equity_curve) if ts and ts.equity_curve else 0,
            "drawdown_curve_bytes": len(ts.drawdown_curve) if ts and ts.drawdown_curve else 0,
            "has_monthly_returns": bool(ts.monthly_returns) if ts else False,
        } if ts else None,
        "trade_count": trade_count,
    }
