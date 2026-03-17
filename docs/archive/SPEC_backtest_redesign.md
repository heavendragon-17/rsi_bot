# Backtest API & UI Redesign — Full Specification

**Date:** 2026-03-12
**Branch:** `fix/backtest-sl-wrong`
**Scope:** Move batch/portfolio aggregation from frontend to backend. Expose three distinct run modes through a single unified API contract. Delete frontend aggregation workaround.

---

## 1. Problem Statement

The current architecture has a fundamental layering violation:

- `run_batch_analysis.py` already performs parallel batch backtesting with proper aggregation in the backend
- `portfolio_engine.py` + `portfolio_event_source.py` already implement true multi-symbol portfolio backtesting with shared capital
- Neither is exposed via the HTTP API
- The UI (`backtestStore.ts`) works around this by firing N separate API calls, streaming N SSE connections in parallel, and running `aggregateBatchResults()` in the browser

**Target architecture:** Backend owns all computation and aggregation. Frontend sends config, receives a run ID, streams one SSE for progress, fetches one result payload.

---

## 2. Mode Definitions

### Mode A — Single
- Run `BacktestEngine` for one symbol
- Same as current behavior
- Capital: `initial_capital` used fully for that symbol

### Mode B — Batch
- Run `BacktestEngine` for N symbols **independently** (parallel workers via `ProcessPoolExecutor`)
- Capital allocation: **user-selectable**
  - `split` — each symbol gets `initial_capital / N`
  - `full` — each symbol gets the full `initial_capital`
- Symbols do NOT interact; no shared exchange state
- Results aggregated server-side into one `BatchResult` payload
- Progress reported as overall completion (e.g., "7/12 symbols done")

### Mode C — Portfolio
- Run `PortfolioEngine` with `PortfolioEventSource` (chronological multiplexing)
- All symbols share **one** `MockExchange` and **one** `PortfolioManager`
- Capital is shared — one symbol's trade affects available balance for others
- Maximum scale: 10–20 symbols (no streaming-from-disk optimization needed)
- Date range overlap: allowed — each symbol runs with whatever data it has in the requested range. `PortfolioEventSource` already handles mismatched start dates via `start_idx`.

---

## 3. API Contract

### 3.1 Unified Request

**Single endpoint for all modes:**

```
POST /api/backtest/run
```

New `BacktestRequest` Pydantic schema (replaces existing):

```python
class BacktestRequest(BaseModel):
    mode: Literal["single", "batch", "portfolio"]
    symbols: list[str]               # single → use symbols[0]
    timeframe: str
    strategy: str
    start_date: str                  # yyyy-MM-dd
    end_date: str
    initial_capital: str = "10000"
    capital_mode: Literal["split", "full"] = "split"   # batch only
    leverage: int = 10
    risk_per_trade_pct: str = "0.02"
    fee_tier: str = "0.001"
    slippage_model: str = "none"
    slippage_pct: str = "0.0"
    params: dict[str, Any] = {}
```

**Response:**

```python
class BacktestStartResponse(BaseModel):
    run_id: int          # For single mode — existing Run row
    batch_run_id: int    # For batch mode — new BatchRun row
    portfolio_run_id: int  # For portfolio mode — new PortfolioRun row
    mode: str
    status: str          # "running"
```

> Only one of `run_id / batch_run_id / portfolio_run_id` will be populated depending on mode.

### 3.2 Progress SSE

All three modes share the same SSE endpoint:

```
GET /api/backtest/{id}/progress?mode=single|batch|portfolio
```

**Single** — existing format:
```json
{"event": "progress", "pct": 42}
{"event": "complete", "run_id": 7, "status": "completed"}
```

**Batch** — adds per-symbol status:
```json
{"event": "progress", "pct": 58, "completed": 7, "total": 12, "symbol": "ETH/USDT", "symbol_status": "completed"}
{"event": "symbol_error", "symbol": "XRP/USDT", "message": "Download failed"}
{"event": "complete", "batch_run_id": 3, "status": "partial", "failed": ["XRP/USDT"]}
```

**Portfolio** — same as single (PortfolioEngine reports 0–100%):
```json
{"event": "progress", "pct": 71}
{"event": "complete", "portfolio_run_id": 5, "status": "completed"}
```

### 3.3 Result Fetch Endpoints

```
GET /api/backtest/{run_id}                         # single — existing RunDetail
GET /api/backtest/batch/{batch_run_id}             # new BatchRunDetail
GET /api/backtest/portfolio/{portfolio_run_id}     # new PortfolioRunDetail

GET /api/backtest/{run_id}/timeseries              # single — unchanged
GET /api/backtest/batch/{batch_run_id}/timeseries  # batch — portfolio equity + per-symbol curves
GET /api/backtest/portfolio/{portfolio_run_id}/timeseries  # portfolio equity curve
```

### 3.4 Cancel

```
DELETE /api/backtest/{id}?mode=single|batch|portfolio
```

- **Single**: existing behavior
- **Batch**: kill all in-flight `ProcessPoolExecutor` workers immediately (`future.cancel()` + `executor.shutdown(wait=False)`)
- **Portfolio**: call `PortfolioEngine.stop()` via event

### 3.5 Auto-Download Behavior

If data is missing for any symbol:
1. Attempt inline download via `download_data()` before starting the engine
2. If download succeeds, proceed
3. If download fails for a symbol:
   - **Single**: return HTTP 400
   - **Batch**: mark that symbol as failed, continue with others (partial result)
   - **Portfolio**: return HTTP 400 (cannot run with any missing symbol since the event stream needs all of them)

---

## 4. Backend Implementation

### 4.1 New API Routes

File: `app/api/routes/backtest.py`

- Extend `POST /api/backtest/run` to dispatch on `body.mode`
- Add `GET /api/backtest/batch/{id}` and `GET /api/backtest/batch/{id}/timeseries`
- Add `GET /api/backtest/portfolio/{id}` and `GET /api/backtest/portfolio/{id}/timeseries`
- Extend `DELETE /api/backtest/{id}` with mode parameter

### 4.2 Batch Execution

Adapted from `run_batch_analysis.py`:

```python
def _run_batch_backtest(batch_run_id, symbols, config, ...):
    with ProcessPoolExecutor(max_workers=min(cpu_count, len(symbols))) as executor:
        futures = {executor.submit(run_single_backtest, sym, ...): sym for sym in symbols}
        for future in as_completed(futures):
            result = future.result()
            # publish per-symbol progress event to SSE queue
            # collect results or errors
    # persist BatchRun + BatchRunResult to DB
    # publish complete event
```

Cancel registers the executor in `exc_mod` so `executor.shutdown(wait=False, cancel_futures=True)` can be called.

### 4.3 Portfolio Execution

Adapted from `run_portfolio_backtest.py`:

```python
def _run_portfolio_backtest(portfolio_run_id, symbols, config, ...):
    dfs = {sym: load_and_prepare_df(sym, ...) for sym in symbols}
    event_source = PortfolioEventSource(dfs, start_idx=220)
    exchange = MockExchange(config)
    engine = PortfolioEngine(event_source, strategy_class, exchange, config, symbols)
    results = engine.run(on_progress=progress_cb)
    # persist PortfolioRun + PortfolioRunResult to DB
```

### 4.4 New Pydantic Schemas

Add to `app/api/schemas.py`:

```python
class BatchSymbolResult(BaseModel):
    symbol: str
    status: Literal["completed", "failed"]
    error: str | None
    net_profit: str | None
    net_profit_pct: float | None
    win_rate: float | None
    profit_factor: float | None
    max_drawdown_pct: float | None
    sharpe_ratio: float | None
    total_trades: int | None
    trades: list[dict[str, Any]] | None

class BatchRunDetail(BaseModel):
    id: int
    mode: Literal["batch"] = "batch"
    strategy_name: str
    timeframe: str
    status: str
    created_at: str
    config: dict[str, Any]
    capital_mode: str            # "split" | "full"
    symbol_count: int
    failed_symbols: list[str]
    aggregate: dict[str, Any]    # total_pnl, portfolio_return, avg_sharpe, total_trades, etc.
    symbols: list[BatchSymbolResult]

class PortfolioRunDetail(BaseModel):
    id: int
    mode: Literal["portfolio"] = "portfolio"
    strategy_name: str
    timeframe: str
    status: str
    created_at: str
    config: dict[str, Any]
    symbols: list[str]
    results: dict[str, Any]      # same shape as single RunResult (shared portfolio metrics)
    trades: list[dict[str, Any]] # all trades with symbol field

class BatchTimeseriesResponse(BaseModel):
    batch_run_id: int
    portfolio_equity_curve: list[dict[str, Any]]   # aggregate equity over time
    per_symbol_equity: dict[str, list[dict]]        # symbol → equity curve
    monthly_returns: dict[str, Any]

class PortfolioTimeseriesResponse(BaseModel):
    portfolio_run_id: int
    equity_curve: list[dict[str, Any]]
    drawdown_curve: list[dict[str, Any]]
    monthly_returns: dict[str, Any]
```

---

## 5. Database Schema

### 5.1 New Tables

```sql
-- Batch runs
CREATE TABLE batch_run (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER REFERENCES strategy(id),
    status      TEXT NOT NULL DEFAULT 'running',   -- running|completed|partial|failed|cancelled
    capital_mode TEXT NOT NULL DEFAULT 'split',    -- split|full
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at  DATETIME,
    completed_at DATETIME
);

CREATE TABLE batch_run_config (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_run_id    INTEGER REFERENCES batch_run(id),
    symbols         TEXT NOT NULL,   -- JSON array
    timeframe       TEXT,
    start_date      DATE,
    end_date        DATE,
    initial_capital TEXT,
    leverage        INTEGER,
    risk_per_trade_pct TEXT,
    params          TEXT             -- JSON
);

CREATE TABLE batch_run_result (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_run_id    INTEGER REFERENCES batch_run(id),
    aggregate_stats TEXT NOT NULL,   -- JSON: total_pnl, portfolio_return, avg_sharpe, etc.
    per_symbol_stats TEXT NOT NULL,  -- JSON: array of BatchSymbolResult
    failed_symbols  TEXT,            -- JSON array
    equity_curve    BLOB,            -- zlib-compressed JSON
    monthly_returns TEXT             -- JSON
);

-- Portfolio runs
CREATE TABLE portfolio_run (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER REFERENCES strategy(id),
    status      TEXT NOT NULL DEFAULT 'running',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at  DATETIME,
    completed_at DATETIME
);

CREATE TABLE portfolio_run_config (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_run_id    INTEGER REFERENCES portfolio_run(id),
    symbols             TEXT NOT NULL,   -- JSON array
    timeframe           TEXT,
    start_date          DATE,
    end_date            DATE,
    initial_capital     TEXT,
    leverage            INTEGER,
    risk_per_trade_pct  TEXT,
    params              TEXT             -- JSON
);

CREATE TABLE portfolio_run_result (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_run_id    INTEGER REFERENCES portfolio_run(id),
    -- same metrics columns as run_result
    net_profit          TEXT,
    net_profit_pct      REAL,
    win_rate            REAL,
    profit_factor       REAL,
    max_drawdown_pct    REAL,
    sharpe_ratio        REAL,
    total_trades        INTEGER,
    exit_reasons        TEXT,    -- JSON
    equity_curve        BLOB,    -- zlib-compressed JSON
    drawdown_curve      BLOB,    -- zlib-compressed JSON
    monthly_returns     TEXT     -- JSON
);

CREATE TABLE portfolio_trade (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_run_id    INTEGER REFERENCES portfolio_run(id),
    -- same columns as trade table + symbol
    symbol              TEXT,
    side                TEXT,
    entry_time          DATETIME,
    exit_time           DATETIME,
    entry_price         TEXT,
    exit_price          TEXT,
    quantity            TEXT,
    pnl                 TEXT,
    pnl_pct             REAL,
    exit_reason         TEXT
);
```

---

## 6. Frontend Implementation

### 6.1 API Layer (`ui/src/api/backtest.ts`)

Replace the current `startBacktest()` signature:

```typescript
export async function startBacktest(params: BacktestRequest): Promise<BacktestStartResponse>

// New result fetchers
export async function getBatchRunDetail(id: number): Promise<BatchRunDetail>
export async function getBatchTimeseries(id: number): Promise<BatchTimeseriesResponse>
export async function getPortfolioRunDetail(id: number): Promise<PortfolioRunDetail>
export async function getPortfolioTimeseries(id: number): Promise<PortfolioTimeseriesResponse>
```

`streamProgress` stays the same — works for all modes since the SSE endpoint is unified.

### 6.2 Store Architecture

Three separate Zustand stores for execution/results:

| Store | Purpose |
|-------|---------|
| `backtestStore.ts` | Config state only (mode, symbols, params, dates). Delegates runBacktest() to mode-specific execution. |
| `singleRunStore.ts` | Single-mode execution + result state |
| `batchRunStore.ts` | Batch-mode execution + result state (replaces batchResultsStore.ts) |
| `portfolioRunStore.ts` | Portfolio-mode execution + result state (new) |

`backtestStore.runBacktest()` inspects `mode` and calls the appropriate store.

#### `backtestStore` changes:
- Remove: `runBacktest`, `cancelBacktest`, `currentRunId`, `runProgress`, `isRunning`
- Add: `activeStore` getter that returns the appropriate execution store based on `mode`
- Add: `capitalMode: "split" | "full"` to persisted config

#### New `batchRunStore`:
```typescript
interface BatchRunState {
  isRunning: boolean
  runProgress: number
  completedSymbols: number
  totalSymbols: number
  symbolStatuses: Record<string, "pending" | "running" | "completed" | "failed">
  currentBatchRunId: number | null
  result: BatchRunDetail | null
  timeseries: BatchTimeseriesResponse | null
  run: (config: BacktestRequest) => Promise<void>
  cancel: () => Promise<void>
}
```

#### New `portfolioRunStore`:
```typescript
interface PortfolioRunState {
  isRunning: boolean
  runProgress: number
  currentPortfolioRunId: number | null
  result: PortfolioRunDetail | null
  timeseries: PortfolioTimeseriesResponse | null
  run: (config: BacktestRequest) => Promise<void>
  cancel: () => Promise<void>
}
```

### 6.3 UI Components

Delete: `ui/src/lib/batch-utils.ts` (aggregation moves to backend)

Delete existing batch workaround components and replace with new ones built against clean backend response shapes:

**New components:**

```
ui/src/components/results/
├── single/
│   ├── SingleResultsDashboard.tsx    (renamed/refactored from ResultsDashboard.tsx)
│   ├── HeroStats.tsx
│   ├── MetricsGrid.tsx
│   ├── TradesTable.tsx
│   ├── EquityUnderwaterChart.tsx
│   └── ExitReasonsChart.tsx
│
├── batch/
│   ├── BatchResultsDashboard.tsx     (new — consumes BatchRunDetail)
│   ├── BatchHeroStats.tsx            (total PnL, portfolio return, avg sharpe)
│   ├── SymbolPerformanceTable.tsx    (per-symbol metrics table)
│   ├── PortfolioEquityChart.tsx      (aggregate equity curve)
│   ├── SymbolEquityChart.tsx         (per-symbol equity overlay)
│   └── FailedSymbolsAlert.tsx        (shows which symbols had errors)
│
└── portfolio/
    ├── PortfolioResultsDashboard.tsx  (new — consumes PortfolioRunDetail)
    ├── PortfolioHeroStats.tsx
    ├── SharedCapitalChart.tsx         (equity curve with shared capital)
    ├── PerSymbolTradesBreakdown.tsx
    └── PortfolioMetricsGrid.tsx
```

**Launchpad (`Launchpad.tsx`) changes:**
- Add `capitalMode` toggle (Split / Full) — visible only when `mode === "batch"`
- `portfolioInput` textarea remains for batch and portfolio modes
- Progress display: for batch, show symbol-by-symbol completion ("7/12 symbols done — ETH/USDT ✓")

### 6.4 History Page (`RunHistory.tsx`)

Add three tabs: **Single | Batch | Portfolio**

Each tab has its own fetch from:
- `GET /api/history` (existing, filtered by `run_type=single`)
- `GET /api/history/batch` (new)
- `GET /api/history/portfolio` (new)

Clicking a row:
- Single → opens `SingleResultsDashboard`
- Batch → opens `BatchResultsDashboard`
- Portfolio → opens `PortfolioResultsDashboard`

### 6.5 TypeScript Types

Add new Pydantic schemas to `app/api/schemas.py`, then regenerate:

```bash
npm run generate-types
```

Do NOT hand-write TypeScript interfaces for the new schemas.

---

## 7. Implementation Order

1. **DB migration** — create new tables (`batch_run`, `portfolio_run`, etc.)
2. **Backend batch endpoint** — `POST /api/backtest/run` dispatches to batch worker, new `GET /api/backtest/batch/{id}` routes
3. **Backend portfolio endpoint** — same pattern for portfolio
4. **Pydantic schemas** — add new request/response models, regenerate TS types
5. **Frontend stores** — `batchRunStore`, `portfolioRunStore`, refactor `backtestStore` to config-only
6. **Frontend API layer** — update `startBacktest()` signature, add new fetchers
7. **UI components** — replace batch components, build portfolio components, update Launchpad progress UI
8. **History page tabs** — add batch/portfolio tabs
9. **Delete dead code** — `lib/batch-utils.ts`, old batch workaround in `backtestStore.runBacktest()`

---

## 8. Out of Scope

- Grid search, walk-forward, sensitivity modes (untouched)
- Pine translator mode (untouched)
- Streaming-from-disk for 50+ symbol portfolios (deferred, 10-20 is max)
- Correlation matrix in batch results (existing component kept if it still renders correctly)
- Short-selling support in portfolio mode

---

## 9. Key Constraints & Invariants

- **`run_batch_analysis.py`** is kept as a CLI tool but its logic (`run_single_backtest`, aggregation) is extracted into a shared module that both the CLI and API use
- **`PortfolioEngine.stop()`** must be called through the executor cancellation path — do not add a new stop mechanism
- **All prices remain Decimal** in the engine; the API serializes to string for JSON transport
- **SSE timeout** stays at 300s per connection — batch runs with 20 symbols against 5000-bar data should complete well within this
- **`backtest-config-v2`** localStorage key: add `capitalMode` to the persisted config in `backtestStore` partialize
