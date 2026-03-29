"""
Portfolio Sweep Runner (Phase 2.3)
===================================
Runs multiple independent portfolio backtests in parallel using
ProcessPoolExecutor. Each run uses a different parameter set (e.g.,
for grid search / parameter optimization). No shared state between
processes.

Usage:
    python -m app.backtest.runners.portfolio_sweep

Or programmatically:
    runner = PortfolioSweepRunner(base_config, strategy_name, ...)
    results = runner.run(param_grid, max_workers=8)
"""

from __future__ import annotations

import copy
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import structlog

from app.core.logging import setup_logging

logger = structlog.get_logger()


class PortfolioSweepRunner:
    """Run parallel portfolio backtests with different parameter sets.

    Args:
        symbols: List of symbols to trade.
        base_config: Base configuration dict (risk, backtest, etc.).
        strategy_name: Strategy identifier from STRATEGY_MAP.
        timeframe: Candle timeframe (e.g. "5m", "15m").
        data_dir: Directory containing CSV data files.
        report_dir: Directory for output reports.
    """

    def __init__(
        self,
        symbols: list[str],
        base_config: dict,
        strategy_name: str,
        timeframe: str,
        data_dir: str | None = None,
        report_dir: str | None = None,
    ) -> None:
        self.symbols = symbols
        self.base_config = base_config
        self.strategy_name = strategy_name
        self.timeframe = timeframe

        backtest_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = data_dir or os.path.join(backtest_dir, "data")
        self.report_dir = report_dir or os.path.join(backtest_dir, "report")

    def run(
        self,
        param_sets: list[dict],
        max_workers: int = 8,
        progress_cb=None,
    ) -> list[dict]:
        """Execute parallel portfolio backtests for each parameter set.

        Args:
            param_sets: List of strategy_params dicts. Each dict is merged
                with base_config["strategy_params"] for one independent run.
            max_workers: Number of parallel processes (default: 8 for Ryzen 7).
            progress_cb: Optional callback({"pct": int, "completed": int, "total": int}).

        Returns:
            List of result dicts, each containing:
                - "params": the parameter set used
                - "results": full backtest results dict
                - "error": error string if the run failed
        """
        os.makedirs(self.report_dir, exist_ok=True)
        start_time = time.time()
        total = len(param_sets)
        sweep_results: list[dict] = []

        logger.info(
            "portfolio_sweep_start",
            total_runs=total,
            max_workers=max_workers,
            strategy=self.strategy_name,
        )

        if max_workers == 1:
            for i, params in enumerate(param_sets):
                result = _run_single_portfolio(
                    symbols=self.symbols,
                    base_config=self.base_config,
                    strategy_name=self.strategy_name,
                    timeframe=self.timeframe,
                    param_overrides=params,
                    data_dir=self.data_dir,
                )
                sweep_results.append(result)
                if progress_cb:
                    progress_cb({"pct": int((i + 1) / total * 100), "completed": i + 1, "total": total})
        else:
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        _run_single_portfolio,
                        symbols=self.symbols,
                        base_config=self.base_config,
                        strategy_name=self.strategy_name,
                        timeframe=self.timeframe,
                        param_overrides=params,
                        data_dir=self.data_dir,
                    ): params
                    for params in param_sets
                }
                completed = 0
                for future in as_completed(futures):
                    params = futures[future]
                    completed += 1
                    try:
                        result = future.result()
                        sweep_results.append(result)
                    except Exception as exc:
                        sweep_results.append({
                            "params": params,
                            "results": None,
                            "error": str(exc),
                        })
                        logger.error("sweep_run_failed", params=params, error=str(exc))
                    if progress_cb:
                        progress_cb({"pct": int(completed / total * 100), "completed": completed, "total": total})

        elapsed = time.time() - start_time
        successful = sum(1 for r in sweep_results if r.get("error") is None)
        logger.info(
            "portfolio_sweep_complete",
            elapsed=f"{elapsed:.1f}s",
            total_runs=total,
            successful=successful,
        )

        # Sort by net_profit descending for convenience
        sweep_results.sort(
            key=lambda r: (
                r.get("results", {}).get("net_profit", float("-inf"))
                if r.get("results")
                else float("-inf")
            ),
            reverse=True,
        )

        return sweep_results


# ── Worker function (top-level for pickling) ────────────────────────────


def _run_single_portfolio(
    symbols: list[str],
    base_config: dict,
    strategy_name: str,
    timeframe: str,
    param_overrides: dict,
    data_dir: str,
) -> dict:
    """Run a single portfolio backtest with given parameter overrides.

    Must be a top-level function for ProcessPoolExecutor pickling.
    """
    setup_logging(level="WARNING")

    try:
        import pandas as pd

        from app.backtest.engine.backtest_engine import BacktestEngine
        from app.backtest.engine.batch_event_source import BatchPortfolioEventSource
        from app.backtest.engine.portfolio_engine import PortfolioEngine
        from app.backtest.exchange.mock_exchange import MockExchange
        from app.core.constants import DEFAULT_MAKER_FEE, DEFAULT_TAKER_FEE, WARMUP
        from app.trading.strategy.loader import STRATEGY_MAP

        strategy_class = STRATEGY_MAP.get(strategy_name)
        if not strategy_class:
            return {"params": param_overrides, "results": None, "error": f"Unknown strategy: {strategy_name}"}

        # Merge params
        config = copy.deepcopy(base_config)
        config.setdefault("strategy_params", {}).update(param_overrides)

        # Compute candle limit from duration config
        duration_cfg = config.get("backtest", {}).get("duration", {})
        limit = 8832
        try:
            from app.backtest.data.download import calculate_candle_limit
            limit = calculate_candle_limit(
                timeframe,
                days=duration_cfg.get("days", 0),
                months=duration_cfg.get("months", 0),
                years=duration_cfg.get("years", 0),
            )
        except (ValueError, ImportError):
            pass

        # Build CSV path per symbol and download if missing
        def _csv_path(sym: str) -> str:
            safe = sym.replace("/", "")
            return os.path.join(data_dir, f"{safe}_{timeframe}.csv")

        missing = [s for s in symbols if not os.path.exists(_csv_path(s))]
        if missing:
            from app.backtest.data.manager import DataManager
            dm = DataManager(data_dir=data_dir, timeframe=timeframe)
            dm.ensure_bulk_data(missing, limit)

        strategy_instance = strategy_class(config)  # type: ignore[abstract]
        dfs: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            df = pd.read_csv(_csv_path(symbol))
            if limit > 0:
                df = df.tail(limit).reset_index(drop=True)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            dfs[symbol] = BacktestEngine._prepare_dataframe(df, strategy_instance, symbol)

        # Setup
        balance = config.get("backtest", {}).get("initial_balance", 10000)
        risk_cfg = config.get("risk", {})
        leverage = risk_cfg.get("leverage", 10)
        taker_fee = float(risk_cfg.get("taker_fee", DEFAULT_TAKER_FEE))
        maker_fee = float(risk_cfg.get("maker_fee", DEFAULT_MAKER_FEE))

        exchange = MockExchange(
            initial_balance=balance,
            leverage=leverage,
            taker_fee=taker_fee,
            maker_fee=maker_fee,
        )
        event_source = BatchPortfolioEventSource(dfs, start_idx=WARMUP)
        engine = PortfolioEngine(
            event_source=event_source,
            strategy_class=strategy_class,
            exchange=exchange,
            config=config,
            symbols=symbols,
        )

        results = engine.run()

        return {
            "params": param_overrides,
            "results": {
                "final_balance": results.get("final_balance", 0),
                "net_profit": results.get("net_profit", 0),
                "net_profit_pct": results.get("net_profit_pct", 0),
                "max_drawdown_pct": results.get("drawdown", {}).get("max_drawdown_pct", 0),
                "sharpe_ratio": results.get("risk_metrics", {}).get("sharpe_ratio", 0),
                "sortino_ratio": results.get("risk_metrics", {}).get("sortino_ratio", 0),
                "total_trades": len(results.get("round_trips", [])),
            },
            "error": None,
        }

    except Exception as exc:
        return {"params": param_overrides, "results": None, "error": str(exc)}


# ── CLI entry point ──────────────────────────────────────────────────────


def main():
    """CLI demo: run a small parameter sweep."""
    import argparse

    import yaml

    from app.backtest.runners.progress import CliProgressBar

    backtest_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    project_root = os.path.dirname(os.path.dirname(backtest_dir))
    config_path = os.path.join(project_root, "config.yaml")
    symbols_path = os.path.join(backtest_dir, "symbols.txt")

    parser = argparse.ArgumentParser(description="Portfolio Parameter Sweep")
    parser.add_argument("--workers", type=int, default=8, help="Max parallel workers")
    parser.add_argument("--strategy", type=str, default=None, help="Strategy name")
    args = parser.parse_args()

    with open(config_path) as f:
        config = yaml.safe_load(f)

    timeframe = config.get("timeframe", "15m")
    strategy_name = args.strategy or config.get("strategy", "rsi_wma_retest")

    symbols = config.get("symbols", [])
    if os.path.exists(symbols_path) and not symbols:
        with open(symbols_path) as f:
            symbols = [line.strip() for line in f if line.strip()]

    if not symbols:
        logger.error("no_symbols_found")
        return

    setup_logging(level="INFO", log_file="sweep.log", console=False)

    # Example grid: vary risk_per_trade_pct
    param_grid = [
        {"risk_per_trade_pct": pct}
        for pct in [0.01, 0.015, 0.02, 0.025, 0.03]
    ]

    bar = CliProgressBar(f"Sweep ({strategy_name}, {len(param_grid)} runs)")
    runner = PortfolioSweepRunner(symbols, config, strategy_name, timeframe)
    results = runner.run(param_grid, max_workers=args.workers, progress_cb=bar.update)
    bar.finish(f"{len(results)} runs complete")

    for r in results:
        if r.get("error"):
            logger.warning("sweep_result_error", params=r["params"], error=r["error"])
            continue
        res = r["results"]
        logger.info(
            "sweep_result",
            params=r["params"],
            pnl=f"${res['net_profit']:,.2f}",
            dd_pct=f"{res['max_drawdown_pct']:.2f}%",
            sharpe=f"{res['sharpe_ratio']:.3f}",
            trades=res["total_trades"],
        )


if __name__ == "__main__":
    main()
