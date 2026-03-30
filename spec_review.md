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

## 2. `spec_strategy_schema.md` — JSON Schema System

### Strengths
- Clean approach: auto-generate base schema from dataclass, enrich with metadata
- UI extensions (`ui_group`, `ui_order`, `ui_step`, `ui_suffix`) are practical
- Frontend consumption examples are well-thought-out

### Issues

**2.1 — No `RsiWmaRetestConfig` dataclass exists**
`rsi_wma_retest.py` does **not** have a frozen config dataclass (only `RsiNoRetestConfig` and `RsiMomentumConfig` exist). The spec needs to either create one or document how strategies without config dataclasses are handled.

**2.2 — `PARAM_METADATA` global dict pattern is fragile**
The registry pattern creates import-order dependencies and tight coupling. **Recommendation:** Use `dataclasses.field(metadata={...})` on each field instead, keeping metadata co-located with the field definition.

**2.3 — Dual approach confusion: `param_schema()` vs `generate_schema_from_dataclass()`**
The spec defines both a hand-written `param_schema()` classmethod AND an auto-generation helper. It's unclear which is primary. Clarify that `param_schema()` should call `generate_schema_from_dataclass()` internally.

**2.4 — `default_factory` handling bug**
Line 148: `prop["default"] = field.default_factory()` calls the factory at schema generation time. For mutable defaults (lists, dicts), this creates shared instances. Should serialize the result to JSON-safe value.

**2.5 — `STRATEGY_CONFIG_MAP` missing `rsi_wma_retest`**
Only maps two strategies; the third would return an empty schema.

---

## 3. `spec_api_contracts.md` — API Contracts

### Strengths
- Comprehensive endpoint catalog with request/response examples
- SSE event table is clear and well-typed
- Error codes table is practical

### Issues

**3.1 — `BacktestRequest` schema is incomplete**
The spec shows a subset. The actual schema in `app/api/schemas.py` includes additional fields used by `service.py`: `fee_tier`, `slippage_model`, `slippage_pct`, `symbols`, `mode`. Document the **full** schema.

**3.2 — Inline download creates race condition**
Currently `service.py:96-99` raises `FileNotFoundError` if CSV is missing. With inline download, the validation moves to the worker thread. What happens if two concurrent requests trigger downloads for the same symbol simultaneously? Need a file lock or "downloading" sentinel.

**3.3 — `RunDetail.trades` response omits existing fields**
The spec's trade schema omits fields the actual `_build_trades_list()` returns: `hold_time_hours`, `stop_loss_price`, `tp1_price`, `tp2_price`, `tp3_price`, `quantity`.

**3.4 — `RunDetail.results` response omits existing fields**
Missing: `gross_profit`, `gross_loss`, `max_drawdown_duration_days`, `max_consecutive_losses`, `avg_hold_time_hours` — all present in `RunResult` model and serialized by `_build_results_dict()`.

**3.5 — `GET /api/strategies/{name}/schema` (Endpoint 11) is redundant**
`GET /api/strategies` already returns `param_schema` per strategy. A separate per-strategy endpoint adds surface area with minimal benefit. Consider dropping.

**3.6 — `PUT /api/settings/concurrency` is unsafe**
Cannot rebuild `ThreadPoolExecutor` while jobs are running. Spec needs to specify behavior when active jobs exist (reject? drain first? adjust for next job only?).

**3.7 — SSE timeout mismatch**
Spec proposes 30s timeout with heartbeat; existing `service.py:212` uses 300s. Align or justify the change.

---

## 4. `spec_phase1_backend.md` — Phase 1 Backend

### Strengths
- Clear stage decomposition (1A through 1D)
- Result persistence verification checklist is thorough

### Issues

**4.1 — CRITICAL: `strategy_registry.py` duplicates existing `seed.py`**
`app/repository/backtest/seed.py` already has `seed_strategies()` that iterates `STRATEGY_MAP`, checks DB, inserts missing strategies. The spec should modify the existing file, not create a parallel system.

**4.2 — CRITICAL: ProgressBus (Section 1B.4) reimplements existing `executor.py`**
The spec proposes new `app/api/progress.py` with `ProgressBus`, `_progress_queues`, `subscribe/unsubscribe`. But `app/api/executor.py` already has all of this: `_progress_queues`, `create_progress_queue()`, `get_progress_queue()`, `publish_event()`, `make_progress_callback()`. **This entire section is redundant.**

**4.3 — CRITICAL: SSE endpoint reimplements existing `stream_progress()`**
`BacktestService.stream_progress()` in `service.py:203-218` already implements the SSE generator. The spec proposes creating a new route handler that duplicates this.

**4.4 — `@app.on_event("startup")` is deprecated**
FastAPI deprecated `on_event` in favor of `lifespan` context managers. Use the existing startup pattern.

**4.5 — Default extraction logic misses `default_factory` fields**
Lines 43-44 skip fields with `default_factory`. The existing `seed.py` uses `getattr(cls, "DEFAULT_CONFIG", {})` — both approaches have gaps and need alignment.

**4.6 — "Missing fields likely" are already present**
The spec says `exit_reasons`, `max_consecutive_wins`, `volatility`, `calmar_ratio`, `expectancy` are "likely missing." But `RunResult` model already has ALL of these columns, and `_build_results_dict()` serializes them all. This section is based on stale assumptions.

**4.7 — File boundary violation**
Proposed `strategy_registry.py` in `app/backtest/` — per CLAUDE.md, strategy-related code belongs in `app/trading/strategy/` or the existing `app/repository/backtest/seed.py`.

**4.8 — `service.py` already at 388 lines**
Adding inline download logic will push it over the 400-line limit. Plan to decompose before adding code.

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
