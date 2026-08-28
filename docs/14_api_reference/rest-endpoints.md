# REST API Endpoints

> All FastAPI REST endpoints for the backtest UI backend.

---

## Base URL

`http://localhost:8100`

## CORS

By default, the API accepts HTTP(S) origins on any `localhost` or
`127.0.0.1` port, including the UI default `http://localhost:3100`. Set
`API_CORS_ORIGINS` to a comma-separated allowlist in deployed environments.
All methods and headers are allowed and credentials are enabled.

---

## Backtest (`/api/backtest`)

Route files:
- `app/api/routes/backtest_run.py` — run creation and cancellation
- `app/api/routes/backtest_results.py` — run detail, timeseries, history
- `app/api/routes/backtest_stream.py` — SSE progress streaming

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/backtest/run` | Start a backtest (any mode) |
| `GET` | `/api/backtest/{run_id}/progress` | SSE stream of progress events |
| `DELETE` | `/api/backtest/{run_id}` | Cancel a running backtest |
| `GET` | `/api/backtest/{run_id}` | Run detail (config + metrics + trades) |
| `GET` | `/api/backtest/{run_id}/timeseries` | Equity + drawdown curves (zlib-decompressed) |

### `POST /api/backtest/run`

**Mode**: Specified via `BacktestMode` enum:

| Mode | Description |
|------|-------------|
| `single` | Single-symbol backtest against a local CSV via `BacktestEngine` |
| `portfolio` | Multi-symbol chronological portfolio simulation via `portfolio_runner` |
| `batch` | Batch runs across multiple configs/symbols via `batch_runner` |
| `tick_replay` | Tick-by-tick replay through `PaperExchange` via `tick_replay` runner |

**Common body fields**: `timeframe`, `strategy`, `start_date`, `end_date`, `initial_capital`, `leverage`, `risk_per_trade_pct`, `fee_tier`, `slippage_model`, `slippage_pct`, `params`

**Response**: `{ run_id, status: "running" }`

**Flow**: Validates request → `BacktestService` (`app/backtest/service.py`) creates `Run` + `RunConfig` DB rows → dispatches to the appropriate runner → returns immediately.

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
