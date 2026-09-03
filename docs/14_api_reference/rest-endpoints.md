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
| `GET` | `/api/signal-replays/availability` | Validate canonical sources and return their aligned replay range |
| `POST` | `/api/signal-replays/runs` | Start a BTC M5/M15/H1/H4 replay job |
| `GET` | `/api/signal-replays/runs` | List recent replay runs |
| `GET` | `/api/signal-replays/runs/{run_id}` | Run provenance, counters, and signal counts |
| `GET` | `/api/signal-replays/runs/{run_id}/progress` | SSE replay progress and terminal status |
| `GET` | `/api/signal-replays/signals` | Paginated signal list with filters |
| `GET` | `/api/signal-replays/signals/{signal_id}` | Full card, structured snapshot, review, and metrics |
| `GET` | `/api/signal-replays/signals/{signal_id}/chart` | Review-gated M5/M15/H1/H4 OHLCV/indicator chart window |
| `GET` | `/api/signal-replays/signals/{signal_id}/forward-metrics` | 1h/4h/12h/24h market observations |
| `PATCH` | `/api/signal-replays/signals/{signal_id}/review` | Save quality, manual outcome, note, and optional TP/SL plan |

### `POST /api/signal-replays/runs`

Body: `{ "start": "YYYY-MM-DD or ISO timestamp", "end": "YYYY-MM-DD or ISO timestamp" }`.
Both properties are optional. When omitted, the API uses the full aligned
intersection returned by `GET /availability`. Naive boundaries are interpreted
as UTC+7; date-only `end` includes the full local day. A supplied range outside
the aligned source coverage is rejected before a run row or worker is created.
The response is `{ run_id, status: "running" }`. Missing or invalid canonical
CSVs fail before a worker is submitted, and a second concurrent signal replay
is rejected.

### `GET /api/signal-replays/availability`

Returns `ready`, `common_start_at`, `common_end_at`, and a `sources` item for
each of `5m`, `15m`, `1h`, and `4h`. Source items include availability, row
count, first/last candle-close time, modification time, and a validation error
when the file cannot be used. The UI derives its all-data and recent-period
presets from this response instead of accepting arbitrary dates.

### `GET /api/signal-replays/signals`

Supported query parameters are `timeframe` (`5m` or `15m`), `replay_run_id`,
`quality`, `human_outcome`, `start`, `end`, `page`, and `limit`. The response
is `{ signals, total, page, pages }`. The UI always supplies
`replay_run_id`, defaults to `quality=UNREVIEWED`, and also exposes explicit
Good, Bad, Uncertain, all-quality, and outcome filters.

### Review and chart gate

`GET /signals/{signal_id}/chart` accepts `timeframe=5m|15m|1h|4h` plus optional
ISO `start` and `end` boundaries. Omitting `timeframe` keeps backward-compatible
signal-timeframe behavior. The payload includes `signal_time` and `anchor_time`;
for non-aligned H1/H4 views, `anchor_time` is the latest native candle close at
or before `signal_time`. Candle rows contain OHLCV, EMA21, EMA200, RSI21,
EMA9(RSI21), WMA45(RSI21), and the anchor marker.

`quality=UNREVIEWED` is the initial state. Until an explicit quality label is
saved, every chart timeframe clamps its requested end to the point-in-time
anchor and returns `future_allowed: false` with a warning. Saving `GOOD`, `BAD`,
or `UNCERTAIN` sets `future_allowed: true`; an omitted chart `end` then returns
up to 2,000 future candles in the requested chart timeframe. Only after quality
review can `WIN`, `LOSS`, or `SKIP` be recorded. `quality` and `human_outcome`
remain independent fields. TP/SL may be saved while quality is still
`UNREVIEWED`; the plan is returned but future candles remain locked and its
result fields are empty until quality is selected.

Forward metrics use the trigger candle close as the baseline. A missing or
shortened CSV returns partial metrics with `complete: false` and a warning
instead of silently presenting a complete result.

The review response always exposes the immutable signal-candle `entry_price`.
The optional `take_profit_price` and `stop_loss_price` fields are saved on the
review row and must be supplied together. Both are validated as positive long
prices relative to the signal entry. The levels may be saved before quality
review. Once a quality label has unlocked future inspection, the API scans
future candles from the signal's native M5 or M15 source and returns `exit_reason`, `exit_at`, `duration_minutes`,
`evaluation_warning`, and `evaluated_at`. `exit_reason` is `TAKE_PROFIT`,
`STOP_LOSS`, `BOTH_SAME_CANDLE`, `OPEN`, or `NO_DATA`. A same-candle TP and SL
touch is not forced into either result because OHLC data cannot prove intrabar
order. This evaluation is not a trade, PnL, 1R, or automatic WIN/LOSS
classification.

---

## Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |

**Response**: `{ status: "ok" }`
