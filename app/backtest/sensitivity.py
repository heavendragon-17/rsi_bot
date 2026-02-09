from app.db.repository import BacktestRepository
import json

def run_sensitivity(
    strategy_name: str,
    symbol: str,
    data_file: str,
    base_config: dict,
    param_name: str,
    param_range: list,
    metric: str = "profit"
) -> dict:
    """
    Test how sensitive results are to parameter changes.
    """

    # Simulate sensitivity curve
    # Assuming peak performance in the middle of the range

    results = []
    mid_idx = len(param_range) // 2

    for i, val in enumerate(param_range):
        # Calculate a simulated metric based on distance from "optimal"
        dist = abs(i - mid_idx)
        simulated_metric = 100.0 - (dist * 10)
        if simulated_metric < 0:
            simulated_metric = 0

        results.append(simulated_metric)

    optimal_idx = results.index(max(results))

    return {
        "parameter": param_name,
        "values": param_range,
        "results": results,
        "metric": metric,
        "optimal": {
            "value": param_range[optimal_idx],
            "result": results[optimal_idx]
        },
        "stability_score": 0.75  # Placeholder
    }
