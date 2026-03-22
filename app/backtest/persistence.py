"""
Backtest result persistence — writes engine results to the database.

Called from worker threads, so each function manages its own DB session.
"""

from __future__ import annotations

import json
import zlib
from datetime import datetime
from typing import Any

import structlog

from app.repository.backtest.database import SessionLocal
from app.repository.backtest.models import (
    Run,
    RunResult,
    RunTimeseries,
    Trade,
)

logger = structlog.get_logger()


def persist_results(run_id: int, results: dict[str, Any]) -> None:
    """Write engine results to DB. Runs in a thread — uses its own session."""
    db = SessionLocal()
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
            trade_row = Trade(
                run_id=run_id,
                symbol=rt.get("symbol", ""),
                side=rt.get("side", "LONG"),
                entry_time=_parse_dt(rt.get("entry_time")),
                exit_time=_parse_dt(rt.get("exit_time")),
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


def mark_failed(run_id: int, error_msg: str) -> None:
    """Mark a run as failed in its own session."""
    db = SessionLocal()
    try:
        run = db.query(Run).filter_by(id=run_id).first()
        if run:
            run.status = "failed"
            run.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def _parse_dt(val: Any) -> datetime | None:
    """Parse various datetime representations to Python datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        import pandas as pd

        return pd.to_datetime(val).to_pydatetime()
    except Exception:
        return None
