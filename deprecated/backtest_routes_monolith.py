"""
Backtest routes.

POST   /api/backtest/run                  — start a backtest
GET    /api/backtest/{run_id}/progress    — SSE stream
DELETE /api/backtest/{run_id}             — cancel
GET    /api/backtest/{run_id}             — run detail (metrics + trades)
GET    /api/backtest/{run_id}/timeseries  — equity/drawdown curves (lazy)
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
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api import executor as exc_mod
from app.api.schemas import (
    BacktestRequest,
    BacktestStartResponse,
    RunDetail,
    TimeseriesResponse,
)
from app.backtest.config_builder import build_backtest_config
from app.trading.strategy.loader import STRATEGY_MAP
from app.repository.backtest.database import SessionLocal
from app.repository.backtest.models import (
    Run,
    RunConfig,
    RunResult,
    RunTimeseries,
    Strategy,
    Tag,
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
# GET /api/backtest/{run_id}/progress  — SSE
# ---------------------------------------------------------------------------


@router.get("/{run_id}/progress")
async def stream_progress(run_id: int):
    """SSE endpoint. Client connects and receives progress events."""
    q = exc_mod.get_progress_queue(run_id)
    if q is None:
        # Run already finished or doesn't exist — send synthetic complete
        async def _done():
            yield f"event: complete\ndata: {json.dumps({'run_id': run_id, 'status': 'completed'})}\n\n"

        return StreamingResponse(
            _done(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def _generate():
        try:
            while True:
                event = await asyncio.wait_for(q.get(), timeout=300.0)
                evt_name = event.pop("event", "progress")
                yield f"event: {evt_name}\ndata: {json.dumps(event)}\n\n"
                if evt_name in ("complete", "error"):
                    break
        except asyncio.TimeoutError:
            yield f"event: error\ndata: {json.dumps({'message': 'timeout'})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
