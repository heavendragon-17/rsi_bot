# Feature Gaps - Backend Implementation Plan

> **Document Type:** Implementation Roadmap  
> **Agent:** backend-specialist  
> **Status:** Phase 2 Documentation

---

## Overview

The existing Figma UI expects features that don't exist in the current backend. This document identifies gaps and plans implementation.

| Feature | Current Status | UI Expects | Priority |
|---------|----------------|------------|----------|
| Single Backtest | ✅ Exists | ✅ Works | - |
| SQLite Storage | ❌ Missing | ✅ Saves runs | P0 |
| Grid Search | ❌ Missing | ✅ Heatmap | P1 |
| Walk-Forward | ❌ Missing | ✅ Charts | P2 |
| Sensitivity | ❌ Missing | ✅ Charts | P2 |
| Run Comparison | ❌ Missing | ✅ Diff view | P1 |

---

## Gap 1: SQLite Storage (P0 - Must Have)

### Current
- Results printed to console
- HTML report generated
- No persistence

### Required
- Save runs to `data/backtest.db`
- Store metrics, trades, time-series
- Query history from UI

### Implementation Plan

**New Files:**
```
app/repository/
├── db.py               # Connection manager
├── runs_repo.py        # Runs CRUD
├── trades_repo.py      # Trades storage
└── timeseries_repo.py  # BLOB compression
```

**Modify:**
```
app/backtest/engine.py     # Add DB write after run
app/backtest/reporting.py  # Optional: keep HTML alongside DB
```

**Effort:** 4-6 hours

---

## Gap 2: Grid Search (P1 - Should Have)

### Current
- Single parameter set per run
- No parameter sweep

### Required
- Define parameter ranges
- Run multiple backtests
- Store grid_search_parent_id
- Generate heatmap data

### Implementation Plan

**New File:** `app/backtest/grid_search.py`

```python
from itertools import product
from typing import Dict, List, Any

class GridSearch:
    def __init__(self, engine_class, strategy_class, config):
        self.engine_class = engine_class
        self.strategy_class = strategy_class
        self.base_config = config
    
    def run(self, param_grid: Dict[str, List[Any]]) -> List[dict]:
        """
        Run grid search across parameter combinations.
        
        Args:
            param_grid: {
                "rsi_period": [14, 21, 28],
                "rsi_wma_length": [30, 45, 60]
            }
        
        Returns:
            List of {params, metrics} for each combination
        """
        results = []
        combinations = self._generate_combinations(param_grid)
        
        # Create parent run
        parent_run_id = self._create_parent_run(len(combinations))
        
        for i, params in enumerate(combinations):
            # Merge params with base config
            run_config = {**self.base_config, **params}
            
            # Run single backtest
            engine = self.engine_class(
                data_path=self.data_path,
                strategy_class=self.strategy_class,
                config=run_config
            )
            engine.run()
            
            # Extract metrics
            metrics = self._extract_metrics(engine)
            
            # Save to DB with parent reference
            run_id = self._save_run(
                config=run_config,
                metrics=metrics,
                parent_id=parent_run_id
            )
            
            results.append({
                "params": params,
                "metrics": metrics,
                "run_id": run_id
            })
            
            self._update_progress(parent_run_id, i + 1, len(combinations))
        
        return results
    
    def _generate_combinations(self, grid: Dict) -> List[Dict]:
        """Generate all parameter combinations."""
        keys = list(grid.keys())
        values = [grid[k] for k in keys]
        return [dict(zip(keys, combo)) for combo in product(*values)]
```

**Heatmap Data Format:**
```python
def get_heatmap_data(parent_run_id: int) -> dict:
    """Get data for heatmap visualization."""
    runs = get_child_runs(parent_run_id)
    
    # Assuming 2D grid (x_param, y_param)
    return {
        "x_param": "rsi_period",
        "y_param": "rsi_wma_length",
        "x_values": [14, 21, 28],
        "y_values": [30, 45, 60],
        "data": [
            # [x_idx, y_idx, metric_value]
            [0, 0, 8.5],   # rsi=14, wma=30 -> 8.5% profit
            [0, 1, 12.3],
            # ...
        ],
        "metric": "net_profit_pct"
    }
```

**Effort:** 6-8 hours

---

## Gap 3: Walk-Forward Optimization (P2 - Could Have)

### Current
- Single in-sample period
- No out-of-sample validation

### Required
- Split data into windows
- In-sample optimization
- Out-of-sample validation
- Track overfitting metrics

### Implementation Plan

**New File:** `app/backtest/walk_forward.py`

```python
class WalkForward:
    def __init__(
        self,
        in_sample_pct: float = 0.7,
        n_windows: int = 5,
        optimization_metric: str = "sharpe_ratio"
    ):
        self.in_sample_pct = in_sample_pct
        self.n_windows = n_windows
        self.optimization_metric = optimization_metric
    
    def run(self, data, strategy_class, param_grid) -> WalkForwardResult:
        """
        Run walk-forward analysis.
        
        1. Split data into n_windows
        2. For each window:
           a. Optimize on in-sample
           b. Validate on out-of-sample
        3. Compare IS vs OOS performance
        """
        windows = self._split_data(data)
        results = []
        
        for window in windows:
            is_data, oos_data = self._split_window(window)
            
            # Optimize on in-sample
            best_params = self._optimize(is_data, param_grid)
            is_metrics = self._run_backtest(is_data, best_params)
            
            # Validate on out-of-sample
            oos_metrics = self._run_backtest(oos_data, best_params)
            
            results.append({
                "window": window.date_range,
                "best_params": best_params,
                "is_metrics": is_metrics,
                "oos_metrics": oos_metrics,
                "degradation": self._calc_degradation(is_metrics, oos_metrics)
            })
        
        return WalkForwardResult(
            windows=results,
            avg_degradation=np.mean([r["degradation"] for r in results]),
            robustness_score=self._calc_robustness(results)
        )
```

**Effort:** 8-10 hours

---

## Gap 4: Sensitivity Analysis (P2 - Could Have)

### Current
- No parameter sensitivity testing

### Required
- Vary single parameter
- Measure metric changes
- Identify fragile parameters

### Implementation Plan

**New File:** `app/backtest/sensitivity.py`

```python
class SensitivityAnalysis:
    def __init__(self, base_config: dict, metric: str = "net_profit_pct"):
        self.base_config = base_config
        self.metric = metric
    
    def analyze_parameter(
        self,
        param_name: str,
        values: List[Any]
    ) -> SensitivityResult:
        """
        Test single parameter across range.
        
        Returns metric curve and fragility score.
        """
        results = []
        
        for value in values:
            config = {**self.base_config, param_name: value}
            metrics = self._run_backtest(config)
            results.append({
                "value": value,
                "metric": metrics[self.metric]
            })
        
        return SensitivityResult(
            param_name=param_name,
            values=values,
            metrics=[r["metric"] for r in results],
            fragility_score=self._calc_fragility(results)
        )
    
    def _calc_fragility(self, results: List[dict]) -> float:
        """
        Fragility = coefficient of variation.
        High fragility = small param changes cause big metric changes.
        """
        metrics = [r["metric"] for r in results]
        return np.std(metrics) / np.abs(np.mean(metrics))
```

**Chart Data Format:**
```python
{
    "param_name": "rsi_period",
    "values": [10, 14, 18, 21, 25, 28, 32],
    "net_profit_pct": [5.2, 8.1, 9.3, 8.5, 7.2, 6.1, 4.8],
    "sharpe_ratio": [0.8, 1.2, 1.4, 1.3, 1.1, 0.9, 0.7],
    "fragility_score": 0.35  # Low fragility = robust
}
```

**Effort:** 4-5 hours

---

## Gap 5: Run Comparison (P1 - Should Have)

### Current
- Single run view only

### Required
- Select 2 runs
- Side-by-side metrics
- Diff highlighting
- Overlay equity curves

### Implementation Plan

**New File:** `app/backtest/comparison.py`

```python
def compare_runs(run_a_id: int, run_b_id: int) -> ComparisonResult:
    """Compare two backtest runs."""
    run_a = get_run_details(run_a_id)
    run_b = get_run_details(run_b_id)
    
    # Metric comparison
    metrics_diff = {}
    for key in run_a.metrics:
        a_val = run_a.metrics[key]
        b_val = run_b.metrics[key]
        diff = b_val - a_val
        pct_diff = (diff / abs(a_val) * 100) if a_val != 0 else 0
        
        metrics_diff[key] = {
            "a": a_val,
            "b": b_val,
            "diff": diff,
            "pct_diff": pct_diff,
            "better": "b" if diff > 0 else "a" if diff < 0 else "equal"
        }
    
    # Config diff
    config_diff = diff_configs(run_a.config, run_b.config)
    
    return ComparisonResult(
        run_a=run_a,
        run_b=run_b,
        metrics_diff=metrics_diff,
        config_diff=config_diff
    )
```

**Save to DB:**
```sql
INSERT INTO comparisons (run_a_id, run_b_id, diff_summary, notes)
VALUES (?, ?, ?, ?);
```

**Effort:** 3-4 hours

---

## Implementation Priority

| Phase | Features | Total Effort |
|-------|----------|--------------|
| **MVP** | SQLite Storage | 4-6 hours |
| **v1.1** | Grid Search, Comparison | 9-12 hours |
| **v1.2** | Walk-Forward, Sensitivity | 12-15 hours |

---

## Cross-Reference

| Document | Purpose |
|----------|---------|
| [API_CONTRACTS.md](./API_CONTRACTS.md) | API for these features |
| [USER_STORIES.md](../use-cases/USER_STORIES.md) | US-040 to US-052 |
| [DATABASE.md](../DATABASE.md) | Schema for grid_search, comparisons |
