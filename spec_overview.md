# RSI Bot — Backend ↔ Frontend Integration Spec

## Master Overview

**Goal:** Wire the existing React UI (currently mock-data-driven) to the existing FastAPI backend (complete API with SSE, persistence, 6 route groups) so backtests run end-to-end from the browser.

**Current State:**
- Backend: Complete API (`/api/backtest/run`, `/api/backtest/{id}/progress` SSE, `/api/history`, `/api/strategies`, `/api/data/status`, `/api/data/download`), persistence layer, backtest engine, strategy configs as frozen dataclasses.
- Frontend: Full component tree (Sidebar, ResultsDashboard, BatchResults, History, GridSearch, WalkForward, Sensitivity), Zustand stores, API client layer (`api/client.ts`, `api/backtest.ts`, etc.), TypeScript types auto-generated from Pydantic schemas.
- Integration state: **Fully broken.** The stores/components are wired to mock data generators. The API functions exist but are not called from the correct store actions with correct payloads.

---

## Decision Log (from Q&A)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Data download on missing data | Server-side inline (download happens as part of backtest SSE stream) |
| 2 | Strategy param UI | API-driven JSON Schema returned per strategy |
| 3 | Backtest execution UX | Background queue — user can navigate freely |
| 4 | Phase 1 modes | Single backtest only |
| 5 | Strategy support | All strategies (generic system) |
| 6 | Concurrent backtests | Configurable server-side (REST endpoint for max_workers) |
| 7 | Error surfacing | Toast notification + retry button |
| 8 | SSE event design | Typed events (`download_progress`, `download_complete`, `progress`, `complete`, `error`) |
| 9 | Portfolio progress | Combined progress bar (single bar, weighted across symbols) |
| 10 | Three run modes | Single, Batch (N independent runs), Portfolio (one balance across all symbols) |
| 11 | Config persistence | Auto-persist via Zustand persist (already exists) + server-side presets |
| 12 | Presets storage | Server-side DB, per-strategy table |
| 13 | Concurrency setting | Server-side REST endpoint (runtime adjustable) |
| 14 | Floating progress widget | Collapsible pill |
| 15 | Strategy seeding | Auto-seed if strategy in STRATEGY_MAP but missing from DB |
| 16 | SSE reconnect | Auto-reconnect on drop |
| 17 | Duplicate runs | Warn + allow |
| 18 | Result caching | Cache + TTL in frontend store |
| 19 | Input validation | Client-side first (from JSON Schema) |
| 20 | Page refresh recovery | localStorage run IDs + poll `/api/backtest/{id}` on mount |
| 21 | Implementation approach | Backend first, then wire frontend |
| 22 | JSON Schema source | Strategy classmethod `param_schema()` on each config dataclass |
| 23 | Batch orchestration | Single API call to backend batch_runner |
| 24 | Candlestick + trades chart | Deferred (skip Phase 1 — already on paper in TradeDeepDive) |
| 25 | Results presentation | Auto-swap to results dashboard on complete |

---

## Phase Plan

### Phase 1 — Single Backtest End-to-End
**Goal:** User clicks "Run Backtest" in sidebar → data auto-downloads if missing → backtest runs → results render in ResultsDashboard.

| Stage | Scope | Owner |
|-------|-------|-------|
| 1A | Backend: Strategy param schema endpoint, auto-seed, inline download SSE | Backend |
| 1B | Backend: Fix/verify single backtest flow (run → persist → detail/timeseries endpoints) | Backend |
| 1C | Frontend: Wire Sidebar → backtestStore.runBacktest() → real API calls | Frontend |
| 1D | Frontend: SSE progress with typed events, download phase UI | Frontend |
| 1E | Frontend: Dynamic strategy param form from JSON Schema | Frontend |
| 1F | Frontend: Floating progress pill widget | Frontend |
| 1G | Frontend: Auto-reconnect SSE, page refresh recovery | Frontend |
| 1H | Integration testing: full flow validation | Both |

### Phase 2 — Batch + Portfolio Modes
**Goal:** Batch mode fires single API call → backend runs N symbols independently. Portfolio mode runs all symbols under one balance via PortfolioEngine.

| Stage | Scope | Owner |
|-------|-------|-------|
| 2A | Backend: Batch endpoint (wraps batch_runner), SSE aggregation | Backend |
| 2B | Backend: Portfolio endpoint (PortfolioEngine), combined progress | Backend |
| 2C | Frontend: Wire batch mode — single call, aggregate results | Frontend |
| 2D | Frontend: Wire portfolio mode — combined progress bar | Frontend |
| 2E | Frontend: BatchResultsDashboard with real data | Frontend |
| 2F | Server-side presets (CRUD endpoints, per-strategy table) | Backend |
| 2G | Frontend: Preset save/load UI | Frontend |

### Phase 3 — Quant Tools Wiring
**Goal:** Grid search, walk-forward, sensitivity analysis use real backend.

| Stage | Scope | Owner |
|-------|-------|-------|
| 3A | Backend: Verify/fix grid-search, walk-forward, sensitivity endpoints | Backend |
| 3B | Frontend: Wire gridSearchStore to real API | Frontend |
| 3C | Frontend: Wire walkForwardStore to real API | Frontend |
| 3D | Frontend: Wire sensitivityStore to real API | Frontend |

### Phase 4 — Polish & Infrastructure
| Stage | Scope | Owner |
|-------|-------|-------|
| 4A | Configurable concurrency REST endpoint | Backend |
| 4B | History page: wire to real `/api/history` with server-side filtering | Frontend |
| 4C | Trade deep-dive chart (candlestick + markers) — already scaffolded | Both |
| 4D | Export features (PDF/CSV/ZIP) with real data | Frontend |

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    React Frontend                        │
│                                                          │
│  Sidebar ──→ backtestStore.runBacktest()                │
│                    │                                     │
│                    ├─→ POST /api/backtest/run             │
│                    │       returns { run_id }             │
│                    │                                     │
│                    ├─→ GET /api/backtest/{id}/progress    │
│                    │       SSE: download_progress →       │
│                    │       SSE: download_complete →       │
│                    │       SSE: progress →                │
│                    │       SSE: complete →                │
│                    │                                     │
│                    ├─→ GET /api/backtest/{id}             │
│                    │       (RunDetail + trades)           │
│                    │                                     │
│                    └─→ GET /api/backtest/{id}/timeseries  │
│                            (equity + drawdown curves)    │
│                                                          │
│  resultsStore.setResults(mapApiToResults(detail, ts))    │
│           │                                              │
│           └──→ ResultsDashboard renders                  │
│                                                          │
│  Floating Pill ←── backtestStore.{isRunning, progress}   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                   FastAPI Backend                         │
│                                                          │
│  POST /api/backtest/run                                  │
│    1. Resolve strategy from DB (auto-seed if missing)    │
│    2. Check data file exists                             │
│       → If missing: inline download via download.py      │
│       → Emit download_progress / download_complete SSE   │
│    3. Build config via config_builder.py                 │
│    4. Submit to ThreadPoolExecutor                       │
│    5. Engine runs with progress callback → SSE progress  │
│    6. persist_results() on complete → SSE complete       │
│                                                          │
│  GET /api/strategies                                     │
│    → Returns [{id, name, description, param_schema}]     │
│    → param_schema = JSON Schema from dataclass method    │
│                                                          │
│  GET /api/settings/concurrency                           │
│  PUT /api/settings/concurrency                           │
│    → Runtime-adjustable ThreadPoolExecutor.max_workers   │
└─────────────────────────────────────────────────────────┘
```

---

## File Organization

```
specs/
├── spec_overview.md          ← This file
├── spec_phase1_backend.md    ← Phase 1 backend changes
├── spec_phase1_frontend.md   ← Phase 1 frontend wiring
├── spec_phase2_backend.md    ← Phase 2 batch/portfolio/presets
├── spec_phase2_frontend.md   ← Phase 2 frontend wiring
├── spec_api_contracts.md     ← All API endpoint contracts
└── spec_strategy_schema.md   ← JSON Schema generation system
```
