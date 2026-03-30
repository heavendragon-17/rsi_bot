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


def run_batch_worker(
    *,
    req,
    run_id: int,
    loop,
    progress_cb,
    publish_event_fn,
    cleanup_fn,
):
    """Worker fn for batch backtest. Wraps existing BatchRunner."""
    from app.backtest.runners.batch_runner import BatchRunner

    try:
        # Phase 1: Download data for all symbols if missing
        for i, symbol in enumerate(req.symbols):
            csv_path = _csv_path(symbol, req.timeframe)
            download_if_missing(
                csv_path=csv_path,
                symbol=symbol,
                timeframe=req.timeframe,
                start_date=req.start_date,
                end_date=req.end_date,
                run_id=run_id,
                loop=loop,
                publish_event_fn=publish_event_fn,
            )

        publish_event_fn(run_id, loop, "download_complete", {"symbol": "all"})

        # Phase 2: Build config dict for BatchRunner
        config = {
            "strategy": req.strategy,
            "strategy_params": req.params,
            "bot": {"timeframe": req.timeframe},
            "risk": {
                "leverage": req.leverage,
                "risk_per_trade_pct": float(req.risk_per_trade_pct),
            },
        }

        max_workers = req.max_workers or min(4, len(req.symbols))
        runner = BatchRunner(
            symbols=req.symbols,
            config=config,
            strategy_name=req.strategy,
            timeframe=req.timeframe,
            balance=float(req.initial_capital),
        )
        batch_results = runner.run(
            max_workers=max_workers,
            progress_cb=progress_cb,
        )

        # Phase 3: Aggregate and persist
        aggregated = _aggregate_batch_results(batch_results, float(req.initial_capital))
        persist_results(run_id, aggregated)
        publish_event_fn(run_id, loop, "complete", {
            "run_id": run_id,
            "status": "completed",
        })

    except Exception as err:
        logger.error("batch_worker_error", run_id=run_id, error=str(err))
        mark_failed(run_id, str(err))
        publish_event_fn(run_id, loop, "error", {"run_id": run_id, "message": str(err)})
    finally:
        cleanup_fn(run_id)


def _csv_path(symbol: str, timeframe: str) -> str:
    """Build CSV path for a symbol. Mirrors service._csv_path."""
    import os

    data_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "data"))
    safe = symbol.replace("/", "")
    return os.path.join(data_dir, f"{safe}_{timeframe}.csv")


def _aggregate_batch_results(
    batch_results: list[dict], initial_capital: float
) -> dict:
    """Aggregate per-symbol batch results into a single results dict for persistence."""
    if not batch_results:
        return {
            "net_profit": 0.0,
            "net_profit_pct": 0.0,
            "metrics": {},
            "drawdown": {},
            "risk_metrics": {},
            "equity_curve": [],
            "drawdown_curve": [],
            "monthly_returns": {},
            "round_trips": [],
        }

    total_profit = sum(r.get("profit", 0) for r in batch_results)
    total_trades = sum(r.get("trades", 0) for r in batch_results)

    # Aggregate metrics from individual results
    all_metrics = [r.get("metrics", {}) for r in batch_results]
    win_counts = sum(m.get("win_count", 0) for m in all_metrics)
    loss_counts = sum(m.get("loss_count", 0) for m in all_metrics)
    gross_profits = sum(float(m.get("gross_profit", 0)) for m in all_metrics)
    gross_losses = sum(float(m.get("gross_loss", 0)) for m in all_metrics)

    win_rate = (win_counts / total_trades * 100) if total_trades > 0 else 0
    profit_factor = (gross_profits / abs(gross_losses)) if gross_losses != 0 else 0

    # Aggregate Sharpe (average across symbols)
    sharpe_values = [
        r.get("metrics", {}).get("sharpe_ratio")
        for r in batch_results
        if r.get("metrics", {}).get("sharpe_ratio") is not None
    ]
    avg_sharpe = sum(sharpe_values) / len(sharpe_values) if sharpe_values else None

    max_dd_pcts = [
        r.get("drawdown", {}).get("max_drawdown_pct", 0)
        if isinstance(r.get("drawdown"), dict)
        else r.get("metrics", {}).get("max_drawdown_pct", 0)
        for r in batch_results
    ]
    max_dd = max(max_dd_pcts) if max_dd_pcts else 0

    return {
        "net_profit": total_profit,
        "net_profit_pct": (total_profit / initial_capital * 100) if initial_capital else 0,
        "metrics": {
            "total_trades": total_trades,
            "win_count": win_counts,
            "loss_count": loss_counts,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "gross_profit": gross_profits,
            "gross_loss": gross_losses,
            "sharpe_ratio": avg_sharpe,
        },
        "drawdown": {
            "max_drawdown_pct": max_dd,
        },
        "risk_metrics": {
            "sharpe_ratio": avg_sharpe,
        },
        "equity_curve": [],
        "drawdown_curve": [],
        "monthly_returns": {},
        "round_trips": [],
    }


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
    import os

    from app.backtest.runners.portfolio_runner import _run_portfolio_backtest

    try:
        # Dynamic progress split: only allocate download weight if files missing
        symbols_needing_download = [
            s for s in req.symbols
            if not os.path.exists(_csv_path(s, req.timeframe))
        ]
        needs_download = len(symbols_needing_download) > 0
        download_weight = 0.3 if needs_download else 0.0
        backtest_weight = 1.0 - download_weight

        # Phase 1: Download (only if needed)
        if needs_download:
            for i, symbol in enumerate(symbols_needing_download):
                csv_path = _csv_path(symbol, req.timeframe)
                download_if_missing(
                    csv_path=csv_path,
                    symbol=symbol,
                    timeframe=req.timeframe,
                    start_date=req.start_date,
                    end_date=req.end_date,
                    run_id=run_id,
                    loop=loop,
                    publish_event_fn=publish_event_fn,
                )
                pct = int((i + 1) / len(symbols_needing_download) * download_weight * 100)
                progress_cb({"pct": pct})
            publish_event_fn(run_id, loop, "download_complete", {"symbol": "all"})

        # Phase 2: Run portfolio engine with weighted progress
        base_pct = int(download_weight * 100)
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
            progress_cb=lambda data: progress_cb({
                "pct": base_pct + int(data.get("pct", 0) * backtest_weight),
            }),
        )
        persist_results(run_id, results)
        publish_event_fn(run_id, loop, "complete", {"run_id": run_id, "status": "completed"})

    except Exception as err:
        logger.error("portfolio_worker_error", run_id=run_id, error=str(err))
        mark_failed(run_id, str(err))
        publish_event_fn(run_id, loop, "error", {"run_id": run_id, "message": str(err)})
    finally:
        cleanup_fn(run_id)
