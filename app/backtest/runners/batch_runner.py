"""
Multi-symbol parallel backtest runner.

Refactored from run_batch_analysis.py — orchestrates parallel backtest
execution across multiple symbols with report generation.
"""

from __future__ import annotations

import argparse
import copy
import os
import time
import webbrowser
from concurrent.futures import ProcessPoolExecutor, as_completed
from decimal import Decimal

import pandas as pd
import structlog
import yaml  # type: ignore[import-untyped]

from app.backtest.data.manager import DataManager
from app.backtest.engine.backtest_engine import BacktestEngine
from app.backtest.enrichment import enrich_round_trips
from app.backtest.reporting.batch_report import BatchHtmlGenerator
from app.backtest.reporting.export import export_combined_signals, export_signals_to_csv
from app.backtest.reporting.reporter import BacktestReporter
from app.core.logging import setup_logging
from app.trading.strategy.loader import STRATEGY_MAP

logger = structlog.get_logger()

BACKTEST_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BACKTEST_DIR))
SYMBOLS_PATH = os.path.join(BACKTEST_DIR, "symbols.txt")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.yaml")
REPORT_DIR = os.path.join(BACKTEST_DIR, "report")
DATA_DIR = os.path.join(BACKTEST_DIR, "data")


class BatchRunner:
    """Multi-symbol parallel backtest orchestration."""

    def __init__(
        self,
        symbols: list[str],
        config: dict,
        strategy_name: str,
        timeframe: str,
        balance: float,
        data_dir: str = DATA_DIR,
        report_dir: str = REPORT_DIR,
    ):
        self.symbols = symbols
        self.config = config
        self.strategy_name = strategy_name
        self.timeframe = timeframe
        self.balance = balance
        self.data_dir = data_dir
        self.report_dir = report_dir

    def run(self, max_workers: int = 4, progress_cb=None) -> list[dict]:
        """Execute backtests across all symbols and return batch results."""
        os.makedirs(self.report_dir, exist_ok=True)
        start_time = time.time()
        batch_results: list[dict] = []
        total = len(self.symbols)

        def _report(completed: int) -> None:
            if progress_cb and total > 0:
                progress_cb({"pct": int(completed / total * 100)})

        if max_workers == 1:
            for i, symbol in enumerate(self.symbols):
                result = _run_single_symbol(
                    symbol,
                    self.config,
                    self.timeframe,
                    self.balance,
                    self.strategy_name,
                    self.data_dir,
                    self.report_dir,
                )
                if result and "error" not in result:
                    batch_results.append(result)
                elif result:
                    logger.warning("symbol_failed", symbol=symbol, error=result["error"])
                _report(i + 1)
        else:
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        _run_single_symbol,
                        symbol,
                        self.config,
                        self.timeframe,
                        self.balance,
                        self.strategy_name,
                        self.data_dir,
                        self.report_dir,
                    ): symbol
                    for symbol in self.symbols
                }
                completed = 0
                for future in as_completed(futures):
                    symbol = futures[future]
                    completed += 1
                    try:
                        result = future.result()
                        if result and "error" not in result:
                            batch_results.append(result)
                            logger.info("symbol_done", symbol=symbol, n=completed, total=total)
                        elif result:
                            logger.warning("symbol_failed", symbol=symbol, error=result["error"])
                    except Exception as exc:
                        logger.error("symbol_exception", symbol=symbol, error=str(exc))
                    _report(completed)

        elapsed = time.time() - start_time
        logger.info("batch_complete", elapsed=f"{elapsed:.1f}s", symbols=len(self.symbols))

        if batch_results:
            export_combined_signals(batch_results, self.report_dir)
            generator = BatchHtmlGenerator(batch_results)
            report_path = os.path.join(self.report_dir, "batch_report.html")
            generator.generate(filename=report_path)

        return batch_results


# ── per-symbol worker (must be top-level for pickling) ──────────────────────


def _run_single_symbol(
    symbol: str,
    config: dict,
    timeframe: str,
    balance: float,
    strategy_name: str,
    data_dir: str,
    report_dir: str,
) -> dict:
    """Run backtest for a single symbol.  Designed for ProcessPoolExecutor."""
    setup_logging(level="INFO")
    try:
        from app.backtest.data.download import calculate_candle_limit
        from app.trading.strategy.loader import STRATEGY_MAP as strategy_map

        strategy_class = strategy_map.get(strategy_name)
        if not strategy_class:
            return {"symbol": symbol, "error": f"Unknown strategy: {strategy_name}"}

        dm = DataManager(data_dir=data_dir, timeframe=timeframe)

        # Prefer date-range limit (API path) over duration config (CLI path)
        start_date = config.get("backtest", {}).get("start_date")
        end_date = config.get("backtest", {}).get("end_date")
        if start_date and end_date:
            from datetime import date as _date
            span = max((_date.fromisoformat(end_date) - _date.fromisoformat(start_date)).days + 1, 1)
            limit = calculate_candle_limit(timeframe, days=span)
        else:
            duration_cfg = config.get("backtest", {}).get("duration", {})
            try:
                limit = calculate_candle_limit(
                    timeframe,
                    days=duration_cfg.get("days", 0),
                    months=duration_cfg.get("months", 0),
                    years=duration_cfg.get("years", 0),
                )
            except ValueError:
                limit = 8832

        data_file = dm.ensure_data(symbol, limit)

        run_config = copy.deepcopy(config)
        run_config["symbols"] = [symbol]

        engine = BacktestEngine(data_file, strategy_class, run_config)
        engine.exchange.initial_balance = Decimal(str(balance))
        engine.exchange.balance = Decimal(str(balance))
        results = engine.run()

        export_signals_to_csv(engine, symbol, report_dir)

        debug_rows = getattr(engine.strategy, "_debug_rows", [])
        if debug_rows:
            safe_sym = symbol.replace("/", "_")
            debug_path = os.path.join(report_dir, "debug_csv", f"debug_{safe_sym}_{timeframe}.csv")
            engine.strategy.export_debug_csv(debug_path)
            results = enrich_round_trips(results, debug_rows)

        leverage = run_config.get("risk", {}).get("leverage", 1)
        strategy_params = {
            **getattr(strategy_class, "DEFAULT_CONFIG", {}),
            **run_config.get("strategy_params", {}),
        }
        reporter = BacktestReporter(
            results,
            symbol=symbol,
            timeframe=timeframe,
            strategy_name=strategy_name,
            leverage=leverage,
            strategy_params=strategy_params,
        )
        html_content = reporter._generate_html_report(return_only=True, output_dir=report_dir)
        reporter._export_csv(output_dir=report_dir)

        metrics = results.get("metrics", {})
        rt_list = results.get("round_trips", [])

        return {
            "symbol": symbol,
            "metrics": metrics,
            "html": html_content,
            "profit": results.get("net_profit", 0.0),
            "profit_pct": results.get("net_profit_pct", 0.0),
            "initial_balance": results.get("initial_balance", float(balance)),
            "final_balance": results.get("final_balance", float(balance)),
            "drawdown": results.get("drawdown", {}).get("avg_drawdown_pct", 0),
            "trades": metrics.get("total_trades", 0),
            "round_trips": pd.DataFrame(rt_list) if rt_list else pd.DataFrame(),
            "equity_curve": results.get("equity_curve", []),
            "drawdown_curve": results.get("drawdown_curve", []),
        }
    except Exception as exc:
        import traceback

        traceback.print_exc()
        return {"symbol": symbol, "error": str(exc)}


# ── CLI entry point ─────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Run batch backtest analysis")
    parser.add_argument("--strategy", type=str, default=None, choices=list(STRATEGY_MAP.keys()))
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--sequential", action="store_true")
    args = parser.parse_args()

    if not os.path.exists(SYMBOLS_PATH):
        logger.error("symbols_file_missing", path=SYMBOLS_PATH)
        return

    setup_logging(level="INFO")

    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    timeframe = config.get("timeframe", "15m")
    balance = config.get("backtest", {}).get("initial_balance", 1000)
    strategy_name = args.strategy or config.get("strategy", "rsi_wma_retest")

    if strategy_name not in STRATEGY_MAP:
        logger.error("unknown_strategy", name=strategy_name, available=list(STRATEGY_MAP.keys()))
        return

    with open(SYMBOLS_PATH) as f:
        symbols = [line.strip() for line in f if line.strip()]

    max_workers = args.workers or min(os.cpu_count() or 4, len(symbols))
    if args.sequential:
        max_workers = 1

    from app.backtest.runners.progress import CliProgressBar

    bar = CliProgressBar(f"Batch ({strategy_name}, {len(symbols)} symbols)")

    runner = BatchRunner(symbols, config, strategy_name, timeframe, balance)
    batch_results = runner.run(max_workers=max_workers, progress_cb=bar.update)

    total_profit = sum(r.get("profit", 0) for r in batch_results)
    bar.finish(f"{len(batch_results)}/{len(symbols)} ok, P&L: ${total_profit:+,.2f}")

    if batch_results:
        report_path = os.path.join(REPORT_DIR, "batch_report.html")
        try:
            webbrowser.open("file://" + os.path.abspath(report_path))
        except Exception:
            logger.info("browser_open_skipped")
    else:
        logger.warning("no_results")


if __name__ == "__main__":
    main()
