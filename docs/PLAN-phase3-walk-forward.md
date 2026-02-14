# Phase 3 Plan: Walk-Forward Optimization End-to-End

## Context

Phase 0 (schema + repos), Phase 1 (backtest pipeline), and Phase 2 (grid search) are complete with 27 tests passing. The walk-forward UI already exists with mock data generation (`walkForwardStore.ts`). Phase 3 replaces the mocks with real execution: UI → API → executor → DB → SSE → UI.

**Walk-Forward concept:** For each rolling window, optimize a parameter on In-Sample (IS) data, then validate on Out-of-Sample (OOS) data. A "robust" strategy has ≥70% positive OOS windows, indicating it's not overfit.

**Key reuse:** Phase 2's `grid_search_executor.py` established the ProcessPoolExecutor + SSE pattern. Walk-forward reuses `_run_single_combo()` for IS optimization (run N param values in parallel), then runs one more backtest for OOS validation.

---

## Architecture: Walk-Forward Execution Flow

```
For each window (sequential):
  ┌─────────────────────────────────────────────┐
  │ IS OPTIMIZATION (parallel via ProcessPool)  │
  │ Run backtests for param_min → param_max     │
  │ Each combo: override param + set date range │
  │ to IS period → run backtest → get metric    │
  │ → Find best param by metric (sharpe, etc.)  │
  └──────────────────────┬──────────────────────┘
                         ↓ best_param_value
  ┌─────────────────────────────────────────────┐
  │ OOS VALIDATION (single backtest)            │
  │ Run backtest with best_param + OOS dates    │
  │ → Get oos_return_pct, is_positive           │
  └──────────────────────┬──────────────────────┘
                         ↓
  Save window result to walk_forward_results table
  Publish SSE progress event
```

**Date windowing:** The actual dates come from the CSV data file. We compute:
- Total data range from first/last candle in the CSV
- Map `isWindowDays`, `oosWindowDays`, `stepSizeDays` to actual date ranges
- Each window has `[is_start, is_end]` then `[oos_start, oos_end]`

**Param optimization within IS:** For each param value in `[paramMin, paramMax]` with `paramStep`:
- Deep copy base_config
- Override `params[paramToOptimize] = value`
- Set `startDate = is_start`, `endDate = is_end`
- Run backtest via `_run_single_combo` pattern
- Collect metric (sharpe, net_pnl, profit_factor, sortino)
- Best param = max(metric) across all values

---

## Tasks

### T3.1 — `app/db/repositories/walk_forward_repo.py` — Walk-forward CRUD

```python
def save_result(conn, run_id: int, session_id: str, result: dict) -> int
    # Insert one row into walk_forward_results
    # result keys: window_index, is_start_date, is_end_date, oos_start_date, oos_end_date,
    #              best_param, best_param_value, is_metric_value, oos_return_pct, is_positive

def save_results_batch(conn, run_id: int, session_id: str, results: list[dict]) -> None
    # Batch insert all window results

def get_results(conn, run_id: int) -> list[dict]
    # Return all results for a run, ordered by window_index

def get_results_by_session(conn, session_id: str) -> list[dict]
    # Return all walk-forward results across runs in a session
```

**Key reuse:**
- Follow exact column names from `app/db/schema.py` `walk_forward_results` table
- Same CRUD pattern as `app/db/repositories/grid_search_repo.py`

---

### T3.2 — `app/engine/walk_forward_executor.py` — Walk-forward runner

**Top-level picklable worker (reuse from grid search):**

```python
def _run_wf_backtest(combo_config: dict) -> dict:
    """
    Run one backtest for a single param value within one IS or OOS window.
    Same pattern as grid_search_executor._run_single_combo but simpler:
    - Only varies ONE param (not two)
    - Filters data by startDate/endDate

    Args:
        combo_config: { symbol, timeframe, strategy, capital, leverage,
                        riskPercent, params, startDate, endDate,
                        param_name, param_value }

    Returns:
        { param_name, param_value, net_pnl_pct, sharpe_ratio,
          profit_factor, sortino_ratio, trade_count }
        OR { "error": str, param_name, param_value }
    """
```

**Window generator:**

```python
def _generate_windows(data_path: str, is_days: int, oos_days: int, step_days: int) -> list[dict]:
    """
    Read CSV to find data date range, then generate rolling windows.

    Returns list of:
        { window_index, is_start, is_end, oos_start, oos_end }
    """
```

**Synchronous orchestrator:**

```python
def _run_walk_forward_sync(
    run_id, session_id, base_config, wf_config, loop
) -> dict:
    """
    For each window:
      1. Generate param combos for IS period
      2. Run IS combos in parallel → find best param
      3. Run OOS backtest with best param
      4. Record window result
      5. Publish SSE progress
    After all windows: save batch to DB, publish done event.

    wf_config: {
        param_to_optimize: str,
        param_min: float, param_max: float, param_step: float,
        is_window_days: int, oos_window_days: int, step_size_days: int,
        optimize_metric: "sharpe" | "net_pnl" | "profit_factor" | "sortino"
    }
    """
```

**Async entry point:**

```python
async def run_walk_forward(session_id, base_config, wf_config) -> tuple[int, int]:
    # Create run record (run_type="walk_forward")
    # Calculate total windows
    # Launch _run_walk_forward_sync in thread pool
    # Return (run_id, total_windows)
```

**Key reuse:**
- `app/engine/executor.py` → `normalize_symbol()`, `resolve_data_path()`, `build_engine_config()`
- `app/engine/grid_search_executor.py` → `_run_single_combo()` pattern for worker
- `app/backtest/engine.py` → `BacktestEngine`
- `app/backtest/reporting.py` → `_build_round_trips()`, `_calculate_metrics()`, `_calculate_risk_metrics()`

**SSE events:**
- `progress` → `{ pct: 0-100, completed: N, total: M, message: "Window 3/8: IS optimization..." }`
- `done` → `{ run_id, status, total_windows, summary: { oos_win_rate, verdict, ... } }`
- `error` → `{ message, run_id }`

**Date filtering:** `build_engine_config()` already supports `startDate`/`endDate` in the config. BacktestEngine respects these when loading data. Pass IS/OOS dates as `startDate`/`endDate` in each combo config.

---

### T3.3 — `app/api/routes/walk_forward.py` — REST + SSE endpoints

```
POST /api/walk-forward/run
  Body: {
    session_id: str,
    config: { symbol, timeframe, strategy, capital, leverage, riskPercent, params },
    walk_forward: {
      param_to_optimize: str,
      param_min: float, param_max: float, param_step: float,
      is_window_days: int, oos_window_days: int, step_size_days: int,
      optimize_metric: "sharpe" | "net_pnl" | "profit_factor" | "sortino"
    }
  }
  Returns: { run_id, status: "pending", total_windows: N }

GET /api/walk-forward/{run_id}
  Returns: {
    results: list[walk_forward_results rows],
    summary: { oos_win_rate, oos_win_count, total_windows, avg_oos_return,
               total_oos_return, best_window, worst_window,
               most_common_param, param_stability, verdict },
    run_status: str
  }

GET /api/walk-forward/{run_id}/progress  (SSE)
  Same pattern as grid search SSE
```

Register router in `app/api/server.py`:
```python
from app.api.routes import sessions, backtest, grid_search, walk_forward
app.include_router(walk_forward.router, prefix="/api")
```

**Summary calculation** (server-side in GET endpoint):
- `oos_win_rate` = positive windows / total × 100
- `verdict` = "robust" if ≥70%, "marginal" if ≥50%, else "overfit"
- `param_stability` = based on std dev of best_param_values
- `most_common_param` = mode of best_param_values
- `best_window` / `worst_window` = max/min by oos_return_pct

---

### T3.4 — Modify `ui/src/stores/walkForwardStore.ts` — Replace mocks with API

**Changes:**
1. **Remove** `generateWindowResult()` and `generateDateRanges()` mock helpers
2. **Keep** `calculateSummary()` — can compute client-side from API results, OR use server-side summary
3. **Replace** `runWalkForward()`:
   - Auto-create/get session (same pattern as gridSearchStore)
   - POST to `/api/walk-forward/run` → get `{ run_id, total_windows }`
   - Open EventSource on `/api/walk-forward/{run_id}/progress`
   - On `progress` events: update `progress`, `currentWindow`
   - On `done` event: GET `/api/walk-forward/{run_id}` → populate `windows[]` + `summary`
4. **Keep** all UI actions: `applyBestParam()`, `exportResults()`, `cancelRun()`, `reset()`
5. **Add** `currentRunId: number | null` to state
6. **Remove** hardcoded `totalDataDays = 365` — get actual window count from API response

**Result mapping** (API → store):
```
API: { window_index, is_start_date, is_end_date, oos_start_date, oos_end_date,
       best_param, best_param_value, is_metric_value, oos_return_pct, is_positive }
→ Store: WalkForwardWindow { index, isStartDate, isEndDate, oosStartDate, oosEndDate,
         bestParam: best_param_value, isMetricValue, oosReturn: oos_return_pct × capital,
         oosReturnPct, isPositive }
```

---

### T3.5 — Integration test `tests/test_walk_forward_pipeline.py`

```python
# Tests:
# T1: _run_wf_backtest() with known params → returns metrics dict
# T2: _generate_windows() with test data → correct number of windows
# T3: Walk-forward executor with small config (2 windows, 2 param values) → 2 rows in DB
# T4: Run status marked "completed" after execution
# T5: POST /api/walk-forward/run → returns run_id + total_windows
# T6: GET nonexistent run → 404
# T7: GET /api/walk-forward/{run_id} returns results + summary after sync run
```

Run: `conda run -n rsi python -m pytest tests/test_walk_forward_pipeline.py -v`

**Test config (small for speed):**
- Use `1INCH/USDT` 15m data (8832 candles ≈ 92 days)
- `is_window_days=30, oos_window_days=15, step_size_days=30` → ~2 windows
- `param_to_optimize="rsi_period", param_min=14, param_max=16, param_step=2` → 2 param values per window
- Total backtests: 2 windows × (2 IS + 1 OOS) = 6 backtests

---

## Critical Files to Read Before Implementing

| File | Why |
|------|-----|
| `app/engine/grid_search_executor.py` | Reuse worker pattern, ProcessPoolExecutor, SSE emit |
| `app/engine/executor.py` | `normalize_symbol`, `resolve_data_path`, `build_engine_config` |
| `app/db/repositories/grid_search_repo.py` | CRUD pattern to follow |
| `app/db/schema.py` | `walk_forward_results` table columns |
| `app/api/routes/grid_search.py` | Route pattern to follow |
| `ui/src/stores/walkForwardStore.ts` | Current mock store, interfaces, UI expectations |
| `ui/src/stores/gridSearchStore.ts` | API integration pattern already implemented |

---

## DB Schema: `walk_forward_results` (from schema.py — DO NOT MODIFY)

```sql
CREATE TABLE walk_forward_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    window_index INTEGER NOT NULL,
    is_start_date DATE,
    is_end_date DATE,
    oos_start_date DATE,
    oos_end_date DATE,
    best_param TEXT,          -- param name (e.g. "rsi_period")
    best_param_value REAL,    -- best value found in IS
    is_metric_value REAL,     -- IS metric score for the best param
    oos_return_pct REAL,      -- OOS return percentage
    is_positive BOOLEAN,      -- oos_return_pct > 0
    FOREIGN KEY (run_id) REFERENCES runs(id),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
```

---

## Agent Constraints (Anti-Hallucination Rules)

### DO NOT TOUCH
- `app/backtest/engine.py` — read-only
- `app/backtest/reporting.py` — read-only
- `app/backtest/mock_exchange.py` — read-only
- `app/core/portfolio.py` — read-only
- `app/db/schema.py` — read-only (Phase 0 finalized it)
- `app/db/connection.py` — read-only
- `app/db/repositories/session_repo.py` — read-only
- `app/db/repositories/run_repo.py` — read-only (call its methods, don't modify)
- `app/db/repositories/grid_search_repo.py` — read-only
- `app/engine/executor.py` — read-only (import helpers, don't modify)
- `app/engine/grid_search_executor.py` — read-only (reference pattern, don't modify)
- `ui/src/stores/backtestStore.ts` — do not touch
- `ui/src/stores/sessionStore.ts` — do not touch
- `ui/src/stores/gridSearchStore.ts` — do not touch
- Any `ui/src/components/` files — do not touch (walk-forward UI components already work)

### STOP CONDITIONS — Ask the user before proceeding if:
- `BacktestEngine` does not filter data by `startDate`/`endDate` (need to verify it works)
- `ProcessPoolExecutor` hangs or fails on Windows
- IS optimization produces no valid results (all errors)
- Date ranges from CSV don't cover enough days for the configured windows

### EXACT FIELD NAMES (from schema.py walk_forward_results)
- `window_index` (INTEGER), `is_start_date` (DATE), `is_end_date` (DATE)
- `oos_start_date` (DATE), `oos_end_date` (DATE)
- `best_param` (TEXT), `best_param_value` (REAL)
- `is_metric_value` (REAL), `oos_return_pct` (REAL), `is_positive` (BOOLEAN)

### NO INVENTED LOGIC
- Do not write your own metrics calculation — use `BacktestReporter` internals
- Do not add new DB columns beyond what `schema.py` defines
- Do not modify walk-forward UI components — only modify `walkForwardStore.ts`
- Worker function must be a **top-level function** for ProcessPoolExecutor pickling

### TESTING RULE
- Run `conda run -n rsi python -c "from app.engine.walk_forward_executor import run_walk_forward; print('ok')"` after T3.2
- Run `conda run -n rsi python -m pytest tests/test_walk_forward_pipeline.py -v` as final gate
- Use small config (2 windows, 2 param values) to keep runtime under 60 seconds
- All Phase 1 + Phase 2 tests must still pass: `conda run -n rsi python -m pytest tests/ -v --ignore=tests/test_binance_adapter.py`

---

## Verification (End-to-End)

1. Start API: `conda run -n rsi python -m app.api.server`
2. Start UI: `cd ui && npm run dev`
3. Open UI → Walk-Forward tab → configure:
   - IS Window: 60 days, OOS Window: 20 days, Step: 20 days
   - Param: rsi_period, Min: 10, Max: 20, Step: 2
   - Metric: Sharpe
4. Click "Run Walk-Forward" → verify:
   - SSE events arrive with window progress
   - Timeline visualization renders with IS/OOS blocks
   - Results summary shows verdict (robust/marginal/overfit)
   - EquityCurveComparison chart renders
5. Check DB: `SELECT COUNT(*) FROM walk_forward_results WHERE run_id = X`
6. Run tests: `conda run -n rsi python -m pytest tests/test_walk_forward_pipeline.py -v`

---

## Out of Scope for Phase 3

- Sensitivity Analysis — Phase 4
- Version comparison UI — Phase 5
- GPU acceleration — Phase 7+
- Walk-forward with multiple params simultaneously (only single param optimization)
