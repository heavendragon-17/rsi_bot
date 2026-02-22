# SPEC: Backtest UI ↔ Backend Integration

> Connect the React UI (`ui/`) to the Python backtest engine via FastAPI.
> **MVP Scope**: Single-pair backtest + Run history.

---

## CRITICAL RULES — READ BEFORE IMPLEMENTING

These rules exist because every single one was violated in previous attempts.

### Completeness Contract

Each phase has a **checklist** at the end. You MUST run every verification command and confirm the expected output before marking a phase complete. If any check fails, the phase is NOT done.

### Mandatory Removal List

The following mock/placeholder code MUST be **deleted entirely** — not commented out, not wrapped in `if`, not left as dead code. After each removal, run the grep verification to prove it's gone.

| What to delete                                             | File                                                           | Why                                                         |
| ---------------------------------------------------------- | -------------------------------------------------------------- | ----------------------------------------------------------- |
| `generateMockResults()` method (lines 123-247)             | `ui/src/stores/resultsStore.ts`                                | Generates fake random data instead of real backtest results |
| `generateMockResults` in interface (line 73)               | `ui/src/stores/resultsStore.ts`                                | Type definition for the mock method                         |
| `generateMockResults()` call (line 77)                     | `ui/src/components/layout/Sidebar.tsx`                         | Sidebar calls mock after run                                |
| `generateMockResults()` call (line 114)                    | `ui/src/components/data-modal/DataPrepModal.tsx`               | DataPrepModal calls mock after run                          |
| `generateMockResults()` call (line 73)                     | `ui/src/components/layout/MobileSidebarSheet.tsx`              | Mobile sidebar calls mock after run                         |
| `generateMockBatchResults()` calls                         | `Sidebar.tsx`, `DataPrepModal.tsx`, `MobileSidebarSheet.tsx`   | Batch mock data (out of MVP but remove the calls)           |
| `persist` middleware wrapping `resultsStore`               | `ui/src/stores/resultsStore.ts` (lines 77, 249-253)            | Results come from API, not localStorage                     |
| `persist` middleware wrapping `historyStore`               | `ui/src/stores/historyStore.ts` (lines 89, 273-286)            | History comes from API, not localStorage                    |
| `addRun()` local method                                    | `ui/src/stores/historyStore.ts` (lines 113-122)                | Runs are created server-side, not client-side               |
| `getFilteredRuns()` local method                           | `ui/src/stores/historyStore.ts` (lines 205-257)                | Filtering is server-side                                    |
| `getPaginatedRuns()` local method                          | `ui/src/stores/historyStore.ts` (lines 259-265)                | Pagination is server-side                                   |
| `setTimeout(800ms)` placeholder in `runBacktest`           | `ui/src/stores/backtestStore.ts` (lines 102-107)               | Fake delay instead of real API call                         |
| Fake download simulation (`setInterval` + `progress += 5`) | `ui/src/components/data-modal/DataPrepModal.tsx` (lines 53-92) | Simulates download with CSS timer instead of real SSE       |
| `addRun()` calls in `Sidebar.tsx` and `DataPrepModal.tsx`  | `Sidebar.tsx` (lines 83-99), `DataPrepModal.tsx`               | Local history insertion — server handles this now           |

**Grep verifications** (run after Phase 5):

```bash
# All must return 0 results
grep -r "generateMockResults" ui/src/
grep -r "generateMockBatchResults" ui/src/
grep -r "setTimeout.*800" ui/src/stores/
grep -r "progress += 5" ui/src/components/
```

### Type Safety Contract

**Pydantic is the source of truth.** All API response shapes are defined in `app/api/schemas.py`. TypeScript types MUST be auto-generated from Pydantic JSON Schema at build time.

- Add npm script: `"generate-types": "..."` that reads Pydantic's `.schema_json()` output and generates `ui/src/types/api-types.ts`
- `ui/src/types/api-types.ts` is auto-generated — never edit manually
- All store actions that receive API data must use these generated types
- If a field is `TEXT` in the DB (Decimal precision), Pydantic serializes it as `str`, and TypeScript receives `string`. The store's `mapApiToResults()` must `parseFloat()` every monetary string field. List every field explicitly — no `as any`.

### SSE Lifecycle Contract

**The store owns the SSE connection, not components.**

- `backtestStore` creates/destroys `EventSource` instances
- Navigation does NOT kill the SSE connection
- Components read `runProgress`/`isRunning` from store — they never create EventSource
- On `runBacktest()`: store creates SSE, stores cleanup function in closure
- On complete/error/cancel: store calls cleanup, sets `isRunning: false`
- On page unload (`beforeunload`): store calls cleanup

### Config Builder Contract

**One function builds the config dict**, used by both CLI and API:

- Create `app/backtest/config_builder.py` with `build_backtest_config(symbol, timeframe, strategy_name, balance, leverage, risk_pct, params, ...)` → returns the config dict that `BacktestEngine.__init__()` expects
- `app/backtest/backtest.py` (CLI) calls this function
- `app/api/routes/backtest.py` (API) calls this function
- NO duplicate config construction logic anywhere

### Data Validation Contract

**Fail fast at API level.** Before creating a `Run` row or submitting to the executor:

1. Check data file exists: `app/backtest/data/{SYMBOL}_{timeframe}.csv`
2. If not: return HTTP 400 with `{"error": "Data file not found: BTCUSDT_1h.csv. Download data first."}`
3. NO orphaned `Run` rows with `status="failed"` due to missing files

---

## 1. Architecture

```
┌─────────────────────┐     HTTP/SSE      ┌─────────────────────┐
│   React UI (:3000)  │ ←──────────────→  │  FastAPI (:8000)    │
│                     │                    │                     │
│  ui/src/api/        │   POST /run        │  app/api/routes/    │
│    client.ts        │   GET  /progress   │    backtest.py      │
│    backtest.ts      │   GET  /history    │    history.py       │
│    history.ts       │   DELETE /cancel   │    strategies.py    │
│                     │                    │    data.py          │
│  stores/            │                    │                     │
│    backtestStore    │                    │  app/api/executor   │
│    resultsStore     │                    │  (ThreadPoolExecutor│
│    historyStore     │                    │   + SSE queues)     │
└─────────────────────┘                    └────────┬────────────┘
                                                    │
                                           ┌────────▼────────────┐
                                           │  BacktestEngine     │
                                           │  + compute_results()│
                                           │  + on_progress cb   │
                                           └────────┬────────────┘
                                                    │
                                           ┌────────▼────────────┐
                                           │  SQLite             │
                                           │  data/backtest.db   │
                                           └─────────────────────┘
```

### Key Decisions

| Decision             | Choice                                       | Rationale                                                                |
| -------------------- | -------------------------------------------- | ------------------------------------------------------------------------ |
| API location         | `app/api/`                                   | Inside `app/` package, follows existing 3-layer architecture             |
| Frontend API pattern | Thin service layer (`ui/src/api/`)           | Typed fetch wrappers. No React Query (overkill for write-once-read-many) |
| Progress streaming   | SSE (Server-Sent Events)                     | Unidirectional progress. Already in CLAUDE.md                            |
| Concurrency          | `ThreadPoolExecutor(max_workers=2)`          | GIL released during pandas/numpy. Simpler than ProcessPool for MVP       |
| Database             | SQLAlchemy ORM                               | Type-safe, migration-ready. Matches `app/repository/`                    |
| Dev workflow         | Separate processes + CORS                    | Vite `:3000` + FastAPI `:8000`                                           |
| Job cancellation     | `{run_id: Future}` + cancel endpoint         | Prevents orphaned jobs                                                   |
| History storage      | DB only                                      | Single source of truth                                                   |
| Themes               | Frontend only                                | No DB for cosmetic feature                                               |
| Auth                 | None                                         | Single-user local tool                                                   |
| Config construction  | Shared `build_backtest_config()`             | One source of truth for CLI + API                                        |
| Metric computation   | Engine owns it (not Reporter)                | Reporter becomes thin HTML/CSV formatter                                 |
| Stdout               | Replace `print()` with `logging`             | Clean server logs                                                        |
| Type safety          | Pydantic → JSON Schema → TypeScript auto-gen | Zero drift between API and frontend                                      |
| SSE lifecycle        | Store owns EventSource, not components       | Survives navigation                                                      |
| Equity curve format  | Engine returns `[{date, balance}]`           | Ready for DB and chart rendering                                         |

---

## 2. Database Layer

### Location

- `app/repository/backtest/__init__.py`
- `app/repository/backtest/database.py` — engine, SessionLocal, `init_db()`
- `app/repository/backtest/models.py` — ORM models
- `app/repository/backtest/seed.py` — seed strategies
- DB file: `data/backtest.db`

### Models (matching `docs/DATABASE.md`)

MVP tables — skip `comparisons` and `themes`:

```python
class Strategy(Base):
    __tablename__ = "strategies"
    id            INTEGER PK AUTOINCREMENT
    name          TEXT NOT NULL UNIQUE
    description   TEXT
    default_config JSON NOT NULL
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP

class Run(Base):
    __tablename__ = "runs"
    id            INTEGER PK AUTOINCREMENT
    strategy_id   INTEGER FK(strategies.id) NOT NULL
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
    started_at    DATETIME
    completed_at  DATETIME
    status        TEXT DEFAULT 'pending'  -- pending|running|completed|failed|cancelled
    git_hash      TEXT
    version       TEXT
    is_grid_search BOOLEAN DEFAULT FALSE
    grid_search_parent_id INTEGER FK(runs.id)
    grid_search_total     INTEGER
    grid_search_completed INTEGER

class RunConfig(Base):
    __tablename__ = "run_configs"
    id            INTEGER PK AUTOINCREMENT
    run_id        INTEGER FK(runs.id) NOT NULL UNIQUE
    symbol        TEXT NOT NULL
    symbols_list  JSON
    is_batch_mode BOOLEAN DEFAULT FALSE
    timeframe     TEXT NOT NULL
    start_date    DATE NOT NULL
    end_date      DATE NOT NULL
    lookback_value INTEGER
    lookback_unit TEXT
    initial_capital TEXT DEFAULT '10000.00'   -- Decimal
    leverage      INTEGER DEFAULT 10
    risk_per_trade_pct TEXT DEFAULT '0.02'    -- Decimal
    fee_tier      TEXT DEFAULT '0.001'        -- Decimal
    slippage_model TEXT DEFAULT 'none'
    slippage_pct  TEXT DEFAULT '0.0'
    params        JSON NOT NULL

class RunResult(Base):
    __tablename__ = "run_results"
    id            INTEGER PK AUTOINCREMENT
    run_id        INTEGER FK(runs.id) NOT NULL UNIQUE
    net_profit    TEXT
    net_profit_pct REAL
    gross_profit  TEXT
    gross_loss    TEXT
    win_rate      REAL
    profit_factor REAL
    expectancy    TEXT
    max_drawdown_pct REAL
    max_drawdown_value TEXT
    max_drawdown_duration_days REAL
    volatility    REAL
    sharpe_ratio  REAL
    sortino_ratio REAL
    calmar_ratio  REAL
    total_trades  INTEGER
    winning_trades INTEGER
    losing_trades INTEGER
    avg_win       TEXT
    avg_loss      TEXT
    largest_win   TEXT
    largest_loss  TEXT
    max_consecutive_wins INTEGER
    max_consecutive_losses INTEGER
    avg_hold_time_hours REAL
    exit_reasons  JSON

class RunTimeseries(Base):
    __tablename__ = "run_timeseries"
    run_id        INTEGER PK FK(runs.id)
    equity_curve  BLOB      -- zlib(JSON[{date, balance}])
    drawdown_curve BLOB     -- zlib(JSON[{date, drawdown}])
    monthly_returns JSON

class Trade(Base):
    __tablename__ = "trades"
    id            INTEGER PK AUTOINCREMENT
    run_id        INTEGER FK(runs.id) NOT NULL
    symbol        TEXT NOT NULL
    side          TEXT NOT NULL
    entry_time    DATETIME NOT NULL
    exit_time     DATETIME
    hold_time_hours REAL
    entry_price   TEXT NOT NULL
    exit_price    TEXT
    stop_loss_price TEXT
    tp1_price     TEXT
    tp2_price     TEXT
    tp3_price     TEXT
    quantity      TEXT NOT NULL
    size_usd      TEXT NOT NULL
    pnl           TEXT
    pnl_pct       REAL
    exit_reason   TEXT
    note          TEXT

class Tag(Base):
    __tablename__ = "tags"
    id            INTEGER PK AUTOINCREMENT
    run_id        INTEGER FK(runs.id) NOT NULL
    name          TEXT NOT NULL
    color         TEXT
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
    UNIQUE(run_id, name)
```

### Indexes

```sql
idx_runs_strategy     ON runs(strategy_id)
idx_runs_created      ON runs(created_at DESC)
idx_runs_status       ON runs(status)
idx_trades_run        ON trades(run_id)
idx_trades_symbol     ON trades(symbol)
idx_tags_run          ON tags(run_id)
idx_tags_name         ON tags(name)
```

### Database Setup

- SQLite with `PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON`
- `init_db()` calls `Base.metadata.create_all()`
- `seed_strategies()` inserts `rsi_no_retest` with default_config from `docs/DATABASE.md` line 58-77

### Phase 1 Checklist

- [x] `python -c "from app.repository.backtest.database import init_db; init_db()"` completes without error
- [x] `data/backtest.db` exists and contains 7 tables (strategies, runs, run_configs, run_results, run_timeseries, trades, tags)
- [x] `python -c "from app.repository.backtest.database import SessionLocal; from app.repository.backtest.models import Strategy; db=SessionLocal(); print(db.query(Strategy).first().name)"` prints `rsi_no_retest`
- [x] `python -m pytest tests/ -v` — all previously passing tests still pass

---

## 3. BacktestEngine Changes

### Move metric computation INTO the engine

The engine gains a `compute_results()` method that calls the computation logic directly. `BacktestReporter` becomes a thin HTML/CSV formatter that receives the results dict.

### File: `app/backtest/engine.py`

**Replace `print()` with `logging`:**

```python
import logging
logger = logging.getLogger(__name__)
```

All `print(...)` → `logger.info(...)`.

**Change `run()` signature:**

```python
def run(self, on_progress=None) -> dict:
```

**Add progress callback in candle loop:**

```python
total_steps = n_rows - warmup_period
last_pct = -1

for i in range(warmup_period, n_rows):
    if on_progress and total_steps > 0:
        pct = int((i - warmup_period) / total_steps * 100)
        if pct != last_pct and pct % 2 == 0:
            on_progress({"pct": pct, "candle": i - warmup_period, "total": total_steps})
            last_pct = pct
    # ... existing candle processing (lines 59-99 unchanged) ...
```

**Add `compute_results()` method to `BacktestEngine`:**

Move the computation logic from `BacktestReporter._build_round_trips`, `_calculate_metrics`, `_calculate_drawdown`, `_calculate_risk_metrics`, `_calculate_monthly_returns` into a new method on `BacktestEngine`. This method:

1. Builds round trips from `self.exchange.trade_history`
2. Computes all metrics, drawdown, risk metrics, monthly returns
3. Builds date-annotated equity curve: `[{"date": "2024-01-15", "balance": "10250.50"}, ...]` by pairing each equity point with the corresponding trade's `exit_time`
4. Returns a complete results dict

**Return results at end of `run()`:**

```python
self._close_open_positions()

if on_progress:
    on_progress({"pct": 100, "candle": total_steps, "total": total_steps})

return self.compute_results()
```

**`compute_results()` returns:**

```python
{
    "metrics": {
        "total_trades": int,
        "win_count": int,
        "loss_count": int,
        "win_rate": float,          # 0-100
        "total_pnl": float,
        "avg_pnl": float,
        "avg_win": float,
        "avg_loss": float,          # negative
        "largest_win": float,
        "largest_loss": float,      # negative
        "profit_factor": float,
        "risk_reward": float,
        "expectancy": float,
        "avg_hold_hours": float,
        "tp1_count": int,
        "tp2_count": int,
        "tp3_count": int,
        "sl_count": int,
        "exit_reason_counts": {"TP1": 5, "SL": 3, ...},
        "max_consec_wins": int,
        "max_consec_losses": int,
        "gross_profit": float,
        "gross_loss": float,        # positive number
    },
    "risk_metrics": {
        "sharpe_ratio": float,
        "sortino_ratio": float,
        "calmar_ratio": float,
        "volatility": float,
        "var_95": float,
    },
    "drawdown": {
        "max_drawdown_pct": float,
        "max_drawdown_value": float,
        "max_dd_duration": int,
        "avg_drawdown_pct": float,
    },
    "monthly_returns": {
        "2024-01": {"pnl": float, "pnl_pct": float, "trades": int},
    },
    "equity_curve": [
        {"date": "2024-01-15T14:00:00", "balance": 10250.50},
    ],
    "drawdown_curve": [
        {"date": "2024-01-20T10:00:00", "drawdown": 2.5},
    ],
    "round_trips": [
        {
            "entry_time": str, "exit_time": str,
            "symbol": str, "entry_price": float, "exit_price": float,
            "avg_exit_price": float, "amount": float,
            "margin": float, "notional": float, "leverage": int,
            "pnl": float, "pnl_pct": float,
            "hold_duration_hours": float,
            "exit_reason": str,
            "hit_tp1": bool, "hit_tp2": bool, "hit_tp3": bool, "hit_sl": bool,
        },
    ],
    "initial_balance": float,
    "final_balance": float,
    "net_profit": float,
    "net_profit_pct": float,
}
```

### File: `app/backtest/reporting.py`

**Reporter becomes a thin formatter.** It receives a results dict and formats HTML/CSV:

```python
class BacktestReporter:
    def __init__(self, results: dict, symbol: str, timeframe: str, strategy_name: str):
        self.results = results
        # ... store for formatting

    def generate_report(self, output_dir: str) -> str:
        # Uses self.results to build HTML + CSV
        # No computation — just formatting
```

### File: `app/backtest/backtest.py`

Update CLI caller to use new signatures:

```python
engine = BacktestEngine(data_path, strategy_class, config)
results = engine.run()

reporter = BacktestReporter(results, symbol=symbol, timeframe=timeframe, strategy_name=strategy_name)
reporter.generate_report(output_dir=args.output)
```

### File: `app/backtest/config_builder.py` (NEW)

```python
def build_backtest_config(
    symbol: str,
    timeframe: str,
    strategy_name: str,
    initial_balance: float = 10000.0,
    leverage: int = 10,
    risk_per_trade_pct: float = 0.02,
    params: dict = None,
    base_config_path: str = "config.yaml",
) -> dict:
    """
    Build the config dict that BacktestEngine expects.
    Single source of truth — used by BOTH CLI and API.
    """
    # Load base config from config.yaml
    # Override with provided params
    # Return complete config dict
```

### Phase 2 Checklist

- [x] `python app/backtest/backtest.py --data app/backtest/data/BTCUSDT_5m.csv --balance 10000` produces HTML report and CSV (backward compat)
- [x] `python -c "from app.backtest.engine import BacktestEngine; ..."` — engine.run() returns a dict with all keys listed above
- [x] `python -c "from app.backtest.config_builder import build_backtest_config; c = build_backtest_config('BTC/USDT', '5m', 'rsi_no_retest'); print(c['symbols'])"` prints `['BTC/USDT']`
- [x] `grep -r "print(" app/backtest/engine.py` returns 0 results (all converted to logger)
- [x] Return dict `equity_curve` contains objects with `date` and `balance` keys (not plain floats)
- [x] `python -m pytest tests/ -v` — existing tests updated to assert on return dict structure
- [x] New test: `tests/test_engine_results.py` verifies return dict has all required keys and correct types

---

## 4. FastAPI Server

### Entry Point: `app/api/main.py`

```bash
python -m app.api.main
# → uvicorn on http://localhost:8000, auto-reload
```

CORS: `allow_origins=["http://localhost:3000", "http://localhost:5173"]`

Startup: `init_db()` + `seed_strategies()`

### Pydantic Schemas: `app/api/schemas.py`

All response models defined here. These generate the JSON Schema that TypeScript types are built from.

**Request:**

```python
class BacktestRequest(BaseModel):
    symbol: str
    timeframe: str
    strategy: str
    start_date: str
    end_date: str
    initial_capital: str = "10000.00"  # TEXT/Decimal
    leverage: int = 10
    risk_per_trade_pct: str = "0.02"
    fee_tier: str = "0.001"
    slippage_model: str = "none"
    slippage_pct: str = "0.0"
    params: dict = {}
```

**Responses:**

```python
class BacktestStartResponse(BaseModel):
    run_id: int
    status: str

class RunSummary(BaseModel):
    """For history list — lightweight, no heavy data."""
    id: int
    strategy_name: str
    symbol: str
    timeframe: str
    status: str
    created_at: str
    start_date: str
    end_date: str
    initial_capital: str    # TEXT — frontend must parseFloat()
    leverage: int
    net_profit: str | None  # TEXT — frontend must parseFloat()
    net_profit_pct: float | None
    win_rate: float | None
    profit_factor: float | None
    max_drawdown_pct: float | None
    sharpe_ratio: float | None
    total_trades: int | None
    tags: list[str]

class RunDetail(BaseModel):
    id: int
    strategy_name: str
    symbol: str
    timeframe: str
    status: str
    created_at: str
    config: dict
    results: dict | None    # All RunResult fields
    trades: list[dict] | None

class TimeseriesResponse(BaseModel):
    run_id: int
    equity_curve: list[dict]    # [{date, balance}]
    drawdown_curve: list[dict]  # [{date, drawdown}]
    monthly_returns: dict

class HistoryResponse(BaseModel):
    runs: list[RunSummary]
    total: int
    page: int
    pages: int

class DataStatusResponse(BaseModel):
    symbol: str
    available: bool
    file_path: str | None
    candle_count: int | None
    date_range: dict | None  # {start, end}

class StrategyInfo(BaseModel):
    id: int
    name: str
    description: str | None
    default_config: dict
```

### JSON Schema export script

Add `app/api/export_schema.py`:

```python
"""Export Pydantic schemas as JSON Schema for TypeScript codegen."""
import json
from app.api.schemas import RunSummary, RunDetail, TimeseriesResponse, ...

schemas = {
    "RunSummary": RunSummary.model_json_schema(),
    "RunDetail": RunDetail.model_json_schema(),
    # ... all response models
}
with open("ui/src/types/api-schema.json", "w") as f:
    json.dump(schemas, f, indent=2)
```

Add to `ui/package.json`:

```json
"scripts": {
    "generate-types": "cd .. && python app/api/export_schema.py && cd ui && npx json-schema-to-typescript -i src/types/api-schema.json -o src/types/api-types.ts"
}
```

---

## 5. API Endpoints

### `POST /api/backtest/run` — Start backtest

**Request:** `BacktestRequest` body
**Response:** `201 BacktestStartResponse`

**Flow:**

1. Validate data file exists → 400 if missing (fail fast)
2. Insert `Run` (status="running") + `RunConfig` into DB
3. Build config via `build_backtest_config()`
4. Create `asyncio.Queue` for SSE
5. Submit to `ThreadPoolExecutor`:
   - `BacktestEngine(data_path, strategy_class, config)`
   - `engine.run(on_progress=callback)`
   - callback bridges to async Queue via `loop.call_soon_threadsafe`
6. `done_callback`:
   - Success → store results in DB (`RunResult`, `Trade[]`, `RunTimeseries` w/ zlib), publish `complete`
   - Failure → update `Run.status="failed"`, publish `error`

### `GET /api/backtest/{run_id}/progress` — SSE stream

**Response:** `text/event-stream`

```
event: progress
data: {"pct": 45, "candle": 2500, "total": 5500}

event: complete
data: {"run_id": 42, "status": "completed"}

event: error
data: {"run_id": 42, "message": "Strategy error: ..."}
```

### `DELETE /api/backtest/{run_id}` — Cancel

**Response:** `{"cancelled": true}`
Updates `Run.status = "cancelled"`.

### `GET /api/backtest/{run_id}` — Run detail

**Response:** `RunDetail` (scalar metrics + trades, no timeseries)

### `GET /api/backtest/{run_id}/timeseries` — Lazy-load charts

**Response:** `TimeseriesResponse` (decompress BLOBs)

### `GET /api/history` — List runs

**Query params:** `page`, `limit`, `strategy`, `symbol`, `status`, `profitable_only`, `search`
**Response:** `HistoryResponse`

Uses dashboard query from DATABASE.md: joins `runs` + `run_results` + `strategies`, no BLOBs.

### `DELETE /api/history/{run_id}` — Delete run (cascade)

**Response:** `{"deleted": true}`

### `GET /api/strategies` — List strategies

**Response:** `list[StrategyInfo]`

### `GET /api/data/status` — Check data availability

**Query params:** `symbol`, `timeframe`
**Response:** `DataStatusResponse`

### `POST /api/data/download` — Start download

**Request:** `{"symbol": "BTC/USDT", "timeframe": "1h", "limit": 5000}`
**Response:** `{"job_id": "uuid", "status": "downloading"}`

### `GET /api/data/download/{job_id}/progress` — SSE for download

Same SSE format as backtest progress.

### Phase 3 Checklist

- [x] `python -m app.api.main` starts without error, logs "Uvicorn running on http://0.0.0.0:8000"
- [x] `curl http://localhost:8000/api/strategies` returns JSON array with `rsi_no_retest`
- [x] `curl http://localhost:8000/api/data/status?symbol=BTC/USDT&timeframe=5m` returns `{"available": true, ...}` (assuming CSV exists)
- [x] `curl -X POST http://localhost:8000/api/backtest/run -H "Content-Type: application/json" -d '{"symbol":"BTC/USDT","timeframe":"5m","strategy":"rsi_no_retest","start_date":"2024-01-01","end_date":"2024-12-31"}'` returns `{"run_id": 1, "status": "running"}`
- [x] `curl http://localhost:8000/api/backtest/1/progress` streams SSE events ending in `event: complete`
- [x] `curl http://localhost:8000/api/backtest/1` returns `RunDetail` with real metrics (NOT zeros, NOT hardcoded)
- [x] `curl http://localhost:8000/api/backtest/1/timeseries` returns decompressed equity curve with `date` and `balance` keys
- [x] `curl http://localhost:8000/api/history` returns the run in history list
- [x] `curl -X DELETE http://localhost:8000/api/history/1` deletes it; subsequent GET returns empty list
- [x] `curl -X POST ... -d '{"symbol":"FAKE/COIN",...}'` returns HTTP 400 (fail fast on missing data)
- [x] New test: `tests/test_api.py` tests each endpoint with real engine execution
- [x] `python -m pytest tests/ -v` — all tests pass

---

## 6. Job Executor: `app/api/executor.py`

```python
_executor = ThreadPoolExecutor(max_workers=2)
_jobs: Dict[int, Future] = {}
_progress_queues: Dict[int, asyncio.Queue] = {}

def submit_backtest(run_id, fn, *args) -> Future
def cancel_job(run_id) -> bool
def create_progress_queue(run_id) -> asyncio.Queue
def cleanup_job(run_id)

def make_progress_callback(run_id: int, loop: asyncio.AbstractEventLoop):
    """Thread→async bridge. Pushes progress to SSE queue."""
    def callback(data: dict):
        q = _progress_queues.get(run_id)
        if q:
            loop.call_soon_threadsafe(q.put_nowait, {"event": "progress", **data})
    return callback
```

---

## 7. Frontend API Layer

### `ui/src/api/client.ts`

```typescript
const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T>;
// Throws ApiError on non-2xx

export function apiSSE(
  path: string,
  onMessage: (event: string, data: any) => void,
  onError?: (err: Event) => void
): () => void;
// Returns cleanup function that closes EventSource
```

### `ui/src/api/backtest.ts`

```typescript
export async function startBacktest(
  params: BacktestRequest
): Promise<BacktestStartResponse>;
export function streamProgress(
  runId: number,
  onProgress,
  onComplete,
  onError
): () => void;
export async function cancelBacktest(runId: number): Promise<void>;
export async function getRunDetail(runId: number): Promise<RunDetail>;
export async function getTimeseries(runId: number): Promise<TimeseriesResponse>;
```

### `ui/src/api/history.ts`

```typescript
export async function fetchHistory(filters): Promise<HistoryResponse>;
export async function deleteRun(runId: number): Promise<void>;
```

### `ui/src/api/strategies.ts`

```typescript
export async function fetchStrategies(): Promise<StrategyInfo[]>;
```

### `ui/src/api/data.ts`

```typescript
export async function checkDataStatus(
  symbol: string,
  timeframe: string
): Promise<DataStatusResponse>;
export async function startDownload(
  symbol,
  timeframe,
  limit
): Promise<{ job_id: string }>;
export function streamDownload(jobId, onProgress, onComplete): () => void;
```

### Phase 4 Checklist

- [x] `ui/src/api/client.ts` exports `apiFetch`, `apiSSE`, `ApiError`
- [x] `ui/src/api/backtest.ts` exports all 5 functions listed above
- [x] `ui/src/api/history.ts` exports `fetchHistory`, `deleteRun`
- [x] `ui/src/api/strategies.ts` exports `fetchStrategies`
- [x] `ui/src/api/data.ts` exports `checkDataStatus`, `startDownload`, `streamDownload`
- [x] `ui/src/api/index.ts` re-exports everything
- [x] `npm run generate-types` produces `ui/src/types/api-types.ts` from Pydantic schemas
- [x] All API functions use generated types (not hand-written interfaces)
- [x] `cd ui && npx tsc --noEmit` — zero TypeScript errors

---

## 8. Store Rewiring

### `backtestStore.ts` — Component Contract

**Add state:**

```typescript
runProgress: number; // 0-100, drives RunButton progress bar
currentRunId: number | null; // active backtest run ID
```

**Add action:**

```typescript
cancelBacktest: () => Promise<void>; // Calls API DELETE, resets state
```

**Replace `runBacktest()`** — the store owns the full SSE lifecycle:

```typescript
runBacktest: async () => {
    const state = get();
    set({ isRunning: true, runProgress: 0 });
    try {
        // 1. Fail fast: check data exists
        const dataStatus = await checkDataStatus(state.symbol, state.timeframe);
        if (!dataStatus.available) {
            throw new Error(`No data for ${state.symbol} ${state.timeframe}. Download first.`);
        }
        // 2. Start backtest via API
        const { run_id } = await startBacktest({
            symbol: state.symbol,
            timeframe: state.timeframe,
            strategy: state.strategy,
            start_date: state.startDate?.toISOString().split("T")[0] ?? "",
            end_date: state.endDate?.toISOString().split("T")[0] ?? "",
            initial_capital: state.capital,
            leverage: parseInt(state.leverage),
            risk_per_trade_pct: (parseFloat(state.riskPercent) / 100).toString(),
            params: state.params,
        });
        set({ currentRunId: run_id });
        // 3. SSE progress — store owns the connection
        await new Promise<void>((resolve, reject) => {
            const cleanup = streamProgress(
                run_id,
                (pct) => set({ runProgress: pct }),
                async (data) => {
                    // 4. On complete: fetch real results from API
                    const detail = await getRunDetail(run_id);
                    const timeseries = await getTimeseries(run_id);
                    useResultsStore.getState().setResults(
                        mapApiToResults(detail, timeseries)
                    );
                    cleanup();
                    resolve();
                },
                (msg) => { cleanup(); reject(new Error(msg)); }
            );
        });
    } catch (err) {
        toast.error(err instanceof Error ? err.message : "Backtest failed");
    } finally {
        set({ isRunning: false, runProgress: 0, currentRunId: null });
    }
},
```

**`RunButton.tsx` already reads these fields** — no component changes needed. The button at `ui/src/components/layout/RunButton.tsx` already:

- Shows progress bar driven by `runProgress` (line 26-28)
- Shows cancel button calling `cancelBacktest()` (line 37-39)
- This works because `RunButton` reads from store, and the store now has real values.

### `resultsStore.ts` — Component Contract

**Delete entirely:**

- `generateMockResults()` method (lines 123-247)
- `generateMockResults` in interface (line 73)
- `persist` middleware wrapper (lines 77, 249-253)

**Add `mapApiToResults()` function:**

```typescript
export function mapApiToResults(
  detail: RunDetail,
  timeseries: TimeseriesResponse
): Partial<ResultsState> {
  const r = detail.results;
  if (!r) return { hasResults: false };
  return {
    hasResults: true,
    netProfit: parseFloat(r.net_profit), // STRING → number
    netProfitPct: r.net_profit_pct, // already float
    profitFactor: r.profit_factor,
    maxDrawdownPct: r.max_drawdown_pct,
    maxDrawdownValue: parseFloat(r.max_drawdown_value),
    sharpeRatio: r.sharpe_ratio,
    sortinoRatio: r.sortino_ratio,
    calmarRatio: r.calmar_ratio,
    volatility: r.volatility,
    expectancy: parseFloat(r.expectancy),
    maxConsecWins: r.max_consecutive_wins,
    winRate: r.win_rate,
    winCount: r.winning_trades,
    lossCount: r.losing_trades,
    avgWin: parseFloat(r.avg_win),
    avgLoss: parseFloat(r.avg_loss),
    bestTrade: parseFloat(r.largest_win),
    worstTrade: parseFloat(r.largest_loss),
    exitReasons: r.exit_reasons ?? {},
    // Timeseries (loaded eagerly on complete for MVP)
    equityCurve: timeseries.equity_curve.map((p) => ({
      time: p.date,
      value: typeof p.balance === "string" ? parseFloat(p.balance) : p.balance,
    })),
    underwaterCurve: timeseries.drawdown_curve.map((p) => ({
      time: p.date,
      value: -(typeof p.drawdown === "number"
        ? p.drawdown
        : parseFloat(p.drawdown)),
    })),
    // Map trades
    trades: (detail.trades ?? []).map((t, i) => ({
      id: i + 1,
      entryTime: t.entry_time,
      exitTime: t.exit_time ?? "",
      symbol: t.symbol,
      side: "LONG" as const, // engine only does LONG for now
      entryPrice: parseFloat(t.entry_price),
      exitPrice: parseFloat(t.exit_price ?? "0"),
      size: parseFloat(t.size_usd ?? "0"),
      pnl: parseFloat(t.pnl ?? "0"),
      pnlPct: t.pnl_pct ?? 0,
      exitReason: t.exit_reason as any,
      fees: 0,
    })),
    filteredTrades: [], // will be set by setFilter
  };
}
```

Every `parseFloat()` call is explicit — no silent `NaN` from string fields.

### `historyStore.ts` — Component Contract

**Delete entirely:**

- `persist` middleware wrapper (lines 89, 273-286)
- `addRun()` method (lines 113-122) — server creates runs
- `getFilteredRuns()` method (lines 205-257) — server filters
- `getPaginatedRuns()` method (lines 259-265) — server paginates
- `getTotalPages()` method (lines 267-271) — server calculates
- `clearAllHistory()` method (line 190-192) — not in MVP

**Add API-backed actions:**

```typescript
fetchRuns: async (filters?) => {
    set({ isLoading: true });
    try {
        const { currentPage, itemsPerPage, filters: storeFilters } = get();
        const response = await fetchHistory({
            page: currentPage,
            limit: itemsPerPage,
            strategy: storeFilters.strategy ?? undefined,
            symbol: storeFilters.symbol ?? undefined,
            profitable_only: storeFilters.profitableOnly || undefined,
            date_range: storeFilters.dateRange !== "all" ? storeFilters.dateRange : undefined,
            search: storeFilters.searchQuery || undefined,
            ...filters,
        });
        set({
            runs: response.runs,
            totalPages: response.pages,
            totalCount: response.total,
            isLoading: false,
        });
    } catch (err) {
        set({ isLoading: false });
        toast.error("Failed to load history");
    }
},

deleteRuns: async (ids: number[]) => {
    for (const id of ids) {
        await deleteRun(id);
    }
    get().fetchRuns();
},
```

**Add state:**

```typescript
totalPages: number;
totalCount: number;
```

**Keep as local UI state:** `selectedRunIds`, `compareModalOpen`, `compareRuns`, `restoreModalOpen`, `runToRestore`

### Sidebar.tsx, DataPrepModal.tsx, MobileSidebarSheet.tsx

**Remove all mock orchestration logic.** These components currently:

1. Call `runBacktest()` (placeholder)
2. Then call `generateMockResults()` (fake data)
3. Then call `addRun()` (local history)

After rewiring:

1. Call `runBacktest()` only — the store handles everything (API call → SSE → results → history is server-side)
2. Delete the `generateMockResults()` and `addRun()` calls
3. Delete the fake download simulation in DataPrepModal (lines 53-92)

### Phase 5 Checklist

- [x] `grep -r "generateMockResults" ui/src/` returns 0 results
- [x] `grep -r "generateMockBatchResults" ui/src/` returns 0 results
- [x] `grep -r "setTimeout.*800" ui/src/stores/` returns 0 results
- [x] `grep -r "progress += 5" ui/src/components/` returns 0 results
- [x] `grep -r "addRun(" ui/src/components/` returns 0 results (history is server-side)
- [x] `grep -rn "persist" ui/src/stores/resultsStore.ts` returns 0 results
- [x] `grep -rn "persist" ui/src/stores/historyStore.ts` returns 0 results
- [x] `cd ui && npx tsc --noEmit` — zero TypeScript errors
- [x] Start both servers. Open UI. Click Run with valid data. See REAL progress bar (not CSS animation). See REAL results (numbers match CLI output). See run in History page. Delete it. It's gone.
- [x] Run with missing data symbol → toast error "No data for X. Download first."
- [x] Start backtest → click Cancel → progress stops, status shows cancelled
- [x] Start backtest → navigate away → navigate back → progress bar shows current state (SSE survived navigation)
- [x] Refresh page mid-run → on reload, progress bar is gone (SSE is not persistent across page loads — this is expected)

---

## 9. Error Handling

### Frontend

- Install `sonner` package
- Wrap `<App />` in `<Toaster />`
- Every `catch` block in stores calls `toast.error(message)`
- API layer throws `ApiError` with status and message

### Backend

- FastAPI exception handler returns `{"error": "message"}` for all non-2xx
- Engine exceptions caught in executor done_callback → `Run.status="failed"` + SSE error event
- Data validation before job submission (fail fast)

---

## 10. File Inventory

### Create (22 files)

| File                                  | Purpose                                        |
| ------------------------------------- | ---------------------------------------------- |
| `app/repository/backtest/__init__.py` | Package                                        |
| `app/repository/backtest/database.py` | Engine, SessionLocal, init_db()                |
| `app/repository/backtest/models.py`   | 7 ORM models                                   |
| `app/repository/backtest/seed.py`     | Seed strategies                                |
| `app/backtest/config_builder.py`      | Shared config builder for CLI + API            |
| `app/api/__init__.py`                 | Package                                        |
| `app/api/main.py`                     | FastAPI app                                    |
| `app/api/schemas.py`                  | Pydantic models (source of truth for types)    |
| `app/api/executor.py`                 | ThreadPool + SSE queues                        |
| `app/api/export_schema.py`            | Pydantic → JSON Schema for TS codegen          |
| `app/api/routes/__init__.py`          | Package                                        |
| `app/api/routes/backtest.py`          | Run, progress SSE, cancel, detail, timeseries  |
| `app/api/routes/history.py`           | List, delete                                   |
| `app/api/routes/strategies.py`        | List                                           |
| `app/api/routes/data.py`              | Status, download                               |
| `ui/src/api/client.ts`                | apiFetch, apiSSE, ApiError                     |
| `ui/src/api/backtest.ts`              | 5 functions                                    |
| `ui/src/api/history.ts`               | fetchHistory, deleteRun                        |
| `ui/src/api/strategies.ts`            | fetchStrategies                                |
| `ui/src/api/data.ts`                  | checkDataStatus, startDownload, streamDownload |
| `ui/src/api/index.ts`                 | Barrel export                                  |
| `tests/test_engine_results.py`        | Verify engine.run() return dict                |

### Modify (8 files)

| File                                              | Change                                                         |
| ------------------------------------------------- | -------------------------------------------------------------- |
| `requirements.txt`                                | Add fastapi, uvicorn[standard], pydantic, sse-starlette        |
| `app/backtest/engine.py`                          | Add on_progress, compute_results(), return dict, print→logging |
| `app/backtest/reporting.py`                       | Refactor to receive results dict, formatting only              |
| `app/backtest/backtest.py`                        | Use config_builder, pass results dict to reporter              |
| `ui/src/stores/backtestStore.ts`                  | Real API+SSE, add runProgress/currentRunId/cancelBacktest      |
| `ui/src/stores/resultsStore.ts`                   | Delete mock, add mapApiToResults(), remove persist             |
| `ui/src/stores/historyStore.ts`                   | Delete local logic, add API calls, remove persist              |
| `ui/src/components/layout/Sidebar.tsx`            | Remove mock orchestration (generateMockResults, addRun calls)  |
| `ui/src/components/data-modal/DataPrepModal.tsx`  | Remove fake download sim + mock calls                          |
| `ui/src/components/layout/MobileSidebarSheet.tsx` | Remove mock calls                                              |

---

## 11. Implementation Order

```
Phase 1: Database layer (app/repository/backtest/)
Phase 2: Engine changes (on_progress, compute_results, config_builder, logging)
    ↑ parallel with Phase 1
Phase 3: FastAPI server + all routes
    ↑ depends on Phase 1 + 2
Phase 4: Frontend API layer (ui/src/api/) + type generation
    ↑ can parallel with Phase 3
Phase 5: Store rewiring + mock removal + component cleanup
    ↑ depends on Phase 3 + 4
```

---

## 12. Dev Workflow

```bash
# Terminal 1: API server
python -m app.api.main

# Terminal 2: React dev server
cd ui && npm run dev

# Terminal 3: Tests
python -m pytest tests/ -v
```

---

## 13. Final Acceptance Test

After all phases complete, run this end-to-end sequence:

1. `python -m app.api.main` — server starts
2. `cd ui && npm run dev` — UI starts
3. Open browser → select BTC/USDT, 5m, rsi_no_retest
4. Click "Run Backtest" → progress bar fills with real percentages → results appear with real numbers
5. Verify: net profit, win rate, sharpe ratio are NOT zero and NOT random mock values
6. Verify: equity curve chart renders with real data points
7. Verify: trades table shows real trades with real entry/exit prices
8. Navigate to History → see the run listed
9. Click delete → run disappears
10. Go back to single mode → run another backtest with different params → both results are different (proves no hardcoded data)
11. Start a backtest → click Cancel → verify it stops
12. Change symbol to one without data → click Run → toast error appears
13. `python -m pytest tests/ -v` — all tests pass
