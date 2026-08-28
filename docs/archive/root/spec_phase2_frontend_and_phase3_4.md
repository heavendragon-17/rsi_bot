# RSI Bot — Phase 2 Frontend + Phase 4 Spec

> **Historical implementation spec (April 2026):** Retained for provenance;
> use `docs/10_frontend_dashboard/` for the current frontend design.

## Phase 2 Frontend Scope

Wire batch and portfolio modes, preset management, BatchResultsDashboard with real data.

---

## Stage 2C: Wire Batch Mode

### Batch Now Uses Existing Endpoint

Since batch mode routes through the existing `POST /api/backtest/run` with `mode=batch` (see `spec_phase2_backend.md`), no separate `startBatch()` function is needed. The existing `startBacktest()` already works.

**Diff — `stores/backtestStore.ts` batch mode:**

```diff
  if (state.mode === "batch") {
    const symbols = state.portfolioInput
      .split("\n").map(s => s.trim()).filter(Boolean);

-   const { batch_id, run_ids } = await startBatch({
-     symbols,
-     ...
-   });
+   // Use existing startBacktest with mode=batch
+   const { run_id } = await startBacktest({
+     mode: "batch",
+     symbols,
+     timeframe: state.timeframe,
+     strategy: state.strategy,
+     start_date: format(parse(state.startDate, "dd-MM-yyyy", new Date()), "yyyy-MM-dd"),
+     end_date: format(parse(state.endDate, "dd-MM-yyyy", new Date()), "yyyy-MM-dd"),
+     initial_capital: state.capital,
+     leverage: parseInt(state.leverage),
+     risk_per_trade_pct: (parseFloat(state.riskPercent) / 100).toFixed(4),
+     params: state.params,
+     max_workers: null,  // use server default
+   });

+   // SSE uses same progress/complete events as single mode
+   const cleanup = streamProgress(
+     run_id,
+     (pct, phase) => { /* same phase-aware progress as single */ },
+     async () => {
+       cleanup();
+       const detail = await getRunDetail(run_id);
+       // detail.symbol contains comma-separated symbols for batch
+       // detail.results contains aggregated batch results
+       // ... hydrate batchResultsStore
+     },
+     (msg) => { cleanup(); toast.error(msg); },
+   );
  }
```

**Note:** The `startBatch()` and `streamBatchProgress()` functions in `api/backtest.ts` are **no longer needed**. Remove them if they exist, or simply don't create them.

### Result Fetching — Use `detail.symbol` Not Index

**Diff — when fetching per-symbol results after batch complete:**

```diff
  const allResults = await Promise.all(
    data.run_ids.map(async (runId) => {
      const [detail, timeseries] = await Promise.all([
        getRunDetail(runId),
        getTimeseries(runId),
      ]);
      return {
-       symbol: symbols[i],  // ← BRITTLE: assumes order matches
+       symbol: detail.symbol,  // ← from RunDetail response
        detail,
        timeseries,
        initialCapital: parseFloat(state.capital),
      };
    })
  );
```

---

## Stage 2E: BatchResultsDashboard with Real Data

The `BatchResultsDashboard` component and `batchResultsStore` already exist with a complete UI. The `aggregateBatchResults()` function in `lib/batch-utils.ts` already maps API data → store shape.

**Verify these mappings work:**

1. `aggregateBatchResults()` receives `{symbol, detail, timeseries, initialCapital}[]`
2. It produces `BatchResultsState` with:
   - `totalPnL`, `totalPnLPct`, `portfolioSharpe`
   - `symbolResults[]` with per-symbol PnL, win rate, equity curves
   - `portfolioEquityCurve` (aggregated)
   - `correlationMatrix` (currently empty — future enhancement)

**Only change needed:** The drill-down flow in `BatchResultsDashboard` — when user clicks a symbol, it hydrates `resultsStore` with that symbol's data. This already works via `SingleResultHydrator`.

---

## Stage 2F-G: Preset Management

### New Store: `stores/presetStore.ts` [NEW]

```typescript
import { create } from "zustand";
import { apiFetch } from "../api/client";
import { toast } from "sonner";

interface Preset {
  id: number;
  name: string;
  strategy: string;
  config: Record<string, unknown>;
  created_at: string;
}

interface PresetState {
  presets: Preset[];
  isLoading: boolean;

  fetchPresets: (strategy?: string) => Promise<void>;
  savePreset: (name: string) => Promise<void>;
  loadPreset: (preset: Preset) => void;
  deletePreset: (id: number) => Promise<void>;
}

export const usePresetStore = create<PresetState>()((set, get) => ({
  presets: [],
  isLoading: false,

  fetchPresets: async (strategy) => {
    set({ isLoading: true });
    try {
      const qs = strategy ? `?strategy=${strategy}` : "";
      const presets = await apiFetch<Preset[]>(`/api/presets${qs}`);
      set({ presets, isLoading: false });
    } catch {
      set({ isLoading: false });
    }
  },

  savePreset: async (name) => {
    const { useBacktestStore } = await import("./backtestStore");
    const state = useBacktestStore.getState();

    await apiFetch("/api/presets", {
      method: "POST",
      body: JSON.stringify({
        name,
        strategy: state.strategy,
        config: {
          symbol: state.symbol,
          timeframe: state.timeframe,
          leverage: state.leverage,
          capital: state.capital,
          riskPercent: state.riskPercent,
          params: state.params,
          startDate: state.startDate,
          endDate: state.endDate,
        },
      }),
    });

    toast.success(`Preset "${name}" saved`);
    get().fetchPresets(state.strategy);
  },

  loadPreset: async (preset) => {
    const { useBacktestStore } = await import("./backtestStore");
    const store = useBacktestStore.getState();

    const c = preset.config;
    if (c.symbol) store.setSymbol(c.symbol as string);
    if (c.timeframe) store.setTimeframe(c.timeframe as string);
    if (c.leverage) store.setLeverage(String(c.leverage));
    if (c.capital) store.setCapital(String(c.capital));
    if (c.params) {
      Object.entries(c.params as Record<string, unknown>).forEach(([k, v]) => {
        store.setParam(k, v);
      });
    }

    toast.success(`Loaded preset "${preset.name}"`);
  },

  deletePreset: async (id) => {
    await apiFetch(`/api/presets/${id}`, { method: "DELETE" });
    set((s) => ({ presets: s.presets.filter((p) => p.id !== id) }));
    toast.success("Preset deleted");
  },
}));
```

### Preset UI in Sidebar

**File:** `components/sidebar/PresetManager.tsx` [NEW]

Add a collapsible "Presets" section below the strategy selector:

```typescript
// In Sidebar.tsx — new section
<CollapsibleSection title="Presets">
  <PresetManager />
</CollapsibleSection>
```

The `PresetManager` component shows a list of saved presets with load/delete buttons and a "Save Current" input.

---

## Phase 3 — Quant Tools: DESCOPED

> **Status:** Phase 3 is descoped from this integration effort.
>
> **Reason:** The backend has **no** grid search, walk-forward, or sensitivity endpoints. The `app/backtest/optimization/` directory is empty (placeholder `__init__.py` only). The frontend has complete UI components and stores (`gridSearchStore`, `walkForwardStore`, `sensitivityStore`, `api/quant.ts`), but the backend API routes they call (`POST /api/grid-search`, `POST /api/walk-forward`, `POST /api/sensitivity`) do not exist.
>
> **What would be needed:** Building three complete optimization engines + API routes + SSE integration from scratch. This is a standalone project (~30-40h), not a "verify/fix" task.
>
> **Frontend readiness:** The stores and components are already wired to the correct API endpoints. Once the backend routes are built, the frontend should work with minimal changes (verify SSE event payloads match store expectations).
>
> **Preserved API contracts:** The expected request/response formats from the frontend stores are documented below for reference when the backend is eventually built.

### Expected API Contracts (for future backend implementation)

**Grid Search:**
- Endpoint: `POST /api/grid-search`
- Request: `{symbol, timeframe, strategy, start_date, end_date, initial_capital, leverage, risk_per_trade_pct, grid_params: {param_name: [values]}}`
- SSE events: `progress` (with `best_result`), `failed_node`, `complete` (with `results[]`)
- Complete payload: `{results: [{params: {}, metrics: {net_profit, sharpe, win_rate, ...}}]}`

**Walk-Forward:**
- Endpoint: `POST /api/walk-forward`
- Request: `{...base_config, walk_forward_params: {param_name, values, window_size, oos_size, metric}}`
- SSE events: `progress`, `skipped_window`, `complete` (with `windows[]`)
- Complete payload: `{windows: [{is_start_date, is_end_date, oos_start_date, oos_end_date, best_param, is_metric_value, oos_return_pct, status}]}`

**Sensitivity:**
- Endpoint: `POST /api/sensitivity`
- Request: `{...base_config, variations: {param: [low, base, high]}}`
- SSE events: `progress`, `complete` (with `results[]`)
- Complete payload: `{results: [{param_name, low_value, base_value, high_value, low_metric, base_metric, high_metric, low_impact_pct, high_impact_pct, total_impact, sensitivity}]}`

---

## Phase 4 — Polish & Infrastructure

### Stage 4A: Configurable Concurrency

**Backend:** `GET/PUT /api/settings/concurrency` — rejects with 409 if jobs running (see `spec_api_contracts.md`).

**Frontend:** Add to Settings modal:

```typescript
const [maxWorkers, setMaxWorkers] = useState(2);

useEffect(() => {
  apiFetch<{max_workers: number}>("/api/settings/concurrency")
    .then(r => setMaxWorkers(r.max_workers));
}, []);

const handleSave = async () => {
  try {
    await apiFetch("/api/settings/concurrency", {
      method: "PUT",
      body: JSON.stringify({ max_workers: maxWorkers })
    });
    toast.success("Concurrency updated");
  } catch (err: any) {
    if (err?.status === 409) {
      toast.error("Cannot change while backtests are running");
    }
  }
};
```

### Stage 4B: History Page Wiring

`historyStore` already calls `fetchHistory()` and `apiDeleteRun()`. Currently working but needs:

1. **Auto-fetch on mount**
2. **Refetch on filter/page change** with debounce on search input

```typescript
// components/history/RunHistory.tsx
import { useDebouncedValue } from "../hooks/useDebouncedValue";

const { fetchRuns, filters, currentPage } = useHistoryStore();
const debouncedSearch = useDebouncedValue(filters.searchQuery, 300);

useEffect(() => {
  fetchRuns();
}, [filters.strategy, filters.symbol, filters.dateRange,
    filters.profitableOnly, debouncedSearch, currentPage]);
```

**Note:** If `useDebouncedValue` hook doesn't exist, create a simple one:

```typescript
function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}
```

### Stage 4C: Trade Deep-Dive (Deferred from Phase 1)

The `TradeDeepDive` component already calls `getTradeChart(tradeId)` which hits `GET /api/trades/{id}/chart`.

**Backend needs:** Endpoint that returns OHLCV candles around a trade's entry/exit with indicator values overlaid. This endpoint does not currently exist — needs to be built.

### Stage 4D: Export with Real Data

Export functionality (`ExportDropdown`, `ExportConfigModal`) already works with `resultsStore` data. Once `resultsStore` has real data (Phase 1), exports work automatically.

**No changes needed** — just verify that `html2canvas` correctly captures the LightweightCharts canvas elements for PNG/PDF export.

---

## Complete File Manifest (Phase 1-2 + Phase 4)

### New Files
| File | Phase | Purpose |
|------|-------|---------|
| `components/sidebar/DynamicParamForm.tsx` | 1 | Schema-driven param form |
| `components/layout/FloatingProgressPill.tsx` | 1 | Collapsible progress widget |
| `components/sidebar/PresetManager.tsx` | 2 | Preset save/load UI |
| `stores/presetStore.ts` | 2 | Preset CRUD state |

### Modified Files
| File | Phase | Changes |
|------|-------|---------|
| `stores/backtestStore.ts` | 1+2 | Dynamic params, batch via existing endpoint, recovery |
| `api/backtest.ts` | 1 | Download events in `streamProgress` |
| `api/client.ts` | 1 | SSE auto-reconnect |
| `components/layout/Sidebar.tsx` | 1+2 | DynamicParamForm, PresetManager |
| `components/layout/MobileSidebarSheet.tsx` | 1 | Same DynamicParamForm replacement |
| `App.tsx` | 1 | FloatingProgressPill, recovery hook, loadStrategies |
| `lib/validation.ts` | 1 | Schema-aware validation |
| `types/generated.ts` | 1 | param_schema types |
| `components/history/RunHistory.tsx` | 4 | Auto-fetch on mount with debounced search |

### Untouched Files (Already Work Once Data Is Real)
| File | Reason |
|------|--------|
| `components/results/ResultsDashboard.tsx` | Reads from resultsStore — works when data is real |
| `components/results/HeroStats.tsx` | Same |
| `components/results/MetricsGrid.tsx` | Same |
| `components/results/EquityUnderwaterChart.tsx` | Same |
| `components/results/TradesTable.tsx` | Same |
| `components/results/ExitReasonsChart.tsx` | Same |
| `components/results/batch/*` | Works once batchResultsStore has real data |
| `lib/batch-utils.ts` | Already maps API → store |
| `lib/export-utils.ts` | Works with real resultsStore data |

### Deferred (Phase 3 — Descoped)
| File | Status |
|------|--------|
| `components/GridSearch.tsx` | Frontend ready, backend not built |
| `components/WalkForward.tsx` | Frontend ready, backend not built |
| `components/Sensitivity.tsx` | Frontend ready, backend not built |
| `stores/gridSearchStore.ts` | Wired to non-existent endpoints |
| `stores/walkForwardStore.ts` | Wired to non-existent endpoints |
| `stores/sensitivityStore.ts` | Wired to non-existent endpoints |
| `api/quant.ts` | API functions ready, endpoints don't exist |

---

## Revised Timeline

| Phase | Scope | Backend | Frontend | Total |
|-------|-------|---------|----------|-------|
| **1** | Single backtest E2E | ~8h | ~12h | ~20h |
| **2** | Batch + Portfolio + Presets | ~7.5h | ~6h | ~13.5h |
| **3** | ~~Quant tools~~ | **Descoped** | **Descoped** | **—** |
| **4** | Polish + infrastructure | ~4h | ~4h | ~8h |
| | | | **Subtotal** | **~41.5h** |
| | | | +20% contingency | **~50h** |
