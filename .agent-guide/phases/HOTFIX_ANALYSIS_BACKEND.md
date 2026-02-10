# HOTFIX: Analysis Backend Implementation

> **Priority:** HIGH | **Depends On:** Existing `app/backtest/engine.py` | **Type:** Backend Python

---

## 🎯 Problem

The analysis UI components (Grid Search, Walk-Forward, Sensitivity) call backend API methods that **DO NOT EXIST YET**. The frontend references `window.pywebview.api.run_grid_search()` etc., but no Python code implements these.

**What's missing:**
1. `app/backtest/grid_search.py` — Does not exist
2. `app/backtest/walk_forward.py` — Does not exist
3. `app/backtest/sensitivity.py` — Does not exist
4. Bridge API methods to expose them via PyWebView — May not exist

---

## 📖 Required Reading (MANDATORY)

**Read BEFORE writing any code:**

1. `.agent-guide/knowledge/BACKTEST_ENGINE.md` — How the engine works, what it produces
2. `app/backtest/engine.py` — The `BacktestEngine` class
3. `app/backtest/reporting.py` — The `BacktestReporter` class (specifically `_calculate_metrics`, `_calculate_drawdown`, `_calculate_risk_metrics`)
4. `app/backtest/run_batch_analysis.py` → function `run_single_backtest()` (lines 218-319) — THIS IS YOUR REFERENCE PATTERN for running a backtest programmatically
5. `app/strategies/loader.py` — How strategies are loaded
6. `config.yaml` — Config structure

---

## 🏗️ Architecture

```
Frontend (React)                    Bridge (Python)                    Engine (Python)
─────────────────                   ──────────────                     ──────────────
GridSearchPanel.tsx                 bridge API method                  grid_search.py
  → window.pywebview.api            → run_grid_search()                → loops BacktestEngine
    .run_grid_search(config)          → returns results                  for each param combo

WalkForwardPanel.tsx                bridge API method                  walk_forward.py
  → window.pywebview.api            → run_walk_forward()               → slices data, runs
    .run_walk_forward(config)         → returns results                  BacktestEngine per window

SensitivityAnalysis.tsx             bridge API method                  sensitivity.py
  → window.pywebview.api            → run_sensitivity()                → loops BacktestEngine
    .run_sensitivity(config)          → returns results                  for each param value
```

---

## ✅ Task 1: Create `app/backtest/grid_search.py`

### Purpose
Run backtest across all combinations of parameter values (grid) and return results sorted by profit.

### Implementation

```python
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
```

### Verification
```python
# Quick test
from app.backtest.grid_search import run_grid_search

results = run_grid_search(
    strategy_name="rsi_no_retest",
    symbol="BTC/USDT",
    data_file="app/backtest/data/BTCUSDT_15m.csv",
    param_grid={"rsi_period": [10, 14]},
)
print(f"Results count: {len(results)}")
for r in results:
    print(f"  {r['params']} → profit: ${r['profit']}")
```

---

## ✅ Task 2: Create `app/backtest/walk_forward.py`

### Purpose
Split data into rolling train/test windows. Optimize on train window, validate on test window.

### Implementation

```python
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

            # Cleanup temp files
            for f in [temp_train_path, temp_oos_path]:
                if os.path.exists(f):
                    os.remove(f)

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
```

### Verification
```python
from app.backtest.walk_forward import run_walk_forward

result = run_walk_forward(
    strategy_name="rsi_no_retest",
    symbol="BTC/USDT",
    data_file="app/backtest/data/BTCUSDT_15m.csv",
    train_days=60,
    test_days=14,
    step_days=14,
)
print(f"Windows: {len(result['windows'])}")
print(f"Consistency: {result['aggregate']['consistency_score']}")
```

---

## ✅ Task 3: Create `app/backtest/sensitivity.py`

### Purpose
Test how a single parameter affects performance. Produces a curve: param value → metric.

### Implementation

```python
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
```

### Verification
```python
from app.backtest.sensitivity import run_sensitivity

result = run_sensitivity(
    strategy_name="rsi_no_retest",
    symbol="BTC/USDT",
    data_file="app/backtest/data/BTCUSDT_15m.csv",
    param_name="rsi_period",
    param_range=[10, 12, 14, 16, 18, 20],
    metric="profit",
)
print(f"Optimal: {result['optimal']}")
print(f"Stability: {result['stability_score']}")
```

---

## ✅ Task 4: Create `app/backtest/compare.py`

### Purpose
Compare two existing backtest runs side-by-side.

### Implementation

```python
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
            differences[key] = round(float(v2) - float(v1), 4)
        except (TypeError, ValueError):
            differences[key] = 0

    better_run = 2 if run2_data.get("profit", 0) > run1_data.get("profit", 0) else 1

    return {
        "run_1": run1_data,
        "run_2": run2_data,
        "differences": differences,
        "better_run": better_run,
    }
```

---

## ✅ Task 5: Wire Bridge API Methods

**Check what bridge/API files exist.** If `app/ui/api/` exists, add methods there. If not, create the API package.

The bridge API must expose these methods to `window.pywebview.api`:

```python
# In your bridge API class (wherever js_api is exposed)

def run_grid_search(self, config: dict) -> list:
    """Called by frontend: window.pywebview.api.run_grid_search(config)"""
    from app.backtest.grid_search import run_grid_search
    return run_grid_search(
        strategy_name=config["strategy_name"],
        symbol=config["symbol"],
        data_file=self._resolve_data_path(config["data_file"]),
        param_grid=config["param_grid"],
        base_config=config.get("base_config", {}),
    )

def run_walk_forward(self, config: dict) -> dict:
    """Called by frontend: window.pywebview.api.run_walk_forward(config)"""
    from app.backtest.walk_forward import run_walk_forward
    return run_walk_forward(
        strategy_name=config["strategy_name"],
        symbol=config["symbol"],
        data_file=self._resolve_data_path(config["data_file"]),
        config_overrides=config.get("config", {}),
        train_days=config.get("train_days", 90),
        test_days=config.get("test_days", 30),
        step_days=config.get("step_days", 30),
    )

def run_sensitivity(self, config: dict) -> dict:
    """Called by frontend: window.pywebview.api.run_sensitivity(config)"""
    from app.backtest.sensitivity import run_sensitivity
    return run_sensitivity(
        strategy_name=config["strategy_name"],
        symbol=config["symbol"],
        data_file=self._resolve_data_path(config["data_file"]),
        base_config=config.get("base_config", {}),
        param_name=config["param_name"],
        param_range=config["param_range"],
        metric=config.get("metric", "profit"),
    )

def compare_runs(self, run_id_1: int, run_id_2: int) -> dict:
    """Called by frontend: window.pywebview.api.compare_runs(id1, id2)"""
    from app.backtest.compare import compare_runs
    # Load both runs from database
    run1 = self._get_run_data(run_id_1)
    run2 = self._get_run_data(run_id_2)
    return compare_runs(run1, run2)

def _resolve_data_path(self, filename: str) -> str:
    """Convert data file name to absolute path."""
    import os
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_root, "app", "backtest", "data", filename)
```

---

## ✅ Task 6: Update `__init__.py`

Update `app/backtest/__init__.py` to export new modules:

```python
from app.backtest.engine import BacktestEngine
from app.backtest.grid_search import run_grid_search
from app.backtest.walk_forward import run_walk_forward
from app.backtest.sensitivity import run_sensitivity
from app.backtest.compare import compare_runs
```

---

## 🔍 Verification Checklist

Run these checks after completing all tasks:

```bash
# 1. Check files exist
ls app/backtest/grid_search.py
ls app/backtest/walk_forward.py
ls app/backtest/sensitivity.py
ls app/backtest/compare.py

# 2. Check imports work (use conda env)
conda run -n rsi python -c "from app.backtest.grid_search import run_grid_search; print('OK')"
conda run -n rsi python -c "from app.backtest.walk_forward import run_walk_forward; print('OK')"
conda run -n rsi python -c "from app.backtest.sensitivity import run_sensitivity; print('OK')"
conda run -n rsi python -c "from app.backtest.compare import compare_runs; print('OK')"

# 3. Quick functional test (if data file exists)
conda run -n rsi python -c "
from app.backtest.grid_search import run_grid_search
results = run_grid_search('rsi_no_retest', 'BTC/USDT', 'app/backtest/data/BTCUSDT_15m.csv', {'rsi_period': [10, 14]})
print(f'Grid search returned {len(results)} results')
"
```

---

## 📤 Report Template

```
## HOTFIX Analysis Backend Complete

### Created Files:
- app/backtest/grid_search.py ✅
- app/backtest/walk_forward.py ✅
- app/backtest/sensitivity.py ✅
- app/backtest/compare.py ✅
- Updated: app/backtest/__init__.py ✅
- Updated: Bridge API methods ✅

### Import Tests:
- grid_search import: ✅ / ❌
- walk_forward import: ✅ / ❌
- sensitivity import: ✅ / ❌
- compare import: ✅ / ❌

### Functional Tests:
- Grid search (2 params): ✅ / ❌
- Walk forward (2 windows): ✅ / ❌
- Sensitivity (5 values): ✅ / ❌

### Notes:
[Any issues or modifications made]
```
