# Backtest Engine Specification

> Single backtest flow, batch mode, engine internals, data management.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  React Frontend (Zustand stores)                                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │backtest  │ │results   │ │history   │ │gridSearch│ ...        │
│  │Store     │ │Store     │ │Store     │ │Store     │            │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘           │
│       │             │            │             │                 │
│  ┌────┴─────────────┴────────────┴─────────────┴──────┐         │
│  │  API Client (REST + SSE)                           │         │
│  └────────────────────┬───────────────────────────────┘         │
└───────────────────────┼─────────────────────────────────────────┘
                        │ HTTP / SSE
┌───────────────────────┼─────────────────────────────────────────┐
│  FastAPI Backend       │                                         │
│  ┌─────────────────────┴──────────────────────────────┐         │
│  │  Routes: /backtest, /history, /data, /strategies   │         │
│  │          /grid-search, /walk-forward, /sensitivity │         │
│  └────────────────────┬───────────────────────────────┘         │
│                       │                                          │
│  ┌────────────────────┴───────────────────────────────┐         │
│  │  Executor (ProcessPoolExecutor, SSE queues)        │         │
│  └────────────────────┬───────────────────────────────┘         │
│                       │                                          │
│  ┌────────────────────┴───────────────────────────────┐         │
│  │  BacktestEngine (MockExchange, Strategy, Portfolio)│         │
│  └────────────────────┬───────────────────────────────┘         │
│                       │                                          │
│  ┌────────────────────┴───────────────────────────────┐         │
│  │  SQLite DB (runs, configs, results, trades, etc.)  │         │
│  └────────────────────────────────────────────────────┘         │
└──────────────────────────────────────────────────────────────────┘
```

## Single Backtest Flow

### Complete Data Flow

```
User clicks "Run Backtest"
        │
        ▼
backtestStore.runBacktest()
  1. checkDataStatus(symbol, timeframe)     ← auto-detect missing data
     └── if missing/outdated → show DataPrepModal (prompt user)
  2. startBacktest(BacktestRequest)          ← POST /api/backtest/run
        │
        ▼
Backend:
  1. Validate request + check CSV exists
  2. Create Run row (status="running") + RunConfig row
  3. Build engine config via config_builder
  4. Create asyncio.Queue for SSE progress
  5. Submit BacktestEngine.run() to ProcessPoolExecutor
  6. Return { run_id, status: "running" }
        │
        ▼
Frontend opens SSE: GET /api/backtest/{run_id}/progress
        │
        ├── "progress" events → update runProgress (0-100%)
        ├── "complete" event  → fetch results
        └── "error" event     → show toast + mark failed
        │
        ▼
On complete:
  1. getRunDetail(run_id)     → scalar metrics + trades
  2. getTimeseries(run_id)    → equity curve, drawdown (lazy, decompressed from zlib BLOB)
  3. mapApiToResults()        → merge into resultsStore
  4. Render ResultsDashboard
```

### SSE Thread-to-Async Bridge

```python
# Worker process → multiprocessing.Queue → Main process → asyncio.Queue → SSE

# In worker process:
mp_queue.put({"event": "progress", "pct": 42, "candle": 3710, "total": 8832})

# In main process (background thread polling mp_queue):
while True:
    msg = mp_queue.get(timeout=1)
    loop.call_soon_threadsafe(async_queue.put_nowait, msg)

# In SSE endpoint:
async def _generate():
    while True:
        event = await asyncio.wait_for(async_queue.get(), timeout=300)
        yield f"event: {event.pop('event')}\ndata: {json.dumps(event)}\n\n"
```

### Crash Recovery

On server startup, run a cleanup sweep:
- Query all rows in `runs` where `status = 'running'`
- Set `status = 'failed'`, `completed_at = NOW()`
- Add note: `"Server restart — run interrupted"`

## Batch Mode (Multi-Symbol)

### Unified Simulation Engine

Batch mode runs a **single engine instance** that simulates portfolio management across all symbols simultaneously. This is NOT N independent backtests.

### Capital Allocation

- **Risk-based sizing**: Each trade risks a fixed portion of current account equity (default 2%)
- **Position size** = `(equity × risk_pct) / sl_distance / price`
- **Max exposure cap**: Total open position value cannot exceed `equity × max_position_pct`
- **Rejection**: If a new trade would exceed the cap, it is **rejected** (not queued)
- Symbols share one capital pool (no individual allocation)

### Multi-Symbol Data Synchronization

1. **Intersection only**: Simulate only the date range where ALL symbols have data
2. **Gap detection**:
   - Small gaps (< 5 candles): Forward-fill with last known values + warn
   - Large gaps (>= 5 candles): Reject and show error listing the gap
3. **Warn user**: Display summary of any date range trimming or gap fills

### Simulation Loop

```python
for timestamp in aligned_timestamps:
    for symbol in symbols:
        candle = candles[symbol][timestamp]
        mock_exchange.update_candle(symbol, candle)    # check fills
        action = strategy.analyze(symbol, df, position, context)

        if action is OpenPosition:
            current_exposure = sum(open_position_sizes)
            new_size = calculate_risk_based_size(equity, risk_pct, sl_distance)
            if current_exposure + new_size > equity * max_position_pct:
                reject_trade(symbol, reason="max_exposure_exceeded")
                continue
            portfolio.on_signal(action_to_signal(action))
```

### Benchmark

- **Default**: Buy-and-hold BTC with same initial capital
- **User can change** the benchmark symbol
- Benchmark equity curve: `capital × (price[t] / price[0])`

### Batch Results

- **Portfolio aggregate**: Total PnL, Sharpe, max drawdown, avg correlation
- **Per-symbol breakdown**: Net PnL, win rate, Sharpe per symbol
- **Correlation matrix**: Pairwise return correlation between symbols
- **Portfolio equity curve** vs benchmark equity curve

## Data Management

### Auto-Detect & Prompt

Before any backtest:
1. `GET /api/data/status?symbol=X&timeframe=Y`
2. Backend checks CSV exists and covers requested date range
3. If missing → show `DataPrepModal`
4. User confirms download → proceed after download completes

### Incremental Downloads

```
Existing:  |---Jan---Feb---Mar---|
Requested: |---Jan---Feb---Mar---Apr---May---Jun---|
Download:                        |---Apr---May---Jun---|
Result:    |---Jan---Feb---Mar---Apr---May---Jun---|
```

1. Read existing CSV → get first and last timestamps
2. Download only the missing portion from Binance API
3. Append to existing CSV (maintain chronological order)
4. Validate: no duplicate timestamps, no gaps > 1 candle interval

### Gap Handling

- **Small gaps (< 5 candles)**: Forward-fill, log warning
- **Large gaps (>= 5 candles)**: Reject, show error with gap details

## Performance Optimizations

### Why No External Engine

The strategy's stateful context (ContextSnapshot with meta dict, 2-candle soft SL pattern, partial TP allocation tracking) is fundamentally incompatible with vectorized frameworks (vectorbt, Backtrader, Zipline).

### Three Targeted Optimizations

#### 1. ProcessPoolExecutor (8-12x speedup for grid search)

Replace `ThreadPoolExecutor` with `ProcessPoolExecutor` to bypass the GIL. Requires `multiprocessing.Queue` → polling thread → `asyncio.Queue` bridge for SSE.

#### 2. float64 in MockExchange (20-40% per run)

Replace `Decimal` with `float64` in backtest mode. `use_float=True` flag on `MockExchange.__init__()`.

#### 3. Fixed-Size Tail Window (10-25% per run)

```python
# Before (O(n) growing slice):
df_slice = self.df.iloc[:i+1]

# After (fixed-size window):
window_size = max(lookback + 10, 40)
start = max(0, i + 1 - window_size)
df_slice = self.df.iloc[start:i+1]
```

### Combined Impact

| Scenario | Before | After |
|----------|--------|-------|
| Single run (8,832 candles) | 2-4s | 1-2s |
| Grid search (200 params, 8 cores) | ~600s | ~30-60s |

## Trade Detail Chart

### Endpoint

```
GET /api/trades/{trade_id}/chart
```

Returns OHLCV candles (50 before entry to 10 after exit), indicator arrays, and trade metadata.

### Frontend: Lightweight Charts v5

```
┌─────────────────────────────────────────────┐
│  Candlestick + EMA overlay + Pine overlays  │
│  ▲ Entry marker   ▼ Exit marker             │
│  --- TP1/TP2 lines (green dashed)           │
│  --- SL line (red dashed)                   │
├─────────────────────────────────────────────┤
│  RSI (14) oscillator pane                    │
│  --- 70 overbought / 30 oversold            │
├─────────────────────────────────────────────┤
│  [Pine oscillator panes, if toggled on]     │
└─────────────────────────────────────────────┘
```
