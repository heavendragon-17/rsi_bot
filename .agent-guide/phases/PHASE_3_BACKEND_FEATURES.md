# Phase 3: Backend Features

> **Phase Type:** Backend | **Estimated Time:** 2-3 hours | **Depends On:** Phase 2

---

## 🎯 Objective

Implement advanced analysis features: Grid Search, Walk-Forward, Sensitivity Analysis, and Run Comparison.

---

## 📖 Required Reading

Before starting, read:
- `docs/backend/FEATURE_GAPS.md`
- `.agent-guide/knowledge/API_REFERENCE.md` (for method signatures)

---

## ✅ Tasks

### Task 3.1: Grid Search

Create `app/backtest/grid_search.py`:

**Purpose:** Run backtests across a grid of parameter combinations.

**Function signature:**
```python
def run_grid_search(
    strategy_name: str,
    symbol: str,
    data_file: str,
    param_grid: dict[str, list],  # {"rsi_period": [10, 14, 20], "tp": [0.02, 0.03]}
    base_config: dict
) -> list[dict]:
    """
    Returns list of results, one per combination:
    [
        {
            "params": {"rsi_period": 10, "tp": 0.02},
            "profit": 1234.56,
            "win_rate": 0.65,
            "trades": 42,
            "run_id": 123
        },
        ...
    ]
    """
```

**Implementation notes:**
- Use `itertools.product` to generate combinations
- Run each combination through existing backtest engine
- Save each run to database
- Return summary for UI display

**Add API method:**
In `app/ui/api/backtest.py`, add:
```python
def run_grid_search(self, config: dict) -> list[dict]:
    # config contains: strategy_name, symbol, data_file, param_grid, base_config
    pass
```

### Task 3.2: Walk-Forward Analysis

Create `app/backtest/walk_forward.py`:

**Purpose:** Validate strategy robustness with rolling in-sample/out-of-sample windows.

**Function signature:**
```python
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
    Returns:
    {
        "windows": [
            {
                "train_start": "2024-01-01",
                "train_end": "2024-03-31",
                "test_start": "2024-04-01",
                "test_end": "2024-04-30",
                "in_sample_profit": 500.0,
                "out_of_sample_profit": 150.0,
                "efficiency_ratio": 0.30
            },
            ...
        ],
        "aggregate": {
            "total_oos_profit": 1200.0,
            "avg_efficiency": 0.28,
            "consistency_score": 0.85
        }
    }
    """
```

**Implementation notes:**
- Slide window across data
- For each window: train on IS period, test on OOS
- Calculate efficiency ratio: OOS_profit / IS_profit
- Return all windows for visualization

**Add API method:**
```python
def run_walk_forward(self, config: dict) -> dict:
    pass
```

### Task 3.3: Sensitivity Analysis

Create `app/backtest/sensitivity.py`:

**Purpose:** Test how sensitive results are to parameter changes.

**Function signature:**
```python
def run_sensitivity(
    strategy_name: str,
    symbol: str,
    data_file: str,
    base_config: dict,
    param_name: str,
    param_range: list,
    metric: str = "profit"  # or "win_rate", "sharpe"
) -> dict:
    """
    Returns:
    {
        "parameter": "rsi_period",
        "values": [10, 12, 14, 16, 18, 20],
        "results": [100, 150, 200, 180, 120, 90],
        "metric": "profit",
        "optimal": {"value": 14, "result": 200},
        "stability_score": 0.72  # How stable across range
    }
    """
```

**Implementation notes:**
- Vary one parameter at a time
- Keep all other params fixed
- Calculate stability score (low variance = high stability)

**Add API method:**
```python
def run_sensitivity(self, config: dict) -> dict:
    pass
```

### Task 3.4: Run Comparison

Create `app/backtest/comparison.py`:

**Purpose:** Compare two backtest runs side-by-side.

**Function signature:**
```python
def compare_runs(run_id_1: int, run_id_2: int) -> dict:
    """
    Returns:
    {
        "run_1": {
            "id": 1,
            "strategy": "RSI_Strategy",
            "profit": 1000,
            "win_rate": 0.6,
            ...
        },
        "run_2": {
            "id": 2,
            "strategy": "MACD_Strategy",
            "profit": 1500,
            "win_rate": 0.55,
            ...
        },
        "differences": {
            "profit": 500,  # run_2 - run_1
            "win_rate": -0.05,
            ...
        },
        "verdict": "Run 2 has higher profit but lower win rate"
    }
    """
```

**Add API method:**
```python
def compare_runs(self, run_id_1: int, run_id_2: int) -> dict:
    pass
```

### Task 3.5: Export Functionality

Add to `app/ui/api/backtest.py`:

```python
def export_results(self, run_id: int, format: str) -> str:
    """
    Export backtest results to file.
    
    Args:
        run_id: The run to export
        format: 'csv' or 'json'
    
    Returns:
        Path to exported file
    """
```

**Export CSV should include:**
- Trade list with all columns
- Summary metrics at top

---

## 🔍 Verification Checkpoint

Test each new feature:

```python
from app.backtest.grid_search import run_grid_search
from app.backtest.walk_forward import run_walk_forward
from app.backtest.sensitivity import run_sensitivity
from app.backtest.comparison import compare_runs

# Test grid search
results = run_grid_search(
    strategy_name="RSI_Strategy",
    symbol="BTCUSDT",
    data_file="BTCUSDT_1h.csv",
    param_grid={"rsi_period": [10, 14]},
    base_config={}
)
assert len(results) == 2

# Test walk-forward
wf_result = run_walk_forward(...)
assert "windows" in wf_result

# Test sensitivity
sens_result = run_sensitivity(...)
assert "optimal" in sens_result

# Test comparison
comp_result = compare_runs(1, 2)
assert "differences" in comp_result

print("All backend features working!")
```

---

## 📤 Report Template

```
## Phase 3 Complete: Backend Features

### Created Files:
- app/backtest/grid_search.py
- app/backtest/walk_forward.py
- app/backtest/sensitivity.py
- app/backtest/comparison.py

### API Methods Added:
- run_grid_search(): ✅
- run_walk_forward(): ✅
- run_sensitivity(): ✅
- compare_runs(): ✅
- export_results(): ✅

### Verification:
- Grid Search test: ✅ / ❌
- Walk-Forward test: ✅ / ❌
- Sensitivity test: ✅ / ❌
- Comparison test: ✅ / ❌

Awaiting "proceed" command for Phase 4.
```

---

## ⏭️ Next Phase

After user approval, proceed to `PHASE_4_FRONTEND_CORE.md`
