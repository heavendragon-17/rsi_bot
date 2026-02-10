"""
Grid Search
============
Test all parameter combinations and rank by performance.
"""
import copy
import itertools
import yaml
import os
import pandas as pd
from decimal import Decimal
from typing import Dict, List, Any

from app.backtest.engine import BacktestEngine
from app.backtest.reporting import BacktestReporter
from app.strategies.loader import load_strategy


def _load_base_config() -> dict:
    """Load config.yaml from project root."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config_path = os.path.join(project_root, "config.yaml")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def run_grid_search(
    strategy_name: str,
    symbol: str,
    data_file: str,
    param_grid: Dict[str, List],
    base_config: Dict = None,
) -> List[Dict[str, Any]]:
    """
    Run backtest for every combination of parameters in param_grid.

    Args:
        strategy_name: e.g. "rsi_no_retest"
        symbol: e.g. "BTC/USDT"
        data_file: Absolute path to CSV data file
        param_grid: e.g. {"rsi_period": [10, 14, 20], "take_profit_pct": [0.02, 0.03]}
        base_config: Optional config overrides (merged on top of config.yaml)

    Returns:
        List of result dicts sorted by profit descending.
        Each dict: {
            "params": {"rsi_period": 14, ...},
            "profit": 1234.56,
            "profit_pct": 12.3,
            "win_rate": 59.5,
            "total_trades": 42,
            "profit_factor": 2.1,
            "max_drawdown": -5.2,
            "sharpe_ratio": 1.5,
        }
    """
    config_base = _load_base_config()
    if base_config:
        config_base.update(base_config)

    # Generate all parameter combinations
    param_names = list(param_grid.keys())
    param_values = list(param_grid.values())
    combinations = list(itertools.product(*param_values))

    results = []

    for combo in combinations:
        params = dict(zip(param_names, combo))

        try:
            result = _run_single(
                strategy_name=strategy_name,
                symbol=symbol,
                data_file=data_file,
                config_base=config_base,
                param_overrides=params,
            )
            result["params"] = params
            results.append(result)
        except Exception as e:
            print(f"[GridSearch] Error with params {params}: {e}")
            results.append({
                "params": params,
                "profit": 0,
                "profit_pct": 0,
                "win_rate": 0,
                "total_trades": 0,
                "profit_factor": 0,
                "max_drawdown": 0,
                "sharpe_ratio": 0,
                "error": str(e),
            })

    # Sort by profit descending
    results.sort(key=lambda x: x.get("profit", 0), reverse=True)
    return results


def _run_single(
    strategy_name: str,
    symbol: str,
    data_file: str,
    config_base: dict,
    param_overrides: dict,
) -> Dict[str, Any]:
    """
    Run a single backtest with specific parameters.
    Returns a dict with key metrics.

    REFERENCE: See app/backtest/run_batch_analysis.py → run_single_backtest()
    """
    config = copy.deepcopy(config_base)
    config["symbols"] = [symbol]
    config["strategy"] = strategy_name

    # Apply parameter overrides
    if "strategy_params" not in config:
        config["strategy_params"] = {}
    config["strategy_params"].update(param_overrides)

    initial_balance = config.get("backtest", {}).get("initial_balance", 10000)

    # Get strategy class and run engine
    strategy_class = load_strategy(config)
    engine = BacktestEngine(
        data_path=data_file,
        strategy_class=strategy_class,
        config=config,
    )
    engine.run()

    # Extract results using reporter
    reporter = BacktestReporter(
        engine.exchange,
        config,
        initial_balance=float(initial_balance),
        symbol=symbol,
        timeframe=config.get("timeframe", "15m"),
        strategy_name=strategy_name,
    )

    trades_df = pd.DataFrame(engine.exchange.trade_history)
    round_trips = reporter._build_round_trips(trades_df)
    metrics = reporter._calculate_metrics(round_trips)
    drawdown = reporter._calculate_drawdown(round_trips)
    risk_metrics = reporter._calculate_risk_metrics(round_trips, drawdown)

    profit = float(round_trips["pnl"].sum()) if not round_trips.empty else 0.0
    profit_pct = (profit / float(initial_balance)) * 100 if initial_balance else 0.0

    return {
        "profit": round(profit, 2),
        "profit_pct": round(profit_pct, 2),
        "win_rate": round(metrics.get("win_rate", 0), 2),
        "total_trades": metrics.get("total_trades", 0),
        "profit_factor": round(metrics.get("profit_factor", 0), 2),
        "max_drawdown": round(drawdown.get("max_drawdown_pct", 0), 2),
        "sharpe_ratio": round(risk_metrics.get("sharpe_ratio", 0), 2),
    }
