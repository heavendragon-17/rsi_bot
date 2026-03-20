"""
Backtest result retrieval routes.

GET /api/backtest/{run_id}            — run detail (metrics + trades)
GET /api/backtest/{run_id}/timeseries — equity/drawdown curves (lazy)
"""
from __future__ import annotations

import json
import zlib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import RunDetail, TimeseriesResponse
from app.repository.backtest.database import SessionLocal
from app.repository.backtest.models import (
    Run,
    RunConfig,
    RunResult,
    RunTimeseries,
    Strategy,
    Trade,
)

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/backtest/{run_id}  — Run detail
# ---------------------------------------------------------------------------


@router.get("/{run_id}", response_model=RunDetail)
def get_run_detail(run_id: int, db: Session = Depends(get_db)):
    run = db.query(Run).filter_by(id=run_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    strat = db.query(Strategy).filter_by(id=run.strategy_id).first()
    cfg = db.query(RunConfig).filter_by(run_id=run_id).first()
    result = db.query(RunResult).filter_by(run_id=run_id).first()
    trades = db.query(Trade).filter_by(run_id=run_id).order_by(Trade.entry_time).all()

    config_dict: dict[str, Any] = {}
    if cfg:
        config_dict = {
            "symbol": cfg.symbol,
            "timeframe": cfg.timeframe,
            "start_date": cfg.start_date.isoformat() if cfg.start_date else None,
            "end_date": cfg.end_date.isoformat() if cfg.end_date else None,
            "initial_capital": str(cfg.initial_capital),
            "leverage": cfg.leverage,
            "risk_per_trade_pct": str(cfg.risk_per_trade_pct),
            "params": cfg.params or {},
        }

    results_dict: dict[str, Any] | None = None
    if result:
        results_dict = {
            "net_profit": str(result.net_profit) if result.net_profit is not None else None,
            "net_profit_pct": result.net_profit_pct,
            "gross_profit": str(result.gross_profit) if result.gross_profit is not None else None,
            "gross_loss": str(result.gross_loss) if result.gross_loss is not None else None,
            "win_rate": result.win_rate,
            "profit_factor": result.profit_factor,
            "expectancy": str(result.expectancy) if result.expectancy is not None else None,
            "max_drawdown_pct": result.max_drawdown_pct,
            "max_drawdown_value": str(result.max_drawdown_value) if result.max_drawdown_value is not None else None,
            "volatility": result.volatility,
            "sharpe_ratio": result.sharpe_ratio,
            "sortino_ratio": result.sortino_ratio,
            "calmar_ratio": result.calmar_ratio,
            "total_trades": result.total_trades,
            "winning_trades": result.winning_trades,
            "losing_trades": result.losing_trades,
            "avg_win": str(result.avg_win) if result.avg_win is not None else None,
            "avg_loss": str(result.avg_loss) if result.avg_loss is not None else None,
            "largest_win": str(result.largest_win) if result.largest_win is not None else None,
            "largest_loss": str(result.largest_loss) if result.largest_loss is not None else None,
            "max_consecutive_wins": result.max_consecutive_wins,
            "max_consecutive_losses": result.max_consecutive_losses,
            "avg_hold_time_hours": result.avg_hold_time_hours,
            "exit_reasons": result.exit_reasons or {},
        }

    trades_list = [
        {
            "id": t.id,
            "symbol": t.symbol,
            "side": t.side,
            "entry_time": t.entry_time.isoformat() if t.entry_time else None,
            "exit_time": t.exit_time.isoformat() if t.exit_time else None,
            "hold_time_hours": t.hold_time_hours,
            "entry_price": str(t.entry_price),
            "exit_price": str(t.exit_price) if t.exit_price is not None else None,
            "stop_loss_price": str(t.stop_loss_price) if t.stop_loss_price is not None else None,
            "tp1_price": str(t.tp1_price) if t.tp1_price is not None else None,
            "tp2_price": str(t.tp2_price) if t.tp2_price is not None else None,
            "tp3_price": str(t.tp3_price) if t.tp3_price is not None else None,
            "quantity": str(t.quantity),
            "size_usd": str(t.size_usd),
            "pnl": str(t.pnl) if t.pnl is not None else None,
            "pnl_pct": t.pnl_pct,
            "exit_reason": t.exit_reason,
        }
        for t in trades
    ]

    return RunDetail(
        id=run.id,
        strategy_name=strat.name if strat else "",
        symbol=cfg.symbol if cfg else "",
        timeframe=cfg.timeframe if cfg else "",
        status=run.status,
        created_at=run.created_at.isoformat() if run.created_at else "",
        config=config_dict,
        results=results_dict,
        trades=trades_list,
    )


# ---------------------------------------------------------------------------
# GET /api/backtest/{run_id}/timeseries  — Lazy-load charts
# ---------------------------------------------------------------------------


@router.get("/{run_id}/timeseries", response_model=TimeseriesResponse)
def get_timeseries(run_id: int, db: Session = Depends(get_db)):
    ts = db.query(RunTimeseries).filter_by(run_id=run_id).first()
    if ts is None:
        raise HTTPException(status_code=404, detail="Timeseries not found for this run")

    equity_curve = json.loads(zlib.decompress(ts.equity_curve)) if ts.equity_curve else []
    drawdown_curve = json.loads(zlib.decompress(ts.drawdown_curve)) if ts.drawdown_curve else []

    return TimeseriesResponse(
        run_id=run_id,
        equity_curve=equity_curve,
        drawdown_curve=drawdown_curve,
        monthly_returns=ts.monthly_returns or {},
    )
