# API Reference

> All REST + SSE endpoints for the backtest UI backend.

---

## Base URL

```
http://localhost:8000/api
```

CORS configured for `localhost:3000` and `localhost:5173`.

---

## Backtest Endpoints

### Start Backtest

```
POST /api/backtest/run
```

**Request Body:**
```json
{
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "strategy": "rsi_no_retest",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "initial_capital": "10000",
  "leverage": 10,
  "risk_per_trade_pct": "0.02",
  "params": { "rsi_period": 21, "ema_fast": 9, ... }
}
```

**Response:** `{ "run_id": 42, "status": "running" }`

**Errors:** 400 if data file missing, 400 if invalid params.

### Stream Progress (SSE)

```
GET /api/backtest/{run_id}/progress
```

**Events:**
```
event: progress
data: { "pct": 42, "candle": 3710, "total": 8832 }

event: complete
data: { "run_id": 42 }

event: error
data: { "message": "Engine crash: invalid RSI period" }
```

Connection timeout: 300s.

### Cancel Backtest

```
DELETE /api/backtest/{run_id}
```

**Response:** `{ "status": "cancelled" }`

### Get Run Detail

```
GET /api/backtest/{run_id}
```

**Response:** Scalar metrics + trades list. Excludes timeseries (use lazy-load endpoint).

### Get Timeseries (Lazy Load)

```
GET /api/backtest/{run_id}/timeseries
```

**Response:** Equity curve, drawdown curve, monthly returns. Decompressed from zlib BLOB.

---

## History Endpoints

### List Runs (Paginated)

```
GET /api/history?page=1&per_page=20&strategy=rsi_no_retest&symbol=BTC/USDT&status=completed
```

**Query Params:** page, per_page, strategy, symbol, status, profitable_only, search

**Response:**
```json
{
  "runs": [...],
  "total_count": 150,
  "total_pages": 8,
  "current_page": 1
}
```

### Delete Run

```
DELETE /api/history/{run_id}
```

Cascades to: RunConfig, RunResult, RunTimeseries, Trades, Tags.

---

## Trade Endpoints

### Trade Detail Chart

```
GET /api/trades/{trade_id}/chart
```

**Response:**
```json
{
  "trade": { "id": 42, "symbol": "BTC/USDT", "side": "LONG", ... },
  "candles": [{ "time": 1710500400, "open": 64850.0, ... }],
  "indicators": {
    "ema_21": [64750.2, ...],
    "rsi_14": [45.2, ...]
  }
}
```

Candle range: 50 candles before entry to 10 candles after exit.

---

## Data Endpoints

### Check Data Status

```
GET /api/data/status?symbol=BTC/USDT&timeframe=1h
```

**Response:**
```json
{
  "available": true,
  "file_path": "app/backtest/data/BTCUSDT_1h.csv",
  "first_date": "2024-01-01",
  "last_date": "2024-12-31",
  "candle_count": 8832
}
```

### Start Download

```
POST /api/data/download
```

**Request Body:**
```json
{
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31"
}
```

**Response:** `{ "job_id": "abc123" }`

### Stream Download Progress (SSE)

```
GET /api/data/download/{job_id}/progress
```

**Events:**
```
event: progress
data: { "pct": 65, "downloaded": 5740, "total": 8832 }

event: complete
data: { "file_path": "app/backtest/data/BTCUSDT_1h.csv" }
```

---

## Strategy Endpoints

### List Strategies

```
GET /api/strategies
```

**Response:**
```json
[
  {
    "id": 1,
    "name": "rsi_no_retest",
    "description": "RSI strategy without retest confirmation",
    "default_config": { "rsi_period": 21, ... }
  }
]
```

---

## Optimization Endpoints (To Implement)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/backtest/batch` | Start batch (multi-symbol) backtest |
| POST | `/api/grid-search` | Start grid search optimization |
| POST | `/api/walk-forward` | Start walk-forward optimization |
| POST | `/api/sensitivity` | Start sensitivity analysis |

See [optimization.md](optimization.md) for request/response details.

---

## Health

```
GET /health
```

**Response:** `{ "status": "ok" }`

---

## Job Executor (`app/api/executor.py`)

- `ThreadPoolExecutor(max_workers=2)` for running backtests
- `_jobs: Dict[int, Future]` for tracking running jobs
- `_progress_queues: Dict[int, asyncio.Queue]` for SSE progress streaming
- `make_progress_callback()` bridges thread → asyncio.Queue via `loop.call_soon_threadsafe`
