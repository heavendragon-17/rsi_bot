# Optimization Specification

> Grid search, walk-forward optimization, sensitivity analysis.

---

## Grid Search

### Concurrency Model

- User selects `max_workers` (1-4) in config panel
- Backend uses `ProcessPoolExecutor(max_workers=N)` per grid search job
- Each parameter combination runs as a separate process

### Storage: Parent + Child Runs

```
runs table:
  ┌─────────────────────────────────────────────┐
  │ id=100, is_grid_search=true, status=running │  ← Parent run
  │ grid_summary (JSON): heatmap data            │
  └─────────────────────────────────────────────┘
       │
       ├── id=101, grid_search_parent_id=100  ← Child (rsi=10, ema=15)
       ├── id=102, grid_search_parent_id=100  ← Child (rsi=10, ema=20)
       └── ...
```

- **Parent run**: Tracks overall grid state, has denormalized `grid_summary` JSON for fast heatmap loading
- **Child runs**: Full individual backtest results, can be drilled into from the heatmap
- **Lazy loading**: Heatmap reads from parent's `grid_summary`. Clicking a cell loads the child run detail

### Endpoint

```
POST /api/grid-search
{
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "strategy": "rsi_no_retest",
  "x_axis": { "param": "rsi_period", "min": 10, "max": 30, "step": 2 },
  "y_axis": { "param": "ema_fast", "min": 10, "max": 30, "step": 2 },
  "max_workers": 4,
  "metric": "sharpe",
  "base_config": { "initial_capital": 10000, "leverage": 10, ... }
}
```

**Response**: `{ "run_id": 100, "total_combinations": 121, "status": "running" }`

### SSE Progress

```
event: progress
data: { "pct": 42, "current": 51, "total": 121, "best_so_far": { "x": 14, "y": 21, "value": 1.85 } }

event: complete
data: { "run_id": 100, "best": { "x_value": 14, "y_value": 21, "metric_value": 1.85 } }
```

### Cancellation: Keep Partial Results

1. Mark parent as `status = 'cancelled'`
2. Cancel pending futures (unstarted combinations)
3. **Keep all completed child runs**
4. Update parent's `grid_summary` with partial heatmap (empty cells for uncompleted)
5. Frontend shows partial heatmap with empty cells (grey/hatched)

---

## Walk-Forward Optimization

### Flow

1. User configures: IS window (days), OOS window (days), step size, param to optimize, param range, metric
2. System computes windows: `total_windows = (total_days - is_window - oos_window) / step_size + 1`
3. For each window:
   a. Run grid of parameter values on IS period → find best param for selected metric
   b. Run single backtest on OOS period with that best param → record OOS return
4. Aggregate results: OOS win rate, avg OOS return, most common param, param stability

### Endpoint

```
POST /api/walk-forward
{
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "strategy": "rsi_no_retest",
  "is_window_days": 90,
  "oos_window_days": 30,
  "step_size_days": 30,
  "param_to_optimize": "rsi_period",
  "param_min": 10, "param_max": 30, "param_step": 2,
  "optimize_metric": "sharpe",
  "max_workers": 4,
  "base_config": { ... }
}
```

### Results & Verdict

**Report only** — user decides whether to apply the best parameter.

| Verdict | Criteria |
|---------|----------|
| **Robust** | param_stability > 0.7 AND oos_win_rate > 60% |
| **Marginal** | param_stability > 0.5 OR oos_win_rate > 50% |
| **Overfit** | param_stability < 0.5 AND oos_win_rate < 50% |

"Apply best param" button updates sidebar config with the most common parameter value.

### SSE Progress

```
event: progress
data: { "pct": 35, "current_window": 4, "total_windows": 12, "phase": "IS" | "OOS" }

event: complete
data: { "run_id": 200, "verdict": "robust", "most_common_param": 21 }
```

---

## Sensitivity Analysis

### Flow

1. **Always run fresh baseline** (1 backtest with current params)
2. For each of 8 parameters: run 2 backtests (base - variation%, base + variation%)
3. Total: 1 + 16 = **17 backtests**
4. Compare each variation's metric against baseline → compute impact %

### Endpoint

```
POST /api/sensitivity
{
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "strategy": "rsi_no_retest",
  "variation_percent": 20,
  "metric": "sharpe",
  "max_workers": 4,
  "base_config": { ... }
}
```

### Results

Per parameter:
- `low_value`, `base_value`, `high_value` (param values tested)
- `low_metric`, `base_metric`, `high_metric` (metric outcomes)
- `low_impact_pct`, `high_impact_pct` (% change from baseline)
- `sensitivity`: "high" (>20% impact), "medium" (10-20%), "low" (<10%)

Auto-generated insights:
- High-sensitivity params (overfitting risk)
- Asymmetric impacts (much worse in one direction)
- Stable params (safe to keep current value)

### Frontend: Tornado Chart

Horizontal bar chart per parameter, showing impact range (low..high) centered on baseline.
