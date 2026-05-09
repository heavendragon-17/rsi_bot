"""
Backtest worker functions — run in ThreadPoolExecutor.

Extracted from service.py to keep file sizes under 400 lines.
Handles inline download + backtest execution + result persistence.
"""

from __future__ import annotations

import os
import webbrowser

import structlog

from app.backtest.batch_aggregation import aggregate_batch_results
from app.backtest.config_builder import build_backtest_config
from app.backtest.data.inline_download import download_if_missing
from app.backtest.persistence import mark_failed, persist_results

logger = structlog.get_logger()

REPORT_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "report", "ui"))
_BENCHMARK_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "data"))


def _inject_benchmark(results: dict, req) -> None:
    """Compute and inject benchmark_curve into results dict (in-place)."""
    benchmark = getattr(req, "benchmark", None)
    if not benchmark:
        return
    from app.backtest.benchmark import compute_benchmark_curve

    results["benchmark_curve"] = compute_benchmark_curve(
        benchmark=benchmark,
        timeframe=req.timeframe,
        start_date=req.start_date,
        end_date=req.end_date,
        initial_capital=float(req.initial_capital),
        data_dir=_BENCHMARK_DATA_DIR,
    )


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
    import os
    import tempfile

    import pandas as pd

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

        # Phase 1b: Filter CSV to the requested date range so the engine runs
        # exactly the same rows as the CLI when given the same dates.
        effective_csv = csv_path
        tmp_path = None
        if req.start_date or req.end_date:
            df = pd.read_csv(csv_path)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            mask = pd.Series([True] * len(df))
            if req.start_date:
                mask &= df["timestamp"] >= req.start_date
            if req.end_date:
                mask &= df["timestamp"] <= req.end_date
            filtered = df[mask].reset_index(drop=True)
            if filtered.empty:
                csv_min = df["timestamp"].min().date() if not df.empty else "?"
                csv_max = df["timestamp"].max().date() if not df.empty else "?"
                raise ValueError(
                    f"No candles found between {req.start_date} and {req.end_date}. "
                    f"Available data: {csv_min} → {csv_max}. "
                    "Adjust the date range or download more data."
                )
            tmp = tempfile.NamedTemporaryFile(
                suffix=".csv", delete=False, mode="w"
            )
            tmp_path = tmp.name
            tmp.close()
            filtered.to_csv(tmp_path, index=False)
            effective_csv = tmp_path

        # Phase 2: Run backtest — load_yaml=False so config.yaml never
        # overrides what the UI sent; all params are explicit.
        # Fees are NOT passed here so the engine uses DEFAULT_TAKER_FEE /
        # DEFAULT_MAKER_FEE from constants — exactly what the CLI uses.
        taker_fee = float(req.taker_fee_pct) / 100
        maker_fee = float(req.maker_fee_pct) / 100
        engine_config = build_backtest_config(
            symbol=req.symbol,
            timeframe=req.timeframe,
            strategy_name=req.strategy,
            initial_balance=float(req.initial_capital),
            leverage=req.leverage,
            risk_per_trade_pct=float(req.risk_per_trade_pct),
            params=req.params,
            load_yaml=False,
            tp1_close_pct=req.tp1_close_pct,
            tp2_close_pct=req.tp2_close_pct,
            max_position_size_pct=req.max_position_size_pct,
            min_sl_distance_pct=req.min_sl_distance_pct,
            use_risk_based_sizing=req.use_risk_based_sizing,
            use_initial_capital_for_risk=req.use_initial_capital_for_risk,
            taker_fee=taker_fee,
            maker_fee=maker_fee,
            slippage_pct=float(req.slippage_pct),
        )
        try:
            engine = BacktestEngine(effective_csv, strategy_class, engine_config)
            results = engine.run(on_progress=progress_cb)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        # Phase 3: Persist + generate debug HTML report
        _inject_benchmark(results, req)
        total_trades = results.get("metrics", {}).get("total_trades", 0) or len(results.get("round_trips", []))
        logger.info(
            "backtest_result_summary",
            run_id=run_id,
            total_trades=total_trades,
            net_profit=results.get("net_profit"),
            net_profit_pct=results.get("net_profit_pct"),
        )
        persist_results(run_id, results)

        publish_event_fn(run_id, loop, "complete", {"run_id": run_id, "status": "completed"})

    except Exception as err:
        err_msg = f"{type(err).__name__}: {err}"
        logger.error("backtest_worker_error", run_id=run_id, error=err_msg)
        mark_failed(run_id, err_msg)
        publish_event_fn(run_id, loop, "error", {"run_id": run_id, "message": err_msg})
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
        for symbol in req.symbols:
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

        # Phase 2: Build config dict for BatchRunner — include ALL risk
        # params so results match CLI (which reads them from config.yaml).
        config = {
            "strategy": req.strategy,
            "strategy_params": req.params,
            "bot": {"timeframe": req.timeframe},
            "backtest": {
                "start_date": req.start_date,
                "end_date": req.end_date,
                "initial_balance": float(req.initial_capital),
            },
            "risk": {
                "leverage": req.leverage,
                "risk_per_trade_pct": float(req.risk_per_trade_pct),
                "tp1_close_pct": req.tp1_close_pct,
                "tp2_close_pct": req.tp2_close_pct,
                "max_position_size_pct": req.max_position_size_pct,
                "min_sl_distance_pct": req.min_sl_distance_pct,
                "use_risk_based_sizing": req.use_risk_based_sizing,
                "use_initial_capital_for_risk": req.use_initial_capital_for_risk,
                "taker_fee": float(req.taker_fee_pct) / 100,
                "maker_fee": float(req.maker_fee_pct) / 100,
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
        aggregated = aggregate_batch_results(batch_results, float(req.initial_capital))
        _inject_benchmark(aggregated, req)
        persist_results(run_id, aggregated)

        publish_event_fn(run_id, loop, "complete", {
            "run_id": run_id,
            "status": "completed",
        })

    except Exception as err:
        err_msg = f"{type(err).__name__}: {err}"
        logger.error("batch_worker_error", run_id=run_id, error=err_msg)
        mark_failed(run_id, err_msg)
        publish_event_fn(run_id, loop, "error", {"run_id": run_id, "message": err_msg})
    finally:
        cleanup_fn(run_id)


def _generate_and_open_report(
    *,
    results: dict,
    symbol: str,
    timeframe: str,
    strategy_name: str,
    leverage: int,
    strategy_params: dict | None,
    run_id: int,
) -> str | None:
    """Generate HTML report and open it in the browser for debugging.

    Always generates the report even with 0 trades so you can see
    the equity curve and metrics to debug why no signals fired.
    """
    from app.backtest.reporting.html import generate_html_report

    try:
        os.makedirs(REPORT_DIR, exist_ok=True)
        report_path = generate_html_report(
            results=results,
            symbol=symbol,
            timeframe=timeframe,
            strategy_name=strategy_name,
            leverage=leverage,
            strategy_params=strategy_params or {},
            return_only=False,
            output_dir=REPORT_DIR,
        )
        if report_path:
            logger.info("ui_report_generated", run_id=run_id, path=report_path)
            webbrowser.open("file://" + os.path.abspath(report_path))
            return report_path
        return None
    except Exception as err:
        logger.warning("ui_report_failed", run_id=run_id, error=str(err))
        return None


def _csv_path(symbol: str, timeframe: str) -> str:
    """Build CSV path for a symbol. Mirrors service._csv_path."""
    import os

    data_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "data"))
    safe = symbol.replace("/", "")
    return os.path.join(data_dir, f"{safe}_{timeframe}.csv")


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
    try:
        from app.backtest.runners.portfolio_runner import _run_portfolio_backtest

        logger.info("portfolio_worker_started", run_id=run_id, symbols=req.symbols)
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
            for symbol in symbols_needing_download:
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

        # Phase 2: Run portfolio backtest
        results = _run_portfolio_backtest(
            symbols=req.symbols,
            strategy_name=req.strategy,
            timeframe=req.timeframe,
            initial_capital=float(req.initial_capital),
            leverage=req.leverage,
            risk_per_trade_pct=float(req.risk_per_trade_pct),
            params=req.params,
            start_date=req.start_date,
            end_date=req.end_date,
            tp1_close_pct=req.tp1_close_pct,
            tp2_close_pct=req.tp2_close_pct,
            max_position_size_pct=req.max_position_size_pct,
            min_sl_distance_pct=req.min_sl_distance_pct,
            use_risk_based_sizing=req.use_risk_based_sizing,
            use_initial_capital_for_risk=req.use_initial_capital_for_risk,
            taker_fee=float(req.taker_fee_pct) / 100,
            maker_fee=float(req.maker_fee_pct) / 100,
            slippage_pct=float(req.slippage_pct),
            progress_cb=lambda data: progress_cb({
                **data,
                "pct": int(download_weight * 100 + data.get("pct", 0) * backtest_weight),
            }),
        )

        # Phase 3: Persist
        _inject_benchmark(results, req)
        persist_results(run_id, results)

        publish_event_fn(run_id, loop, "complete", {
            "run_id": run_id,
            "status": "completed",
        })

    except Exception as err:
        err_msg = f"{type(err).__name__}: {err}"
        logger.error("portfolio_worker_error", run_id=run_id, error=err_msg)
        mark_failed(run_id, err_msg)
        publish_event_fn(run_id, loop, "error", {"run_id": run_id, "message": err_msg})
    finally:
        cleanup_fn(run_id)
