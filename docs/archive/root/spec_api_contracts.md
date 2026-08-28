# RSI Bot — API Contracts Spec

> **Historical integration spec (April 2026):** Retained for provenance; use
> `docs/14_api_reference/` for current API contracts.

## Existing Endpoints (Verify & Fix)

### 1. `POST /api/backtest/run` [EXISTS — MODIFY]

**Current state:** Exists in `app/api/routes/backtest_run.py`. Accepts `BacktestRequest`, returns `BacktestStartResponse`. Currently raises 400 if CSV missing.

**Changes needed for Phase 1:**
- Move data-file check into worker thread: if CSV missing, download inline before running backtest.
- Emit `download_progress` and `download_complete` SSE events on the progress stream.
- Add file lock during inline download to prevent concurrent duplicate downloads.
- Auto-seed strategy into DB already handled by startup hook (`seed.py`).

**Request — `BacktestRequest` (full schema from `app/api/schemas.py`):**
```json
{
  "mode": "single",
  "symbol": "BTC/USDT",
  "symbols": null,
  "timeframe": "1h",
  "strategy": "rsi_no_retest",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "initial_capital": "10000.00",
  "leverage": 10,
  "risk_per_trade_pct": "0.02",
  "fee_tier": "0.001",
  "slippage_model": "none",
  "slippage_pct": "0.0",
  "params": {
    "rsi_period": 14,
    "rsi_ema_length": 9,
    "nr_tp1_rr": 1.5
  },
  "max_workers": null,
  "tick_data_path": null
}
```

**Field reference:**

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `mode` | `BacktestMode \| null` | `null` (auto-detect) | `single`, `portfolio`, `batch`, `tick_replay` |
| `symbol` | `str \| null` | `null` | Required for `single`, `tick_replay` |
| `symbols` | `list[str] \| null` | `null` | Required for `portfolio`, `batch` |
| `timeframe` | `str` | — | Required |
| `strategy` | `str` | — | Required, must be in `STRATEGY_MAP` |
| `start_date` | `str` | — | ISO format `yyyy-MM-dd` |
| `end_date` | `str` | — | ISO format `yyyy-MM-dd` |
| `initial_capital` | `str` | `"10000.00"` | Decimal string |
| `leverage` | `int` | `10` | |
| `risk_per_trade_pct` | `str` | `"0.02"` | Decimal string |
| `fee_tier` | `str` | `"0.001"` | Taker fee rate |
| `slippage_model` | `str` | `"none"` | `none`, `fixed`, `proportional` |
| `slippage_pct` | `str` | `"0.0"` | Slippage percentage |
| `params` | `dict` | `{}` | Strategy-specific params (must match config dataclass fields) |
| `max_workers` | `int \| null` | `null` | Batch mode only |
| `tick_data_path` | `str \| null` | `null` | Tick replay mode only |

**Mode validation (model_validator):**
- `single` / `tick_replay` → requires `symbol`
- `portfolio` / `batch` → requires `symbols`
- `null` → auto-detect from `symbol` vs `symbols`

**Response — 201:**
```json
{
  "run_id": 42,
  "status": "running"
}
```

**Error — 400:**
```json
{
  "detail": "Unknown strategy: xyz_crossover"
}
```

### Inline Download — File Lock Strategy

When the worker thread detects a missing CSV, it must acquire a file lock before downloading to prevent concurrent duplicate downloads for the same symbol.

```python
# Implementation approach:
# 1. Check if CSV exists → if yes, skip download
# 2. Try to acquire lock file: {csv_path}.lock
# 3. After acquiring lock, re-check CSV (another worker may have finished)
# 4. Download if still missing
# 5. Release lock

import fcntl

lock_path = f"{csv_path}.lock"
with open(lock_path, "w") as lock_file:
    fcntl.flock(lock_file, fcntl.LOCK_EX)  # Block until lock acquired
    try:
        if not os.path.exists(csv_path):  # Double-check after lock
            download_data_with_progress(...)
    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
```

---

### 2. `GET /api/backtest/{run_id}/progress` (SSE) [EXISTS — MODIFY]

**Current state:** Emits `progress` and `complete` events via `BacktestService.stream_progress()` (already implemented in `service.py:203-218`). Uses existing `_progress_queues` from `executor.py`. Timeout: **300s** (keep as-is).

**Changes needed:** Add `download_progress` and `download_complete` event types to the worker's event emissions. The SSE generator itself needs no changes — it already forwards any event type from the queue.

**Required SSE event types (typed events):**

| Event Name | Payload | When |
|------------|---------|------|
| `download_progress` | `{"pct": 45, "symbol": "BTC/USDT", "candles_fetched": 2300, "candles_total": 5000}` | During inline data download |
| `download_complete` | `{"symbol": "BTC/USDT", "candles_total": 5000}` | Download finished, backtest starting |
| `progress` | `{"pct": 67, "candle": 3350, "total": 5000}` | During backtest execution |
| `complete` | `{"run_id": 42, "status": "completed"}` | Backtest finished successfully |
| `error` | `{"message": "Insufficient data for date range", "code": "DATA_ERROR"}` | Any failure |

**SSE format (standard EventSource):**
```
event: download_progress
data: {"pct": 45, "symbol": "BTC/USDT", "candles_fetched": 2300, "candles_total": 5000}

event: progress
data: {"pct": 67, "candle": 3350, "total": 5000}

event: complete
data: {"run_id": 42, "status": "completed"}
```

**Implementation notes:**
- The SSE generator (`stream_progress()`) already forwards any `event` key from the queue — no change needed.
- The worker thread emits download events via `executor.publish_event(run_id, loop, "download_progress", {...})`.
- Download progress comes from `download_data()` pagination — emit after each 1000-candle page.

---

### 3. `DELETE /api/backtest/{run_id}` [EXISTS — NO CHANGES]

**Current state:** Exists. Cancels a running backtest.

**No changes needed.** Frontend already calls `cancelBacktest(runId)`.

---

### 4. `GET /api/backtest/{run_id}` [EXISTS — VERIFY]

**Current state:** Returns `RunDetail` with results + trades via `BacktestService.get_run_detail()`.

**Response — `RunDetail` (complete — matches `_build_results_dict()` + `_build_trades_list()`):**
```json
{
  "id": 42,
  "strategy_name": "rsi_no_retest",
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "status": "completed",
  "created_at": "2024-03-20T18:00:00Z",
  "config": {
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "initial_capital": "10000.00",
    "leverage": 10,
    "risk_per_trade_pct": "0.02",
    "params": {"rsi_period": 14}
  },
  "results": {
    "net_profit": "1234.56",
    "net_profit_pct": 12.35,
    "gross_profit": "2500.00",
    "gross_loss": "-1265.44",
    "win_rate": 65.2,
    "profit_factor": 1.85,
    "expectancy": "23.45",
    "max_drawdown_pct": 8.3,
    "max_drawdown_value": "830.00",
    "max_drawdown_duration_days": 12.5,
    "volatility": 12.5,
    "sharpe_ratio": 1.42,
    "sortino_ratio": 1.89,
    "calmar_ratio": 1.49,
    "total_trades": 69,
    "winning_trades": 45,
    "losing_trades": 24,
    "avg_win": "56.78",
    "avg_loss": "-32.10",
    "largest_win": "245.00",
    "largest_loss": "-89.50",
    "max_consecutive_wins": 8,
    "max_consecutive_losses": 4,
    "avg_hold_time_hours": 6.5,
    "exit_reasons": {
      "TP1": 25,
      "TP2": 15,
      "SL": 20,
      "LOCK_PROFIT": 5,
      "DISASTER_SL": 4
    }
  },
  "trades": [
    {
      "id": 1,
      "symbol": "BTC/USDT",
      "side": "LONG",
      "entry_time": "2024-01-15T08:00:00",
      "exit_time": "2024-01-15T14:00:00",
      "hold_time_hours": 6.0,
      "entry_price": "42150.00",
      "exit_price": "42890.00",
      "stop_loss_price": "41800.00",
      "tp1_price": "42500.00",
      "tp2_price": "43200.00",
      "tp3_price": null,
      "quantity": "0.012",
      "size_usd": "500.00",
      "pnl": "87.65",
      "pnl_pct": 1.75,
      "exit_reason": "TP1"
    }
  ]
}
```

**Note:** All fields above match the actual `_build_results_dict()` and `_build_trades_list()` output in `service.py:334-387`. The frontend `mapApiToResults()` must handle all of these.

---

### 5. `GET /api/backtest/{run_id}/timeseries` [EXISTS — VERIFY]

**Current state:** Returns compressed equity + drawdown curves via `BacktestService.get_timeseries()`.

**Response — `TimeseriesResponse`:**
```json
{
  "run_id": 42,
  "equity_curve": [
    {"date": "2024-01-01", "balance": "10000.00"},
    {"date": "2024-01-02", "balance": "10045.30"}
  ],
  "drawdown_curve": [
    {"date": "2024-01-01", "drawdown": 0.0},
    {"date": "2024-01-02", "drawdown": -0.5}
  ],
  "monthly_returns": {
    "2024-01": 4.5,
    "2024-02": -1.2
  }
}
```

**Verification needed:** Frontend expects `date` key (not `time`) and `balance` (not `equity`). Check `persistence.py` output format matches.

---

### 6. `GET /api/strategies` [EXISTS — MODIFY]

**Current state:** Returns `[{id, name, description, default_config}]` via `app/api/routes/strategies.py`.

**Changes for Phase 1 — add `param_schema`:**

The schema is generated via `STRATEGY_MAP[name].CONFIG_CLASS.param_schema()` (see `spec_strategy_schema.md`).

```json
[
  {
    "id": 1,
    "name": "rsi_no_retest",
    "description": "RSI No-Retest Long/Short Strategy",
    "default_config": {
      "rsi_period": 21,
      "rsi_ema_length": 9,
      "nr_tp1_rr": 1.0
    },
    "param_schema": {
      "type": "object",
      "properties": {
        "rsi_period": {
          "type": "integer",
          "title": "RSI Period",
          "default": 21,
          "minimum": 2,
          "maximum": 100,
          "description": "RSI calculation period",
          "ui_group": "indicators",
          "ui_order": 1
        }
      },
      "ui_groups": {
        "indicators": {"title": "Indicators", "icon": "sliders", "order": 1},
        "entry": {"title": "Entry Conditions", "icon": "activity", "order": 2},
        "exit_sl": {"title": "Stop Loss", "icon": "shield", "order": 3},
        "exit_tp": {"title": "Take Profit", "icon": "target", "order": 4},
        "management": {"title": "Trade Management", "icon": "settings", "order": 5}
      }
    }
  }
]
```

**Implementation:**
```python
# app/api/routes/strategies.py
from app.trading.strategy.loader import STRATEGY_MAP

@router.get("/api/strategies")
def list_strategies(db: Session = Depends(get_db)):
    strategies = db.query(Strategy).all()
    results = []
    for s in strategies:
        strategy_cls = STRATEGY_MAP.get(s.name)
        config_cls = getattr(strategy_cls, "CONFIG_CLASS", None) if strategy_cls else None
        schema = config_cls.param_schema() if config_cls and hasattr(config_cls, "param_schema") else {}
        results.append(StrategyInfo(
            id=s.id,
            name=s.name,
            description=s.description or "",
            default_config=s.default_config or {},
            param_schema=schema,
        ))
    return results
```

**Pydantic schema change:**
```python
# app/api/schemas.py — add param_schema field
class StrategyInfo(BaseModel):
    id: int
    name: str
    description: str | None
    default_config: dict[str, Any]
    param_schema: dict[str, Any] = {}  # ← NEW
```

---

### 7. `GET /api/data/status` [EXISTS — NO CHANGES]

**Current state:** Returns file existence + date range.

**No changes needed.** Frontend `checkDataStatus()` already uses this correctly.

---

### 8. `POST /api/data/download` + `GET /api/data/download/{job_id}/progress` [EXISTS — NO CHANGES]

**Current state:** Standalone download endpoints.

**Phase 1 note:** These become secondary — the primary flow is inline download during backtest. These endpoints remain for the DataPrepModal manual download UX.

---

### 9. `GET /api/history` [EXISTS — NO CHANGES]

**Current state:** Returns paginated `HistoryResponse`.

**No changes needed for Phase 1.** Frontend `historyStore.fetchRuns()` already maps correctly.

---

### 10. `DELETE /api/history/{run_id}` [EXISTS — NO CHANGES]

**Current state:** Cascade deletes run + related rows.

**No changes needed.**

---

## New Endpoints

### 11. `POST /api/backtest/batch` (Phase 2)

**Purpose:** Single API call to run N symbols independently (batch mode).

**Request:**
```json
{
  "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
  "timeframe": "1h",
  "strategy": "rsi_no_retest",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "initial_capital": "10000.00",
  "leverage": 10,
  "risk_per_trade_pct": "0.02",
  "params": {}
}
```

**Response — 201:**
```json
{
  "batch_id": 100,
  "run_ids": [101, 102, 103],
  "status": "running"
}
```

**SSE:** `GET /api/backtest/batch/{batch_id}/progress`
- Emits per-symbol progress: `{"pct": 45, "symbol": "BTC/USDT", "phase": "backtest"}`
- Emits combined progress: `{"pct": 33, "completed": 1, "total": 3}`

---

### 12. Preset CRUD Endpoints (Phase 2)

```
GET    /api/presets?strategy=rsi_no_retest     → [{id, name, strategy, config, created_at}]
POST   /api/presets                             → {id, name, ...}
PUT    /api/presets/{id}                        → {id, name, ...}
DELETE /api/presets/{id}                         → 204
```

**Preset schema:**
```json
{
  "id": 1,
  "name": "BTC Aggressive",
  "strategy": "rsi_no_retest",
  "config": {
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "leverage": 20,
    "params": {"rsi_period": 14, "nr_tp1_rr": 2.0}
  },
  "created_at": "2024-03-20T18:00:00Z"
}
```

---

### 13. Concurrency Settings (Phase 4)

```
GET /api/settings/concurrency  → {"max_workers": 2}
PUT /api/settings/concurrency  → body: {"max_workers": 4} → 200 or 409
```

**Implementation:**
- `GET` reads the current `max_workers` value.
- `PUT` **rejects with 409 Conflict if any jobs are currently running.** Otherwise, rebuilds the `ThreadPoolExecutor` with the new `max_workers` value.

```python
@router.put("/api/settings/concurrency")
def update_concurrency(body: ConcurrencyUpdate):
    if executor.any_jobs_running():
        raise HTTPException(409, "Cannot change concurrency while backtests are running. "
                           "Wait for all runs to complete, then retry.")
    executor.rebuild(body.max_workers)
    return {"max_workers": body.max_workers}
```

---

## SSE Client Contract

The frontend `apiSSE()` in `client.ts` already listens for these named events:
```typescript
["progress", "complete", "error", "download_progress", "download_complete"]
```

**Phase 2 addition — batch events:**
```typescript
["batch_progress", "batch_symbol_complete", "batch_complete"]
```

These should be added to the `apiSSE()` event listener list.

---

## Error Codes

| Code | HTTP Status | When |
|------|-------------|------|
| `DATA_MISSING` | 400 | CSV file not found AND inline download disabled |
| `DATA_DOWNLOAD_FAILED` | 500 | Binance API unreachable during inline download |
| `STRATEGY_UNKNOWN` | 400 | Strategy name not in STRATEGY_MAP |
| `INVALID_PARAMS` | 422 | Param validation failed server-side |
| `RUN_NOT_FOUND` | 404 | run_id doesn't exist |
| `RUN_ALREADY_COMPLETE` | 409 | Trying to cancel already-finished run |
| `CONCURRENCY_LIMIT` | 429 | Max concurrent backtests reached |
| `CONCURRENCY_BUSY` | 409 | Cannot change max_workers while jobs running |

---

## CORS & Base URL

- Backend runs on `http://localhost:8000`
- Frontend uses `VITE_API_URL` env var, defaults to `http://localhost:8000`
- CORS already configured in FastAPI (verify `allow_origins=["*"]` for dev)
