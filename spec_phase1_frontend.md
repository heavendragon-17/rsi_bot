# RSI Bot — Phase 1 Frontend Spec

## Scope

Wire the UI to run a single backtest end-to-end: load strategies from API, render dynamic param forms, run backtest via API, show SSE progress (download + backtest) in floating pill, render real results in ResultsDashboard.

**Key principle:** The existing `backtestStore.runBacktest()` already handles single/batch/portfolio modes and calls the right API functions. Changes should be **surgical diffs**, not full rewrites.

---

## Stage 1C: Wire backtestStore to Real API

### Current State

`backtestStore.runBacktest()` already:
1. Calls `startBacktest()` → gets `run_id`
2. Opens SSE via `streamProgress()`
3. On complete: fetches `getRunDetail()` + `getTimeseries()`
4. Maps via `mapApiToResults()` → pushes to `resultsStore`

**This is ~90% correct.** Three fixes needed:

### Fix 1: Strategy Params — Replace Hardcoded DEFAULT_PARAMS

**Problem:** `DEFAULT_PARAMS` uses wrong keys (`ema_fast` vs `rsi_ema_length`, `tp1_rr` vs `nr_tp1_rr`).

**Diff — `stores/backtestStore.ts`:**

```diff
- const DEFAULT_PARAMS = {
-   rsi_period: 14,
-   ema_fast: 9,
-   ema_slow: 21,
-   tp1_rr: 1.5,
-   tp2_rr: 3.0,
-   sl_buffer_pct: 1.0,
-   overbought: 70,
-   oversold: 30,
- };

  // DEFAULT_PARAMS removed — params come from API's default_config
```

**Add new state fields:**

```diff
  interface BacktestState {
    // ... existing fields ...
+   currentParamSchema: JSONSchema | null;
+   runPhase: "idle" | "download" | "backtest";
+   downloadProgress: number;
+   backtestProgress: number;
  }
```

**Initial state changes:**

```diff
- params: { ...DEFAULT_PARAMS },
+ params: {},  // Populated by loadStrategies()
+ currentParamSchema: null,
+ runPhase: "idle",
+ downloadProgress: 0,
+ backtestProgress: 0,
```

**Enhance `loadStrategies()` — set schema + defaults for current strategy:**

```diff
  loadStrategies: async () => {
    const strategies = await fetchStrategies();
    set({ availableStrategies: strategies });

-   // (currently does nothing with default_config)
+   const current = strategies.find(s => s.name === get().strategy);
+   if (current) {
+     set({
+       currentParamSchema: current.param_schema,
+       params: { ...current.default_config },
+     });
+   }
  },
```

**Enhance `setStrategy()` — rebuild params on strategy change:**

```diff
- setStrategy: (strategy) => set({ strategy }),
+ setStrategy: (strategy) => {
+   const strat = get().availableStrategies.find(s => s.name === strategy);
+   set({
+     strategy,
+     currentParamSchema: strat?.param_schema || null,
+     params: strat?.default_config ? { ...strat.default_config } : {},
+   });
+ },
```

**Update `resetParams()` — reset to strategy defaults, not hardcoded:**

```diff
  resetParams: () => {
+   const strat = get().availableStrategies.find(s => s.name === get().strategy);
    set({
-     params: { ...DEFAULT_PARAMS },
+     params: strat?.default_config ? { ...strat.default_config } : {},
      capital: "10000",
      leverage: "1",
      riskPercent: "1",
    });
  },
```

### Fix 2: Date Format

Store sends dates as `dd-MM-yyyy`, API expects `yyyy-MM-dd`.

**Current code already handles this** via `parse(state.startDate, "dd-MM-yyyy", new Date())` + `format(startDate, "yyyy-MM-dd")`. **No change needed — verify only.**

### Fix 3: Simplify DataPrepModal Integration

Since download is now inline (server-side), the run flow no longer needs to check data status.

**Diff — `Sidebar.tsx` or `RunButton.tsx` (wherever `handleRunRequest` lives):**

```diff
  handleRunRequest = async () => {
    if (!validateAllParams()) return;

-   // Check data availability first
-   const status = await checkDataStatus(symbol, timeframe);
-   if (!status.available) {
-     openDataPrepModal();
-     return;
-   }

    await runBacktest();
  };
```

The DataPrepModal remains available for manual data management but is no longer required before running.

---

## Stage 1D: SSE Progress with Download Phase

### SSE Client — No Changes

`apiSSE()` in `client.ts` already listens for:
```typescript
["progress", "complete", "error", "download_progress", "download_complete"]
```

### streamProgress() — Add Phase Parameter

**Diff — `api/backtest.ts`:**

```diff
  export function streamProgress(
    runId: number,
-   onProgress: (pct: number) => void,
+   onProgress: (pct: number, phase?: "download" | "backtest") => void,
    onComplete: (data: { run_id: number; status: string }) => void,
    onError: (message: string) => void,
  ): () => void {
    return apiSSE(
      `/api/backtest/${runId}/progress`,
      (eventName, data) => {
-       if (eventName === "progress") {
+       if (eventName === "download_progress") {
+         const d = data as { pct?: number };
+         onProgress(d.pct ?? 0, "download");
+       } else if (eventName === "download_complete") {
+         onProgress(100, "download");
+       } else if (eventName === "progress") {
          const d = data as { pct?: number };
-         onProgress(d.pct ?? 0);
+         onProgress(d.pct ?? 0, "backtest");
        } else if (eventName === "complete") {
```

### backtestStore — Phase-Aware Progress

**Diff — inside `runBacktest()` SSE callback:**

```diff
  const cleanup = streamProgress(
    run_id,
-   (pct) => set({ runProgress: pct }),
+   (pct, phase) => {
+     if (phase === "download") {
+       set({ runPhase: "download", downloadProgress: pct, runProgress: pct * 0.3 });
+     } else {
+       set({ runPhase: "backtest", backtestProgress: pct, runProgress: 30 + pct * 0.7 });
+     }
+   },
    // ... rest unchanged
  );
```

Download = 30% of perceived progress, backtest = 70%.

---

## Stage 1E: Dynamic Strategy Param Form

### New Component: `components/sidebar/DynamicParamForm.tsx` [NEW]

New `components/sidebar/` directory for sidebar-specific sub-components. `DynamicParamForm` replaces the hardcoded param inputs in `Sidebar.tsx`.

**Loading state:** Shows a skeleton until `loadStrategies()` completes and `currentParamSchema` is populated. No fallback params needed — the form is simply not rendered until the schema is available.

```typescript
// components/sidebar/DynamicParamForm.tsx
import React from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { CollapsibleSection } from "../ui/CollapsibleSection";
import { ValidatedInput } from "../ui/ValidatedInput";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Switch } from "../ui/switch";
import { RotateCcw } from "lucide-react";

export const DynamicParamForm: React.FC = () => {
  const { currentParamSchema, params, setParam, resetParams } = useBacktestStore();

  // Loading skeleton while schema loads
  if (!currentParamSchema?.properties) {
    return (
      <div className="space-y-3 p-4">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="space-y-1.5 animate-pulse">
            <div className="h-3 w-24 bg-bg-elevated rounded" />
            <div className="h-8 w-full bg-bg-elevated rounded" />
          </div>
        ))}
      </div>
    );
  }

  const schema = currentParamSchema;
  const groups = schema.ui_groups || {};
  const properties = schema.properties;

  // Group params
  const groupedParams: Record<string, [string, any][]> = {};

  for (const [key, prop] of Object.entries(properties)) {
    if (prop.ui_hidden) continue;
    const group = prop.ui_group || "__ungrouped__";
    if (!groupedParams[group]) groupedParams[group] = [];
    groupedParams[group].push([key, prop]);
  }

  // Sort groups by order
  const sortedGroupKeys = Object.keys(groups).sort(
    (a, b) => (groups[a].order || 0) - (groups[b].order || 0)
  );

  // Add ungrouped at end
  if (groupedParams["__ungrouped__"]) {
    sortedGroupKeys.push("__ungrouped__");
    groups["__ungrouped__"] = { title: "Other", order: 999 };
  }

  return (
    <>
      {sortedGroupKeys.map((groupKey) => {
        const groupMeta = groups[groupKey];
        const groupParams = (groupedParams[groupKey] || [])
          .sort(([, a], [, b]) => (a.ui_order || 0) - (b.ui_order || 0));

        if (groupParams.length === 0) return null;

        return (
          <CollapsibleSection
            key={groupKey}
            title={groupMeta.title}
            headerAction={
              groupKey === sortedGroupKeys[0] ? (
                <button
                  onClick={(e) => { e.stopPropagation(); resetParams(); }}
                  className="p-1 hover:bg-bg-elevated rounded text-text-muted hover:text-text-primary transition-colors"
                  title="Reset to Defaults"
                >
                  <RotateCcw size={12} />
                </button>
              ) : undefined
            }
          >
            <div className="space-y-3">
              {groupParams.map(([paramName, prop]) => (
                <ParamInput
                  key={paramName}
                  name={paramName}
                  prop={prop}
                  value={params[paramName]}
                  onChange={(v) => setParam(paramName, v)}
                />
              ))}
            </div>
          </CollapsibleSection>
        );
      })}
    </>
  );
};

// Individual param input renderer
const ParamInput: React.FC<{
  name: string;
  prop: any;
  value: unknown;
  onChange: (value: unknown) => void;
}> = ({ name, prop, value, onChange }) => {
  if (prop.type === "boolean") {
    return (
      <div className="flex items-center justify-between">
        <label className="text-xs font-medium text-text-secondary">
          {prop.title}
        </label>
        <Switch
          checked={Boolean(value)}
          onCheckedChange={onChange}
        />
      </div>
    );
  }

  if (prop.enum) {
    return (
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-text-secondary">
          {prop.title}
        </label>
        <Select value={String(value)} onValueChange={onChange}>
          <SelectTrigger className="w-full bg-input/50 border-border-main">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {prop.enum.map((opt: string) => (
              <SelectItem key={opt} value={opt}>{opt}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    );
  }

  // Number / Integer input
  return (
    <ValidatedInput
      label={prop.title}
      paramKey={name}
      value={String(value ?? prop.default ?? "")}
      onChangeValue={(v) => {
        const num = prop.type === "integer" ? parseInt(v) : parseFloat(v);
        if (!isNaN(num)) onChange(num);
        else onChange(v);
      }}
      suffix={prop.ui_suffix}
    />
  );
};
```

### Sidebar.tsx — Replace Hardcoded Params

**Diff:**

```diff
+ import { DynamicParamForm } from "../sidebar/DynamicParamForm";

- {/* Parameters */}
- <CollapsibleSection
-   title="Parameters"
-   headerAction={
-     <button onClick={(e) => { e.stopPropagation(); resetParams(); }}
-       className="p-1 hover:bg-bg-elevated rounded text-text-muted hover:text-text-primary transition-colors"
-       title="Reset to Defaults">
-       <RotateCcw size={12} />
-     </button>
-   }
- >
-   <div className="space-y-3">
-     <ValidatedInput label="RSI Period" paramKey="rsi_period" ... />
-     <ValidatedInput label="EMA Fast" paramKey="ema_fast" ... />
-     <ValidatedInput label="EMA Slow" paramKey="ema_slow" ... />
-     <ValidatedInput label="TP1 Risk Ratio" paramKey="tp1_rr" ... />
-     <ValidatedInput label="SL Buffer" paramKey="sl_buffer_pct" ... />
-   </div>
- </CollapsibleSection>

+ <DynamicParamForm />
```

Same replacement in `MobileSidebarSheet.tsx` — import `DynamicParamForm` and replace the hardcoded params section.

### Validation — Schema-Driven

**Diff — `lib/validation.ts`:**

```diff
+ // Schema-aware validation (used by DynamicParamForm)
+ export const validateFromSchema = (
+   key: string,
+   value: string,
+   schema?: any
+ ): ValidationResult => {
+   if (value === "") return { isValid: false, error: "Required" };
+
+   const prop = schema?.properties?.[key];
+   if (!prop) {
+     const n = parseFloat(value);
+     if (isNaN(n)) return { isValid: false, error: "Must be a number" };
+     return { isValid: true, error: null };
+   }
+
+   const n = prop.type === "integer" ? parseInt(value) : parseFloat(value);
+
+   if (prop.type === "integer" || prop.type === "number") {
+     if (isNaN(n)) return { isValid: false, error: `${prop.title} must be a number` };
+     if (prop.minimum !== undefined && n < prop.minimum)
+       return { isValid: false, error: `Min: ${prop.minimum}` };
+     if (prop.maximum !== undefined && n > prop.maximum)
+       return { isValid: false, error: `Max: ${prop.maximum}` };
+   }
+
+   return { isValid: true, error: null };
+ };
```

The existing hardcoded `validateParam()` remains for non-strategy fields (`leverage`, `capital`, `risk_percent`).

---

## Stage 1F: Floating Progress Pill

### New Component: `components/layout/FloatingProgressPill.tsx` [NEW]

Collapsible pill showing active backtest progress. Appears when `isRunning` is true.

```typescript
// components/layout/FloatingProgressPill.tsx
import React, { useState } from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { motion, AnimatePresence } from "motion/react";
import { ChevronDown, ChevronUp, Download, Activity } from "lucide-react";
import { cn } from "../../lib/utils";

export const FloatingProgressPill: React.FC = () => {
  const {
    isRunning, runProgress, runPhase,
    downloadProgress, backtestProgress,
    cancelBacktest,
  } = useBacktestStore();
  const [expanded, setExpanded] = useState(false);

  if (!isRunning) return null;

  return (
    <motion.div
      initial={{ y: 100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      exit={{ y: 100, opacity: 0 }}
      className="fixed bottom-6 right-6 z-50"
    >
      <div className={cn(
        "bg-bg-surface/95 backdrop-blur-xl border border-accent-main/30",
        "shadow-2xl shadow-accent-main/10 rounded-2xl overflow-hidden",
        "transition-all duration-300",
        expanded ? "w-80" : "w-56"
      )}>
        {/* Header */}
        <div
          className="flex items-center justify-between px-4 py-3 cursor-pointer"
          onClick={() => setExpanded(!expanded)}
        >
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-accent-main animate-pulse" />
            <span className="text-xs font-medium text-text-primary">
              {runPhase === "download" ? "Downloading..." : "Running..."}
            </span>
            <span className="text-xs font-mono text-accent-main">
              {Math.round(runProgress)}%
            </span>
          </div>
          {expanded ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
        </div>

        {/* Progress Bar */}
        <div className="px-4 pb-2">
          <div className="h-1.5 bg-bg-elevated rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-accent-main rounded-full"
              animate={{ width: `${runProgress}%` }}
              transition={{ ease: "easeOut" }}
            />
          </div>
        </div>

        {/* Expanded Details */}
        <AnimatePresence>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="px-4 pb-4 space-y-3 border-t border-border-main/50 pt-3">
                <div className="flex items-center gap-2">
                  <Download size={12} className={cn(
                    runPhase === "download" ? "text-accent-main" : "text-success"
                  )} />
                  <span className="text-xs text-text-secondary flex-1">Data Download</span>
                  <span className="text-xs font-mono text-text-primary">
                    {runPhase === "download" ? `${downloadProgress}%` : "Done"}
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <Activity size={12} className={cn(
                    runPhase === "backtest" ? "text-accent-main" :
                    runPhase === "download" ? "text-text-muted" : "text-success"
                  )} />
                  <span className="text-xs text-text-secondary flex-1">Backtest</span>
                  <span className="text-xs font-mono text-text-primary">
                    {runPhase === "backtest" ? `${backtestProgress}%` :
                     runPhase === "download" ? "Waiting" : "Done"}
                  </span>
                </div>

                <button
                  onClick={(e) => { e.stopPropagation(); cancelBacktest(); }}
                  className="w-full py-1.5 text-xs text-danger hover:bg-danger/10 rounded-lg transition-colors"
                >
                  Cancel Backtest
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
};
```

### Add to App.tsx:

```diff
+ import { FloatingProgressPill } from './components/layout/FloatingProgressPill';

  return (
    <Layout>
      {/* ... existing content ... */}
      <DataPrepModal />
+     <FloatingProgressPill />
      <Toaster richColors position="bottom-right" />
    </Layout>
  );
```

---

## Stage 1G: SSE Auto-Reconnect + Page Refresh Recovery

### SSE Auto-Reconnect

**Diff — `api/client.ts`:**

```diff
  export function apiSSE(
    path: string,
    onMessage: (event: string, data: unknown) => void,
    onError?: (err: Event) => void,
+   maxRetries: number = 3,
  ): () => void {
-   const url = `${BASE_URL}${path}`;
-   const es = new EventSource(url);
+   let es: EventSource | null = null;
+   let retryCount = 0;
+   let isClosed = false;
+
+   const connect = () => {
+     if (isClosed) return;
+     es = new EventSource(`${BASE_URL}${path}`);

      // ... existing event listeners unchanged ...

-   es.onerror = (e) => onError?.(e);
+     es.onerror = (e) => {
+       if (isClosed) return;
+       es?.close();
+       if (retryCount < maxRetries) {
+         retryCount++;
+         setTimeout(connect, 1000 * retryCount);
+       } else {
+         onError?.(e);
+       }
+     };
+
+     es.onopen = () => { retryCount = 0; };
+   };
+
+   connect();

    return () => {
+     isClosed = true;
      es?.close();
    };
  }
```

### Page Refresh Recovery

**Diff — `stores/backtestStore.ts`:**

```diff
  // Inside runBacktest(), after getting run_id:
  set({ currentRunId: run_id });
+ localStorage.setItem("activeRunId", String(run_id));

  // In the finally block:
  set({ isRunning: false, runProgress: 0, currentRunId: null });
+ localStorage.removeItem("activeRunId");
```

**New action — `recoverActiveRun()` (call from App.tsx useEffect on mount):**

```typescript
recoverActiveRun: async () => {
  const activeRunId = localStorage.getItem("activeRunId");
  if (!activeRunId) return;

  const runId = parseInt(activeRunId);
  try {
    const detail = await getRunDetail(runId);

    if (detail.status === "completed") {
      const timeseries = await getTimeseries(runId);
      useResultsStore.getState().setResults(mapApiToResults(detail, timeseries));
      localStorage.removeItem("activeRunId");
      toast.success("Previous backtest completed!");
    } else if (detail.status === "running") {
      set({ isRunning: true, currentRunId: runId });
      // Reconnect SSE stream for this run_id...
    } else {
      localStorage.removeItem("activeRunId");
    }
  } catch {
    localStorage.removeItem("activeRunId");
  }
},
```

**App.tsx diff:**

```diff
+ import { useBacktestStore } from './stores/backtestStore';

  function App() {
+   const recoverActiveRun = useBacktestStore(s => s.recoverActiveRun);
+   const loadStrategies = useBacktestStore(s => s.loadStrategies);
+
+   useEffect(() => {
+     loadStrategies();
+     recoverActiveRun();
+   }, []);
```

---

## Stage 1H: Duplicate Run Warning

**Toast-based** (non-blocking, uses existing `sonner` library):

```typescript
// In handleRunRequest, before calling runBacktest():
const isDuplicate = get().recentConfigs.some(c =>
  c.symbol === state.symbol &&
  c.timeframe === state.timeframe &&
  c.strategy === state.strategy &&
  JSON.stringify(c.params) === JSON.stringify(state.params)
);

if (isDuplicate) {
  toast("Duplicate config detected", {
    action: { label: "Run Anyway", onClick: () => get().runBacktest() },
    duration: 5000,
  });
  return;  // Don't auto-run — wait for user to click "Run Anyway"
}

await runBacktest();
```

---

## Files Changed

| File | Change |
|------|--------|
| `stores/backtestStore.ts` | MODIFY — remove `DEFAULT_PARAMS`, add `currentParamSchema`/phase state, enhance `loadStrategies`/`setStrategy`/`resetParams`, add `recoverActiveRun`, phase-aware progress |
| `api/backtest.ts` | MODIFY — add `phase` param to `streamProgress` callback |
| `api/client.ts` | MODIFY — SSE auto-reconnect with retry |
| `components/sidebar/DynamicParamForm.tsx` | NEW — schema-driven param form with loading skeleton |
| `components/layout/Sidebar.tsx` | MODIFY — replace hardcoded params with `<DynamicParamForm />` |
| `components/layout/MobileSidebarSheet.tsx` | MODIFY — same replacement |
| `components/layout/FloatingProgressPill.tsx` | NEW — collapsible progress widget |
| `App.tsx` | MODIFY — add `FloatingProgressPill`, `loadStrategies()` + `recoverActiveRun()` on mount |
| `lib/validation.ts` | MODIFY — add `validateFromSchema()` (keep existing `validateParam()` for non-strategy fields) |
| `types/generated.ts` | MODIFY — add `param_schema` to `StrategyInfo`, add `JSONSchema` + `ParamSchemaProp` types |
