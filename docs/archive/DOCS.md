# Backtest UI — Complete Specification

> This document captures all architectural decisions, data flows, and design choices for the backtest UI system. It serves as the single source of truth for implementation.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Navigation & Layout](#2-navigation--layout)
3. [Single Backtest Flow](#3-single-backtest-flow)
4. [Trade Detail Chart](#4-trade-detail-chart)
5. [Batch Mode (Multi-Symbol)](#5-batch-mode-multi-symbol)
6. [Grid Search](#6-grid-search)
7. [Walk-Forward Optimization](#7-walk-forward-optimization)
8. [Sensitivity Analysis](#8-sensitivity-analysis)
9. [Run History & Comparison](#9-run-history--comparison)
10. [Data Management](#10-data-management)
11. [Pine Indicator System](#11-pine-indicator-system)
12. [Export System](#12-export-system)
13. [Themes](#13-themes)
14. [Performance Optimizations](#14-performance-optimizations)
15. [Error Handling](#15-error-handling)
16. [API Reference](#16-api-reference)
17. [Database Schema](#17-database-schema)

---

## 1. System Overview

### Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + TypeScript, Zustand, Tailwind CSS, Radix UI (shadcn/ui) |
| Backend | FastAPI + SQLAlchemy ORM, structlog |
| Database | SQLite (`data/backtest.db`) |
| Streaming | Server-Sent Events (SSE) for real-time progress |
| Charts | TradingView Lightweight Charts v5 (candlestick, equity) + Recharts (bar charts, grids) |
| Build | Vite (frontend), ProcessPoolExecutor (backend parallelism) |

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  React Frontend (Zustand stores)                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │backtest  │ │results   │ │history   │ │gridSearch│ ...    │
│  │Store     │ │Store     │ │Store     │ │Store     │        │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘       │
│       │             │            │             │             │
│  ┌────┴─────────────┴────────────┴─────────────┴──────┐     │
│  │  API Client (REST + SSE)                           │     │
│  └────────────────────┬───────────────────────────────┘     │
└───────────────────────┼─────────────────────────────────────┘
                        │ HTTP / SSE
┌───────────────────────┼─────────────────────────────────────┐
│  FastAPI Backend       │                                     │
│  ┌─────────────────────┴──────────────────────────────┐     │
│  │  Routes: /backtest, /history, /data, /strategies   │     │
│  │          /grid-search, /walk-forward, /sensitivity │     │
│  └────────────────────┬───────────────────────────────┘     │
│                       │                                      │
│  ┌────────────────────┴───────────────────────────────┐     │
│  │  Executor (ProcessPoolExecutor, SSE queues)        │     │
│  └────────────────────┬───────────────────────────────┘     │
│                       │                                      │
│  ┌────────────────────┴───────────────────────────────┐     │
│  │  BacktestEngine (MockExchange, Strategy, Portfolio)│     │
│  └────────────────────┬───────────────────────────────┘     │
│                       │                                      │
│  ┌────────────────────┴───────────────────────────────┐     │
│  │  SQLite DB (runs, configs, results, trades, etc.)  │     │
│  └────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

### Crash Recovery

On server startup, run a cleanup sweep:
- Query all rows in `runs` where `status = 'running'`
- Set `status = 'failed'`, `completed_at = NOW()`
- Add note: `"Server restart — run interrupted"`

This is simple and honest. No checkpoint/resume complexity.

---

## 2. Navigation & Layout

### Mode Switching: Top Tab Bar

Replace the current sidebar mode selector with a **horizontal tab bar** at the top of the main content area.

```
┌──────────────────────────────────────────────────────────┐
│  [Backtest] [Batch] [Grid Search] [Walk-Forward]         │
│  [Sensitivity] [History]                                  │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  Main content area (mode-specific)                        │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

### Sidebar: Shared Config Only

The sidebar always shows the same configuration regardless of mode:
- Symbol selector
- Strategy selector
- Timeframe selector
- Date range (start/end + lookback presets)
- Capital, leverage, risk percent
- Strategy parameters (RSI period, EMA lengths, TP ratios, etc.)
- **Run button** (at bottom)

**Mode-specific configuration** (grid axes, walk-forward windows, sensitivity variation%, batch symbol list) lives in the **main content area**, above the results.

---

## 3. Single Backtest Flow

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

---

## 4. Trade Detail Chart

### Endpoint

```
GET /api/trades/{trade_id}/chart
```

**Response:**
```json
{
  "trade": {
    "id": 42,
    "symbol": "BTC/USDT",
    "side": "LONG",
    "entry_time": "2024-03-15T14:00:00Z",
    "exit_time": "2024-03-15T18:30:00Z",
    "entry_price": "65230.50",
    "exit_price": "65890.20",
    "stop_loss_price": "64800.00",
    "tp1_price": "65600.00",
    "tp2_price": "66100.00",
    "tp3_price": "66800.00",
    "pnl": "659.70",
    "pnl_pct": "3.21",
    "exit_reason": "TP2"
  },
  "candles": [
    { "time": 1710500400, "open": 64850.0, "high": 64920.0, "low": 64780.0, "close": 64900.0, "volume": 1234.5 }
  ],
  "indicators": {
    "ema_21": [64750.2, 64780.5, ...],
    "rsi_14": [45.2, 48.1, ...]
  }
}
```

### Backend Implementation

1. Look up trade by ID → get `run_id`, `entry_time`, `exit_time`, `symbol`
2. Look up run config → get `timeframe`, `strategy_name`, strategy params
3. Locate CSV file: `app/backtest/data/{SYMBOL}_{timeframe}.csv`
4. Slice candles: **50 candles before entry** to **10 candles after exit** (padding for context)
5. Compute all strategy indicators (EMA, RSI, etc.) using the strategy's `Indicators` class
6. Return OHLCV + indicator arrays + trade metadata

### Frontend: Lightweight Charts v5

Why Lightweight Charts:
- **Already in the project** (`package.json` + `EquityUnderwaterChart.tsx`)
- Native candlestick series, series markers (entry/exit arrows), price lines (SL/TP)
- Multi-pane support in v5 (`chart.addPane()` for oscillators like RSI)
- ~50KB gzipped (vs ~150KB+ for ECharts tree-shaken)

**Chart structure:**
```
┌─────────────────────────────────────────────┐
│  Candlestick + EMA overlay + Pine overlays  │
│  ▲ Entry marker   ▼ Exit marker             │
│  --- TP1 line (green dashed)                │
│  --- TP2 line (green dashed)                │
│  --- SL line (red dashed)                   │
├─────────────────────────────────────────────┤
│  RSI (14) oscillator pane                    │
│  --- 70 overbought (red dashed)             │
│  --- 30 oversold (green dashed)             │
├─────────────────────────────────────────────┤
│  [Pine oscillator panes, if toggled on]     │
└─────────────────────────────────────────────┘
```

**Key APIs used:**
- `chart.addSeries(CandlestickSeries, options)` — main price chart
- `createSeriesMarkers(series, [...])` — entry/exit arrows with `belowBar`/`aboveBar`
- `series.createPriceLine({ price, color, title, lineStyle })` — SL/TP horizontal lines
- `chart.addPane({ height })` — separate pane for RSI and other oscillators
- `pane.addSeries(LineSeries, { color })` — indicator lines in panes

---

## 5. Batch Mode (Multi-Symbol)

### Unified Simulation Engine

Batch mode runs a **single engine instance** that simulates portfolio management across all symbols simultaneously. This is NOT N independent backtests.

### Capital Allocation

- **Risk-based sizing**: Each trade risks a fixed portion of current account equity (default 2%)
- **Position size** = `(equity × risk_pct) / sl_distance / price`
- **Max exposure cap**: Total open position value cannot exceed `equity × max_position_pct` (configurable)
- **Rejection**: If a new trade would exceed the cap, it is **rejected** (not queued)
- Symbols are **not** allocated individual capital slices — they all share one pool

### Multi-Symbol Data Synchronization

When loading CSVs for multiple symbols:

1. **Intersection only**: Only simulate the date range where ALL symbols have data
2. **Gap detection**: Check for internal gaps within each symbol's data
   - Small gaps (< 5 candles): Forward-fill with last known values + warn
   - Large gaps (>= 5 candles): Reject and show error listing the gap
3. **Warn user**: Display a summary of any date range trimming or gap fills before running

### Simulation Loop

```python
# Pseudo-code for unified batch engine
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

### Backend Endpoint

```
POST /api/backtest/batch
{
  "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
  "timeframe": "1h",
  "strategy": "rsi_no_retest",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "initial_capital": 10000,
  "leverage": 10,
  "risk_per_trade_pct": 0.02,
  "max_position_pct": 0.5,
  "params": { ... }
}
```

### Benchmark

- **Default**: Buy-and-hold BTC with same initial capital
- **User can change** the benchmark symbol via a dropdown in the batch results panel
- Benchmark equity curve is computed as: `capital × (price[t] / price[0])`

### Results

The `batchResultsStore` displays:
- **Portfolio aggregate**: Total PnL, Sharpe, max drawdown, avg correlation
- **Per-symbol breakdown**: Net PnL, win rate, Sharpe per symbol
- **Correlation matrix**: Pairwise return correlation between symbols
- **Portfolio equity curve** vs benchmark equity curve
- **Best/worst symbol** identification

---

## 6. Grid Search

### Concurrency Model

**Configurable parallelism** per request:
- User selects `max_workers` (1-4) in the grid search config panel
- Backend uses `ProcessPoolExecutor(max_workers=N)` for that grid search job
- Each parameter combination runs as a separate process

### Storage: Parent + Child Runs

```
runs table:
  ┌─────────────────────────────────────────────┐
  │ id=100, is_grid_search=true, status=running │  ← Parent run
  │ grid_summary (JSON): heatmap data            │
  └─────────────────────────────────────────────┘
       │
       ├── id=101, grid_search_parent_id=100  ← Child (rsi=10, ema=15)
       ├── id=102, grid_search_parent_id=100  ← Child (rsi=10, ema=20)
       ├── id=103, grid_search_parent_id=100  ← Child (rsi=10, ema=25)
       └── ...
```

- **Parent run**: Tracks overall grid state, has a denormalized `grid_summary` JSON for fast heatmap loading
- **Child runs**: Full individual backtest results, can be drilled into from the heatmap
- **Lazy loading**: Heatmap reads from parent's `grid_summary`. Clicking a cell loads the child run detail

### Backend Endpoint

```
POST /api/grid-search
{
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "strategy": "rsi_no_retest",
  "x_axis": { "param": "rsi_period", "min": 10, "max": 30, "step": 2 },
  "y_axis": { "param": "ema_fast", "min": 10, "max": 30, "step": 2 },
  "max_workers": 4,
  "metric": "sharpe",
  "base_config": { "initial_capital": 10000, "leverage": 10, ... }
}
```

**Response:** `{ "run_id": 100, "total_combinations": 121, "status": "running" }`

### SSE Progress

```
event: progress
data: { "pct": 42, "current": 51, "total": 121, "best_so_far": { "x": 14, "y": 21, "value": 1.85 } }

event: complete
data: { "run_id": 100, "best": { "x_value": 14, "y_value": 21, "metric_value": 1.85 } }
```

### Cancellation: Keep Partial Results

When user cancels a running grid search:
1. Mark parent as `status = 'cancelled'`
2. Attempt to cancel pending futures (unstarted combinations)
3. **Keep all completed child runs** — they have valid data
4. Update parent's `grid_summary` with partial heatmap (empty cells for uncompleted combinations)
5. Frontend shows partial heatmap with empty cells clearly marked (grey/hatched)

---

## 7. Walk-Forward Optimization

### Flow

1. User configures: IS window (days), OOS window (days), step size, param to optimize, param range, metric
2. System computes windows: `total_windows = (total_days - is_window - oos_window) / step_size + 1`
3. For each window:
   a. Run grid of parameter values on IS period → find best param for selected metric
   b. Run single backtest on OOS period with that best param → record OOS return
4. Aggregate results: OOS win rate, avg OOS return, most common param, param stability

### Backend Endpoint

```
POST /api/walk-forward
{
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "strategy": "rsi_no_retest",
  "is_window_days": 90,
  "oos_window_days": 30,
  "step_size_days": 30,
  "param_to_optimize": "rsi_period",
  "param_min": 10, "param_max": 30, "param_step": 2,
  "optimize_metric": "sharpe",
  "max_workers": 4,
  "base_config": { ... }
}
```

### Results & Verdict

**Report only** — user decides whether to apply the best parameter.

Verdict logic:
- **Robust**: param_stability > 0.7 AND oos_win_rate > 60%
- **Marginal**: param_stability > 0.5 OR oos_win_rate > 50%
- **Overfit**: param_stability < 0.5 AND oos_win_rate < 50%

User can click "Apply best param" button to update the sidebar config with the most common parameter value.

### SSE Progress

```
event: progress
data: { "pct": 35, "current_window": 4, "total_windows": 12, "phase": "IS" | "OOS" }

event: complete
data: { "run_id": 200, "verdict": "robust", "most_common_param": 21 }
```

---

## 8. Sensitivity Analysis

### Flow

1. **Always run fresh baseline** (1 backtest with current params)
2. For each of 8 parameters: run 2 backtests (base - variation%, base + variation%)
3. Total: 1 + 16 = **17 backtests**
4. Compare each variation's metric against baseline → compute impact %

### Backend Endpoint

```
POST /api/sensitivity
{
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "strategy": "rsi_no_retest",
  "variation_percent": 20,
  "metric": "sharpe",
  "max_workers": 4,
  "base_config": { ... }
}
```

### Results

Per parameter:
- `low_value`, `base_value`, `high_value` (the param values tested)
- `low_metric`, `base_metric`, `high_metric` (the metric outcomes)
- `low_impact_pct`, `high_impact_pct` (% change from baseline)
- `sensitivity`: "high" (>20% impact), "medium" (10-20%), "low" (<10%)

Auto-generated insights:
- Identify high-sensitivity params (overfitting risk)
- Detect asymmetric impacts (much worse in one direction)
- Flag stable params (safe to keep current value)

### Frontend: Tornado Chart

Horizontal bar chart per parameter, showing the impact range (low..high) centered on the baseline.

---

## 9. Run History & Comparison

### History Page

- Server-side pagination + filtering (strategy, symbol, status, profitable_only, search)
- Failed runs visible with `status='failed'` and error message viewable on click

### Comparison

**Two modes:**

| Mode | Runs | Content |
|---|---|---|
| Detailed comparison | Exactly 2 | Overlay equity curves + metrics diff table + trade overlap timeline |
| Metrics comparison | N (unlimited) | Metrics columns table only (no charts) |

**Detailed comparison view:**
- **Overlay equity curves**: Two equity curves on one Lightweight Chart (different colors)
- **Metrics diff table**: Run A vs Run B vs Delta (absolute and %)
- **Trade overlap timeline**: Horizontal timeline showing when each run had open positions, color-coded by run. Highlights periods where trades overlapped or diverged.

**N-run metrics comparison:**
- Table with one column per selected run
- Rows: net profit, sharpe, max DD, win rate, profit factor, total trades, etc.
- Sortable by any metric
- Available when selecting multiple runs via checkboxes in history

---

## 10. Data Management

### Auto-Detect & Prompt

Before running any backtest, the system checks data availability:

1. Call `GET /api/data/status?symbol=X&timeframe=Y`
2. Backend checks CSV: exists? covers requested date range?
3. If data is **missing or doesn't cover the date range** → show `DataPrepModal`
4. Modal shows: what's available, what's missing, download button
5. User confirms download → proceed to backtest after download completes

### Incremental Downloads

When extending an existing CSV:

1. Read existing CSV → get first and last timestamps
2. Determine missing range(s): before existing start, after existing end, or both
3. Download only the missing portion from Binance API
4. **Append** to existing CSV (maintain chronological order)
5. Validate: no duplicate timestamps, no gaps > 1 candle interval

```
Existing:  |---Jan---Feb---Mar---|
Requested: |---Jan---Feb---Mar---Apr---May---Jun---|
Download:                        |---Apr---May---Jun---|
Result:    |---Jan---Feb---Mar---Apr---May---Jun---|
```

### Gap Handling

- **Small gaps (< 5 candles)**: Forward-fill with last known OHLCV values, log warning
- **Large gaps (>= 5 candles)**: Reject download, show error with gap details
- Always validate after append: check timestamp continuity

---

## 11. Pine Indicator System

### Purpose

The Pine system exists to **draw custom indicators on the trade detail chart**. It does NOT execute Pine strategies.

### Flow

1. **Paste**: User pastes PineScript code (e.g., a Bollinger Bands indicator from TradingView)
2. **Verify**: Parser extracts indicator metadata:
   - Type: `overlay` (drawn on price chart) or `oscillator` (separate pane)
   - Parameters: `{ length: 20, mult: 2.0 }`
   - Output plots: `[{ name: "upper", color: "#4CAF50" }, { name: "lower", color: "#4CAF50" }, { name: "basis", color: "#2196F3" }]`
3. **Save**: Stored in localStorage as a `SavedIndicator`

### Chart Integration

On the trade detail chart, users can toggle **multiple indicators simultaneously**:

- **Overlays** (EMA, Bollinger, etc.): Each output plot becomes a `LineSeries` on the main candlestick pane
- **Oscillators** (RSI, MACD, etc.): Each oscillator gets its own pane via `chart.addPane()`
- Strategy's built-in indicators (EMA21, RSI14) are always shown
- Pine indicators are **additional** — users toggle them on/off via checkboxes

### Indicator Computation

Since the backend computes everything:
1. When user toggles a Pine indicator on the trade detail chart, frontend sends the indicator definition to the backend
2. Backend computes indicator values from the OHLCV data (using the parsed formula/type)
3. Returns computed arrays alongside the existing chart data
4. Frontend renders as additional series on the Lightweight Chart

**Alternative (simpler for v1)**: Compute common indicators (SMA, EMA, RSI, MACD, Bollinger) client-side using a JS TA library (e.g., `technicalindicators`), since the OHLCV data is already available from the chart endpoint. Reserve backend computation for complex/custom indicators.

---

## 12. Export System

### Supported Formats (v1)

| Format | Content |
|---|---|
| **CSV** | Trade list with all columns (entry/exit prices, PnL, exit reason, etc.) |
| **JSON** | Full run config + metrics + trades — reproducible backtest definition |

**PDF is deferred** — low priority, complex to implement well.

### CSV Export

- Export all trades or filtered trades (by exit reason, by tag)
- Columns: trade_id, symbol, side, entry_time, exit_time, entry_price, exit_price, quantity, size_usd, pnl, pnl_pct, exit_reason, hold_time_hours, sl_price, tp1_price, tp2_price, tp3_price
- Include summary row at bottom: total trades, win rate, total PnL, avg PnL

### JSON Export

```json
{
  "export_version": "1.0",
  "exported_at": "2024-12-01T10:00:00Z",
  "config": {
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "strategy": "rsi_no_retest",
    "params": { "rsi_period": 21, "ema_fast": 9, ... },
    "initial_capital": 10000,
    "leverage": 10,
    "risk_per_trade_pct": 0.02,
    "start_date": "2024-01-01",
    "end_date": "2024-12-31"
  },
  "results": {
    "net_profit": "1234.56",
    "sharpe_ratio": 1.85,
    "max_drawdown_pct": 12.3,
    ...
  },
  "trades": [ ... ]
}
```

### Trade Annotations

Users can annotate individual trades with:
- **Notes**: Free-text commentary
- **Tags**: `star`, `review`, `learning`, `idea`, `lucky`, `unlucky`
- Stored in `exportStore` (localStorage)
- Annotations are included in CSV/JSON exports

---

## 13. Themes

### Decision: Hardcoded Only

3 built-in themes, no custom theme creation:
- `cyberpunk-neon`
- `beach-paradise`
- `midnight-ocean`

Themes are stored in the frontend `themeStore` only. The `themes` database table is not used.

Each theme defines CSS custom properties for colors, backgrounds, borders, etc. Applied via `document.documentElement.style.setProperty()`.

---

## 14. Performance Optimizations

### Why No External Engine

The strategy's stateful context (`ContextSnapshot` with meta dict, 2-candle soft SL pattern, partial TP allocation tracking) is **fundamentally incompatible** with vectorized frameworks (vectorbt, Backtrader, Zipline) without a complete rewrite. The stateful logic cannot be expressed as boolean signal arrays.

### Three Targeted Optimizations

#### 1. ProcessPoolExecutor (8-12x speedup for grid search)

Replace `ThreadPoolExecutor` in `executor.py` with `ProcessPoolExecutor` to bypass the GIL.

**The SSE bridge changes:**
- Current: `loop.call_soon_threadsafe(queue.put_nowait, data)` (works across threads)
- New: `multiprocessing.Queue` → polling thread → `asyncio.Queue` → SSE (works across processes)

```python
# executor.py changes
_executor = ProcessPoolExecutor(max_workers=max_workers)  # per-request

# Progress bridge:
mp_queue = multiprocessing.Queue()  # cross-process
# Background thread in main process polls mp_queue
# and forwards to asyncio.Queue via loop.call_soon_threadsafe
```

**Impact**: 200-param grid search on 8-core machine: ~600s → ~60s

#### 2. float64 in MockExchange (20-40% per run)

In backtest mode, replace `Decimal` with `float64` in `MockExchange`:
- `float64` has 15-16 significant digits — sufficient for backtest prices
- Create a `use_float=True` flag on `MockExchange.__init__()`
- Replace `to_decimal()` calls with `float()` casts in `update_candle()`
- Live trading continues to use `Decimal`

#### 3. Fixed-Size Tail Window (10-25% per run)

In `BacktestEventSource.events()`, replace the growing slice:

```python
# Before (O(n) growing slice per candle):
df_slice = self.df.iloc[:i+1]

# After (fixed-size window, strategy only needs last ~40 rows):
window_size = max(lookback + 10, 40)
start = max(0, i + 1 - window_size)
df_slice = self.df.iloc[start:i+1]
```

### Combined Impact

| Single run (8,832 candles) | Before | After |
|---|---|---|
| Time | 2-4s | 1-2s |

| Grid search (200 params, 8 cores) | Before | After |
|---|---|---|
| Time | ~600s | ~30-60s |

---

## 15. Error Handling

### Error Flow

```
Engine crash / bad params / CSV parse error
        │
        ▼
Worker process catches exception
  → publishes SSE "error" event with message
  → marks Run as status="failed" in DB with error message
        │
        ▼
Frontend receives SSE "error"
  → shows toast notification (immediate feedback)
  → sets isRunning = false
        │
        ▼
Failed run appears in History
  → status badge shows "failed" (red)
  → clicking the run shows error message detail
  → user can delete or retry with modified config
```

### Error Categories

| Category | Example | Handling |
|---|---|---|
| Data missing | CSV file not found | Pre-flight check in `runBacktest()`, show DataPrepModal |
| Data invalid | CSV parse error, wrong columns | Backend validation, SSE error event |
| Config invalid | Invalid param combination | Backend validation, HTTP 400 |
| Engine crash | Unhandled exception in strategy | try/catch in worker, SSE error + DB mark |
| Timeout | SSE connection drops after 300s | Frontend reconnects or shows stale warning |

---

## 16. API Reference

### Existing Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/backtest/run` | Start single backtest |
| GET | `/api/backtest/{run_id}/progress` | SSE progress stream |
| DELETE | `/api/backtest/{run_id}` | Cancel running backtest |
| GET | `/api/backtest/{run_id}` | Get run detail (metrics + trades) |
| GET | `/api/backtest/{run_id}/timeseries` | Lazy-load equity/drawdown curves |
| GET | `/api/history` | Paginated run list with filters |
| DELETE | `/api/history/{run_id}` | Delete run (cascade) |
| GET | `/api/data/status` | Check CSV availability |
| POST | `/api/data/download` | Start data download |
| GET | `/api/data/download/{job_id}/progress` | SSE download progress |
| GET | `/api/strategies` | List available strategies |
| GET | `/health` | Health check |

### New Endpoints (To Implement)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/trades/{trade_id}/chart` | Trade detail chart data (OHLCV + indicators) |
| POST | `/api/backtest/batch` | Start batch (multi-symbol) backtest |
| POST | `/api/grid-search` | Start grid search optimization |
| POST | `/api/walk-forward` | Start walk-forward optimization |
| POST | `/api/sensitivity` | Start sensitivity analysis |

---

## 17. Database Schema

See the current generated [database reference](../14_api_reference/database.md)
for the full schema.

### Key Design Principles

- **TEXT for money**: All financial values stored as TEXT, parsed with Python `Decimal`
- **BLOB compression**: Equity/drawdown curves stored as zlib-compressed JSON in `run_timeseries`
- **Cascade deletes**: Deleting a run cascades to config, result, timeseries, trades, tags
- **Grid search parent/child**: `runs.grid_search_parent_id` links child runs to parent
- **Lazy loading**: Heavy data (timeseries) in separate table, loaded only when needed

### New Fields Needed

**`runs` table additions:**
- `grid_summary` (TEXT, JSON) — denormalized heatmap data for grid search parents
- `error_message` (TEXT) — error detail for failed runs

**`run_configs` table additions:**
- `max_workers` (INTEGER) — parallelism level for quant jobs
- `max_position_pct` (TEXT) — max total exposure for batch mode

---

## Appendix: Zustand Stores Overview

| Store | Purpose | Persistence |
|---|---|---|
| `backtestStore` | Config + run orchestration | localStorage (config only) |
| `resultsStore` | Single backtest results | None (loaded from API) |
| `historyStore` | Paginated run history | None (loaded from API) |
| `batchResultsStore` | Multi-symbol portfolio results | localStorage (flag only) |
| `gridSearchStore` | Grid search config + results | None |
| `walkForwardStore` | Walk-forward config + results | None |
| `sensitivityStore` | Sensitivity config + results | None |
| `exportStore` | Export config + trade annotations | localStorage (all) |
| `dataPrepStore` | Data download tracking | None |
| `themeStore` | UI themes (3 hardcoded) | None |
| `pineStore` | Custom indicator library | localStorage (saved indicators) |
