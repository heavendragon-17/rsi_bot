# Optimization Suite

> Grid search, walk-forward optimization, and sensitivity analysis.
>
> **Modules**: `app/backtest/optimization/` (placeholder for future optimization tools), `app/backtest/statistics/` (analyzer.py, metrics.py, visualize.py).

---

## Grid Search

### How It Works
- User selects 2 parameters as X/Y axes with min/max/step ranges
- Each combination runs as a separate backtest via `ProcessPoolExecutor`
- Results stored as parent run (heatmap summary) + child runs (individual results)

### Endpoint: `POST /api/grid-search`

```json
{
  "symbol": "BTC/USDT", "timeframe": "1h", "strategy": "rsi_no_retest",
  "x_axis": { "param": "rsi_period", "min": 10, "max": 30, "step": 2 },
  "y_axis": { "param": "ema_fast", "min": 10, "max": 30, "step": 2 },
  "max_workers": 4, "metric": "sharpe",
  "base_config": { "initial_capital": 10000, "leverage": 10 }
}
```

### Storage: Parent + Child Runs
- **Parent run**: `is_grid_search=true`, has `grid_summary` JSON for fast heatmap loading
- **Child runs**: `grid_search_parent_id=parent_id`, full individual results
- **Lazy loading**: Heatmap from parent's summary; clicking a cell loads child detail

### Cancellation
Keeps all completed child runs. Parent marked `cancelled`. Partial heatmap shown with empty cells.

---

## Walk-Forward Optimization

### How It Works
1. Split data into rolling IS (in-sample) + OOS (out-of-sample) windows
2. For each window: optimize parameter on IS → test best param on OOS
3. Aggregate OOS results → produce robustness verdict

### Endpoint: `POST /api/walk-forward`

```json
{
  "symbol": "BTC/USDT", "strategy": "rsi_no_retest",
  "is_window_days": 90, "oos_window_days": 30, "step_size_days": 30,
  "param_to_optimize": "rsi_period",
  "param_min": 10, "param_max": 30, "param_step": 2,
  "optimize_metric": "sharpe", "max_workers": 4
}
```

### Verdict Criteria

| Verdict | Criteria |
|---------|----------|
| **Robust** | param_stability > 0.7 AND oos_win_rate > 60% |
| **Marginal** | param_stability > 0.5 OR oos_win_rate > 50% |
| **Overfit** | param_stability < 0.5 AND oos_win_rate < 50% |

"Apply best param" button updates sidebar config with the most common parameter value.

---

## Sensitivity Analysis

### How It Works
1. Run baseline backtest with current parameters
2. For each of 8 key parameters: run ±variation% (default ±20%)
3. Total: 1 + 16 = 17 backtests
4. Compare each variation's metric against baseline

### Endpoint: `POST /api/sensitivity`

```json
{
  "symbol": "BTC/USDT", "strategy": "rsi_no_retest",
  "variation_percent": 20, "metric": "sharpe", "max_workers": 4
}
```

### Results Per Parameter
- `low_value`, `base_value`, `high_value` — param values tested
- `low_metric`, `base_metric`, `high_metric` — metric outcomes
- `sensitivity`: "high" (>20% impact), "medium" (10-20%), "low" (<10%)

### Visualization
Tornado chart: horizontal bars per parameter showing impact range centered on baseline. Auto-generated insights for high-sensitivity and asymmetric parameters.
