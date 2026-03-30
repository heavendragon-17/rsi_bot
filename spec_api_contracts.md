# RSI Bot — API Contracts Spec

## Existing Endpoints (Verify & Fix)

### 1. `POST /api/backtest/run`

**Current state:** Exists, accepts `BacktestRequest`, returns `{run_id, status}`.

**Changes needed for Phase 1:**
- Add server-side inline download: if CSV file missing, download before running backtest.
- Emit `download_progress` and `download_complete` SSE events on the progress stream.
- Auto-seed strategy into DB if it exists in `STRATEGY_MAP` but not in `strategies` table.

**Request — `BacktestRequest` (no schema changes needed):**
```json
{
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "strategy": "rsi_no_retest",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "initial_capital": "10000.00",
  "leverage": 10,
  "risk_per_trade_pct": "0.02",
  "params": {
    "rsi_period": 14,
    "rsi_ema_length": 9,
    "nr_tp1_rr": 1.5
  }
}
```

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

---

### 2. `GET /api/backtest/{run_id}/progress` (SSE)

**Current state:** Emits `progress` and `complete` events. Frontend `apiSSE()` already listens for `download_progress` and `download_complete`.

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
- The SSE stream has two phases: download (optional, only if data missing) → backtest.
- The progress callback in `BacktestEngine` already emits `{pct, candle, total}` — just need to wire to SSE.
- Download progress comes from `download_data()` pagination — emit after each 1000-candle page.

---

### 3. `DELETE /api/backtest/{run_id}`

**Current state:** Exists. Cancels a running backtest.

**No changes needed.** Frontend already calls `cancelBacktest(runId)`.

---

### 4. `GET /api/backtest/{run_id}`

**Current state:** Returns `RunDetail` with results + trades.

**Response — `RunDetail`:**
```json
{
  "id": 42,
  "strategy_name": "rsi_no_retest",
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "status": "completed",
  "created_at": "2024-03-20T18:00:00Z",
  "config": {
    "initial_capital": "10000.00",
    "leverage": 10,
    "risk_per_trade_pct": "0.02",
    "params": {"rsi_period": 14}
  },
  "results": {
    "net_profit": "1234.56",
    "net_profit_pct": 12.35,
    "win_rate": 65.2,
    "profit_factor": 1.85,
    "max_drawdown_pct": 8.3,
    "max_drawdown_value": "830.00",
    "sharpe_ratio": 1.42,
    "sortino_ratio": 1.89,
    "calmar_ratio": 1.49,
    "volatility": 12.5,
    "expectancy": "23.45",
    "max_consecutive_wins": 8,
    "winning_trades": 45,
    "losing_trades": 24,
    "total_trades": 69,
    "avg_win": "56.78",
    "avg_loss": "-32.10",
    "largest_win": "245.00",
    "largest_loss": "-89.50",
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
      "entry_time": "2024-01-15T08:00:00",
      "exit_time": "2024-01-15T14:00:00",
      "symbol": "BTC/USDT",
      "side": "LONG",
      "entry_price": "42150.00",
      "exit_price": "42890.00",
      "size_usd": "500.00",
      "pnl": "87.65",
      "pnl_pct": 1.75,
      "exit_reason": "TP1",
      "fee": "0.85"
    }
  ]
}
```

**Verification needed:** Ensure `results` dict includes all fields that `mapApiToResults()` in `resultsStore.ts` expects: `exit_reasons`, `largest_win`, `largest_loss`, `max_consecutive_wins`, `volatility`, `calmar_ratio`, `sortino_ratio`, `expectancy`.

---

### 5. `GET /api/backtest/{run_id}/timeseries`

**Current state:** Returns compressed equity + drawdown curves.

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

### 6. `GET /api/strategies`

**Current state:** Returns `[{id, name, description, default_config}]`.

**Changes for Phase 1 — add `param_schema`:**
```json
[
  {
    "id": 1,
    "name": "rsi_no_retest",
    "description": "RSI No-Retest Long/Short Strategy",
    "default_config": {
      "rsi_period": 21,
      "rsi_ema_length": 9,
      "nr_tp1_rr": 1.5
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
          "ui_group": "indicators"
        },
        "nr_tp1_rr": {
          "type": "number",
          "title": "TP1 Risk-Reward",
          "default": 1.5,
          "minimum": 0.1,
          "maximum": 10.0,
          "ui_step": 0.1,
          "description": "First take-profit level as R multiple",
          "ui_group": "exit"
        }
      },
      "required": ["rsi_period"]
    }
  }
]
```

**See `spec_strategy_schema.md` for JSON Schema generation details.**

---

### 7. `GET /api/data/status`

**Current state:** Returns file existence + date range.

**No changes needed.** Frontend `checkDataStatus()` already uses this correctly.

---

### 8. `POST /api/data/download` + `GET /api/data/download/{job_id}/progress`

**Current state:** Standalone download endpoints.

**Phase 1 change:** These become secondary — the primary flow is inline download during backtest. These endpoints remain for the DataPrepModal manual download UX.

---

### 9. `GET /api/history`

**Current state:** Returns paginated `HistoryResponse`.

**No changes needed for Phase 1.** Frontend `historyStore.fetchRuns()` already maps correctly.

---

### 10. `DELETE /api/history/{run_id}`

**Current state:** Cascade deletes run + related rows.

**No changes needed.**

---

## New Endpoints

### 11. `GET /api/strategies/{name}/schema` (Phase 1)

**Purpose:** Returns only the JSON Schema for a specific strategy's parameters. Useful when user switches strategy in sidebar and needs to rebuild the param form.

**Response:**
```json
{
  "strategy": "rsi_no_retest",
  "param_schema": { /* JSON Schema object */ }
}
```

**Implementation:** Call `strategy_config_class.param_schema()` classmethod.

---

### 12. `POST /api/backtest/batch` (Phase 2)

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

### 13. Preset CRUD Endpoints (Phase 2)

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

### 14. Concurrency Settings (Phase 4)

```
GET /api/settings/concurrency  → {"max_workers": 2}
PUT /api/settings/concurrency  → body: {"max_workers": 4} → 200
```

**Implementation:** Rebuilds `ThreadPoolExecutor` with new `max_workers`.

---

## SSE Client Contract

The frontend `apiSSE()` in `client.ts` already listens for these named events:
```typescript
["progress", "complete", "error", "download_progress", "download_complete"]
```

**Phase 1 addition — batch events (Phase 2):**
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

---

## CORS & Base URL

- Backend runs on `http://localhost:8000`
- Frontend uses `VITE_API_URL` env var, defaults to `http://localhost:8000`
- CORS already configured in FastAPI (verify `allow_origins=["*"]` for dev)
