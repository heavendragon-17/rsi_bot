# REST API Endpoints

> All FastAPI REST endpoints for the backtest UI backend.

---

## Base URL

`http://localhost:8000`

## CORS

Allowed origins: `http://localhost:3000`, `http://localhost:5173` (Vite dev server). All methods and headers allowed, credentials enabled.

---

## Backtest (`/api/backtest`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/backtest/run` | Start a backtest |
| `GET` | `/api/backtest/{run_id}/progress` | SSE stream of progress events |
| `DELETE` | `/api/backtest/{run_id}` | Cancel a running backtest |
| `GET` | `/api/backtest/{run_id}` | Run detail (config + metrics + trades) |
| `GET` | `/api/backtest/{run_id}/timeseries` | Equity + drawdown curves (zlib-decompressed) |

### `POST /api/backtest/run`

**Body**: `{ symbol, timeframe, strategy, params, initial_capital, leverage, risk_per_trade_pct, ... }`

**Response**: `{ run_id, status: "running" }`

**Flow**: Validates request → creates Run + RunConfig DB rows → submits to ThreadPoolExecutor → returns immediately.

### `GET /api/backtest/{run_id}/progress` (SSE)

**Events**:
- `progress`: `{ pct, candle, total }`
- `complete`: `{ run_id }`
- `error`: `{ message }`

Client should close connection on `complete` or `error`.

---

## History (`/api/history`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/history` | Paginated run list with filters |
| `DELETE` | `/api/history/{run_id}` | Delete run (cascade) |

### `GET /api/history`

**Query params**: `page` (default 1), `limit` (default 20, max 100), `strategy`, `symbol`, `status`, `profitable_only`, `search`

**Response**: `{ runs: [RunSummary], total, page, pages }`

`RunSummary` includes: id, strategy_name, symbol, timeframe, status, created_at, start/end dates, initial_capital, leverage, net_profit, net_profit_pct, win_rate, profit_factor, max_drawdown_pct, sharpe_ratio, total_trades, tags.

---

## Strategies (`/api/strategies`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/strategies` | List all seeded strategies |

**Response**: `[{ id, name, description, default_config }]`

---

## Data (`/api/data`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/data/status` | Check if CSV exists, return metadata |
| `POST` | `/api/data/download` | Start download job |
| `GET` | `/api/data/download/{job_id}/progress` | SSE stream for download |

### `GET /api/data/status`

**Query params**: `symbol`, `timeframe`

**Response**: `{ symbol, timeframe, available, file_path, candle_count, date_range: { start, end } }`

### `POST /api/data/download`

**Body**: `{ symbol, timeframe, limit }`

**Response**: `{ job_id, status: "downloading" }`

---

## Trades (`/api/trades`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/trades/{trade_id}/chart` | Chart data (OHLCV + indicators + trade metadata) |

Returns 50 candles before entry to 10 after exit, with indicator arrays.

---

## Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |

**Response**: `{ status: "ok" }`
