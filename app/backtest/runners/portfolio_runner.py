"""
Unified multi-symbol portfolio backtest runner.

Refactored from run_portfolio_backtest.py.  Provides both a class-based
API (``PortfolioRunner``) and the ``_run_portfolio_backtest()`` function
consumed by ``BacktestService._portfolio_worker()``.
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd
import structlog
import yaml

from app.backtest.data_manager import DataManager
from app.backtest.download_data import calculate_candle_limit
from app.backtest.engine import BacktestEngine
from app.backtest.enrichment import enrich_round_trips
from app.backtest.export import export_json_report
from app.backtest.mock_exchange import MockExchange
from app.backtest.portfolio_engine import PortfolioEngine
from app.backtest.portfolio_event_source import PortfolioEventSource
from app.backtest.reporting import BacktestReporter
from app.core.logging import setup_logging
from app.trading.strategy.loader import STRATEGY_MAP

logger = structlog.get_logger()

BACKTEST_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BACKTEST_DIR))
SYMBOLS_PATH = os.path.join(BACKTEST_DIR, "symbols.txt")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.yaml")
REPORT_DIR = os.path.join(BACKTEST_DIR, "report")
DATA_DIR = os.path.join(BACKTEST_DIR, "data")


class PortfolioRunner:
    """Unified multi-symbol portfolio backtest."""

    def __init__(
        self,
        symbols: list[str],
        config: dict,
        strategy_name: str,
        timeframe: str,
        data_dir: str = DATA_DIR,
        report_dir: str = REPORT_DIR,
    ):
        self.symbols = symbols
        self.config = config
        self.strategy_name = strategy_name
        self.timeframe = timeframe
        self.data_dir = data_dir
        self.report_dir = report_dir

    def run(self, progress_cb=None) -> dict:
        """Execute portfolio backtest and return results dict."""
        strategy_class = STRATEGY_MAP.get(self.strategy_name)
        if not strategy_class:
            raise ValueError(f"Unknown strategy: {self.strategy_name}")

        # 1. Ensure data
        dm = DataManager(data_dir=self.data_dir, timeframe=self.timeframe)
        duration_cfg = self.config.get("backtest", {}).get("duration", {})
        try:
            limit = calculate_candle_limit(
                self.timeframe,
                days=duration_cfg.get("days", 0),
                months=duration_cfg.get("months", 0),
                years=duration_cfg.get("years", 0),
            )
        except ValueError:
            limit = 8832

        dm.ensure_bulk_data(self.symbols, limit)

        # 2. Load and prepare data
        strategy_instance = strategy_class(self.config)
        dfs: dict[str, pd.DataFrame] = {}
        for symbol in self.symbols:
            data_file = dm.get_csv_path(symbol)
            df = pd.read_csv(data_file)
            if limit > 0:
                df = df.tail(limit).reset_index(drop=True)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            dfs[symbol] = BacktestEngine._prepare_dataframe(df, strategy_instance, symbol)

        # 3. Setup execution
        balance = self.config.get("backtest", {}).get("initial_balance", 10000)
        risk_cfg = self.config.get("risk", {})
        leverage = risk_cfg.get("leverage", 10)
        taker_fee = float(risk_cfg.get("taker_fee", 0.0005))
        maker_fee = float(risk_cfg.get("maker_fee", 0.0002))

        exchange = MockExchange(
            initial_balance=balance, leverage=leverage,
            taker_fee=taker_fee, maker_fee=maker_fee,
        )
        event_source = PortfolioEventSource(dfs, start_idx=220)
        engine = PortfolioEngine(
            event_source=event_source, strategy_class=strategy_class,
            exchange=exchange, config=self.config, symbols=self.symbols,
        )

        # 4. Run
        logger.info(
            "portfolio_backtest_start",
            strategy=self.strategy_name, symbols=len(self.symbols),
            balance=balance, leverage=leverage,
        )
        results = engine.run(on_progress=progress_cb)

        # 5. Enrich
        debug_rows = getattr(engine.strategy, "_debug_rows", [])
        if debug_rows:
            os.makedirs(os.path.join(self.report_dir, "debug_csv"), exist_ok=True)
            debug_path = os.path.join(
                self.report_dir, "debug_csv", f"debug_PORTFOLIO_{self.timeframe}.csv",
            )
            engine.strategy.export_debug_csv(debug_path)
            results = enrich_round_trips(results, debug_rows)

        # 6. Generate reports
        os.makedirs(self.report_dir, exist_ok=True)
        reporter = BacktestReporter(
            results, symbol="PORTFOLIO", timeframe=self.timeframe,
            strategy_name=self.strategy_name, leverage=leverage,
            strategy_params={
                **strategy_class.DEFAULT_CONFIG,
                **self.config.get("strategy_params", {}),
            },
        )
        html = reporter._generate_html_report(return_only=True, output_dir=self.report_dir)
        report_path = os.path.join(self.report_dir, "portfolio_backtest_report.html")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info("report_saved", path=report_path)

        json_path = os.path.join(self.report_dir, "portfolio_backtest_report.json")
        export_json_report(results, json_path)

        return results


# ── API entry point (called from BacktestService) ──────────────────────────

def _run_portfolio_backtest(
    symbols: list[str],
    strategy_name: str,
    timeframe: str,
    start_date=None,
    end_date=None,
    initial_capital: float = 10000,
    leverage: int = 10,
    risk_per_trade_pct: float = 1.0,
    fee_tier: str = "taker",
    slippage_model: str = "none",
    slippage_pct: float = 0.0,
    params: dict | None = None,
    progress_cb=None,
) -> dict:
    """Thin wrapper that ``BacktestService._portfolio_worker()`` imports."""
    config = {
        "symbols": symbols,
        "timeframe": timeframe,
        "backtest": {
            "initial_balance": initial_capital,
            "start_date": start_date,
            "end_date": end_date,
        },
        "risk": {
            "leverage": leverage,
            "risk_per_trade_pct": risk_per_trade_pct,
            "taker_fee": 0.0005,
            "maker_fee": 0.0002,
        },
        "strategy_params": params or {},
    }
    runner = PortfolioRunner(
        symbols=symbols, config=config,
        strategy_name=strategy_name, timeframe=timeframe,
    )
    return runner.run(progress_cb=progress_cb)


# ── CLI entry point ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run Unified Portfolio Backtest")
    parser.add_argument(
        "--strategy", type=str, default=None, choices=list(STRATEGY_MAP.keys()),
        help="Strategy to use (default: from config.yaml)",
    )
    args = parser.parse_args()

    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)

    timeframe = config.get("timeframe", "15m")
    strategy_name = args.strategy or config.get("strategy", "rsi_wma_retest")

    symbols = config.get("symbols", [])
    if os.path.exists(SYMBOLS_PATH) and not symbols:
        with open(SYMBOLS_PATH, "r") as f:
            symbols = [line.strip() for line in f if line.strip()]

    if not symbols:
        logger.error("no_symbols_found")
        return

    setup_logging(level="DEBUG", log_file="backtest.log", console=False)

    runner = PortfolioRunner(symbols, config, strategy_name, timeframe)
    results = runner.run()

    profit = results.get("net_profit", 0.0)
    profit_pct = results.get("net_profit_pct", 0.0)
    logger.info("portfolio_done", profit=f"${profit:.2f}", pct=f"{profit_pct:+.2f}%")

    import webbrowser
    report_path = os.path.join(REPORT_DIR, "portfolio_backtest_report.html")
    try:
        webbrowser.open(f"file://{os.path.abspath(report_path)}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
