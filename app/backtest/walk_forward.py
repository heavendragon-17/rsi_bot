"""
Walk-Forward Analysis
=======================
Split data into rolling train/test windows to validate strategy robustness.
"""
import copy
import yaml
import os
import pandas as pd
import numpy as np
from decimal import Decimal
from typing import Dict, List, Any

from app.backtest.engine import BacktestEngine
from app.backtest.reporting import BacktestReporter
from app.strategies.loader import load_strategy


def _load_base_config() -> dict:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config_path = os.path.join(project_root, "config.yaml")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def run_walk_forward(
    strategy_name: str,
    symbol: str,
    data_file: str,
    config_overrides: Dict = None,
    train_days: int = 90,
    test_days: int = 30,
    step_days: int = 30,
) -> Dict[str, Any]:
    """
    Run walk-forward analysis by splitting the data into multiple train/test windows.

    The process:
    1. Load full dataset
    2. Create rolling windows: [train_start, train_end] [test_start, test_end]
    3. Run backtest on each test window
    4. Collect per-window performance
    5. Calculate aggregate stats

    Args:
        strategy_name: Strategy key from STRATEGY_MAP
        symbol: Trading pair e.g. "BTC/USDT"
        data_file: Absolute path to CSV
        config_overrides: Optional config overrides
        train_days: Number of days for in-sample training
        test_days: Number of days for out-of-sample testing
        step_days: How many days to slide the window forward each step

    Returns:
        {
            "windows": [
                {
                    "window_id": 1,
                    "train_start": "2024-01-01",
                    "train_end": "2024-03-31",
                    "test_start": "2024-04-01",
                    "test_end": "2024-04-30",
                    "in_sample_profit": 500,
                    "out_of_sample_profit": 150,
                    "oos_profit_pct": 1.5,
                    "oos_win_rate": 55.0,
                    "oos_trades": 12,
                    "efficiency_ratio": 0.30,
                },
                ...
            ],
            "aggregate": {
                "total_oos_profit": 1200,
                "avg_oos_profit": 200,
                "avg_efficiency": 0.28,
                "total_oos_trades": 72,
                "profitable_windows": 4,
                "total_windows": 6,
                "consistency_score": 0.67,  # ratio of profitable windows
            }
        }
    """
    config_base = _load_base_config()
    if config_overrides:
        config_base.update(config_overrides)

    # Load full data to determine date range
    full_data = pd.read_csv(data_file)
    full_data["timestamp"] = pd.to_datetime(full_data["timestamp"])
    data_start = full_data["timestamp"].min()
    data_end = full_data["timestamp"].max()

    # Generate windows
    windows = []
    window_id = 1
    current_start = data_start

    while True:
        train_start = current_start
        train_end = train_start + pd.Timedelta(days=train_days)
        test_start = train_end
        test_end = test_start + pd.Timedelta(days=test_days)

        # Stop if test window extends past data
        if test_end > data_end:
            break

        # Slice data for train and test periods
        # For walk-forward, we run backtest on each period separately
        # We use the FULL data up to test_end so indicators have warmup data
        # But only count trades within the test window

        try:
            # --- IN-SAMPLE: Run on train period ---
            train_data = full_data[
                (full_data["timestamp"] >= train_start) &
                (full_data["timestamp"] < train_end)
            ]

            # --- OUT-OF-SAMPLE: Run on full data up to test_end ---
            # This gives indicators enough warmup from the training data
            oos_data = full_data[
                (full_data["timestamp"] >= train_start) &
                (full_data["timestamp"] < test_end)
            ]

            # Save temp CSV files for engine (engine expects file path)
            temp_train_path = data_file.replace(".csv", "_wf_train.csv")
            temp_oos_path = data_file.replace(".csv", "_wf_oos.csv")
            train_data.to_csv(temp_train_path, index=False)
            oos_data.to_csv(temp_oos_path, index=False)

            # Run IS backtest
            is_result = _run_period(
                strategy_name, symbol, temp_train_path, config_base
            )

            # Run OOS backtest (includes train data for indicator warmup)
            oos_result = _run_period(
                strategy_name, symbol, temp_oos_path, config_base
            )

            # Calculate how much profit came from the OOS part
            # We need to subtract IS profit from the combined run
            oos_profit = oos_result["profit"] - is_result["profit"]
            oos_profit_pct = oos_result["profit_pct"] - is_result["profit_pct"]

            # Efficiency = OOS profit / IS profit (how well does IS predict OOS)
            efficiency = (oos_profit / is_result["profit"]) if is_result["profit"] != 0 else 0

            windows.append({
                "window_id": window_id,
                "train_start": train_start.strftime("%Y-%m-%d"),
                "train_end": train_end.strftime("%Y-%m-%d"),
                "test_start": test_start.strftime("%Y-%m-%d"),
                "test_end": test_end.strftime("%Y-%m-%d"),
                "in_sample_profit": round(is_result["profit"], 2),
                "out_of_sample_profit": round(oos_profit, 2),
                "oos_profit_pct": round(oos_profit_pct, 2),
                "oos_win_rate": round(oos_result.get("win_rate", 0), 2),
                "oos_trades": oos_result.get("total_trades", 0) - is_result.get("total_trades", 0),
                "efficiency_ratio": round(efficiency, 4),
            })

        except Exception as e:
            print(f"[WalkForward] Window {window_id} error: {e}")
            windows.append({
                "window_id": window_id,
                "train_start": train_start.strftime("%Y-%m-%d"),
                "train_end": train_end.strftime("%Y-%m-%d"),
                "test_start": test_start.strftime("%Y-%m-%d"),
                "test_end": test_end.strftime("%Y-%m-%d"),
                "error": str(e),
            })
        finally:
            # Cleanup temp files
            for f in [temp_train_path, temp_oos_path]:
                if os.path.exists(f):
                    os.remove(f)

        window_id += 1
        current_start += pd.Timedelta(days=step_days)

    # Calculate aggregates
    valid_windows = [w for w in windows if "error" not in w]
    profitable_windows = [w for w in valid_windows if w.get("out_of_sample_profit", 0) > 0]

    aggregate = {
        "total_oos_profit": round(sum(w.get("out_of_sample_profit", 0) for w in valid_windows), 2),
        "avg_oos_profit": round(np.mean([w.get("out_of_sample_profit", 0) for w in valid_windows]), 2) if valid_windows else 0,
        "avg_efficiency": round(np.mean([w.get("efficiency_ratio", 0) for w in valid_windows]), 4) if valid_windows else 0,
        "total_oos_trades": sum(w.get("oos_trades", 0) for w in valid_windows),
        "profitable_windows": len(profitable_windows),
        "total_windows": len(valid_windows),
        "consistency_score": round(len(profitable_windows) / len(valid_windows), 2) if valid_windows else 0,
    }

    return {"windows": windows, "aggregate": aggregate}


def _run_period(strategy_name, symbol, data_file, config_base):
    """Run backtest on a specific data period. Returns metrics dict."""
    config = copy.deepcopy(config_base)
    config["symbols"] = [symbol]
    config["strategy"] = strategy_name
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
    metrics = reporter._calculate_metrics(round_trips)

    profit = float(round_trips["pnl"].sum()) if not round_trips.empty else 0.0
    profit_pct = (profit / float(initial_balance)) * 100 if initial_balance else 0.0

    return {
        "profit": profit,
        "profit_pct": profit_pct,
        "win_rate": metrics.get("win_rate", 0),
        "total_trades": metrics.get("total_trades", 0),
    }
