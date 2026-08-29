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

## BTC Signal Review (`/api/signal-replays`)

Signal Review is a separate alert-review dataset. It does not use the normal
backtest `Run`, `RunResult`, or `Trade` models because a raw Telegram alert has
no execution lifecycle. A replay run stores provenance and immutable signal
snapshots; a signal stores the exact rendered Telegram card, structured
indicator fields, latest human review, and objective forward observations.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/signal-replays/runs` | Start a BTC M5/M15/H1/H4 replay job |
| `GET` | `/api/signal-replays/runs` | List recent replay runs |
| `GET` | `/api/signal-replays/runs/{run_id}` | Run provenance, counters, and signal counts |
| `GET` | `/api/signal-replays/runs/{run_id}/progress` | SSE replay progress and terminal status |
| `GET` | `/api/signal-replays/signals` | Paginated signal list with filters |
| `GET` | `/api/signal-replays/signals/{signal_id}` | Full card, structured snapshot, review, and metrics |
| `GET` | `/api/signal-replays/signals/{signal_id}/chart` | Review-gated OHLCV/indicator chart window |
| `GET` | `/api/signal-replays/signals/{signal_id}/forward-metrics` | 1h/4h/12h/24h market observations |
| `PATCH` | `/api/signal-replays/signals/{signal_id}/review` | Save quality, outcome, and note |

### `POST /api/signal-replays/runs`

Body: `{ "start": "YYYY-MM-DD or ISO timestamp", "end": "YYYY-MM-DD or ISO timestamp" }`.
Naive boundaries are interpreted as UTC+7; date-only `end` includes the full
local day. The response is `{ run_id, status: "running" }`. Missing or
invalid canonical CSVs fail before a worker is submitted.

### `GET /api/signal-replays/signals`

Supported query parameters are `timeframe` (`5m` or `15m`), `replay_run_id`,
`quality`, `human_outcome`, `start`, `end`, `page`, and `limit`. The response
is `{ signals, total, page, pages }`. The `quality=GOOD` query is the saved
Good Signals view used by the UI.

### Review and chart gate

`quality=UNREVIEWED` is the initial state. Until an explicit quality label is
saved, the chart endpoint clamps its requested end to the trigger close and
returns `future_allowed: false` with a warning. Saving `GOOD`, `BAD`, or
`UNCERTAIN` sets `future_allowed: true`; only then can `WIN`, `LOSS`, or `SKIP`
be recorded. `quality` and `human_outcome` remain independent fields.

Forward metrics use the trigger candle close as the baseline. A missing or
shortened CSV returns partial metrics with `complete: false` and a warning
instead of silently presenting a complete result.

---

## Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |

**Response**: `{ status: "ok" }`
