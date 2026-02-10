# Master Agent Prompt — Backtest System Scaling

> **Copy and paste this to start the agent on the full backtest scaling plan.**
> Covers Phase A → B → C → D.

---

## Your Mission

Complete ALL phases in `docs/PLAN-backtest-scaling.md`. The backtest UI frontend exists (React/30 components) and calls bridge APIs, but the Python backend modules currently return **fake data** (hardcoded stubs). Your job is to wire real engine calls, refactor the codebase, and build new analysis tools.

---

## MANDATORY: Read These Docs First (In Order)

1. **`.agent-guide/knowledge/BACKTEST_ENGINE.md`** — How BacktestEngine works
2. **`.agent-guide/knowledge/STRATEGY_DEV_GUIDE.md`** — Strategy architecture and clean boundaries
3. **`.agent-guide/knowledge/DATABASE_SCHEMA.md`** — DB tables and repository
4. **`.agent-guide/knowledge/API_REFERENCE.md`** — Bridge API contract
5. **`docs/PLAN-backtest-scaling.md`** — The master plan (this is your task list)

---

## Critical Reference Pattern

**Study this function before writing ANY code:**

```
app/backtest/run_batch_analysis.py → function run_single_backtest() (line 218)
```

This is the proven pattern for:
- Loading strategy via `load_strategy()`
- Creating `BacktestEngine(data_path, strategy_class, config)`
- Running `engine.run()`
- Extracting metrics via `BacktestReporter`
- Saving to DB via `BacktestRepository`

**ALL your implementations must follow this pattern.**

---

## Execution Rules

| Rule | Detail |
|------|--------|
| **One-by-one** | Complete each task, verify it passes, THEN move to next |
| **Verify after each** | Run the verification command specified in the plan |
| **Auto-proceed** | If verification passes, move to next task without asking |
| **Stop on error** | If verification fails, debug and fix before continuing |
| **Conda env** | Use `conda run -n rsi` for ALL Python commands |
| **No float for money** | Use `Decimal(str(value))` for all price/money calculations |
| **No new tables** | Use existing DB schema from `docs/DATABASE.md` |
| **Strategy is read-only** | Never modify `.py` strategy files. Use JSON overrides. |

---

## Phase A: Wire Real Engine (DO FIRST)

Replace stub implementations with real BacktestEngine calls.

### Task A1: Fix Broken Import + Wire `run_backtest()`
**File:** `app/ui/api/backtest.py`
- Remove broken `from app.backtest.data import load_csv_data` (line 3)
- Replace stub `run_backtest()` with real engine call (follow `run_single_backtest()` pattern)
- Fix `get_run_history()` to return real `net_profit_pct`
- **Verify:** `conda run -n rsi python -c "from app.ui.api.backtest import BacktestAPIMixin; print('import OK')"`

### Task A2: Wire `grid_search.py`
**File:** `app/backtest/grid_search.py`
- Replace `100.0 * (1 + modifier)` with real engine runs per parameter combination
- **Verify:** `conda run -n rsi python -c "from app.backtest.grid_search import run_grid_search; print('import OK')"`

### Task A3: Wire `walk_forward.py`
**File:** `app/backtest/walk_forward.py`
- Replace 5 hardcoded windows with real rolling window backtest runs
- Compute IS profit, OOS profit, efficiency ratio, consistency score
- **Verify:** `conda run -n rsi python -c "from app.backtest.walk_forward import run_walk_forward; print('import OK')"`

### Task A4: Wire `sensitivity.py`
**File:** `app/backtest/sensitivity.py`
- Replace `100.0 - (dist * 10)` bell curve with real engine runs per parameter value
- **Verify:** `conda run -n rsi python -c "from app.backtest.sensitivity import run_sensitivity; print('import OK')"`

### Task A5: Wire `get_strategy_config()`
**File:** `app/ui/api/config.py`
- Return real `DEFAULT_CONFIG` from strategy class instead of empty `{}`
- Merge with JSON override from `config/strategy_overrides/`
- **Verify:** `conda run -n rsi python -c "from app.ui.api.config import ConfigAPIMixin; print('import OK')"`

### Task A6: Full Verification
Run ALL verifications. If ANY fail, go back and fix before proceeding to Phase B.

---

## Phase B: Refactor Folder Structure (AFTER Phase A passes)

> **Gate:** Do NOT start Phase B until ALL of A1–A6 verify successfully.

### Task B1: Extract Metrics
- `app/backtest/reporting.py` (43KB monolith) → split into:
  - `app/metrics/calculator.py` — metric computation functions
  - `app/metrics/risk.py` — risk metrics (Sharpe, Sortino, drawdown)
  - `app/metrics/__init__.py` — re-export for backward compatibility

### Task B2: Split Batch Runner
- `app/backtest/run_batch_analysis.py` (33KB monolith) → split into:
  - `app/analysis/batch_run.py` — multi-symbol batch orchestration
  - `app/analysis/single_run.py` — single backtest run logic

### Task B3: Move Engine Core
- `app/backtest/engine.py` + `mock_exchange.py` → `app/engine/`
- Update all imports across the codebase

### Task B4: Move Analysis Tools
- `app/backtest/grid_search.py`, `walk_forward.py`, `sensitivity.py`, `comparison.py` → `app/analysis/`
- Update bridge API imports

### Task B5: (Optional) Strategy Auto-Discovery
- Auto-scan `app/strategies/` for `BaseStrategy` subclasses
- Only implement if time allows; manual registration via `loader.py` is acceptable

### Task B-VERIFY: Full Re-test
- Run **ALL Phase A verification commands again** to confirm refactoring didn't break anything
- If anything broke, fix before proceeding

---

## Phase C: New Analysis Features (AFTER Phase B passes)

> **Gate:** Do NOT start Phase C until B-VERIFY passes.

Each tool requires **4 components:**
1. Python module in `app/analysis/` (or `app/backtest/`)
2. Bridge API method in `app/ui/api/`
3. React frontend component (if not already built)
4. Verification test

### Task C1: Monte Carlo Simulation (Medium)
- Randomly shuffle trade sequence 1000x
- Build distribution of final equity, max drawdown, Sharpe
- Return: p5, p25, p50, p75, p95 percentiles + risk-of-ruin %

### Task C2: Parameter Stability Heatmap (Easy)
- 2D grid: pick 2 params → run engine for each (x, y) combination
- Return metric matrix for frontend heatmap rendering

### Task C3: Correlation Matrix (Easy)
- Run same strategy across N symbols
- Calculate pairwise correlation of equity curves
- Return NxN correlation matrix

### Task C4: Regime Analysis (Medium)
- Split data by market regime (trending up, trending down, ranging)
- Run backtest on each regime separately
- Return per-regime metrics + regime detection timestamps

### Task C5: Slippage Sensitivity (Easy)
- Run same strategy with varying slippage values (0bp, 5bp, 10bp, 25bp, 50bp)
- Return profit curve as function of slippage

### Task C6: Risk-of-Ruin Calculator (Easy)
- Given win_rate and avg_win/avg_loss ratio
- Calculate probability of hitting X% drawdown
- Return table: drawdown threshold → probability

### Task C7: Strategy Combination (Hard)
- Run 2+ strategies on same data independently
- Combine equity curves with weighting
- Calculate combined metrics + diversification benefit

### Task C8: OOS Degradation Tracker (Medium)
- Compare walk-forward OOS performance over time
- Detect if strategy is degrading (OOS profit trending down)
- Return degradation score + trend chart data

---

## Phase D: Advanced Infrastructure (Long-term, Lower Priority)

Only proceed if Phases A–C are complete and verified:

| Feature | What to Build |
|---------|---------------|
| Vectorized engine v2 | Pure vectorized ops (no candle-by-candle loop) for 100x speed |
| Multi-timeframe | Run 5m data with 1h signal filter |
| Paper trading | MockExchange → live WebSocket feed |
| Cloud execution | Offload heavy grid searches to cloud workers |
| Data management UI | Download/update OHLCV data from within the React UI |
| HTTP API | REST layer for headless/external access |

---

## Architecture Boundaries (NEVER Violate)

```
Layer 1: Data       → IDataProvider, IDataStore     (where prices come from)
Layer 2: Core Logic → IStrategy, IIndicators        (strategies live here)
Layer 3: Execution  → IExchange, IPortfolio          (how orders execute)
Layer 4: UI/DB      → Bridge API, Repository, React  (presentation + persistence)
```

- **Strategies (Layer 2)** must NEVER import from Layer 1, 3, or 4
- **Analysis tools** can import from Layer 2 and 3 (engine + strategies)
- **Bridge API (Layer 4)** calls analysis tools and returns JSON to frontend
- **Database ops** go through `BacktestRepository` only

---

## Quick Reference: Key Files

| What | Path |
|------|------|
| BacktestEngine | `app/backtest/engine.py` |
| MockExchange | `app/backtest/mock_exchange.py` |
| BacktestReporter | `app/backtest/reporting.py` |
| Reference pattern | `app/backtest/run_batch_analysis.py` → `run_single_backtest()` (line 218) |
| Strategy loader | `app/strategies/loader.py` |
| Strategies | `app/strategies/rsi_wma_retest.py`, `rsi_no_retest.py` |
| Bridge API | `app/ui/bridge.py`, `app/ui/api/` |
| DB repository | `app/db/repository.py` |
| DB models | `app/db/models.py` |
| DB schema doc | `docs/DATABASE.md` |
| Config | `config.yaml` |
| OHLCV data | `app/backtest/data/*.csv` |

---

## Start Now

Begin with **Task A1** and work sequentially through the plan. Verify each task before moving on. Report completion status per phase.
