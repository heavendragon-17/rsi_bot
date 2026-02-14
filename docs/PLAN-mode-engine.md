# Mode-Aware Engine & Quant Tool Architecture

## Goal

Build a **Session-Based Engine Layer** between the UI stores and Python backend that:

1. Auto-creates sessions per backtest run
2. Persists all quant tool results (Grid Search, Walk-Forward, Sensitivity) to SQLite
3. Supports parameter versioning with comparison across versions/sessions
4. Connects UI → local REST API → Python backtest engine → DB
5. Enables auto-run of user-selected quant tools after each backtest

---

## Project Type

**FULL-STACK** (Python backend + React/Vite frontend + SQLite database)

---

## Decisions Register (User-Approved)

| #   | Decision        | Choice                                                      |
| --- | --------------- | ----------------------------------------------------------- |
| 1   | Database        | **SQLite** with sessions + version chaining (NOT NoSQL)     |
| 2   | Sessions        | **Auto-created** per backtest run                           |
| 3   | Batch + Quant   | **User chooses**: per-symbol OR portfolio-level (UI toggle) |
| 4   | Python API      | **Local REST API** (FastAPI on `localhost`)                 |
| 5   | Migration       | **Clean slate** — no backward compat                        |
| 6   | Auto-Quant      | Sidebar settings, user picks what auto-runs, default = ALL  |
| 7   | Param Versions  | Create **version N+1** alongside old, enable comparison     |
| 8   | Cross-Session   | **Yes** — compare Grid Search across sessions               |
| 9   | Concurrency     | **Parallel** via `ProcessPoolExecutor` (must-have)          |
| 10  | Cancellation    | **Keep** partial results, mark as `partial`                 |
| 11  | Data Volume     | 3 months / 15m timeframe. GPU accel explored later          |
| 12  | Timeseries      | Store equity curves for combos **above threshold** only     |
| 13  | Cleanup         | **Size-based slider** in Settings (like Telegram)           |
| 14  | Multi-Strategy  | One strategy per session, compare **across sessions**       |
| 15  | Config Snapshot | Show **warning** if strategy code changed since run         |

---

## Addressing the NoSQL Concern

> _"What if user adjusts parameters and compares to previous result? NoSQL can save multiple runs with different params in the same session."_

**SQLite handles this identically — and better.** Here's how:

```sql
-- Session "sess_abc" has version chain:
-- v1: base backtest (RSI=14)
-- v2: grid search with RSI 10-20
-- v3: user tweaks RSI to 12-18, reruns grid search

SELECT r.id, r.run_type, r.version_number, rr.sharpe_ratio, rr.win_rate
FROM runs r
JOIN run_results rr ON r.id = rr.run_id
WHERE r.session_id = 'sess_abc'
ORDER BY r.version_number;

-- Result:
-- id=1, backtest, v1, sharpe=1.2, win_rate=0.55
-- id=2, grid_search, v1, sharpe=1.8, win_rate=0.62   ← original
-- id=3, grid_search, v2, sharpe=1.9, win_rate=0.65   ← after tweak
```

Each "version" is just another row with `version_number` and `parent_run_id`. The session groups them. SQL JOINs let you compare any version against any other in one query. NoSQL would require you to write custom comparison logic.

---

## Tech Stack

| Layer          | Technology                  | Rationale                                       |
| -------------- | --------------------------- | ----------------------------------------------- |
| Database       | **SQLite** (existing)       | Single file, zero config, already in project    |
| Backend API    | **FastAPI**                 | Async, auto-docs, SSE for progress, lightweight |
| Execution      | **ProcessPoolExecutor**     | Already proven in `run_batch_analysis.py`       |
| Frontend State | **Zustand** (existing)      | Already used for all stores                     |
| Frontend HTTP  | **fetch** / **EventSource** | SSE for progress streaming                      |

---

## Database Schema Evolution

> Based on existing `docs/DATABASE.md` + new session/versioning tables.

### New Tables

```sql
-- ============================================
-- SESSIONS TABLE (Groups related runs)
-- ============================================
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,                -- "sess_abc123" (UUID)
    mode_type TEXT NOT NULL,            -- "single" | "batch"
    strategy_id INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_accessed DATETIME,
    status TEXT DEFAULT 'active',       -- "active" | "archived"
    config_snapshot JSON NOT NULL,      -- Full config at creation time
    git_hash TEXT,                      -- Code version at session creation
    notes TEXT,                         -- User notes

    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
);
```

### Modified Tables

```sql
-- RUNS TABLE: Add session_id, run_type, version_number
ALTER TABLE runs ADD COLUMN session_id TEXT REFERENCES sessions(id);
ALTER TABLE runs ADD COLUMN run_type TEXT DEFAULT 'backtest';
    -- "backtest" | "grid_search" | "walk_forward" | "sensitivity"
ALTER TABLE runs ADD COLUMN version_number INTEGER DEFAULT 1;
ALTER TABLE runs ADD COLUMN parent_run_id INTEGER REFERENCES runs(id);
ALTER TABLE runs ADD COLUMN auto_quant_config JSON;
    -- Which quant tools were auto-triggered, with what configs
```

### New Quant Results Tables

```sql
-- ============================================
-- GRID SEARCH RESULTS
-- ============================================
CREATE TABLE grid_search_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    x_param TEXT NOT NULL,
    x_value REAL NOT NULL,
    y_param TEXT NOT NULL,
    y_value REAL NOT NULL,
    -- Metrics (REAL for ratios, TEXT for money)
    net_pnl TEXT,
    net_pnl_pct REAL,
    sharpe_ratio REAL,
    profit_factor REAL,
    win_rate REAL,
    max_drawdown_pct REAL,
    trade_count INTEGER,
    calmar_ratio REAL,
    sortino_ratio REAL,
    -- Threshold flag
    above_threshold BOOLEAN DEFAULT FALSE,

    FOREIGN KEY (run_id) REFERENCES runs(id),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- ============================================
-- WALK FORWARD RESULTS
-- ============================================
CREATE TABLE walk_forward_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    window_index INTEGER NOT NULL,
    is_start_date DATE,
    is_end_date DATE,
    oos_start_date DATE,
    oos_end_date DATE,
    best_param TEXT,
    best_param_value REAL,
    is_metric_value REAL,
    oos_return_pct REAL,
    is_positive BOOLEAN,

    FOREIGN KEY (run_id) REFERENCES runs(id),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- ============================================
-- SENSITIVITY RESULTS
-- ============================================
CREATE TABLE sensitivity_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    param_name TEXT NOT NULL,
    low_value REAL,
    base_value REAL,
    high_value REAL,
    low_metric REAL,
    base_metric REAL,
    high_metric REAL,
    metric_name TEXT,
    sensitivity_level TEXT,     -- "high" | "medium" | "low"

    FOREIGN KEY (run_id) REFERENCES runs(id),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- ============================================
-- DB SIZE TRACKING (for cleanup slider)
-- ============================================
CREATE TABLE db_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Seed: max_db_size_mb = "0" (0 = unlimited)

-- ============================================
-- NEW INDEXES
-- ============================================
CREATE INDEX idx_sessions_mode ON sessions(mode_type);
CREATE INDEX idx_sessions_strategy ON sessions(strategy_id);
CREATE INDEX idx_sessions_created ON sessions(created_at DESC);
CREATE INDEX idx_runs_session ON runs(session_id);
CREATE INDEX idx_runs_type ON runs(run_type);
CREATE INDEX idx_runs_version ON runs(version_number);
CREATE INDEX idx_gs_results_run ON grid_search_results(run_id);
CREATE INDEX idx_gs_results_session ON grid_search_results(session_id);
CREATE INDEX idx_wf_results_run ON walk_forward_results(run_id);
CREATE INDEX idx_sens_results_run ON sensitivity_results(run_id);
```

---

## File Structure (New/Modified Files)

### Backend (Python)

```
app/
├── api/                          [NEW DIRECTORY]
│   ├── __init__.py
│   ├── server.py                 # FastAPI app, CORS, startup
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── backtest.py           # POST /api/backtest/run, GET /api/backtest/{id}
│   │   ├── sessions.py           # CRUD /api/sessions
│   │   ├── grid_search.py        # POST /api/grid-search/run, GET results
│   │   ├── walk_forward.py       # POST /api/walk-forward/run, GET results
│   │   ├── sensitivity.py        # POST /api/sensitivity/run, GET results
│   │   └── settings.py           # GET/PUT /api/settings (cleanup slider etc.)
│   └── sse.py                    # Server-Sent Events for progress streaming
├── db/                           [NEW DIRECTORY]
│   ├── __init__.py
│   ├── connection.py             # SQLite connection manager
│   ├── schema.py                 # CREATE TABLE statements
│   ├── migrations.py             # Schema versioning
│   └── repositories/
│       ├── __init__.py
│       ├── session_repo.py       # Session CRUD
│       ├── run_repo.py           # Run CRUD (extends existing)
│       ├── grid_search_repo.py   # Grid search result CRUD
│       ├── walk_forward_repo.py  # Walk-forward result CRUD
│       ├── sensitivity_repo.py   # Sensitivity result CRUD
│       └── settings_repo.py      # DB settings (cleanup config)
├── engine/                       [NEW DIRECTORY]
│   ├── __init__.py
│   ├── session_manager.py        # Create/load/archive sessions
│   ├── executor.py               # Orchestrates backtest + auto-quant pipeline
│   ├── grid_search_executor.py   # Parallel grid search runner
│   ├── walk_forward_executor.py  # Walk-forward runner
│   └── sensitivity_executor.py   # Sensitivity runner
```

### Frontend (TypeScript/React)

```
ui/src/
├── stores/
│   ├── sessionStore.ts           [NEW] Session state management
│   ├── engineStore.ts            [NEW] Execution bridge (API calls + SSE)
│   ├── backtestStore.ts          [MODIFY] Slim down, delegate to session
│   ├── gridSearchStore.ts        [MODIFY] Remove mock data, use API
│   ├── walkForwardStore.ts       [MODIFY] Remove mock data, use API
│   ├── sensitivityStore.ts       [MODIFY] Remove mock data, use API
│   ├── resultsStore.ts           [MODIFY] Read from DB via API
│   └── settingsStore.ts          [NEW/MODIFY] Cleanup slider state
├── components/
│   ├── layout/Sidebar.tsx        [MODIFY] Auto-quant toggles
│   ├── settings/SettingsPage.tsx  [MODIFY] Add cleanup slider
│   └── session/                  [NEW DIRECTORY]
│       ├── SessionPanel.tsx       # Session list/switcher
│       ├── VersionCompare.tsx     # Compare param versions
│       └── SessionWarning.tsx     # Strategy-changed warning
```

---

## Task Breakdown

### Phase 0: Foundation — Schema + API + Safety Net

> **Goal:** Prove the full stack works with ONE integration test before touching UI.

- [ ] **T0.1** Create `app/db/schema.py` with all CREATE TABLE statements

  - INPUT: Schema from this plan + existing `DATABASE.md`
  - OUTPUT: `schema.py` that creates all tables
  - VERIFY: `conda run -n rsi python -c "from app.db.schema import init_db; init_db('test.db')"` → no errors, `test.db` has all tables

- [ ] **T0.2** Create `app/db/connection.py` — SQLite connection manager

  - INPUT: Database path from config
  - OUTPUT: Context manager for DB connections
  - VERIFY: Unit test creates connection, inserts row, reads it back

- [ ] **T0.3** Create `app/db/repositories/session_repo.py` — Session CRUD

  - INPUT: Session data model
  - OUTPUT: `create_session()`, `get_session()`, `list_sessions()`, `archive_session()`
  - VERIFY: Integration test: create → read → list → archive

- [ ] **T0.4** Create `app/db/repositories/run_repo.py` — Run CRUD with version chaining

  - INPUT: Run data model with `session_id`, `version_number`, `parent_run_id`
  - OUTPUT: `create_run()`, `get_runs_by_session()`, `get_run_versions()`
  - VERIFY: Test creating v1 run, then v2 with parent_run_id pointing to v1

- [ ] **T0.5** Create `app/api/server.py` — FastAPI app with CORS

  - INPUT: FastAPI + uvicorn
  - OUTPUT: Server starts on `localhost:8765`
  - VERIFY: `conda run -n rsi python -m app.api.server` → visit `http://localhost:8765/docs`

- [ ] **T0.6** Create `app/api/routes/sessions.py` — Session REST endpoints

  - INPUT: Session repo
  - OUTPUT: `POST /api/sessions`, `GET /api/sessions`, `GET /api/sessions/{id}`
  - VERIFY: `curl -X POST http://localhost:8765/api/sessions -d '{"mode_type":"single","config":{...}}'` → returns session JSON

- [ ] **T0.7** Create `tests/test_schema_integration.py` — **SAFETY NET TEST**
  - INPUT: Schema + repos
  - OUTPUT: Test that creates DB → session → run → results → reads everything back
  - VERIFY: `conda run -n rsi python -m pytest tests/test_schema_integration.py -v` → all pass

---

### Phase 1: Backtest Pipeline End-to-End

> **Goal:** Run a backtest from API → save results to DB → retrieve via API.

- [ ] **T1.1** Create `app/engine/executor.py` — Main execution orchestrator

  - INPUT: Session config, strategy class
  - OUTPUT: Runs `BacktestEngine`, saves results to `runs`, `run_results`, `run_timeseries`, `trades` tables
  - VERIFY: Test: call executor with known config → check DB has expected rows

- [ ] **T1.2** Create `app/api/routes/backtest.py` — Backtest REST endpoints

  - INPUT: `POST /api/backtest/run` with session_id + config
  - OUTPUT: Starts backtest, returns run_id. SSE endpoint for progress.
  - VERIFY: curl POST → check run appears in DB with status "completed"

- [ ] **T1.3** Create `app/api/sse.py` — Server-Sent Events for progress

  - INPUT: Execution progress events
  - OUTPUT: SSE stream at `GET /api/progress/{run_id}`
  - VERIFY: EventSource in browser connects, receives progress updates

- [ ] **T1.4** Create `ui/src/stores/engineStore.ts` — Frontend execution bridge

  - INPUT: API endpoints
  - OUTPUT: `runBacktest()`, `getProgress()` via SSE, `getResults()`
  - VERIFY: Store calls API, receives progress, displays results

- [ ] **T1.5** Create `ui/src/stores/sessionStore.ts` — Session state

  - INPUT: Session API endpoints
  - OUTPUT: `createSession()`, `listSessions()`, `activeSession`
  - VERIFY: Creating session from UI → appears in session list

- [ ] **T1.6** Modify `ui/src/stores/backtestStore.ts` — Slim down

  - INPUT: Current backtestStore
  - OUTPUT: Remove mock data generation, delegate execution to engineStore
  - VERIFY: "Run Backtest" button → calls API → results appear in dashboard

- [ ] **T1.7** Integration test: Full backtest pipeline
  - VERIFY: `conda run -n rsi python -m pytest tests/test_backtest_pipeline.py -v`

---

### Phase 2: Grid Search End-to-End

> **Goal:** Grid Search runs in parallel via API, persists to DB, displays heatmap.

- [ ] **T2.1** Create `app/engine/grid_search_executor.py` — Parallel grid search

  - INPUT: Grid config (x/y params, ranges), session_id
  - OUTPUT: Runs all combos via `ProcessPoolExecutor`, saves to `grid_search_results`
  - VERIFY: Test with 3×3 grid → 9 result rows in DB

- [ ] **T2.2** Create `app/db/repositories/grid_search_repo.py`

  - OUTPUT: `save_results()`, `get_results()`, `get_results_by_session()`

- [ ] **T2.3** Create `app/api/routes/grid_search.py` — REST + SSE

  - OUTPUT: `POST /api/grid-search/run`, `GET /api/grid-search/{run_id}/results`

- [ ] **T2.4** Modify `ui/src/stores/gridSearchStore.ts`

  - Remove `generateMockResult()`, call API instead
  - Support version comparison (v1 vs v2 of same grid search)

- [ ] **T2.5** Store timeseries only for combos above threshold (Sharpe > 0)
  - VERIFY: Run grid search → only positive-Sharpe combos have equity curves in `run_timeseries`

---

### Phase 3: Walk-Forward End-to-End

> **Goal:** Walk-Forward runs via API, persists windows to DB, displays chart.

- [ ] **T3.1** Create `app/engine/walk_forward_executor.py`
- [ ] **T3.2** Create `app/db/repositories/walk_forward_repo.py`
- [ ] **T3.3** Create `app/api/routes/walk_forward.py`
- [ ] **T3.4** Modify `ui/src/stores/walkForwardStore.ts` — remove mocks, use API

---

### Phase 4: Sensitivity End-to-End

> **Goal:** Sensitivity analysis runs via API, persists to DB, displays tornado chart.

- [ ] **T4.1** Create `app/engine/sensitivity_executor.py`
- [ ] **T4.2** Create `app/db/repositories/sensitivity_repo.py`
- [ ] **T4.3** Create `app/api/routes/sensitivity.py`
- [ ] **T4.4** Modify `ui/src/stores/sensitivityStore.ts` — remove mocks, use API

---

### Phase 5: Session Management + UX Features

> **Goal:** Session panel, version comparison, auto-quant toggles, cleanup slider.

- [ ] **T5.1** Create `ui/src/components/session/SessionPanel.tsx` — session list/switcher
- [ ] **T5.2** Create `ui/src/components/session/VersionCompare.tsx` — diff two versions
- [ ] **T5.3** Modify `ui/src/components/layout/Sidebar.tsx` — auto-quant toggle section
- [ ] **T5.4** Create `ui/src/components/session/SessionWarning.tsx` — strategy-changed warning
- [ ] **T5.5** Modify `ui/src/components/settings/SettingsPage.tsx` — cleanup slider (size-based, like Telegram)
- [ ] **T5.6** Create `app/api/routes/settings.py` — GET/PUT cleanup config + trigger cleanup
- [ ] **T5.7** Cross-session comparison — extend `comparisons` table to reference `session_id`

---

### Phase 6: Batch Mode Quant Access

> **Goal:** Batch mode users can run quant tools per-symbol or portfolio-level.

- [ ] **T6.1** Add symbol selector to quant tools when in batch mode
- [ ] **T6.2** Add "Run for all symbols" option in Grid Search
- [ ] **T6.3** Aggregated walk-forward across portfolio
- [ ] **T6.4** Portfolio-level sensitivity analysis

---

## Verification Plan

### Automated Tests

All tests run in `rsi` conda environment:

```bash
# Phase 0 safety net
conda run -n rsi python -m pytest tests/test_schema_integration.py -v

# Phase 1 backtest pipeline
conda run -n rsi python -m pytest tests/test_backtest_pipeline.py -v

# Phase 2 grid search
conda run -n rsi python -m pytest tests/test_grid_search_pipeline.py -v

# API smoke test
conda run -n rsi python -m pytest tests/test_api_endpoints.py -v

# Full suite
conda run -n rsi python -m pytest tests/ -v --ignore=tests/test_binance_adapter.py
```

### Manual Verification

1. **Start API server**: `conda run -n rsi python -m app.api.server`
2. **Start UI dev server**: `cd ui && npm run dev`
3. **Run single backtest**: Click "Run" → verify progress bar → results appear
4. **Check DB**: Open `data/backtest.db` → verify session + run + results rows exist
5. **Run Grid Search**: Configure 3×3 grid → runs in parallel → heatmap renders
6. **Tweak params + rerun**: Change RSI range → run again → version 2 appears alongside v1
7. **Compare versions**: Click compare → side-by-side heatmaps
8. **Cleanup slider**: Settings → drag slider → old sessions auto-archived

---

## AI Agent Prompt Strategy

> User requested: "Create a folder with detailed prompts to guide AI agents."

For each phase, we'll create a `docs/prompts/` file with:

- **Context**: What files to read, what NOT to touch
- **Constraints**: Exact schema to use, error handling rules
- **Stop conditions**: When to ask the user instead of guessing
- **Verification**: Exact commands to run after implementation

These will be created during EXECUTION mode, one per phase.

---

## GPU Acceleration Note

> User wants GPU accel for parallel backtesting (Intel B580 / RTX 3060).

This is a **Phase 7+ optimization**. Current priority is getting the pipeline working with CPU `ProcessPoolExecutor`. GPU acceleration would require:

- Vectorized strategy logic in NumPy/CuPy
- Significant refactoring of `BacktestEngine.run()` loop
- Different GPU compute backends (CUDA for NVIDIA, OneAPI for Intel)

Recommend: Get Phase 0-6 working first, then profile bottlenecks, THEN decide if GPU is worth the investment.

---

## Risk Register

| Risk                                           | Impact                      | Mitigation                           |
| ---------------------------------------------- | --------------------------- | ------------------------------------ |
| Schema design wrong                            | Must redo all repos + tests | Phase 0 safety net test              |
| FastAPI dependency conflicts                   | Blocks all API work         | Isolated conda env, pin versions     |
| ProcessPoolExecutor spawning issues on Windows | Parallel execution fails    | Test early, fallback to sequential   |
| DB size grows too fast at 15m                  | Disk usage concerns         | Cleanup slider + threshold filtering |
| SSE connection drops                           | UI shows stale progress     | Reconnect logic + polling fallback   |

---

> ⚠️ **This plan is NO CODE.** Review and approve before we proceed to implementation Phase 0.
