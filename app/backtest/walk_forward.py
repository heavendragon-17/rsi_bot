import datetime

def run_walk_forward(
    strategy_name: str,
    symbol: str,
    data_file: str,
    config: dict,
    train_days: int = 90,
    test_days: int = 30,
    step_days: int = 30
) -> dict:
    """
    Run walk-forward analysis with rolling windows.
    """
    # In a real implementation, we'd load the full data and slice it.
    # For now, we simulate the windows.

    start_date = datetime.date(2024, 1, 1)

    windows = []

    for i in range(5):  # Simulate 5 windows
        train_start = start_date + datetime.timedelta(days=i * step_days)
        train_end = train_start + datetime.timedelta(days=train_days)
        test_start = train_end + datetime.timedelta(days=1)
        test_end = test_start + datetime.timedelta(days=test_days)

        # Simulate results
        # Assuming better performance in-sample than out-of-sample
        is_profit = 500.0 + (i * 20)
        oos_profit = 150.0 + (i * 10)

        windows.append({
            "train_start": train_start.isoformat(),
            "train_end": train_end.isoformat(),
            "test_start": test_start.isoformat(),
            "test_end": test_end.isoformat(),
            "in_sample_profit": is_profit,
            "out_of_sample_profit": oos_profit,
            "efficiency_ratio": round(oos_profit / is_profit if is_profit != 0 else 0, 2)
        })

    total_oos = sum(w["out_of_sample_profit"] for w in windows)
    avg_eff = sum(w["efficiency_ratio"] for w in windows) / len(windows)

    return {
        "windows": windows,
        "aggregate": {
            "total_oos_profit": total_oos,
            "avg_efficiency": round(avg_eff, 2),
            "consistency_score": 0.85
        }
    }
