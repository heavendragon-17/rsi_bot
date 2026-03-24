"""
History routes.

GET    /api/history         — paginated list of runs
DELETE /api/history/{id}    — delete a run (cascade)
"""
from __future__ import annotations

import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import json
from app.api.schemas import HistoryResponse, RunSummary
from app.repository.backtest.database import SessionLocal
from app.repository.backtest.models import (
    Run, RunConfig, RunResult, Strategy, Tag,
    BatchRun, BatchRunConfig, BatchRunResult,
    PortfolioRun, PortfolioRunConfig, PortfolioRunResult
)

router = APIRouter(prefix="/api/history", tags=["history"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=HistoryResponse)
def list_runs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    strategy: str | None = None,
    symbol: str | None = None,
    status: str | None = None,
    profitable_only: bool = False,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    q = (
        db.query(Run, RunConfig, RunResult, Strategy)
        .join(RunConfig, RunConfig.run_id == Run.id, isouter=True)
        .join(RunResult, RunResult.run_id == Run.id, isouter=True)
        .join(Strategy, Strategy.id == Run.strategy_id)
        .order_by(Run.created_at.desc())
    )

    if strategy:
        q = q.filter(Strategy.name == strategy)
    if symbol:
        q = q.filter(RunConfig.symbol == symbol)
    if status:
        q = q.filter(Run.status == status)
    if profitable_only:
        q = q.filter(RunResult.net_profit_pct > 0)
    if search:
        q = q.filter(
            (RunConfig.symbol.ilike(f"%{search}%"))
            | (Strategy.name.ilike(f"%{search}%"))
        )

    total = q.count()
    pages = max(1, math.ceil(total / limit))
    rows = q.offset((page - 1) * limit).limit(limit).all()

    summaries = []
    for run, cfg, result, strat in rows:
        tags = [t.name for t in db.query(Tag).filter_by(run_id=run.id).all()]
        summaries.append(
            RunSummary(
                id=run.id,
                strategy_name=strat.name,
                symbol=cfg.symbol if cfg else "",
                timeframe=cfg.timeframe if cfg else "",
                status=run.status,
                created_at=run.created_at.isoformat() if run.created_at else "",
                start_date=cfg.start_date.isoformat() if cfg and cfg.start_date else "",
                end_date=cfg.end_date.isoformat() if cfg and cfg.end_date else "",
                initial_capital=str(cfg.initial_capital) if cfg else "10000.00",
                leverage=cfg.leverage if cfg else 10,
                net_profit=str(result.net_profit) if result and result.net_profit is not None else None,
                net_profit_pct=result.net_profit_pct if result else None,
                win_rate=result.win_rate if result else None,
                profit_factor=result.profit_factor if result else None,
                max_drawdown_pct=result.max_drawdown_pct if result else None,
                sharpe_ratio=result.sharpe_ratio if result else None,
                total_trades=result.total_trades if result else None,
                tags=tags,
            )
        )

    return HistoryResponse(runs=summaries, total=total, page=page, pages=pages)


@router.get("/batch", response_model=HistoryResponse)
def list_batch_runs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    strategy: str | None = None,
    db: Session = Depends(get_db),
):
    q = (
        db.query(BatchRun, BatchRunConfig, BatchRunResult, Strategy)
        .join(BatchRunConfig, BatchRunConfig.batch_run_id == BatchRun.id, isouter=True)
        .join(BatchRunResult, BatchRunResult.batch_run_id == BatchRun.id, isouter=True)
        .join(Strategy, Strategy.id == BatchRun.strategy_id)
        .order_by(BatchRun.created_at.desc())
    )

    if strategy:
        q = q.filter(Strategy.name == strategy)

    total = q.count()
    pages = max(1, math.ceil(total / limit))
    rows = q.offset((page - 1) * limit).limit(limit).all()

    summaries = []
    for run, cfg, result, strat in rows:
        agg = json.loads(result.aggregate_stats) if result and result.aggregate_stats else {}
        syms = json.loads(cfg.symbols) if cfg else []
        summaries.append(
            RunSummary(
                id=run.id,
                strategy_name=strat.name,
                symbol=f"{len(syms)} pairs",
                timeframe=cfg.timeframe if cfg else "",
                status=run.status,
                created_at=run.created_at.isoformat() if run.created_at else "",
                start_date=cfg.start_date.isoformat() if cfg and cfg.start_date else "",
                end_date=cfg.end_date.isoformat() if cfg and cfg.end_date else "",
                initial_capital=str(cfg.initial_capital) if cfg else "10000.00",
                leverage=cfg.leverage if cfg else 1,
                net_profit=str(agg.get("total_pnl")) if "total_pnl" in agg else None,
                net_profit_pct=agg.get("portfolio_return"),
                win_rate=None,
                profit_factor=None,
                max_drawdown_pct=None,
                sharpe_ratio=None,
                total_trades=agg.get("total_trades"),
                tags=[],
            )
        )

    return HistoryResponse(runs=summaries, total=total, page=page, pages=pages)

@router.get("/portfolio", response_model=HistoryResponse)
def list_portfolio_runs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    strategy: str | None = None,
    db: Session = Depends(get_db),
):
    q = (
        db.query(PortfolioRun, PortfolioRunConfig, PortfolioRunResult, Strategy)
        .join(PortfolioRunConfig, PortfolioRunConfig.portfolio_run_id == PortfolioRun.id, isouter=True)
        .join(PortfolioRunResult, PortfolioRunResult.portfolio_run_id == PortfolioRun.id, isouter=True)
        .join(Strategy, Strategy.id == PortfolioRun.strategy_id)
        .order_by(PortfolioRun.created_at.desc())
    )

    if strategy:
        q = q.filter(Strategy.name == strategy)

    total = q.count()
    pages = max(1, math.ceil(total / limit))
    rows = q.offset((page - 1) * limit).limit(limit).all()

    summaries = []
    for run, cfg, result, strat in rows:
        syms = json.loads(cfg.symbols) if cfg else []
        summaries.append(
            RunSummary(
                id=run.id,
                strategy_name=strat.name,
                symbol=f"{len(syms)} pairs",
                timeframe=cfg.timeframe if cfg else "",
                status=run.status,
                created_at=run.created_at.isoformat() if run.created_at else "",
                start_date=cfg.start_date.isoformat() if cfg and cfg.start_date else "",
                end_date=cfg.end_date.isoformat() if cfg and cfg.end_date else "",
                initial_capital=str(cfg.initial_capital) if cfg else "10000.00",
                leverage=cfg.leverage if cfg else 1,
                net_profit=str(result.net_profit) if result and result.net_profit is not None else None,
                net_profit_pct=result.net_profit_pct if result else None,
                win_rate=result.win_rate if result else None,
                profit_factor=result.profit_factor if result else None,
                max_drawdown_pct=result.max_drawdown_pct if result else None,
                sharpe_ratio=result.sharpe_ratio if result else None,
                total_trades=result.total_trades if result else None,
                tags=[],
            )
        )

    return HistoryResponse(runs=summaries, total=total, page=page, pages=pages)


@router.delete("/{run_id}")
def delete_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(Run).filter_by(id=run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    db.delete(run)
    db.commit()
    return {"deleted": True}
