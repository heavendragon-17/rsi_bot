# Spec Review: RSI Bot Backend ↔ Frontend Integration

**Reviewer:** Claude Code
**Date:** 2026-03-30
**Files Reviewed:** 7 spec documents (`spec_overview.md`, `spec_strategy_schema.md`, `spec_api_contracts.md`, `spec_phase1_backend.md`, `spec_phase1_frontend.md`, `spec_phase2_backend.md`, `spec_phase2_frontend_and_phase3_4.md`)
**Method:** Cross-referenced every spec claim against the actual codebase

---

## Overall Assessment

These are **well-structured, detailed specs** with clear phase breakdown, decision log, and file-level change tracking. The architecture decisions (server-side inline download, JSON Schema-driven forms, SSE typed events, background queue) are sound. However, cross-referencing against the actual codebase reveals several **factual inaccuracies, redundant proposals, and gaps** that should be addressed before implementation begins.

---

## 1. `spec_overview.md` — Master Overview ✅ RESOLVED

### Strengths
- Decision log is excellent — captures 25 key decisions with clear rationale
- Phase plan is well-scoped with sensible dependency ordering
- Architecture diagram accurately reflects the data flow

### Issues — All Fixed

**1.1 — Architecture diagram implies infrastructure needs to be built, but it already exists**
~~The diagram shows `ThreadPoolExecutor`, SSE streaming, and progress callbacks as if they're new.~~
**Fixed:** Added "Already Implemented" section to Current State. Architecture diagram now uses `[EXISTS]`/`[NEW]`/`[MODIFY]` legend.

**1.2 — Missing strategy: `rsi_wma_retest`**
~~All downstream specs only mention two strategies.~~
**Fixed:** Decision #5 now lists all 3 strategies. Added Pre-requisites section: create `RsiWmaRetestConfig` frozen dataclass before Phase 1.

**1.3 — File organization references wrong paths**
~~Lists files in `specs/` subdirectory.~~
**Fixed:** Updated to repo root paths with correct filenames.

**1.4 — `POST /api/backtest/run` already returns `run_id`**
**Fixed:** Covered by the `[EXISTS]` annotations in the architecture diagram.

---

## 2. `spec_strategy_schema.md` — JSON Schema System ✅ RESOLVED

### Strengths
- Clean approach: auto-generate base schema from dataclass, enrich with metadata
- UI extensions (`ui_group`, `ui_order`, `ui_step`, `ui_suffix`) are practical
- Frontend consumption examples are well-thought-out

### Issues — All Fixed

**2.1 — No `RsiWmaRetestConfig` dataclass exists**
~~`rsi_wma_retest.py` does not have a frozen config dataclass.~~
**Fixed:** Spec now includes `RsiWmaRetestConfig` definition derived from existing `DEFAULT_CONFIG` dict, with full metadata.

**2.2 — `PARAM_METADATA` global dict pattern is fragile**
~~The registry pattern creates import-order dependencies and tight coupling.~~
**Fixed:** Replaced with shared metadata file (`param_metadata.py`) + explicit imports. No global mutable registry.

**2.3 — Dual approach confusion: `param_schema()` vs `generate_schema_from_dataclass()`**
~~The spec defines both without clarifying how they relate.~~
**Fixed:** `param_schema()` is written once in `SchemaConfigMixin`, delegates to `generate_schema_from_dataclass()`. DRY — no per-strategy duplication.

**2.4 — `default_factory` handling bug**
~~Calling the factory at schema generation time creates shared mutable instances.~~
**Fixed:** Schema helper now deep-copies factory output before storing in schema.

**2.5 — `STRATEGY_CONFIG_MAP` missing `rsi_wma_retest`**
~~Separate config map only listed 2 of 3 strategies.~~
**Fixed:** Eliminated `STRATEGY_CONFIG_MAP` entirely. Each strategy class exposes `CONFIG_CLASS` attribute. Config discovered via `STRATEGY_MAP[name].CONFIG_CLASS` — single source of truth.

---

## 3. `spec_api_contracts.md` — API Contracts ✅ RESOLVED

### Strengths
- Comprehensive endpoint catalog with request/response examples
- SSE event table is clear and well-typed
- Error codes table is practical

### Issues — All Fixed

**3.1 — `BacktestRequest` schema is incomplete**
~~Spec showed only a subset of fields.~~
**Fixed:** Full schema documented with all 16 fields (`mode`, `symbols`, `fee_tier`, `slippage_model`, `slippage_pct`, `max_workers`, `tick_data_path`), field reference table, and mode validation rules.

**3.2 — Inline download creates race condition**
~~Concurrent requests could trigger duplicate downloads for the same symbol.~~
**Fixed:** Added file lock strategy using `fcntl.flock()` with double-check pattern (check → lock → re-check → download → unlock).

**3.3 — `RunDetail.trades` response omits existing fields**
~~Missing `hold_time_hours`, `stop_loss_price`, `tp1_price`, `tp2_price`, `tp3_price`, `quantity`.~~
**Fixed:** Response example now includes all fields matching `_build_trades_list()` output.

**3.4 — `RunDetail.results` response omits existing fields**
~~Missing `gross_profit`, `gross_loss`, `max_drawdown_duration_days`, `max_consecutive_losses`, `avg_hold_time_hours`.~~
**Fixed:** Response example now includes all fields matching `_build_results_dict()` output.

**3.5 — `GET /api/strategies/{name}/schema` (Endpoint 11) is redundant**
~~Separate endpoint duplicated `GET /api/strategies` which already returns `param_schema`.~~
**Fixed:** Removed the endpoint entirely. Endpoint numbering adjusted.

**3.6 — `PUT /api/settings/concurrency` is unsafe**
~~No behavior defined when jobs are running.~~
**Fixed:** Spec now requires 409 Conflict rejection if any jobs are active. Code example included.

**3.7 — SSE timeout mismatch**
~~Spec proposed 30s, existing code uses 300s.~~
**Fixed:** Spec now states 300s timeout to match existing `service.py:212`. Added `CONCURRENCY_BUSY` error code.

---

## 4. `spec_phase1_backend.md` — Phase 1 Backend ✅ RESOLVED

### Strengths
- Clear stage decomposition (1A through 1D)
- Result persistence verification checklist is thorough

### Issues — All Fixed

**4.1 — CRITICAL: `strategy_registry.py` duplicates existing `seed.py`**
~~Spec proposed creating new `app/backtest/strategy_registry.py`.~~
**Fixed:** Spec now modifies existing `app/repository/backtest/seed.py`. No new file.

**4.2 — CRITICAL: ProgressBus (Section 1B.4) reimplements existing `executor.py`**
~~Spec proposed new `app/api/progress.py` with duplicate queue infrastructure.~~
**Fixed:** Entire section removed. Workers use existing `executor.publish_event()` directly.

**4.3 — CRITICAL: SSE endpoint reimplements existing `stream_progress()`**
~~Spec proposed new SSE route handler.~~
**Fixed:** Section removed. Existing `BacktestService.stream_progress()` and `backtest_stream.py` route are sufficient.

**4.4 — `@app.on_event("startup")` is deprecated**
~~Spec used deprecated FastAPI pattern.~~
**Fixed:** Spec now references existing `lifespan` context manager in `main.py`. No changes to `main.py` needed.

**4.5 — Default extraction logic misses `default_factory` fields**
~~Both approaches had gaps.~~
**Fixed:** `seed.py` now extracts defaults from `CONFIG_CLASS` frozen dataclass fields, filtering `METADATA`/`UI_GROUPS` class vars.

**4.6 — "Missing fields likely" are already present**
~~Spec assumed `exit_reasons`, `max_consecutive_wins`, etc. were missing.~~
**Fixed:** Stage 1C rewritten as "ALREADY COMPLETE — verify only". All 22 fields documented with file:line references.

**4.7 — File boundary violation**
~~`strategy_registry.py` proposed in `app/backtest/`.~~
**Fixed:** No new strategy-related file. Existing `seed.py` in `app/repository/backtest/` is modified.

**4.8 — `service.py` already at 388 lines**
~~Adding inline download would exceed 400-line limit.~~
**Fixed:** Worker functions extracted to `app/backtest/workers.py`. Download logic isolated in `app/backtest/data/inline_download.py`. `service.py` stays under 400 lines.

---

## 5. `spec_phase1_frontend.md` — Phase 1 Frontend

### Strengths
- Accurately identifies the 3 main fixes (params mapping, date format, DataPrepModal)
- SSE phase tracking (download=30%, backtest=70%) is good UX
- Recovery-on-refresh logic is well-designed
- FloatingProgressPill component is thorough

### Issues

**5.1 — Spec rewrites existing code instead of showing diffs**
`backtestStore.ts` (lines 236-399) already handles all three modes. `streamProgress()` already exists in `api/backtest.ts`. The spec should show surgical changes, not full rewrites that risk losing existing functionality.

**5.2 — Wrong component paths**
`DynamicParamForm` imports from `../../stores/backtestStore` assuming it lives in `components/sidebar/`. The codebase has no `components/sidebar/` — sidebar components are in `components/layout/`.

**5.3 — `window.confirm()` breaks design system (Stage 1H)**
Browser `confirm()` dialog is inconsistent with the existing toast/modal UI. Use the project's existing modal or confirmation pattern.

**5.4 — Missing `resetParams` store action**
`DynamicParamForm` references `resetParams` from the store, but this action isn't defined in the spec's store changes.

**5.5 — `DEFAULT_PARAMS` keys don't match dataclass fields**
The spec correctly identifies this (e.g. `ema_fast` vs `rsi_ema_length`) but the fix relies entirely on schema loading working correctly. Add a fallback for when schema hasn't loaded yet.

---

## 6. `spec_phase2_backend.md` — Phase 2 Backend

### Strengths
- Clean separation of batch vs portfolio modes
- Preset CRUD is straightforward
- Batch DB schema is sensible

### Issues

**6.1 — Batch worker runs sequentially, not in parallel**
Line 79: `for i, (run_id, symbol) in enumerate(...)` processes symbols sequentially. The existing `batch_runner.py` uses `ProcessPoolExecutor` for parallel execution. The spec **downgrades performance** without explanation.

**6.2 — Separate batch endpoint vs existing mode discriminator**
`BacktestService.start_run()` already detects portfolio mode via `req.symbols` and `req.mode`. Adding a separate `POST /api/backtest/batch` creates two entry points. Consider routing batch through the existing endpoint with `mode=batch`.

**6.3 — `Batch` model missing SQLAlchemy relationship**
Adds `batch_id` FK to `Run` but doesn't update `Run.relationship()` or add `back_populates`. SQLAlchemy needs both sides.

**6.4 — `PresetUpdate` falsy check bug**
`if body.name: preset.name = body.name` — empty string `""` is falsy and won't update. Use `is not None` instead.

**6.5 — Portfolio progress split is static**
50/50 download/backtest split means progress jumps from 0% to 50% instantly when data is already cached. Make dynamic.

**6.6 — No DB migration mentioned**
Adding `Preset`, `Batch` tables and `Run.batch_id` column requires migration tooling (Alembic). Not mentioned.

---

## 7. `spec_phase2_frontend_and_phase3_4.md` — Phase 2 Frontend + Phase 3-4

### Strengths
- Batch flow correctly uses `Promise.all` for parallel result fetching
- "Untouched Files" section is helpful for scoping
- Phase 3-4 correctly identifies mostly verification tasks

### Issues

**7.1 — `require()` in ESM codebase**
Line 245: `const { useBacktestStore } = require("./backtestStore")` — the codebase uses ESM imports. This will fail in Vite. Use `import()`.

**7.2 — Batch symbol-to-result mapping is brittle**
`symbol: symbols[i]` assumes `run_ids` order matches `symbols` array order. If any symbol fails or executes out of order, mapping breaks. Backend should include `symbol` in each run's response.

**7.3 — Phase 3 quant tool endpoints may not exist**
The route files show: `backtest_run.py`, `backtest_results.py`, `backtest_stream.py`, `history.py`, `strategies.py`, `data.py` — **no grid search, walk-forward, or sensitivity routes**. These may need to be built from scratch, not just "verified."

**7.4 — History filter lacks debounce**
`useEffect` watching 6 filter dependencies fires on every keystroke in search. Needs debounce.

**7.5 — Timeline estimate is optimistic**
62 hours total given the discrepancies found. Budget 20-30% contingency (~80h).

---

## Cross-Cutting Concerns

### A. Missing Test Plan
None of the 7 specs include testing strategy. For SSE streaming, thread pools, progress callbacks, and dynamic schema generation — tests are critical:
- Schema generation round-trip tests
- SSE event sequence tests (mock worker → verify event order)
- Frontend store integration tests (mock API → verify state transitions)

### B. Missing DB Migration Plan
Adding `batch_id` to `Run`, new `Preset`/`Batch` tables — no migration tooling mentioned.

### C. No Rollback Plan
What if Phase 1 is partially implemented? Can the system still function? Consider ensuring each stage is independently deployable.

### D. Architectural Rule Compliance
- `service.py` at 388 lines — will exceed 400-line limit with additions
- Progress split constants (30/70, 50/50) should go in `app/core/constants.py`

---

## Priority Action Items

| Priority | Item | Spec |
|----------|------|------|
| **Critical** | Don't recreate ProgressBus — use existing `executor.py` | Phase 1 Backend §1B.4 |
| **Critical** | Don't recreate strategy seeding — modify existing `seed.py` | Phase 1 Backend §1A.1 |
| **Critical** | Include `rsi_wma_retest` in all strategy references | All specs |
| **Critical** | Verify quant tool endpoints exist before planning Phase 3 | Phase 2 Frontend §3A |
| **High** | Document full `BacktestRequest`/`RunDetail` schemas | API Contracts §3.1-3.4 |
| **High** | Address concurrent download race condition | API Contracts §3.2 |
| **High** | Fix `require()` → `import()` in presetStore | Phase 2 Frontend §7.1 |
| **High** | Make batch worker parallel (match existing `batch_runner.py`) | Phase 2 Backend §6.1 |
| **Medium** | Use `dataclasses.field(metadata=)` instead of global `PARAM_METADATA` | Strategy Schema §2.2 |
| **Medium** | Add testing strategy across all phases | All specs |
| **Medium** | Plan DB migrations for new tables/columns | Phase 2 Backend §6.6 |
| **Medium** | Fix component paths (`components/sidebar/` → `components/layout/`) | Phase 1 Frontend §5.2 |
| **Low** | Replace `window.confirm()` with design-system modal | Phase 1 Frontend §5.3 |
| **Low** | Add debounce to history filter `useEffect` | Phase 2 Frontend §7.4 |
| **Low** | Drop redundant `GET /api/strategies/{name}/schema` endpoint | API Contracts §3.5 |
