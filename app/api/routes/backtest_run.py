"""
Backtest run management routes.

POST   /api/backtest/run       — start a backtest
DELETE /api/backtest/{run_id}  — cancel a running backtest
"""
from __future__ import annotations

import asyncio
import json
import os
import zlib
from datetime import date, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api import executor as exc_mod
from app.api.schemas import BacktestRequest, BacktestStartResponse
from app.backtest.config_builder import build_backtest_config
from app.trading.strategy.loader import STRATEGY_MAP
from app.repository.backtest.database import SessionLocal
from app.repository.backtest.models import (
    Run,
    RunConfig,
    RunResult,
    RunTimeseries,
    Strategy,
    Trade,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "app", "backtest", "data")
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _csv_path(symbol: str, timeframe: str) -> str:
    safe = symbol.replace("/", "")
    return os.path.join(DATA_DIR, f"{safe}_{timeframe}.csv")


# ---------------------------------------------------------------------------
# POST /api/backtest/run
# ---------------------------------------------------------------------------


@router.post("/run", status_code=201, response_model=BacktestStartResponse)
async def start_backtest(body: BacktestRequest, db: Session = Depends(get_db)):
    is_portfolio = bool(body.symbols)

    # 1. Fail fast — check data file (single mode only; portfolio downloads dynamically)
    if not is_portfolio:
        csv_path = _csv_path(body.symbol, body.timeframe)
        if not os.path.exists(csv_path):
            safe = body.symbol.replace("/", "")
            raise HTTPException(
                status_code=400,
                detail=f"Data file not found: {safe}_{body.timeframe}.csv. Download data first.",
            )

    # 2. Resolve strategy
    strategy_class = STRATEGY_MAP.get(body.strategy)
    if strategy_class is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown strategy: {body.strategy}. Available: {list(STRATEGY_MAP)}",
        )

    # 3. Resolve strategy DB row
    strat_row = db.query(Strategy).filter_by(name=body.strategy).first()
    if strat_row is None:
        raise HTTPException(status_code=400, detail=f"Strategy '{body.strategy}' not seeded in DB")

    # 4. Create Run + RunConfig rows
    run = Run(
        strategy_id=strat_row.id,
        status="running",
        started_at=datetime.utcnow(),
    )
    db.add(run)
    db.flush()  # populate run.id

    cfg = RunConfig(
        run_id=run.id,
        symbol="PORTFOLIO" if is_portfolio else body.symbol,
        timeframe=body.timeframe,
        start_date=date.fromisoformat(body.start_date),
        end_date=date.fromisoformat(body.end_date),
        initial_capital=body.initial_capital,
        leverage=body.leverage,
        risk_per_trade_pct=body.risk_per_trade_pct,
        fee_tier=body.fee_tier,
        slippage_model=body.slippage_model,
        slippage_pct=body.slippage_pct,
        params=body.params,
    )
    db.add(cfg)
    db.commit()

    run_id = run.id

    # 5. Create SSE queue
    loop = asyncio.get_event_loop()
    exc_mod.create_progress_queue(run_id)

    progress_cb = exc_mod.make_progress_callback(run_id, loop)

    if is_portfolio:
        # --- Portfolio mode ---
        symbols = body.symbols

        def _run_backtest():
            from app.backtest.run_portfolio_backtest import _run_portfolio_backtest

            try:
                results = _run_portfolio_backtest(
                    symbols=symbols,
                    strategy_name=body.strategy,
                    timeframe=body.timeframe,
                    start_date=body.start_date,
                    end_date=body.end_date,
                    initial_capital=float(body.initial_capital),
                    leverage=body.leverage,
                    risk_per_trade_pct=float(body.risk_per_trade_pct),
                    fee_tier=body.fee_tier,
                    slippage_model=body.slippage_model,
                    slippage_pct=float(body.slippage_pct),
                    params=body.params,
                    progress_cb=progress_cb,
                )
                _persist_results(run_id, results)
                exc_mod.publish_event(
                    run_id, loop, "complete", {"run_id": run_id, "status": "completed"}
                )
            except Exception as err:
                logger.error("portfolio_backtest_worker_error", run_id=run_id, error=str(err))
                _mark_failed(run_id, str(err))
                exc_mod.publish_event(
                    run_id, loop, "error", {"run_id": run_id, "message": str(err)}
                )
            finally:
                exc_mod.cleanup_job(run_id)
    else:
        # --- Single-symbol mode ---
        engine_config = build_backtest_config(
            symbol=body.symbol,
            timeframe=body.timeframe,
            strategy_name=body.strategy,
            initial_balance=float(body.initial_capital),
            leverage=body.leverage,
            risk_per_trade_pct=float(body.risk_per_trade_pct),
            params=body.params,
        )

        def _run_backtest():
            from app.backtest.engine import BacktestEngine

            try:
                engine = BacktestEngine(csv_path, strategy_class, engine_config)
                results = engine.run(on_progress=progress_cb)
                _persist_results(run_id, results)
                exc_mod.publish_event(
                    run_id, loop, "complete", {"run_id": run_id, "status": "completed"}
                )
            except Exception as err:
                logger.error("backtest_worker_error", run_id=run_id, error=str(err))
                _mark_failed(run_id, str(err))
                exc_mod.publish_event(
                    run_id, loop, "error", {"run_id": run_id, "message": str(err)}
                )
            finally:
                exc_mod.cleanup_job(run_id)

    exc_mod.submit_backtest(run_id, _run_backtest)

    return BacktestStartResponse(run_id=run_id, status="running")


# ---------------------------------------------------------------------------
# DELETE /api/backtest/{run_id}  — Cancel
# ---------------------------------------------------------------------------


@router.delete("/{run_id}")
def cancel_backtest(run_id: int, db: Session = Depends(get_db)):
    cancelled = exc_mod.cancel_job(run_id)
    run = db.query(Run).filter_by(id=run_id).first()
    if run:
        run.status = "cancelled"
        db.commit()
    return {"cancelled": True, "was_pending": cancelled}


# ---------------------------------------------------------------------------
# Internal helpers (called from worker thread)
# ---------------------------------------------------------------------------


def _persist_results(run_id: int, results: dict[str, Any]) -> None:
    """Write engine results to DB. Runs in a thread — uses its own session."""
    from app.repository.backtest.database import SessionLocal as _SessionLocal

    db = _SessionLocal()
    try:
        run = db.query(Run).filter_by(id=run_id).first()
        if run is None:
            return

        run.status = "completed"
        run.completed_at = datetime.utcnow()

        metrics = results.get("metrics", {})
        drawdown = results.get("drawdown", {})
        risk = results.get("risk_metrics", {})

        result_row = RunResult(
            run_id=run_id,
            net_profit=str(results.get("net_profit", 0)),
            net_profit_pct=results.get("net_profit_pct", 0.0),
            gross_profit=str(metrics.get("gross_profit", 0)),
            gross_loss=str(metrics.get("gross_loss", 0)),
            win_rate=metrics.get("win_rate"),
            profit_factor=metrics.get("profit_factor"),
            expectancy=str(metrics.get("expectancy", 0)),
            max_drawdown_pct=drawdown.get("max_drawdown_pct"),
            max_drawdown_value=str(drawdown.get("max_drawdown_value", 0)),
            max_drawdown_duration_days=drawdown.get("max_dd_duration"),
            volatility=risk.get("volatility"),
            sharpe_ratio=risk.get("sharpe_ratio"),
            sortino_ratio=risk.get("sortino_ratio"),
            calmar_ratio=risk.get("calmar_ratio"),
            total_trades=metrics.get("total_trades"),
            winning_trades=metrics.get("win_count"),
            losing_trades=metrics.get("loss_count"),
            avg_win=str(metrics.get("avg_win", 0)),
            avg_loss=str(metrics.get("avg_loss", 0)),
            largest_win=str(metrics.get("largest_win", 0)),
            largest_loss=str(metrics.get("largest_loss", 0)),
            max_consecutive_wins=metrics.get("max_consec_wins"),
            max_consecutive_losses=metrics.get("max_consec_losses"),
            avg_hold_time_hours=metrics.get("avg_hold_hours"),
            exit_reasons=metrics.get("exit_reason_counts", {}),
        )
        db.add(result_row)

        # Timeseries (zlib-compressed JSON)
        equity_curve = results.get("equity_curve", [])
        drawdown_curve = results.get("drawdown_curve", [])
        monthly_returns = results.get("monthly_returns", {})

        ts_row = RunTimeseries(
            run_id=run_id,
            equity_curve=zlib.compress(json.dumps(equity_curve).encode()),
            drawdown_curve=zlib.compress(json.dumps(drawdown_curve).encode()),
            monthly_returns=monthly_returns,
        )
        db.add(ts_row)

        # Individual trades
        for rt in results.get("round_trips", []):
            entry_t = rt.get("entry_time")
            exit_t = rt.get("exit_time")

            def _parse_dt(val):
                if val is None:
                    return None
                if isinstance(val, datetime):
                    return val
                try:
                    import pandas as pd
                    return pd.to_datetime(val).to_pydatetime()
                except Exception:
                    return None

            trade_row = Trade(
                run_id=run_id,
                symbol=rt.get("symbol", ""),
                side=rt.get("side", "LONG"),
                entry_time=_parse_dt(entry_t),
                exit_time=_parse_dt(exit_t),
                hold_time_hours=rt.get("hold_duration_hours"),
                entry_price=str(rt.get("entry_price", 0)),
                exit_price=str(rt.get("avg_exit_price", rt.get("exit_price", 0))),
                quantity=str(rt.get("amount", 0)),
                size_usd=str(rt.get("notional", rt.get("margin", 0))),
                pnl=str(rt.get("pnl", 0)),
                pnl_pct=rt.get("pnl_pct"),
                exit_reason=rt.get("exit_reason"),
            )
            db.add(trade_row)

        db.commit()
        logger.info("backtest_persisted", run_id=run_id)
    except Exception as err:
        db.rollback()
        logger.error("persist_error", run_id=run_id, error=str(err))
        raise
    finally:
        db.close()


def _mark_failed(run_id: int, error_msg: str) -> None:
    """Mark a run as failed in its own session."""
    from app.repository.backtest.database import SessionLocal as _SessionLocal

    db = _SessionLocal()
    try:
        run = db.query(Run).filter_by(id=run_id).first()
        if run:
            run.status = "failed"
            run.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()
