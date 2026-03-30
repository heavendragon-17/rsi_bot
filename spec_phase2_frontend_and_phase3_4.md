# RSI Bot — Phase 2 Frontend + Phase 3-4 Spec

## Phase 2 Frontend Scope

Wire batch and portfolio modes, preset management, BatchResultsDashboard with real data.

---

## Stage 2C: Wire Batch Mode

### New API Function: `startBatch()`

**File:** `api/backtest.ts`

```typescript
export interface BatchStartResponse {
  batch_id: number;
  run_ids: number[];
  status: string;
}

export async function startBatch(
  params: Omit<BacktestRequest, "symbol"> & { symbols: string[] }
): Promise<BatchStartResponse> {
  return apiFetch<BatchStartResponse>("/api/backtest/batch", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function streamBatchProgress(
  batchId: number,
  onProgress: (data: { pct: number; symbol: string; completed: number; total: number }) => void,
  onSymbolComplete: (data: { symbol: string; run_id: number }) => void,
  onComplete: (data: { batch_id: number; run_ids: number[] }) => void,
  onError: (message: string) => void,
): () => void {
  return apiSSE(
    `/api/backtest/batch/${batchId}/progress`,
    (eventName, data) => {
      if (eventName === "batch_progress") onProgress(data as any);
      else if (eventName === "batch_symbol_complete") onSymbolComplete(data as any);
      else if (eventName === "batch_complete") onComplete(data as any);
      else if (eventName === "error") onError((data as any)?.message ?? "Batch error");
    },
    () => onError("SSE connection lost"),
  );
}
```

### Add SSE event types to client.ts:

```typescript
// api/client.ts — add to event listener list
for (const eventName of [
  "progress", "complete", "error",
  "download_progress", "download_complete",
  "batch_progress", "batch_symbol_complete", "batch_complete",  // ← NEW
]) {
```

### backtestStore Batch Flow:

```typescript
runBacktest: async () => {
  const state = get();

  if (state.mode === "batch") {
    // --- BATCH MODE ---
    set({ isRunning: true, runProgress: 0, runPhase: "backtest" });

    const symbols = state.portfolioInput
      .split("\n").map(s => s.trim()).filter(Boolean);

    try {
      const { batch_id, run_ids } = await startBatch({
        symbols,
        timeframe: state.timeframe,
        strategy: state.strategy,
        start_date: format(parse(state.startDate, "dd-MM-yyyy", new Date()), "yyyy-MM-dd"),
        end_date: format(parse(state.endDate, "dd-MM-yyyy", new Date()), "yyyy-MM-dd"),
        initial_capital: state.capital,
        leverage: parseInt(state.leverage),
        risk_per_trade_pct: (parseFloat(state.riskPercent) / 100).toFixed(4),
        params: state.params,
      });

      localStorage.setItem("activeBatchId", String(batch_id));

      await new Promise<void>((resolve, reject) => {
        const completedRunIds: number[] = [];

        const cleanup = streamBatchProgress(
          batch_id,
          (data) => set({ runProgress: data.pct }),
          (data) => completedRunIds.push(data.run_id),
          async (data) => {
            cleanup();

            // Fetch all results
            const allResults = await Promise.all(
              data.run_ids.map(async (runId, i) => {
                const [detail, timeseries] = await Promise.all([
                  getRunDetail(runId),
                  getTimeseries(runId),
                ]);
                return {
                  symbol: symbols[i],
                  detail,
                  timeseries,
                  initialCapital: parseFloat(state.capital),
                };
              })
            );

            const { aggregateBatchResults } = await import("../lib/batch-utils");
            const aggregated = aggregateBatchResults(allResults);

            const { useBatchResultsStore } = await import("./batchResultsStore");
            useBatchResultsStore.getState().setBatchResults({
              ...aggregated,
              symbols,
              allocationMode: "equal_weight",
            });

            set({ mode: "batch" });
            localStorage.removeItem("activeBatchId");
            resolve();
          },
          (msg) => {
            cleanup();
            toast.error(msg);
            reject(new Error(msg));
          },
        );
      });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Batch failed");
    } finally {
      set({ isRunning: false, runProgress: 0 });
    }
    return;
  }

  if (state.mode === "portfolio") {
    // --- PORTFOLIO MODE ---
    // (same as current code — single run_id, symbols array)
    // ... existing portfolio flow ...
    return;
  }

  // --- SINGLE MODE (Phase 1) ---
  // ... existing single flow ...
},
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
   - `correlationMatrix` (currently empty — Phase 4 enhancement)

**Only change needed:** The drill-down flow in `BatchResultsDashboard` — when user clicks a symbol, it hydrates `resultsStore` with that symbol's data. This already works via `SingleResultHydrator`.

---

## Stage 2F-G: Preset Management

### New Store: `presetStore.ts`

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

  loadPreset: (preset) => {
    const { useBacktestStore } = require("./backtestStore");
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

Add a collapsible "Presets" section below the strategy selector:

```typescript
// In Sidebar.tsx — new section
<CollapsibleSection title="Presets">
  <PresetManager />
</CollapsibleSection>
```

The `PresetManager` component shows a list of saved presets with load/delete buttons and a "Save Current" input.

---

## Phase 3 — Quant Tools Wiring

### Stage 3A: Verify Backend Endpoints

The following endpoints already exist (used by `api/quant.ts`):
- `POST /api/grid-search` → returns `{run_id, status}`
- `POST /api/walk-forward` → returns `{run_id, status}`
- `POST /api/sensitivity` → returns `{run_id, status}`

All stream progress via `GET /api/backtest/{run_id}/progress`.

**Backend verification checklist:**
- [ ] Grid search endpoint accepts `grid_params: {param_name: [values]}` format
- [ ] Walk-forward endpoint accepts `walk_forward_params` with IS/OOS config
- [ ] Sensitivity endpoint accepts `variations: {param: [low, base, high]}` format
- [ ] All emit `progress` SSE events with correct `pct` values
- [ ] All emit `complete` with structured `results` payload
- [ ] Grid search complete payload has `results[]` with per-node metrics
- [ ] Walk-forward complete payload has `windows[]` with IS/OOS per window
- [ ] Sensitivity complete payload has `results[]` with per-param impact

### Stage 3B: Wire gridSearchStore

The `gridSearchStore` already calls `startGridSearch()` and `streamQuantProgress()`. The SSE handler already parses `data.results` into the 2D heatmap array.

**Changes needed:**
1. Verify the `complete` payload matches what the store expects
2. Handle `failed_node` SSE events for individual grid nodes that errored
3. Handle `skipped_window` events (walk-forward only)

### Stage 3C: Wire walkForwardStore

Same pattern — already calls `startWalkForward()` + `streamQuantProgress()`. The `complete` handler maps `data.windows` to `WalkForwardWindow[]`.

**Key verification:** The backend walk-forward response must include per-window:
```json
{
  "windows": [
    {
      "is_start_date": "2024-01-01",
      "is_end_date": "2024-03-01",
      "oos_start_date": "2024-03-01",
      "oos_end_date": "2024-04-01",
      "best_param": 14,
      "is_metric_value": 1.35,
      "oos_return_pct": 3.2,
      "status": "success"
    }
  ]
}
```

### Stage 3D: Wire sensitivityStore

Same pattern — calls `startSensitivity()` + `streamQuantProgress()`.

**Backend response must include:**
```json
{
  "results": [
    {
      "param_name": "rsi_period",
      "low_value": 11,
      "base_value": 14,
      "high_value": 17,
      "low_metric": 850,
      "base_metric": 1200,
      "high_metric": 1050,
      "low_impact_pct": -29.2,
      "high_impact_pct": -12.5,
      "total_impact": 41.7,
      "sensitivity": "high"
    }
  ]
}
```

---

## Phase 4 — Polish & Infrastructure

### Stage 4A: Configurable Concurrency

**Backend:** `GET/PUT /api/settings/concurrency` (see `spec_api_contracts.md`)

**Frontend:** Add to Settings modal:

```typescript
// In ThemeSettings.tsx or new SettingsPanel
const [maxWorkers, setMaxWorkers] = useState(2);

useEffect(() => {
  apiFetch<{max_workers: number}>("/api/settings/concurrency")
    .then(r => setMaxWorkers(r.max_workers));
}, []);

const handleSave = async () => {
  await apiFetch("/api/settings/concurrency", {
    method: "PUT",
    body: JSON.stringify({ max_workers: maxWorkers })
  });
  toast.success("Concurrency updated");
};
```

### Stage 4B: History Page Wiring

`historyStore` already calls `fetchHistory()` and `apiDeleteRun()`. Currently working but needs:

1. **Auto-fetch on mount:** Add `useEffect` in `RunHistory` to call `fetchRuns()`.
2. **Refetch on filter/page change:** Add `useEffect` watching `filters` and `currentPage`.

```typescript
// components/history/RunHistory.tsx
const { fetchRuns, filters, currentPage } = useHistoryStore();

useEffect(() => {
  fetchRuns();
}, [filters.strategy, filters.symbol, filters.dateRange,
    filters.profitableOnly, filters.searchQuery, currentPage]);
```

### Stage 4C: Trade Deep-Dive (Deferred from Phase 1)

The `TradeDeepDive` component already calls `getTradeChart(tradeId)` which hits `GET /api/trades/{id}/chart`.

**Backend needs:** Endpoint that returns OHLCV candles around a trade's entry/exit with indicator values overlaid.

This is already partially implemented — verify the endpoint returns the expected `ChartCandle[]` shape.

### Stage 4D: Export with Real Data

Export functionality (`ExportDropdown`, `ExportConfigModal`) already works with `resultsStore` data. Once `resultsStore` has real data (Phase 1), exports work automatically.

**No changes needed** — just verify that `html2canvas` correctly captures the LightweightCharts canvas elements for PNG/PDF export.

---

## Complete File Manifest (All Phases)

### New Files
| File | Phase | Purpose |
|------|-------|---------|
| `components/sidebar/DynamicParamForm.tsx` | 1 | Schema-driven param form |
| `components/layout/FloatingProgressPill.tsx` | 1 | Collapsible progress widget |
| `components/sidebar/PresetManager.tsx` | 2 | Preset save/load UI |
| `stores/presetStore.ts` | 2 | Preset CRUD state |
| `api/presets.ts` | 2 | Preset API functions |

### Modified Files
| File | Phase | Changes |
|------|-------|---------|
| `stores/backtestStore.ts` | 1+2 | Dynamic params, batch flow, recovery |
| `api/backtest.ts` | 1+2 | Download events, batch API, batch SSE |
| `api/client.ts` | 1 | SSE auto-reconnect, batch events |
| `api/index.ts` | 2 | Export new functions |
| `components/layout/Sidebar.tsx` | 1 | DynamicParamForm, remove hardcoded params |
| `components/layout/MobileSidebarSheet.tsx` | 1 | Same |
| `App.tsx` | 1 | FloatingProgressPill, recovery hook |
| `lib/validation.ts` | 1 | Schema-aware validation |
| `types/generated.ts` | 1 | param_schema types |
| `stores/resultsStore.ts` | 1 | Verify mapping fields |
| `components/history/RunHistory.tsx` | 4 | Auto-fetch on mount |

### Untouched Files (Already Work)
| File | Reason |
|------|--------|
| `components/results/ResultsDashboard.tsx` | Reads from resultsStore — works when data is real |
| `components/results/HeroStats.tsx` | Same |
| `components/results/MetricsGrid.tsx` | Same |
| `components/results/EquityUnderwaterChart.tsx` | Same |
| `components/results/TradesTable.tsx` | Same |
| `components/results/ExitReasonsChart.tsx` | Same |
| `components/results/batch/*` | Works once batchResultsStore has real data |
| `components/GridSearch.tsx` | Already wired to gridSearchStore |
| `components/WalkForward.tsx` | Already wired to walkForwardStore |
| `components/Sensitivity.tsx` | Already wired to sensitivityStore |
| `lib/batch-utils.ts` | Already maps API → store |
| `lib/export-utils.ts` | Works with real resultsStore data |

---

## Estimated Timeline

| Phase | Scope | Backend | Frontend | Total |
|-------|-------|---------|----------|-------|
| **1** | Single backtest E2E | ~12h | ~16h | ~28h |
| **2** | Batch + Portfolio + Presets | ~10h | ~8h | ~18h |
| **3** | Quant tools wiring | ~4h (verify) | ~4h (verify) | ~8h |
| **4** | Polish + infrastructure | ~4h | ~4h | ~8h |
| | | | **Grand Total** | **~62h** |
