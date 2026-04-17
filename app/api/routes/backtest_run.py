"""
Backtest run management routes.

POST   /api/backtest/run       — start a backtest
DELETE /api/backtest/{run_id}  — cancel a running backtest
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import BacktestRequest, BacktestStartResponse
from app.backtest.service import BacktestService
from app.repository.backtest.database import SessionLocal

router = APIRouter(prefix="/api/backtest", tags=["backtest"])
logger = structlog.get_logger()

_service = BacktestService()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/run", status_code=201, response_model=BacktestStartResponse)
async def start_backtest(body: BacktestRequest, db: Session = Depends(get_db)):
    logger.info(
        "api_start_backtest",
        strategy=body.strategy,
        symbol=body.symbol,
        symbols=body.symbols,
        timeframe=body.timeframe,
        mode=body.mode,
    )
    try:
        run_id = await _service.start_run(body, db)
    except FileNotFoundError as exc:
        logger.warning("api_start_backtest_file_not_found", error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except ValueError as exc:
        logger.warning("api_start_backtest_validation_error", error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from None
    logger.info("api_start_backtest_ok", run_id=run_id)
    return BacktestStartResponse(run_id=run_id, status="running")


@router.delete("/{run_id}")
def cancel_backtest(run_id: int, db: Session = Depends(get_db)):
    return _service.cancel_run(run_id, db)
