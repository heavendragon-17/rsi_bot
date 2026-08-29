# SSE Event Reference

> All Server-Sent Event types, payloads, and error handling.

---

## Backtest Progress (`GET /api/backtest/{run_id}/progress`)

| Event | Payload | When |
|-------|---------|------|
| `progress` | `{ pct: number, candle: number, total: number }` | Every 2% of candles processed |
| `complete` | `{ run_id: string }` | Backtest finished successfully |
| `error` | `{ message: string }` | Backtest failed |

**Client behavior**: Close SSE connection on `complete` or `error`. Then fetch results via `GET /api/backtest/{run_id}`.

## Data Download Progress (`GET /api/data/download/{job_id}/progress`)

| Event | Payload | When |
|-------|---------|------|
| `progress` | `{ pct: number }` | Download progress |
| `complete` | `{ pct: 100 }` | Download finished |
| `error` | `{ message: string }` | Download failed |

**Timeout**: 60 seconds per event. If no event within timeout, connection closes.

## BTC Signal Replay Progress (`GET /api/signal-replays/runs/{run_id}/progress`)

| Event | Payload | When |
|-------|---------|------|
| `progress` | `{ pct, phase, candle, total }` | Market-data load, signal detection, forward-metric preparation, persistence, and completion |
| `complete` | `{ run_id, status, signal_count, m5_count, m15_count }` | The immutable review dataset is committed |
| `error` | `{ run_id?, message }` | Validation or worker failure, including an interrupted run after restart |

Current phase values are `load`, `signals`, `metrics`, `saving`, and
`complete`. The client closes the stream on a terminal event and reloads the
selected run's signal queue. Refreshing the page can reconnect while the same
API process still owns the executor queue.

## Grid Search Progress (`GET /api/grid-search/{run_id}/progress`)

| Event | Payload | When |
|-------|---------|------|
| `progress` | `{ pct, current, total, best_so_far: { x, y, value } }` | Each combination completed |
| `complete` | `{ run_id, best: { x_value, y_value, metric_value } }` | All combinations done |
| `error` | `{ message }` | Grid search failed |

## Walk-Forward Progress (`GET /api/walk-forward/{run_id}/progress`)

| Event | Payload | When |
|-------|---------|------|
| `progress` | `{ pct, current_window, total_windows, phase: "IS"\|"OOS" }` | Each window phase completed |
| `complete` | `{ run_id, verdict, most_common_param }` | All windows done |

## Thread-to-Async Bridge Pattern

SSE events originate from background threads/processes and must be bridged to async FastAPI:

```
Worker Thread → multiprocessing.Queue → Polling Thread → loop.call_soon_threadsafe() → asyncio.Queue → SSE Endpoint
```

The SSE endpoint reads from `asyncio.Queue` with a timeout. If the queue is empty for 300 seconds (backtest) or 60 seconds (download), the connection is closed.
