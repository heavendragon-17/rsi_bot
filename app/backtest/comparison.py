from app.db.repository import BacktestRepository

def compare_runs(run_id_1: int, run_id_2: int) -> dict:
    """Compare two backtest runs side-by-side."""
    repo = BacktestRepository()

    run1 = repo.get_run(run_id_1)
    results1 = repo.get_run_results(run_id_1)

    run2 = repo.get_run(run_id_2)
    results2 = repo.get_run_results(run_id_2)

    if not run1 or not run2 or not results1 or not results2:
        return {"error": "One or both runs not found"}

    # Calculate differences
    differences = {}
    metric_keys = ["total_profit", "win_rate", "total_trades", "profit_factor", "max_drawdown", "sharpe_ratio"]

    for k in metric_keys:
        val1 = results1.get(k, 0)
        val2 = results2.get(k, 0)
        # Handle Decimal
        if hasattr(val1, "to_eng_string"):
            val1 = float(val1)
        if hasattr(val2, "to_eng_string"):
            val2 = float(val2)

        differences[k] = val2 - val1

    verdict = "Run 2 is better" if differences["total_profit"] > 0 else "Run 1 is better"

    return {
        "run_1": {
            "id": run1["id"],
            "strategy": run1["strategy_name"],
            **results1
        },
        "run_2": {
            "id": run2["id"],
            "strategy": run2["strategy_name"],
            **results2
        },
        "differences": differences,
        "verdict": verdict
    }
