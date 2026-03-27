"""
Portfolio Parameter Sweep Runner (Phase 2.3)
=============================================
Runs multiple independent portfolio backtests in parallel using
ProcessPoolExecutor. Each run uses a different parameter set.

Usage:
    from app.backtest.runners.portfolio_sweep import PortfolioSweepRunner

    sweep = PortfolioSweepRunner(
        symbols=["BTC/USDT", "ETH/USDT"],
        base_config=config,
        strategy_name="rsi_no_retest",
        timeframe="5m",
        param_grid={"nr_rsi_spread_min": [1.5, 2.0, 2.5, 3.0]},
    )
    results = sweep.run(max_workers=8)
"""

from __future__ import annotations

import copy
import itertools
import os
from concurrent.futures import ProcessPoolExecutor, as_completed

import structlog

from app.core.constants import DEFAULT_MAKER_FEE, DEFAULT_TAKER_FEE

logger = structlog.get_logger()

BACKTEST_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BACKTEST_DIR, "data")


def _run_single_portfolio(
    symbols: list[str],
    config: dict,
    strategy_name: str,
    timeframe: str,
    param_set: dict,
    run_id: int,
) -> dict:
    """Run one portfolio backtest with a specific parameter set.

    This is the worker function executed in each subprocess.
    """
    from app.backtest.runners.portfolio_runner import PortfolioRunner

    # Merge param_set into config
    cfg = copy.deepcopy(config)
    cfg.setdefault("strategy_params", {}).update(param_set)

    runner = PortfolioRunner(
        symbols=symbols,
        config=cfg,
        strategy_name=strategy_name,
        timeframe=timeframe,
        data_dir=DATA_DIR,
        report_dir=os.path.join(BACKTEST_DIR, "report", f"sweep_{run_id}"),
    )

    try:
        results = runner.run()
        results["_param_set"] = param_set
        results["_run_id"] = run_id
        return results
    except Exception as e:
        logger.error("sweep_run_failed", run_id=run_id, params=param_set, error=str(e))
        return {
            "_param_set": param_set,
            "_run_id": run_id,
            "_error": str(e),
            "net_profit": 0.0,
            "net_profit_pct": 0.0,
        }


class PortfolioSweepRunner:
    """Run parallel portfolio backtests over a parameter grid.

    Args:
        symbols: List of trading pairs.
        base_config: Base configuration dict (strategy_params will be overridden).
        strategy_name: Strategy identifier from STRATEGY_MAP.
        timeframe: Candle timeframe (e.g. "5m", "15m").
        param_grid: Dict mapping param names to lists of values to sweep.
            Example: {"nr_rsi_spread_min": [1.5, 2.0, 2.5]}
    """

    def __init__(
        self,
        symbols: list[str],
        base_config: dict,
        strategy_name: str,
        timeframe: str,
        param_grid: dict[str, list],
    ):
        self.symbols = symbols
        self.base_config = base_config
        self.strategy_name = strategy_name
        self.timeframe = timeframe
        self.param_grid = param_grid

        # Generate all combinations
        keys = list(param_grid.keys())
        values = list(param_grid.values())
        self.param_sets = [dict(zip(keys, combo)) for combo in itertools.product(*values)]

    def run(self, max_workers: int | None = None) -> list[dict]:
        """Execute all parameter combinations in parallel.

        Args:
            max_workers: Max parallel processes. Defaults to CPU count.
                         For Ryzen 7 7700: 8 cores recommended.

        Returns:
            List of result dicts, each with '_param_set' and '_run_id' keys.
            Sorted by net_profit_pct descending.
        """
        if max_workers is None:
            max_workers = min(os.cpu_count() or 4, len(self.param_sets))

        n = len(self.param_sets)
        logger.info(
            "portfolio_sweep_start",
            strategy=self.strategy_name,
            combinations=n,
            workers=max_workers,
        )

        results: list[dict] = []

        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(
                    _run_single_portfolio,
                    self.symbols,
                    self.base_config,
                    self.strategy_name,
                    self.timeframe,
                    param_set,
                    run_id,
                ): run_id
                for run_id, param_set in enumerate(self.param_sets)
            }

            for future in as_completed(futures):
                run_id = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    pnl_pct = result.get("net_profit_pct", 0.0)
                    logger.info(
                        "sweep_run_complete",
                        run_id=run_id,
                        params=result.get("_param_set"),
                        pnl_pct=f"{pnl_pct:+.2f}%",
                        done=f"{len(results)}/{n}",
                    )
                except Exception as e:
                    logger.error("sweep_future_error", run_id=run_id, error=str(e))

        # Sort by profit descending
        results.sort(key=lambda r: r.get("net_profit_pct", 0.0), reverse=True)

        if results:
            best = results[0]
            logger.info(
                "portfolio_sweep_complete",
                total_runs=len(results),
                best_params=best.get("_param_set"),
                best_pnl_pct=f"{best.get('net_profit_pct', 0.0):+.2f}%",
            )

        return results
