# Spec Review: RSI Bot Backend ↔ Frontend Integration

> **Historical review (April 2026):** Retained for provenance; findings may
> have been superseded by later implementation.

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

## 5. `spec_phase1_frontend.md` — Phase 1 Frontend ✅ RESOLVED

### Strengths
- Accurately identifies the 3 main fixes (params mapping, date format, DataPrepModal)
- SSE phase tracking (download=30%, backtest=70%) is good UX
- Recovery-on-refresh logic is well-designed
- FloatingProgressPill component is thorough

### Issues — All Fixed

**5.1 — Spec rewrites existing code instead of showing diffs**
~~Full rewrites of `runBacktest()` and `streamProgress()` risk losing existing functionality.~~
**Fixed:** All changes now shown as surgical diffs against the existing code.

**5.2 — Wrong component paths**
~~`DynamicParamForm` assumed `components/sidebar/` which doesn't exist.~~
**Fixed:** New `components/sidebar/` directory created for sidebar sub-components. Import paths corrected.

**5.3 — `window.confirm()` breaks design system (Stage 1H)**
~~Browser `confirm()` dialog is inconsistent with the UI.~~
**Fixed:** Replaced with `sonner` toast + "Run Anyway" action button. Non-blocking, consistent with existing patterns.

**5.4 — Missing `resetParams` store action**
~~`DynamicParamForm` references `resetParams` which wasn't in the spec.~~
**Fixed:** `resetParams` already exists in the store (line 422). Updated to reset to strategy `default_config` instead of hardcoded `DEFAULT_PARAMS`.

**5.5 — `DEFAULT_PARAMS` keys don't match dataclass fields**
~~No fallback for when schema hasn't loaded.~~
**Fixed:** `DynamicParamForm` shows a loading skeleton until `loadStrategies()` completes. No fallback params needed — the form renders only after schema is available.

---

## 6. `spec_phase2_backend.md` — Phase 2 Backend ✅ RESOLVED

### Strengths
- Clean separation of batch vs portfolio modes
- Preset CRUD is straightforward
- Batch DB schema is sensible

### Issues — All Fixed

**6.1 — Batch worker runs sequentially, not in parallel**
~~Sequential for-loop downgrades performance vs existing `BatchRunner`.~~
**Fixed:** Batch worker now wraps existing `BatchRunner` which uses `ProcessPoolExecutor` with configurable `max_workers`.

**6.2 — Separate batch endpoint vs existing mode discriminator**
~~Separate `POST /api/backtest/batch` creates duplicate entry points.~~
**Fixed:** All modes route through existing `POST /api/backtest/run` with `mode=batch`. No new endpoint.

**6.3 — `Batch` model missing SQLAlchemy relationship**
~~`batch_id` FK added without `back_populates`.~~
**Fixed:** Both `Batch.runs` and `Run.batch` relationships added with `back_populates`.

**6.4 — `PresetUpdate` falsy check bug**
~~`if body.name:` treats empty string as no-update.~~
**Fixed:** Changed to `if body.name is not None:` and `if body.config is not None:`.

**6.5 — Portfolio progress split is static**
~~50/50 split causes instant jump when data is cached.~~
**Fixed:** Dynamic split — download gets 30% only if files need downloading, otherwise backtest gets 100%.

**6.6 — No DB migration mentioned**
~~New column on existing table requires migration.~~
**Fixed:** Confirmed project uses `create_all()` (no Alembic). New tables auto-create. Added `_migrate_add_batch_id()` helper using `ALTER TABLE` for the existing `runs` table, called from `init_db()`.

---

## 7. `spec_phase2_frontend_and_phase3_4.md` — Phase 2 Frontend + Phase 3-4 ✅ RESOLVED

### Strengths
- Batch flow correctly uses `Promise.all` for parallel result fetching
- "Untouched Files" section is helpful for scoping

### Issues — All Fixed

**7.1 — `require()` in ESM codebase**
~~`require("./backtestStore")` fails in Vite ESM environment.~~
**Fixed:** Changed to `await import("./backtestStore")` (dynamic ESM import).

**7.2 — Batch symbol-to-result mapping is brittle**
~~`symbol: symbols[i]` assumes order matches.~~
**Fixed:** Use `detail.symbol` from `RunDetail` response instead of index-based mapping.

**7.3 — Phase 3 quant tool endpoints may not exist**
~~Spec said "verify/fix" but endpoints don't exist at all.~~
**Fixed:** Phase 3 fully descoped. Documented as "frontend ready, backend not built (~30-40h standalone project)." API contracts preserved for future reference.

**7.4 — History filter lacks debounce**
~~`useEffect` fires on every keystroke.~~
**Fixed:** Added `useDebouncedValue` hook for `searchQuery` (300ms debounce).

**7.5 — Timeline estimate is optimistic**
~~62h total with discrepancies.~~
**Fixed:** Revised to ~41.5h (Phase 3 descoped, Phase 1-2 estimates updated from prior section fixes) + 20% contingency = ~50h.

---

## Cross-Cutting Concerns ✅ ALL RESOLVED

### A. Missing Test Plan
~~No specs included testing strategy.~~
**Fixed:** Testing Plan section added to `spec_overview.md` with per-phase test requirements (backend unit tests + frontend manual/Playwright tests).

### B. Missing DB Migration Plan
~~No migration tooling mentioned.~~
**Fixed:** Resolved in Section 6. `create_all()` handles new tables. `_migrate_add_batch_id()` helper added for existing `runs` table column.

### C. No Rollback Plan
Each phase is independently deployable:
- Phase 1 adds schema + inline download — existing single-mode flow is enhanced, not replaced
- Phase 2 adds batch/portfolio/presets — new capabilities, doesn't break Phase 1
- Phase 4 is polish — optional, doesn't affect core flow

### D. Architectural Rule Compliance
~~`service.py` at 388 lines would exceed limit.~~
**Fixed:** Resolved in Section 4. Workers extracted to `workers.py`, download logic to `inline_download.py`.

---

## Priority Action Items — ✅ ALL RESOLVED

All 15 original action items have been addressed across the 7 spec rewrites:

| # | Item | Resolution |
|---|------|-----------|
| 1 | Don't recreate ProgressBus | Removed — use existing `executor.py` |
| 2 | Don't recreate strategy seeding | Modified existing `seed.py` with `CONFIG_CLASS` |
| 3 | Include `rsi_wma_retest` | Added to all specs + pre-requisite for frozen dataclass |
| 4 | Quant tool endpoints don't exist | Phase 3 descoped entirely |
| 5 | Document full API schemas | Complete `BacktestRequest` (16 fields) + `RunDetail` (22+15 fields) |
| 6 | Concurrent download race condition | File lock with `fcntl.flock()` + double-check |
| 7 | `require()` → `import()` | Fixed to dynamic ESM import |
| 8 | Batch worker parallel | Wraps existing `BatchRunner` with `ProcessPoolExecutor` |
| 9 | Shared metadata file | `param_metadata.py` + `SchemaConfigMixin` (not global dict) |
| 10 | Testing plan | Added per-phase test requirements to `spec_overview.md` |
| 11 | DB migration | `_migrate_add_batch_id()` for existing table, `create_all()` for new tables |
| 12 | Component paths | New `components/sidebar/` directory for sidebar sub-components |
| 13 | `window.confirm()` | Replaced with `sonner` toast + action button |
| 14 | History debounce | `useDebouncedValue` hook (300ms) |
| 15 | Redundant schema endpoint | Dropped `GET /api/strategies/{name}/schema` |

### Revised Timeline

| Phase | Scope | Estimate |
|-------|-------|----------|
| **1** | Single backtest E2E | ~20h |
| **2** | Batch + Portfolio + Presets | ~13.5h |
| **3** | ~~Quant tools~~ | **Descoped** |
| **4** | Polish + infrastructure | ~8h |
| | **Subtotal** | **~41.5h** |
| | +20% contingency | **~50h** |
