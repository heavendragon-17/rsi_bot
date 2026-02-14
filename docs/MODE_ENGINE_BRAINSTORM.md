# 🧠 Brainstorm: Mode-Aware Engine & Quant Tool Architecture

## Context

**Problem:** The current UI has no dedicated engine layer between the stores and the Python backend. Single mode and batch mode share a flat `backtestStore` config, the database treats them almost identically (just a `is_batch_mode` boolean), and the quant tools (Grid Search, Walk-Forward, Sensitivity) generate their own mock data instead of consuming real backtest results. This means:

1. Quant tools cannot run on batch mode data at all
2. There is no "session" concept linking a run → its results → its quant analysis
3. The database doesn't differentiate optimization runs from regular runs
4. Results from Grid Search / Walk-Forward are ephemeral (lost on refresh)
5. No pipeline connects: **Config → Execute → Store Results → Feed to Quant Tools**

**Goal:** Both Single and Batch modes should access ALL quant tools, each with their own isolated data, configuration, and results. Quant tool results should persist in the database.

---

## 🔴 Current Problems (Detailed)

### Problem 1: No Engine Layer

```
CURRENT (broken):
┌──────────┐     ┌──────────────┐     ┌──────────┐
│ Sidebar  │────→│ backtestStore│────→│ Mock Data│
│ (Config) │     │ (flat state) │     │ (fake)   │
└──────────┘     └──────────────┘     └──────────┘
                        ↓
                 ┌──────────────┐
                 │ resultsStore │  ← mock generated, no DB
                 └──────────────┘

Quant tools are completely isolated:
┌──────────────────┐     ┌─────────────────────┐
│ gridSearchStore  │────→│ Own mock data gen    │
│ walkForwardStore │────→│ Own mock data gen    │
│ sensitivityStore │────→│ Own mock data gen    │
└──────────────────┘     └─────────────────────┘
```

### Problem 2: Flat Config (No Session Scoping)

```typescript
// backtestStore has ONE flat config for everything:
{
  mode: "single",    // <-- can be "single" or "batch"
  symbol: "BTC/USDT", // <-- irrelevant in batch mode
  batchSymbols: [...], // <-- irrelevant in single mode
  params: { ... },     // <-- shared between modes
}
```

- No concept of "this grid search belongs to this batch run"
- No way to run walk-forward per-symbol in batch mode
- Parameter changes in one quant tool silently affect the sidebar

### Problem 3: Database Schema Gaps

```sql
-- Current: runs table has no quant tool differentiation
CREATE TABLE runs (
    ...
    is_grid_search BOOLEAN,          -- crude boolean
    grid_search_parent_id INTEGER,   -- only for grid search
    -- ❌ No walk_forward support
    -- ❌ No sensitivity support
    -- ❌ No session/context grouping
    -- ❌ No mode_type field
);
```

### Problem 4: Results Are Ephemeral

- Grid Search heatmap data → gone on refresh
- Walk-Forward window results → gone on refresh
- Sensitivity tornado chart → gone on refresh
- No way to compare past optimization runs

---

## Architectural Options

---

### Option A: Session-Based Engine (Recommended)

**Concept:** Introduce a `Session` abstraction that groups a backtest run with its quant analysis. Each session has a `mode_type` and the engine routes data appropriately.

```
┌──────────────────────────────────────────────────┐
│                   ENGINE LAYER                    │
│                                                  │
│  ┌──────────┐   ┌───────────┐   ┌────────────┐ │
│  │ Session   │   │ Executor  │   │ DB Client  │ │
│  │ Manager   │──→│ (Python   │──→│ (SQLite)   │ │
│  │           │   │  bridge)  │   │            │ │
│  └──────────┘   └───────────┘   └────────────┘ │
│       ↕                                         │
│  ┌──────────────────────────────────────────┐   │
│  │ Session {                                 │   │
│  │   id: "sess_abc123"                      │   │
│  │   mode: "single" | "batch"               │   │
│  │   config: { symbol, params, dates, ... } │   │
│  │   baseRunId: 42                          │   │
│  │   quantRuns: {                           │   │
│  │     gridSearch: [runId: 43, 44, ...]     │   │
│  │     walkForward: [runId: 55, 56, ...]    │   │
│  │     sensitivity: [runId: 60]             │   │
│  │   }                                      │   │
│  │ }                                        │   │
│  └──────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┘
```

**New UI stores:**

```
sessionStore (NEW) ← replaces parts of backtestStore
  ├── activeSession: Session
  ├── createSession(mode, config)
  ├── getSessionResults()
  └── getQuantRunResults(toolType)

engineStore (NEW) ← the execution bridge
  ├── executeBacktest(session)
  ├── executeGridSearch(session, gridConfig)
  ├── executeWalkForward(session, wfConfig)
  ├── executeSensitivity(session, sensConfig)
  └── status / progress / errors
```

**Database Schema Changes:**

```sql
-- NEW: Sessions table
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,              -- "sess_abc123"
    mode_type TEXT NOT NULL,          -- "single" | "batch"
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_accessed DATETIME,
    status TEXT DEFAULT 'active',
    config JSON NOT NULL              -- full config snapshot
);

-- MODIFIED: runs table gets session_id + run_type
ALTER TABLE runs ADD COLUMN session_id TEXT REFERENCES sessions(id);
ALTER TABLE runs ADD COLUMN run_type TEXT DEFAULT 'backtest';
-- run_type: "backtest" | "grid_search" | "walk_forward" | "sensitivity"

-- NEW: Quant-specific results tables
CREATE TABLE grid_search_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    x_param TEXT, x_value REAL,
    y_param TEXT, y_value REAL,
    metric_name TEXT,
    metric_value REAL,
    full_results JSON,
    FOREIGN KEY (run_id) REFERENCES runs(id),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE walk_forward_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    window_index INTEGER,
    is_start_date DATE, is_end_date DATE,
    oos_start_date DATE, oos_end_date DATE,
    best_param TEXT, best_param_value REAL,
    is_metric_value REAL,
    oos_return_pct REAL,
    FOREIGN KEY (run_id) REFERENCES runs(id),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE sensitivity_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    param_name TEXT,
    low_value REAL, base_value REAL, high_value REAL,
    low_metric REAL, base_metric REAL, high_metric REAL,
    sensitivity_level TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(id),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
```

✅ **Pros:**

- Clean separation: each mode has its own session
- Quant results persist in DB (no more lost on refresh)
- Sessions are reloadable/shareable
- Batch mode can have per-symbol quant analysis
- History view shows sessions, not individual scattered runs
- Easy to add new quant tools later

❌ **Cons:**

- Major refactoring across all stores
- Need to build Python API bridge (executor)
- Session management adds UX complexity
- Migration needed for existing DB data

📊 **Effort:** High (3-4 weeks)

---

### Option B: Mode Context Provider (Lighter Refactor)

**Concept:** Keep existing stores but add a `ModeContext` that wraps quant tool stores with the correct data source based on active mode.

```typescript
// New: modeContextStore.ts
{
  activeMode: "single" | "batch",
  activeSymbol: "BTC/USDT" | null,  // for batch: which symbol is selected

  // Computed: returns the correct results based on mode
  getActiveResults(): ResultsData {
    if (activeMode === "single") return resultsStore.getState();
    if (activeMode === "batch") return batchResultsStore.getSymbolResults(activeSymbol);
  }

  // Quant tools read from this instead of generating mock data
  getParamsForOptimization(): Params { ... }
  getEquityCurve(): EquityPoint[] { ... }
  getTradeList(): Trade[] { ... }
}
```

**Changes:**

- Add `modeContextStore` as a data router
- Modify quant tool stores to accept `dataSource` parameter
- Keep existing DB structure, add `run_type` column to `runs`
- Save quant results as JSON in a new `quant_results` table

✅ **Pros:**

- Less refactoring (keeps existing stores)
- Faster to implement
- No session management overhead
- Easier to roll back if issues arise

❌ **Cons:**

- Still somewhat coupled — quant tools share global state
- No true session isolation (batch symbol A's grid search could conflict with B's)
- Less scalable for future tools
- History/persistence is bolted on, not native

📊 **Effort:** Medium (1.5-2 weeks)

---

### Option C: Micro-Frontend per Mode (Full Isolation)

**Concept:** Treat Single and Batch as completely separate "apps" with their own store instances, sharing only the theme and layout.

```
┌─────────────────────────────────────┐
│              Shell (Shared)         │
│  ├── Navbar, Theme, Layout         │
│  └── Mode Switcher                 │
│                                     │
│  ┌────────────┐ ┌────────────────┐ │
│  │ Single App │ │   Batch App    │ │
│  │            │ │                │ │
│  │ Own stores │ │ Own stores    │ │
│  │ Own quant  │ │ Own quant    │ │
│  │ Own results│ │ Own results  │ │
│  │ Own history│ │ Own history  │ │
│  └────────────┘ └────────────────┘ │
└─────────────────────────────────────┘
```

✅ **Pros:**

- True isolation — zero conflicts between modes
- Each mode evolves independently
- Simplest mental model per mode

❌ **Cons:**

- Massive duplication of code and logic
- Two separate histories, two separate DBs (or namespaced)
- Users lose cross-mode comparison ability
- Highest development effort

📊 **Effort:** Very High (5-6 weeks)

---

## 💡 Recommendation

**Option A (Session-Based Engine)** — because it solves ALL the problems properly while creating a foundation that scales. Here's why:

| Criteria                 | Option A | Option B     | Option C |
| ------------------------ | -------- | ------------ | -------- |
| True mode isolation      | ✅       | ⚠️ Partial   | ✅       |
| Quant results persist    | ✅       | ⚠️ Bolted on | ✅       |
| Reloadable sessions      | ✅       | ❌           | ❌       |
| Minimal code duplication | ✅       | ✅           | ❌       |
| Batch per-symbol quant   | ✅       | ⚠️ Hacky     | ✅       |
| Cross-mode comparison    | ✅       | ⚠️           | ❌       |
| Future scalability       | ✅       | ⚠️           | ✅       |

---

## 📋 Refactoring Scope (Option A)

### Phase 1: Database Schema Evolution

| Action | File                         | Details                              |
| ------ | ---------------------------- | ------------------------------------ |
| ADD    | `sessions` table             | Session identity + mode + config     |
| ALTER  | `runs` table                 | Add `session_id`, `run_type` columns |
| ADD    | `grid_search_results` table  | Persist heatmap data                 |
| ADD    | `walk_forward_results` table | Persist window results               |
| ADD    | `sensitivity_results` table  | Persist tornado data                 |
| MODIFY | `docs/DATABASE.md`           | Document new schema                  |

### Phase 2: New Core Stores

| Action   | File                      | Details                                                    |
| -------- | ------------------------- | ---------------------------------------------------------- |
| CREATE   | `stores/sessionStore.ts`  | Session CRUD, active session, session list                 |
| CREATE   | `stores/engineStore.ts`   | Execution bridge, progress, error handling                 |
| REFACTOR | `stores/backtestStore.ts` | Extract config into session, slim down to UI-only concerns |

### Phase 3: Refactor Quant Tool Stores

| Action   | File                          | Details                                            |
| -------- | ----------------------------- | -------------------------------------------------- |
| REFACTOR | `stores/gridSearchStore.ts`   | Accept session context, persist results to DB      |
| REFACTOR | `stores/walkForwardStore.ts`  | Accept session context, persist results to DB      |
| REFACTOR | `stores/sensitivityStore.ts`  | Accept session context, persist results to DB      |
| REFACTOR | `stores/resultsStore.ts`      | Read from DB via session, not mock generation      |
| REFACTOR | `stores/batchResultsStore.ts` | Read from DB via session, support per-symbol quant |

### Phase 4: Component Updates

| Action | File                                | Details                                     |
| ------ | ----------------------------------- | ------------------------------------------- |
| MODIFY | `components/layout/Sidebar.tsx`     | Session-aware config, create session on run |
| MODIFY | `components/GridSearch.tsx`         | Read/write via session context              |
| MODIFY | `components/WalkForward.tsx`        | Read/write via session context              |
| MODIFY | `components/Sensitivity.tsx`        | Read/write via session context              |
| ADD    | `components/SessionPanel.tsx`       | Session list/switcher in sidebar            |
| MODIFY | `components/history/RunHistory.tsx` | Group by session, show quant runs           |

### Phase 5: Batch Mode Quant Access

| Action | Details                                       |
| ------ | --------------------------------------------- |
| ADD    | Symbol selector in quant tools for batch mode |
| ADD    | "Run for all symbols" option in Grid Search   |
| ADD    | Aggregated walk-forward across portfolio      |
| ADD    | Portfolio-level sensitivity analysis          |

---

## 🗣️ Questions for Discussion

Before implementing, I need your input on these decisions:

1. **Session UX:** Should sessions be explicit (user clicks "New Session") or implicit (auto-created on every backtest run)?

2. **Batch + Quant tools:** When running Grid Search in batch mode, should it run separately per symbol, or optimize across the entire portfolio?

3. **Python API:** Is there a REST API planned for the backend, or should the UI call Python scripts directly via WebSocket/subprocess?

4. **Migration:** Should we keep backward compatibility with existing localStorage data, or is a clean slate fine?

5. **Priority:** Which phase do you want to tackle first? Schema → Stores → Components, or should we do a vertical slice (one quant tool end-to-end first)?

---

> ⚠️ **This is a significant refactoring.** I recommend we discuss these questions before writing any code, then create a detailed implementation plan with clear phase boundaries.
