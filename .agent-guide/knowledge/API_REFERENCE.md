# API Reference

> **For AI Agents** | Complete PyWebView API specification

---

## 📌 Overview

All API methods are exposed via `window.pywebview.api` in the frontend.

Python implementation location: `app/ui/api/`

---

## 🔧 Data APIs

### get_data_files()
```typescript
get_data_files(): Promise<string[]>
```
Returns list of available CSV data files.

**Example response:**
```json
["BTCUSDT_1h.csv", "ETHUSDT_1h.csv", "BTCUSDT_15m.csv"]
```

---

### get_strategies()
```typescript
get_strategies(): Promise<string[]>
```
Returns list of available strategy names.

**Example response:**
```json
["RSI_Strategy", "MACD_Strategy", "BB_Strategy"]
```

---

## ⚙️ Config APIs

### get_strategy_config(strategyName)
```typescript
get_strategy_config(strategyName: string): Promise<StrategyConfig>
```
Returns strategy parameters with defaults and validation rules.

**Example response:**
```json
{
  "rsi_period": {"type": "int", "default": 14, "min": 5, "max": 50},
  "rsi_overbought": {"type": "float", "default": 70, "min": 50, "max": 90},
  "rsi_oversold": {"type": "float", "default": 30, "min": 10, "max": 50},
  "take_profit": {"type": "float", "default": 0.02, "min": 0.005, "max": 0.1},
  "stop_loss": {"type": "float", "default": 0.01, "min": 0.005, "max": 0.05}
}
```

---

### save_strategy_config(strategyName, config)
```typescript
save_strategy_config(strategyName: string, config: object): Promise<boolean>
```
Saves strategy config to JSON override file (not .py file).

**Saves to:** `config/strategy_overrides/{strategyName}.json`

---

### get_global_config()
```typescript
get_global_config(): Promise<GlobalConfig>
```
Returns global settings from config.yaml.

**Example response:**
```json
{
  "default_symbol": "BTCUSDT",
  "default_timeframe": "1h",
  "initial_balance": 10000,
  "commission_rate": 0.001
}
```

---

### save_global_config(config)
```typescript
save_global_config(config: object): Promise<boolean>
```
Writes settings to config.yaml.

---

## 🧪 Backtest APIs

### run_backtest(config)
```typescript
run_backtest(config: BacktestConfig): Promise<BacktestResult>
```

**Input:**
```json
{
  "strategy_name": "RSI_Strategy",
  "symbol": "BTCUSDT",
  "data_file": "BTCUSDT_1h.csv",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "parameters": {
    "rsi_period": 14,
    "take_profit": 0.02
  }
}
```

**Output:**
```json
{
  "run_id": 123,
  "strategy_name": "RSI_Strategy",
  "total_profit": "1234.56",
  "win_rate": 0.65,
  "total_trades": 42,
  "profit_factor": 1.8,
  "max_drawdown": "-5.2",
  "sharpe_ratio": 1.5
}
```

---

### get_run_history()
```typescript
get_run_history(): Promise<RunSummary[]>
```

Returns all runs with summary metrics.

**Example response:**
```json
[
  {
    "id": 123,
    "strategy_name": "RSI_Strategy",
    "symbol": "BTCUSDT",
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "created_at": "2024-12-15T10:30:00",
    "profit": "1234.56",
    "win_rate": 0.65,
    "trades": 42
  },
  ...
]
```

---

### get_run_details(runId)
```typescript
get_run_details(runId: number): Promise<RunDetails>
```

Full details for a single run including all metrics.

---

### get_run_timeseries(runId)
```typescript
get_run_timeseries(runId: number): Promise<TimeseriesData>
```

**LAZY LOAD ONLY** - Don't call in list views.

**Example response:**
```json
{
  "equity_curve": [[1704067200, 10000], [1704153600, 10050], ...],
  "drawdown_curve": [[1704067200, 0], [1704153600, -0.5], ...]
}
```

---

### get_trades(runId)
```typescript
get_trades(runId: number): Promise<Trade[]>
```

**Example response:**
```json
[
  {
    "id": 1,
    "entry_time": "2024-01-05T14:00:00",
    "exit_time": "2024-01-05T18:00:00",
    "side": "long",
    "entry_price": "42000.50",
    "exit_price": "42840.00",
    "quantity": "0.1",
    "pnl": "83.95",
    "exit_reason": "tp"
  },
  ...
]
```

---

## 📊 Analysis APIs

### run_grid_search(config)
```typescript
run_grid_search(config: GridSearchConfig): Promise<GridSearchResult[]>
```

**Input:**
```json
{
  "strategy_name": "RSI_Strategy",
  "symbol": "BTCUSDT",
  "data_file": "BTCUSDT_1h.csv",
  "param_grid": {
    "rsi_period": [10, 14, 20],
    "take_profit": [0.02, 0.03]
  },
  "base_config": {}
}
```

**Output:**
```json
[
  {"params": {"rsi_period": 10, "take_profit": 0.02}, "profit": 500, "win_rate": 0.55, "run_id": 124},
  {"params": {"rsi_period": 10, "take_profit": 0.03}, "profit": 650, "win_rate": 0.52, "run_id": 125},
  ...
]
```

---

### run_walk_forward(config)
```typescript
run_walk_forward(config: WalkForwardConfig): Promise<WalkForwardResult>
```

**Input:**
```json
{
  "strategy_name": "RSI_Strategy",
  "symbol": "BTCUSDT",
  "data_file": "BTCUSDT_1h.csv",
  "config": {},
  "train_days": 90,
  "test_days": 30,
  "step_days": 30
}
```

**Output:**
```json
{
  "windows": [
    {
      "train_start": "2024-01-01",
      "train_end": "2024-03-31",
      "test_start": "2024-04-01",
      "test_end": "2024-04-30",
      "in_sample_profit": 500,
      "out_of_sample_profit": 150,
      "efficiency_ratio": 0.30
    },
    ...
  ],
  "aggregate": {
    "total_oos_profit": 1200,
    "avg_efficiency": 0.28,
    "consistency_score": 0.85
  }
}
```

---

### run_sensitivity(config)
```typescript
run_sensitivity(config: SensitivityConfig): Promise<SensitivityResult>
```

**Input:**
```json
{
  "strategy_name": "RSI_Strategy",
  "symbol": "BTCUSDT",
  "data_file": "BTCUSDT_1h.csv",
  "base_config": {},
  "param_name": "rsi_period",
  "param_range": [10, 12, 14, 16, 18, 20],
  "metric": "profit"
}
```

**Output:**
```json
{
  "parameter": "rsi_period",
  "values": [10, 12, 14, 16, 18, 20],
  "results": [100, 150, 200, 180, 120, 90],
  "metric": "profit",
  "optimal": {"value": 14, "result": 200},
  "stability_score": 0.72
}
```

---

### compare_runs(runId1, runId2)
```typescript
compare_runs(runId1: number, runId2: number): Promise<ComparisonResult>
```

**Output:**
```json
{
  "run_1": {"id": 1, "profit": 1000, "win_rate": 0.6, ...},
  "run_2": {"id": 2, "profit": 1500, "win_rate": 0.55, ...},
  "differences": {"profit": 500, "win_rate": -0.05, ...}
}
```

---

## 📤 Export APIs

### export_results(runId, format)
```typescript
export_results(runId: number, format: 'csv' | 'json'): Promise<string>
```

Returns path to exported file.

---

## 🎨 Theme APIs

### get_themes()
```typescript
get_themes(): Promise<string[]>
```

**Response:** `["dark", "light", "midnight"]`

---

### get_active_theme()
```typescript
get_active_theme(): Promise<string>
```

**Response:** `"dark"`

---

### set_active_theme(themeName)
```typescript
set_active_theme(themeName: string): Promise<boolean>
```

Sets active theme and persists to database.
