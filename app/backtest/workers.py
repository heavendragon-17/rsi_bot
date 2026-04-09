"""
Backtest worker functions — run in ThreadPoolExecutor.

Extracted from service.py to keep file sizes under 400 lines.
Handles inline download + backtest execution + result persistence.
"""

from __future__ import annotations

import os
import webbrowser

import pandas as pd
import structlog

from app.backtest.config_builder import build_backtest_config
from app.backtest.data.inline_download import download_if_missing
from app.backtest.engine.curves import calculate_portfolio_drawdown
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

        # Phase 2: Build config dict for BatchRunner — include ALL risk
        # params so results match CLI (which reads them from config.yaml).
        config = {
            "strategy": req.strategy,
            "strategy_params": req.params,
            "bot": {"timeframe": req.timeframe},
            "backtest": {
                "start_date": req.start_date,
                "end_date": req.end_date,
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
        aggregated = _aggregate_batch_results(batch_results, float(req.initial_capital))
        _inject_benchmark(aggregated, req)
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


def _build_batch_portfolio_curves(
    batch_results: list[dict], initial_capital: float
) -> tuple[list[dict], list[dict], list[dict], dict]:
    """Build combined portfolio equity, drawdown, and dispersion curves from batch results.

    Forward-fill rule per symbol:
      - Dates before the symbol's first trade: symbol excluded (not yet active).
      - Dates from first trade onward with exact data: use that balance.
      - Dates after the symbol's last trade: forward-fill with its final balance.

    This prevents the portfolio curve from being biased toward whichever symbol
    happened to have the most recent trade exit, which was causing artificial
    drawdown spikes and chart/stats mismatches.

    Returns:
        (equity_curve, drawdown_curve, dispersion_range, dd_stats) — all empty/{}
        if no data. dd_stats contains max_drawdown_pct, max_drawdown_value, etc.
    """
    sym_curves: list[dict[str, float]] = []
    for r in batch_results:
        ec = r.get("equity_curve", [])
        if not ec or initial_capital <= 0:
            continue
        # Map date→balance, using date[:10] to normalize to YYYY-MM-DD
        curve = {
            str(p.get("date", p.get("time", "")))[:10]: float(p["balance"])
            for p in ec
            if ("date" in p or "time" in p) and "balance" in p
        }
        if curve:
            sym_curves.append(curve)

    if not sym_curves:
        return [], [], [], {}

    # Collect all unique dates in sorted order
    all_dates = sorted(set().union(*(c.keys() for c in sym_curves)))

    # Precompute first/last date per symbol for the forward-fill logic
    sym_meta = [
        {"curve": c, "first": min(c.keys()), "last": max(c.keys())}
        for c in sym_curves
    ]

    equity_curve: list[dict] = []
    dispersion_range: list[dict] = []

    for date in all_dates:
        pcts: list[float] = []
        for meta in sym_meta:
            c, first, last = meta["curve"], meta["first"], meta["last"]
            if date < first:
                continue  # symbol not yet active — exclude from average
            balance = c[date] if date in c else c[last]  # exact or forward-fill
            pcts.append((balance - initial_capital) / initial_capital * 100)

        if not pcts:
            continue

        avg_pct = sum(pcts) / len(pcts)
        equity_curve.append({"date": date, "balance": round(initial_capital * (1 + avg_pct / 100), 2)})
        dispersion_range.append({"date": date, "min": round(min(pcts), 4), "max": round(max(pcts), 4)})

    # Delegate drawdown to the shared utility (also computes max_drawdown_value)
    dd_stats = calculate_portfolio_drawdown(equity_curve, initial_capital)
    return equity_curve, dd_stats["drawdown_curve"], dispersion_range, dd_stats


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
            "dispersion_range": [],
            "monthly_returns": {},
            "round_trips": [],
        }

    n_symbols = max(len(batch_results), 1)
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

    # Aggregate Sharpe (average across symbols) — sharpe lives in risk_metrics
    sharpe_values = [
        r.get("risk_metrics", {}).get("sharpe_ratio")
        for r in batch_results
        if r.get("risk_metrics", {}).get("sharpe_ratio") is not None
    ]
    avg_sharpe = sum(sharpe_values) / len(sharpe_values) if sharpe_values else None

    # Collect all round_trips from per-symbol results so trades get persisted
    all_round_trips: list[dict] = []
    for r in batch_results:
        rt = r.get("round_trips")
        sym = r.get("symbol", "")
        if isinstance(rt, pd.DataFrame) and not rt.empty:
            rt_copy = rt.copy()
            if "symbol" not in rt_copy.columns:
                rt_copy["symbol"] = sym
            all_round_trips.extend(rt_copy.to_dict("records"))
        elif isinstance(rt, list):
            for item in rt:
                if isinstance(item, dict) and "symbol" not in item:
                    item = {**item, "symbol": sym}
                all_round_trips.append(item)

    equity_curve, drawdown_curve, dispersion_range, dd_stats = _build_batch_portfolio_curves(
        batch_results, initial_capital
    )

    # dd_stats comes from calculate_portfolio_drawdown — use portfolio-level values
    max_dd = dd_stats.get("max_drawdown_pct", 0)
    max_dd_value = dd_stats.get("max_drawdown_value", 0)

    return {
        "net_profit": total_profit / n_symbols,
        "net_profit_pct": (total_profit / n_symbols / initial_capital * 100) if initial_capital else 0,
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
            "max_drawdown_value": max_dd_value,
        },
        "risk_metrics": {
            "sharpe_ratio": avg_sharpe,
        },
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "dispersion_range": dispersion_range,
        "monthly_returns": {},
        "round_trips": all_round_trips,
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
        logger.error("portfolio_worker_error", run_id=run_id, error=str(err))
        mark_failed(run_id, str(err))
        publish_event_fn(run_id, loop, "error", {"run_id": run_id, "message": str(err)})
    finally:
        cleanup_fn(run_id)
