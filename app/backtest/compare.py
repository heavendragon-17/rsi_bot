"""
Run Comparison
===============
Compare two backtest runs side-by-side.
"""
from typing import Dict, Any


def compare_runs(run1_data: Dict, run2_data: Dict) -> Dict[str, Any]:
    """
    Compare two run result dicts.

    Args:
        run1_data: First run's metrics dict
        run2_data: Second run's metrics dict

    Returns:
        {
            "run_1": {metrics...},
            "run_2": {metrics...},
            "differences": {
                "profit": 500,        # run2 - run1
                "win_rate": -5.0,
                ...
            },
            "better_run": 2,          # which run has higher profit
        }
    """
    compare_keys = [
        "profit", "profit_pct", "win_rate", "total_trades",
        "profit_factor", "max_drawdown", "sharpe_ratio",
    ]

    differences = {}
    for key in compare_keys:
        v1 = run1_data.get(key, 0)
        v2 = run2_data.get(key, 0)
        try:
            if v1 is None: v1 = 0
            if v2 is None: v2 = 0
            differences[key] = round(float(v2) - float(v1), 4)
        except (TypeError, ValueError):
            differences[key] = 0

    # Determine better run based on profit
    # Handle cases where profit might be missing or None
    p1 = run1_data.get("profit", 0)
    p2 = run2_data.get("profit", 0)

    try:
        if p1 is None: p1 = 0
        if p2 is None: p2 = 0
        better_run = 2 if float(p2) > float(p1) else 1
    except (TypeError, ValueError):
        better_run = 1

    return {
        "run_1": run1_data,
        "run_2": run2_data,
        "differences": differences,
        "better_run": better_run,
    }
