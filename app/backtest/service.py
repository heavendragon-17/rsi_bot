"""
BacktestService — business logic for backtest operations.

Routes to the correct runner by mode, manages DB records, persists results.
API route handlers delegate here and remain thin HTTP adapters.
"""

from __future__ import annotations

import asyncio
import json
import os
import zlib
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.api import executor as exc_mod
    from app.api.schemas import BacktestMode, BacktestRequest, RunDetail, TimeseriesResponse

from app.repository.backtest.models import (
    Run,
    RunConfig,
    RunResult,
    RunTimeseries,
    Strategy,
    Trade,
)
from app.trading.strategy.loader import STRATEGY_MAP

logger = structlog.get_logger()

DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "data"))

# Lazy-loaded to avoid backtest → api import boundary violation at module level.
# Tests can still patch "app.backtest.service.exc_mod" because __getattr__ makes
# it appear as a real module attribute on first access.
def _load_exc_mod():
    """Lazy import of app.api.executor — called on first access of exc_mod."""
    import sys

    from app.api import executor

    # Store in module globals so subsequent lookups (and mock.patch) work.
    current_module = sys.modules[__name__]
    current_module.exc_mod = executor
    return executor


def __getattr__(name: str):
    if name == "exc_mod":
        return _load_exc_mod()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")





def _csv_path(symbol: str, timeframe: str) -> str:
    safe = symbol.replace("/", "")
    return os.path.join(DATA_DIR, f"{safe}_{timeframe}.csv")


class BacktestService:
    """Business logic for backtest operations. Routes to the correct runner by mode."""

    # ------------------------------------------------------------------
    # Start a backtest run
    # ------------------------------------------------------------------

    async def start_run(self, req: BacktestRequest, db: Session) -> int:
        """Validate params, create DB run, submit to executor. Returns run_id."""
        from app.api.schemas import BacktestMode

        mode = self._resolve_mode(req)
        is_portfolio = mode == BacktestMode.PORTFOLIO

        # 1. Resolve strategy (fail fast before filesystem checks)
        strategy_class = STRATEGY_MAP.get(req.strategy)
        if strategy_class is None:
            raise ValueError(f"Unknown strategy: {req.strategy}. Available: {list(STRATEGY_MAP)}")

        strat_row = db.query(Strategy).filter_by(name=req.strategy).first()
        if strat_row is None:
            raise ValueError(f"Strategy '{req.strategy}' not seeded in DB")

        is_batch = mode == BacktestMode.BATCH

        # 2. Resolve CSV path (single mode; download happens inline in worker)
        csv_path = None
        if not is_portfolio and not is_batch:
            csv_path = _csv_path(req.symbol, req.timeframe)

        # 3. Create Run + RunConfig rows
        run = Run(
            strategy_id=strat_row.id,
            status="running",
            started_at=datetime.utcnow(),
        )
        db.add(run)
        db.flush()

        if is_batch or is_portfolio:
            cfg_symbol = "BATCH" if is_batch else "PORTFOLIO"
        else:
            cfg_symbol = req.symbol

        cfg = RunConfig(
            run_id=run.id,
            symbol=cfg_symbol,
            symbols_list=req.symbols if (is_batch or is_portfolio) else None,
            is_batch_mode=is_batch,
            timeframe=req.timeframe,
            start_date=date.fromisoformat(req.start_date),
            end_date=date.fromisoformat(req.end_date),
            initial_capital=req.initial_capital,
            leverage=req.leverage,
            risk_per_trade_pct=req.risk_per_trade_pct,
            fee_tier=req.fee_tier,
            slippage_model=req.slippage_model,
            slippage_pct=req.slippage_pct,
            params=req.params,
        )
        db.add(cfg)
        db.commit()

        run_id = run.id

        # 4. Create SSE queue + submit to executor
        loop = asyncio.get_event_loop()
        exc_mod.create_progress_queue(run_id)
        progress_cb = exc_mod.make_progress_callback(run_id, loop)

        worker_fn = self._build_worker(
            mode=mode,
            req=req,
            run_id=run_id,
            loop=loop,
            progress_cb=progress_cb,
            strategy_class=strategy_class,
            csv_path=csv_path,
        )
        exc_mod.submit_backtest(run_id, worker_fn)

        return run_id

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_run_detail(self, run_id: int, db: Session) -> RunDetail:
        """Fetch run config + metrics + trades from DB."""
        from app.api.schemas import RunDetail

        run = db.query(Run).filter_by(id=run_id).first()
        if run is None:
            raise LookupError("Run not found")

        strat = db.query(Strategy).filter_by(id=run.strategy_id).first()
        cfg = db.query(RunConfig).filter_by(run_id=run_id).first()
        result = db.query(RunResult).filter_by(run_id=run_id).first()
        trades = db.query(Trade).filter_by(run_id=run_id).order_by(Trade.entry_time).all()

        return RunDetail(
            id=run.id,
            strategy_name=strat.name if strat else "",
            symbol=cfg.symbol if cfg else "",
            timeframe=cfg.timeframe if cfg else "",
            status=run.status,
            created_at=run.created_at.isoformat() if run.created_at else "",
            config=_build_config_dict(cfg),
            results=_build_results_dict(result),
            trades=_build_trades_list(trades),
        )

    def get_timeseries(self, run_id: int, db: Session) -> TimeseriesResponse:
        """Fetch compressed equity/drawdown curves."""
        from app.api.schemas import TimeseriesResponse

        ts = db.query(RunTimeseries).filter_by(run_id=run_id).first()
        if ts is None:
            raise LookupError("Timeseries not found for this run")

        equity_curve = json.loads(zlib.decompress(ts.equity_curve)) if ts.equity_curve else []
        drawdown_curve = json.loads(zlib.decompress(ts.drawdown_curve)) if ts.drawdown_curve else []

        return TimeseriesResponse(
            run_id=run_id,
            equity_curve=equity_curve,
            drawdown_curve=drawdown_curve,
            monthly_returns=ts.monthly_returns or {},
        )

    def cancel_run(self, run_id: int, db: Session) -> dict:
        """Cancel a running backtest."""
        cancelled = exc_mod.cancel_job(run_id)
        run = db.query(Run).filter_by(id=run_id).first()
        if run:
            run.status = "cancelled"
            db.commit()
        return {"cancelled": True, "was_pending": cancelled}

    async def stream_progress(self, run_id: int) -> AsyncIterator[str]:
        """Yield SSE-formatted progress events."""
        q = exc_mod.get_progress_queue(run_id)
        if q is None:
            yield f"event: complete\ndata: {json.dumps({'run_id': run_id, 'status': 'completed'})}\n\n"
            return

        try:
            while True:
                event = await asyncio.wait_for(q.get(), timeout=300.0)
                evt_name = event.pop("event", "progress")
                yield f"event: {evt_name}\ndata: {json.dumps(event)}\n\n"
                if evt_name in ("complete", "error"):
                    break
        except TimeoutError:
            yield f"event: error\ndata: {json.dumps({'message': 'timeout'})}\n\n"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_mode(req: BacktestRequest) -> BacktestMode:
        """Determine backtest mode from request."""
        from app.api.schemas import BacktestMode

        if req.mode is not None:
            return req.mode
        return BacktestMode.PORTFOLIO if req.symbols else BacktestMode.SINGLE

    def _build_worker(
        self,
        *,
        mode: BacktestMode,
        req: BacktestRequest,
        run_id: int,
        loop: asyncio.AbstractEventLoop,
        progress_cb,
        strategy_class,
        csv_path: str | None,
    ):
        """Return a callable to execute in the thread pool."""
        from app.api.schemas import BacktestMode
        from app.backtest.workers import run_batch_worker, run_portfolio_worker, run_single_worker

        if mode == BacktestMode.PORTFOLIO:
            return lambda: run_portfolio_worker(
                req=req,
                run_id=run_id,
                loop=loop,
                progress_cb=progress_cb,
                publish_event_fn=exc_mod.publish_event,
                cleanup_fn=exc_mod.cleanup_job,
            )
        if mode == BacktestMode.BATCH:
            return lambda: run_batch_worker(
                req=req,
                run_id=run_id,
                loop=loop,
                progress_cb=progress_cb,
                publish_event_fn=exc_mod.publish_event,
                cleanup_fn=exc_mod.cleanup_job,
            )
        return lambda: run_single_worker(
            req=req,
            run_id=run_id,
            loop=loop,
            progress_cb=progress_cb,
            publish_event_fn=exc_mod.publish_event,
            cleanup_fn=exc_mod.cleanup_job,
            strategy_class=strategy_class,
            csv_path=csv_path,
        )


# ------------------------------------------------------------------
# Dict builders (pure functions, no DB access)
# ------------------------------------------------------------------


def _build_config_dict(cfg: RunConfig | None) -> dict[str, Any]:
    if not cfg:
        return {}
    return {
        "symbol": cfg.symbol,
        "timeframe": cfg.timeframe,
        "start_date": cfg.start_date.isoformat() if cfg.start_date else None,
        "end_date": cfg.end_date.isoformat() if cfg.end_date else None,
        "initial_capital": str(cfg.initial_capital),
        "leverage": cfg.leverage,
        "risk_per_trade_pct": str(cfg.risk_per_trade_pct),
        "params": cfg.params or {},
    }


def _build_results_dict(result: RunResult | None) -> dict[str, Any] | None:
    if not result:
        return None
    return {
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


def _build_trades_list(trades: list[Trade]) -> list[dict[str, Any]]:
    return [
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
