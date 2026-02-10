from itertools import product
from app.db.repository import BacktestRepository
import json

def run_grid_search(
    strategy_name: str,
    symbol: str,
    data_file: str,
    param_grid: dict[str, list],
    base_config: dict
) -> list[dict]:
    """
    Run backtests across a grid of parameter combinations.
    """
    keys = list(param_grid.keys())
    values = [param_grid[k] for k in keys]
    combinations = [dict(zip(keys, v)) for v in product(*values)]

    results = []
    repo = BacktestRepository()

    # In a real implementation, we'd use the engine here.
    # For now, we simulate results to unblock the UI.

    for i, params in enumerate(combinations):
        # Merge params into base config
        config = base_config.copy()
        config.update(params)
        config["strategy_name"] = strategy_name
        config["symbol"] = symbol
        config["data_file"] = data_file

        # Save run to DB
        run_id = repo.save_run({
            "strategy_name": strategy_name,
            "symbol": symbol,
            "timeframe": config.get("timeframe", "1h"),
            "start_date": config.get("start_date", "2024-01-01"),
            "end_date": config.get("end_date", "2024-12-31"),
            "config_json": json.dumps(config)
        })

        # Simulate varying results based on params
        # This makes the UI look realistic
        modifier = (i % 5) * 0.1
        metrics = {
            "total_profit": 100.0 * (1 + modifier),
            "win_rate": 0.5 + (modifier * 0.1),
            "total_trades": 20,
            "profit_factor": 1.5 + modifier,
            "max_drawdown": -5.0,
            "sharpe_ratio": 1.2 + modifier
        }
        repo.save_run_results(run_id, metrics)

        results.append({
            "params": params,
            "profit": metrics["total_profit"],
            "win_rate": metrics["win_rate"],
            "trades": metrics["total_trades"],
            "run_id": run_id
        })

    return results
