"""
Sensitivity Analysis
=====================
Test how a single parameter affects strategy performance.
"""
import copy
import yaml
import os
import pandas as pd
from decimal import Decimal
from typing import Dict, List, Any, Union

from app.backtest.engine import BacktestEngine
from app.backtest.reporting import BacktestReporter
from app.strategies.loader import load_strategy


def _load_base_config() -> dict:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config_path = os.path.join(project_root, "config.yaml")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def run_sensitivity(
    strategy_name: str,
    symbol: str,
    data_file: str,
    base_config: Dict = None,
    param_name: str = "rsi_period",
    param_range: List[Union[int, float]] = None,
    metric: str = "profit",
) -> Dict[str, Any]:
    """
    Run backtest for each value of a single parameter to see its effect.

    Args:
        strategy_name: Strategy key
        symbol: Trading pair
        data_file: Absolute path to CSV
        base_config: Optional config overrides
        param_name: Parameter to vary (e.g. "rsi_period")
        param_range: List of values to test (e.g. [10, 12, 14, 16, 18, 20])
        metric: Which metric to track: "profit", "win_rate", "sharpe_ratio",
                "profit_factor", "max_drawdown", "total_trades"

    Returns:
        {
            "parameter": "rsi_period",
            "metric": "profit",
            "values": [10, 12, 14, 16, 18, 20],
            "results": [100, 150, 200, 180, 120, 90],
            "full_results": [
                {"value": 10, "profit": 100, "win_rate": 55, ...},
                ...
            ],
            "optimal": {"value": 14, "result": 200},
            "stability_score": 0.72,
        }
    """
    if param_range is None:
        param_range = [10, 12, 14, 16, 18, 20]

    config_base = _load_base_config()
    if base_config:
        config_base.update(base_config)

    # Valid metrics to extract
    metric_map = {
        "profit": "profit",
        "win_rate": "win_rate",
        "sharpe_ratio": "sharpe_ratio",
        "profit_factor": "profit_factor",
        "max_drawdown": "max_drawdown",
        "total_trades": "total_trades",
    }

    if metric not in metric_map:
        raise ValueError(f"Unknown metric: {metric}. Available: {list(metric_map.keys())}")

    full_results = []
    metric_values = []

    for value in param_range:
        try:
            config = copy.deepcopy(config_base)
            config["symbols"] = [symbol]
            config["strategy"] = strategy_name

            if "strategy_params" not in config:
                config["strategy_params"] = {}
            config["strategy_params"][param_name] = value

            initial_balance = config.get("backtest", {}).get("initial_balance", 10000)

            strategy_class = load_strategy(config)
            engine = BacktestEngine(
                data_path=data_file,
                strategy_class=strategy_class,
                config=config,
            )
            engine.run()

            reporter = BacktestReporter(
                engine.exchange, config,
                initial_balance=float(initial_balance),
                symbol=symbol,
                timeframe=config.get("timeframe", "15m"),
                strategy_name=strategy_name,
            )

            trades_df = pd.DataFrame(engine.exchange.trade_history)
            round_trips = reporter._build_round_trips(trades_df)
            metrics_dict = reporter._calculate_metrics(round_trips)
            drawdown = reporter._calculate_drawdown(round_trips)
            risk_metrics = reporter._calculate_risk_metrics(round_trips, drawdown)

            profit = float(round_trips["pnl"].sum()) if not round_trips.empty else 0.0
            profit_pct = (profit / float(initial_balance)) * 100 if initial_balance else 0.0

            entry = {
                "value": value,
                "profit": round(profit, 2),
                "profit_pct": round(profit_pct, 2),
                "win_rate": round(metrics_dict.get("win_rate", 0), 2),
                "total_trades": metrics_dict.get("total_trades", 0),
                "profit_factor": round(metrics_dict.get("profit_factor", 0), 2),
                "max_drawdown": round(drawdown.get("max_drawdown_pct", 0), 2),
                "sharpe_ratio": round(risk_metrics.get("sharpe_ratio", 0), 2),
            }

            full_results.append(entry)
            metric_values.append(entry.get(metric, 0))

        except Exception as e:
            print(f"[Sensitivity] Error with {param_name}={value}: {e}")
            full_results.append({"value": value, "error": str(e)})
            metric_values.append(0)

    # Find optimal
    if metric_values:
        if metric == "max_drawdown":
            # For drawdown, closer to 0 is better (less negative)
            best_idx = max(range(len(metric_values)), key=lambda i: metric_values[i])
        else:
            best_idx = max(range(len(metric_values)), key=lambda i: metric_values[i])

        optimal = {
            "value": param_range[best_idx],
            "result": metric_values[best_idx],
        }
    else:
        optimal = {"value": None, "result": None}

    # Calculate stability score
    # Stability = what fraction of values produce positive results relative to optimal
    stability_score = _calculate_stability(metric_values)

    return {
        "parameter": param_name,
        "metric": metric,
        "values": param_range,
        "results": metric_values,
        "full_results": full_results,
        "optimal": optimal,
        "stability_score": round(stability_score, 4),
    }


def _calculate_stability(values: List[float]) -> float:
    """
    Calculate stability score (0 to 1).
    Higher = metric is stable across parameter values.
    Lower = metric is very sensitive to parameter choice.

    Uses coefficient of variation: lower CV = more stable.
    """
    if not values or len(values) < 2:
        return 0.0

    import numpy as np
    arr = np.array(values, dtype=float)
    mean = np.mean(arr)
    std = np.std(arr)

    if mean == 0:
        return 0.0

    cv = abs(std / mean)  # coefficient of variation

    # Convert to 0-1 score: CV of 0 = score 1.0, CV of 2+ = score ~0
    stability = max(0, 1.0 - cv / 2.0)
    return stability
