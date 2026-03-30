"""
Backtest worker functions — run in ThreadPoolExecutor.

Extracted from service.py to keep file sizes under 400 lines.
Handles inline download + backtest execution + result persistence.
"""

from __future__ import annotations

import structlog

from app.backtest.config_builder import build_backtest_config
from app.backtest.data.inline_download import download_if_missing
from app.backtest.persistence import mark_failed, persist_results

logger = structlog.get_logger()


def run_single_worker(
    *,
    req,
    run_id: int,
    loop,
    progress_cb,
    publish_event_fn,
    cleanup_fn,
    strategy_class,
    csv_path: str,
):
    """Worker fn for single-symbol backtest. Called from ThreadPoolExecutor."""
    from app.backtest.engine.backtest_engine import BacktestEngine

    try:
        # Phase 1: Download data if CSV missing (with file lock)
        download_if_missing(
            csv_path=csv_path,
            symbol=req.symbol,
            timeframe=req.timeframe,
            start_date=req.start_date,
            end_date=req.end_date,
            run_id=run_id,
            loop=loop,
            publish_event_fn=publish_event_fn,
        )

        # Phase 2: Run backtest
        engine_config = build_backtest_config(
            symbol=req.symbol,
            timeframe=req.timeframe,
            strategy_name=req.strategy,
            initial_balance=float(req.initial_capital),
            leverage=req.leverage,
            risk_per_trade_pct=float(req.risk_per_trade_pct),
            params=req.params,
        )
        engine = BacktestEngine(csv_path, strategy_class, engine_config)
        results = engine.run(on_progress=progress_cb)

        # Phase 3: Persist
        persist_results(run_id, results)
        publish_event_fn(run_id, loop, "complete", {"run_id": run_id, "status": "completed"})

    except Exception as err:
        logger.error("backtest_worker_error", run_id=run_id, error=str(err))
        mark_failed(run_id, str(err))
        publish_event_fn(run_id, loop, "error", {"run_id": run_id, "message": str(err)})
    finally:
        cleanup_fn(run_id)


def run_portfolio_worker(
    *,
    req,
    run_id: int,
    loop,
    progress_cb,
    publish_event_fn,
    cleanup_fn,
):
    """Worker fn for portfolio backtest. Called from ThreadPoolExecutor."""
    from app.backtest.runners.portfolio_runner import _run_portfolio_backtest

    try:
        results = _run_portfolio_backtest(
            symbols=req.symbols,
            strategy_name=req.strategy,
            timeframe=req.timeframe,
            start_date=req.start_date,
            end_date=req.end_date,
            initial_capital=float(req.initial_capital),
            leverage=req.leverage,
            risk_per_trade_pct=float(req.risk_per_trade_pct),
            fee_tier=req.fee_tier,
            slippage_model=req.slippage_model,
            slippage_pct=float(req.slippage_pct),
            params=req.params,
            progress_cb=progress_cb,
        )
        persist_results(run_id, results)
        publish_event_fn(run_id, loop, "complete", {"run_id": run_id, "status": "completed"})

    except Exception as err:
        logger.error("portfolio_worker_error", run_id=run_id, error=str(err))
        mark_failed(run_id, str(err))
        publish_event_fn(run_id, loop, "error", {"run_id": run_id, "message": str(err)})
    finally:
        cleanup_fn(run_id)
