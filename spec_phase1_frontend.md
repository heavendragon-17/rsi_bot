# RSI Bot — Phase 1 Frontend Spec

## Scope

Wire the UI to run a single backtest end-to-end: load strategies from API, render dynamic param forms, run backtest via API, show SSE progress (download + backtest) in floating pill, render real results in ResultsDashboard.

---

## Stage 1C: Wire backtestStore to Real API

### Current State

`backtestStore.runBacktest()` already:
1. Calls `startBacktest()` → gets `run_id`
2. Opens SSE via `streamProgress()`
3. On complete: fetches `getRunDetail()` + `getTimeseries()`
4. Maps via `mapApiToResults()` → pushes to `resultsStore`

**This is ~90% correct.** The main issues are:

### Fix 1: Strategy Params Mapping

The sidebar currently sends hardcoded param keys (`rsi_period`, `ema_fast`, `ema_slow`, `tp1_rr`, `sl_buffer_pct`) that don't match the strategy dataclass field names.

**Current params in store:**
```typescript
params: {
  rsi_period: 14,    // matches
  ema_fast: 9,       // ← WRONG: dataclass has "rsi_ema_length" or "price_ema_fast"
  ema_slow: 21,      // ← WRONG: dataclass has "price_ema_slow"
  tp1_rr: 1.5,       // ← WRONG: dataclass has "nr_tp1_rr"
  sl_buffer_pct: 1.0 // matches
}
```

**Fix:** Once JSON Schema is loaded from API, params should use the actual dataclass field names. The dynamic form will handle this automatically.

**Migration path:**
1. On `loadStrategies()`, store the `param_schema` per strategy.
2. When strategy changes, rebuild `params` from `default_config`.
3. Remove hardcoded `DEFAULT_PARAMS` — replace with schema-driven defaults.

### Fix 2: Date Format

Store sends dates as `dd-MM-yyyy` strings, API expects `yyyy-MM-dd`.

**Current code already handles this** via `parse(state.startDate, "dd-MM-yyyy", new Date())` + `format(startDate, "yyyy-MM-dd")`. Verify this works.

### Fix 3: DataPrepModal Integration

The sidebar's `handleRunRequest()` currently:
1. Validates params
2. Calls `checkDataStatus()` (client-side)
3. If data missing → opens DataPrepModal for separate download
4. Then runs backtest

**Phase 1 change:** Since download is now inline (server-side), simplify this:

```typescript
handleRunRequest = async () => {
  // 1. Validate params (client-side from JSON Schema)
  if (!validateAllParams()) return;

  // 2. Just run — server handles download inline
  await runBacktest();
};
```

The DataPrepModal becomes **optional** — only used if user wants to explicitly manage data before running. The run flow no longer needs to check data status.

### backtestStore Changes

```typescript
// backtestStore.ts changes

// REMOVE: hardcoded DEFAULT_PARAMS
// REPLACE WITH: dynamic defaults from API

interface BacktestState {
  // ... existing fields ...

  // NEW: Strategy schema for dynamic form
  currentParamSchema: JSONSchema | null;

  // CHANGED: params is now dynamic shape
  params: Record<string, unknown>;
}

// loadStrategies already exists, enhance it:
loadStrategies: async () => {
  const strategies = await fetchStrategies();
  set({ availableStrategies: strategies });

  // Set param schema + defaults for current strategy
  const current = strategies.find(s => s.name === get().strategy);
  if (current) {
    set({
      currentParamSchema: current.param_schema,
      params: { ...current.default_config }
    });
  }
},

// When strategy changes:
setStrategy: (strategy) => {
  const strat = get().availableStrategies.find(s => s.name === strategy);
  set({
    strategy,
    currentParamSchema: strat?.param_schema || null,
    params: strat?.default_config ? { ...strat.default_config } : {}
  });
},

// Simplified runBacktest (no data check):
runBacktest: async () => {
  const state = get();
  set({ isRunning: true, runProgress: 0 });

  try {
    const startDate = parse(state.startDate, "dd-MM-yyyy", new Date());
    const endDate = parse(state.endDate, "dd-MM-yyyy", new Date());

    const { run_id } = await startBacktest({
      symbol: state.symbol,
      timeframe: state.timeframe,
      strategy: state.strategy,
      start_date: format(startDate, "yyyy-MM-dd"),
      end_date: format(endDate, "yyyy-MM-dd"),
      initial_capital: state.capital,
      leverage: parseInt(state.leverage) || 10,
      risk_per_trade_pct: (parseFloat(state.riskPercent) / 100).toFixed(4),
      params: state.params,  // sent as-is — matches dataclass fields
    });

    set({ currentRunId: run_id });

    // SSE connection
    await new Promise<void>((resolve, reject) => {
      const cleanup = streamProgress(
        run_id,
        (pct) => set({ runProgress: pct }),
        async () => {
          cleanup();
          const [detail, timeseries] = await Promise.all([
            getRunDetail(run_id),
            getTimeseries(run_id),
          ]);
          useResultsStore.getState().setResults(
            mapApiToResults(detail, timeseries)
          );
          set({ mode: "single" }); // switch to results view
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
    toast.error(err instanceof Error ? err.message : "Backtest failed");
  } finally {
    set({ isRunning: false, runProgress: 0, currentRunId: null });
  }
},
```

---

## Stage 1D: SSE Progress with Download Phase

### Current SSE Client

`apiSSE()` in `client.ts` already listens for:
```typescript
["progress", "complete", "error", "download_progress", "download_complete"]
```

This is correct. No changes needed to the SSE client.

### streamProgress Enhancement

Update `streamProgress()` to handle download events:

```typescript
// api/backtest.ts

export function streamProgress(
  runId: number,
  onProgress: (pct: number, phase?: "download" | "backtest") => void,
  onComplete: (data: { run_id: number; status: string }) => void,
  onError: (message: string) => void,
): () => void {
  return apiSSE(
    `/api/backtest/${runId}/progress`,
    (eventName, data) => {
      if (eventName === "download_progress") {
        const d = data as { pct?: number };
        onProgress(d.pct ?? 0, "download");
      } else if (eventName === "download_complete") {
        onProgress(100, "download");
      } else if (eventName === "progress") {
        const d = data as { pct?: number };
        onProgress(d.pct ?? 0, "backtest");
      } else if (eventName === "complete") {
        onComplete(data as { run_id: number; status: string });
      } else if (eventName === "error") {
        const d = data as { message?: string };
        onError(d.message ?? "Unknown error");
      }
    },
    () => onError("SSE connection lost"),
  );
}
```

### backtestStore Progress State Enhancement

```typescript
interface BacktestState {
  // ... existing ...
  runPhase: "idle" | "download" | "backtest";
  downloadProgress: number;  // 0-100
  backtestProgress: number;  // 0-100
}

// In runBacktest:
const cleanup = streamProgress(
  run_id,
  (pct, phase) => {
    if (phase === "download") {
      set({ runPhase: "download", downloadProgress: pct, runProgress: pct * 0.3 });
      // Download = 30% of total perceived progress
    } else {
      set({ runPhase: "backtest", backtestProgress: pct, runProgress: 30 + pct * 0.7 });
      // Backtest = 70% of total perceived progress
    }
  },
  // ...
);
```

---

## Stage 1E: Dynamic Strategy Param Form

### New Component: `DynamicParamForm.tsx`

Replaces the hardcoded param inputs in `Sidebar.tsx` and `MobileSidebarSheet.tsx`.

```typescript
// components/sidebar/DynamicParamForm.tsx
import React from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { CollapsibleSection } from "../ui/CollapsibleSection";
import { ValidatedInput } from "../ui/ValidatedInput";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Switch } from "../ui/switch";
import { RotateCcw } from "lucide-react";

const ICONS: Record<string, string> = {
  sliders: "Sliders",
  activity: "Activity",
  shield: "Shield",
  target: "Target",
};

export const DynamicParamForm: React.FC = () => {
  const { currentParamSchema, params, setParam, resetParams } = useBacktestStore();

  if (!currentParamSchema?.properties) {
    return <div className="text-xs text-text-muted p-4">No parameters available</div>;
  }

  const schema = currentParamSchema;
  const groups = schema.ui_groups || {};
  const properties = schema.properties;

  // Group params
  const groupedParams: Record<string, [string, any][]> = {};
  const ungrouped: [string, any][] = [];

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
                  className="p-1 hover:bg-bg-elevated rounded text-text-muted"
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
        else onChange(v); // let validation catch it
      }}
      suffix={prop.ui_suffix}
    />
  );
};
```

### Sidebar.tsx Changes

Replace the hardcoded "Parameters" section:

```diff
- <CollapsibleSection title="Parameters" headerAction={...}>
-   <ValidatedInput label="RSI Period" paramKey="rsi_period" ... />
-   <ValidatedInput label="EMA Fast" paramKey="ema_fast" ... />
-   <ValidatedInput label="EMA Slow" paramKey="ema_slow" ... />
-   <ValidatedInput label="TP1 Risk Ratio" paramKey="tp1_rr" ... />
-   <ValidatedInput label="SL Buffer" paramKey="sl_buffer_pct" ... />
- </CollapsibleSection>

+ <DynamicParamForm />
```

### Validation Update

Replace the hardcoded `validateParam()` with schema-driven validation:

```typescript
// lib/validation.ts — add schema-aware validation
export const validateFromSchema = (
  key: string,
  value: string,
  schema?: any
): ValidationResult => {
  if (value === "") return { isValid: false, error: "Required" };

  const prop = schema?.properties?.[key];
  if (!prop) {
    // Fall back to generic number validation
    const n = parseFloat(value);
    if (isNaN(n)) return { isValid: false, error: "Must be a number" };
    return { isValid: true, error: null };
  }

  const n = prop.type === "integer" ? parseInt(value) : parseFloat(value);

  if (prop.type === "integer" || prop.type === "number") {
    if (isNaN(n)) return { isValid: false, error: `${prop.title} must be a number` };
    if (prop.minimum !== undefined && n < prop.minimum)
      return { isValid: false, error: `Min: ${prop.minimum}` };
    if (prop.maximum !== undefined && n > prop.maximum)
      return { isValid: false, error: `Max: ${prop.maximum}` };
  }

  return { isValid: true, error: null };
};
```

---

## Stage 1F: Floating Progress Pill

### New Component: `FloatingProgressPill.tsx`

Collapsible pill showing active backtest progress. Appears when `isRunning` is true.

```typescript
// components/layout/FloatingProgressPill.tsx
import React, { useState } from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { motion, AnimatePresence } from "motion/react";
import { ChevronDown, ChevronUp, X, Download, Activity } from "lucide-react";
import { cn } from "../../lib/utils";

export const FloatingProgressPill: React.FC = () => {
  const {
    isRunning, runProgress, runPhase,
    downloadProgress, backtestProgress,
    currentRunId, cancelBacktest, symbol
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
        {/* Header — always visible */}
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
          <div className="flex items-center gap-1">
            {expanded ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
          </div>
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
                {/* Download Phase */}
                <div className="flex items-center gap-2">
                  <Download size={12} className={cn(
                    runPhase === "download" ? "text-accent-main" : "text-success"
                  )} />
                  <span className="text-xs text-text-secondary flex-1">Data Download</span>
                  <span className="text-xs font-mono text-text-primary">
                    {runPhase === "download" ? `${downloadProgress}%` : "✓"}
                  </span>
                </div>
                {runPhase === "download" && (
                  <div className="h-1 bg-bg-elevated rounded-full overflow-hidden ml-5">
                    <div
                      className="h-full bg-accent-main/60 rounded-full transition-all"
                      style={{ width: `${downloadProgress}%` }}
                    />
                  </div>
                )}

                {/* Backtest Phase */}
                <div className="flex items-center gap-2">
                  <Activity size={12} className={cn(
                    runPhase === "backtest" ? "text-accent-main" :
                    runPhase === "download" ? "text-text-muted" : "text-success"
                  )} />
                  <span className="text-xs text-text-secondary flex-1">Backtest</span>
                  <span className="text-xs font-mono text-text-primary">
                    {runPhase === "backtest" ? `${backtestProgress}%` :
                     runPhase === "download" ? "Waiting" : "✓"}
                  </span>
                </div>
                {runPhase === "backtest" && (
                  <div className="h-1 bg-bg-elevated rounded-full overflow-hidden ml-5">
                    <div
                      className="h-full bg-accent-main/60 rounded-full transition-all"
                      style={{ width: `${backtestProgress}%` }}
                    />
                  </div>
                )}

                {/* Cancel Button */}
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

Enhance `apiSSE()` to auto-reconnect on connection drop:

```typescript
// api/client.ts — enhanced apiSSE
export function apiSSE(
  path: string,
  onMessage: (event: string, data: unknown) => void,
  onError?: (err: Event) => void,
  maxRetries: number = 3,
): () => void {
  let es: EventSource | null = null;
  let retryCount = 0;
  let isClosed = false;

  const connect = () => {
    if (isClosed) return;
    const url = `${BASE_URL}${path}`;
    es = new EventSource(url);

    // ... existing event listeners ...

    es.onerror = (e) => {
      if (isClosed) return;
      es?.close();

      if (retryCount < maxRetries) {
        retryCount++;
        setTimeout(connect, 1000 * retryCount); // exponential-ish backoff
      } else {
        onError?.(e);
      }
    };

    // Reset retry count on successful connection
    es.onopen = () => { retryCount = 0; };
  };

  connect();

  return () => {
    isClosed = true;
    es?.close();
  };
}
```

### Page Refresh Recovery

On app mount, check localStorage for running backtest IDs and attempt to reconnect:

```typescript
// backtestStore.ts — add recovery logic

// Save run ID to localStorage when backtest starts
runBacktest: async () => {
  // ... after getting run_id ...
  set({ currentRunId: run_id });
  localStorage.setItem("activeRunId", String(run_id));

  // ... on complete/error ...
  localStorage.removeItem("activeRunId");
},

// Recovery on mount (call from App.tsx useEffect)
recoverActiveRun: async () => {
  const activeRunId = localStorage.getItem("activeRunId");
  if (!activeRunId) return;

  const runId = parseInt(activeRunId);
  try {
    const detail = await getRunDetail(runId);

    if (detail.status === "completed") {
      // Already done — fetch results
      const timeseries = await getTimeseries(runId);
      useResultsStore.getState().setResults(mapApiToResults(detail, timeseries));
      localStorage.removeItem("activeRunId");
      toast.success("Previous backtest completed!");
    } else if (detail.status === "running") {
      // Still running — reconnect SSE
      set({ isRunning: true, currentRunId: runId });
      // reconnect SSE stream...
    } else {
      // Failed or unknown
      localStorage.removeItem("activeRunId");
    }
  } catch {
    localStorage.removeItem("activeRunId");
  }
},
```

---

## Stage 1H: Duplicate Run Warning

When user clicks Run with identical config to a recent run:

```typescript
// In handleRunRequest:
const isDuplicate = get().recentConfigs.some(c =>
  c.symbol === state.symbol &&
  c.timeframe === state.timeframe &&
  c.strategy === state.strategy &&
  JSON.stringify(c.params) === JSON.stringify(state.params)
);

if (isDuplicate) {
  const confirmed = window.confirm(
    "You already ran a backtest with identical settings. Run again?"
  );
  if (!confirmed) return;
}
```

---

## Files Changed

| File | Change |
|------|--------|
| `stores/backtestStore.ts` | Dynamic params, simplified run flow, recovery, phase tracking |
| `api/backtest.ts` | `streamProgress` handles download events |
| `api/client.ts` | SSE auto-reconnect |
| `components/sidebar/DynamicParamForm.tsx` | NEW — renders form from JSON Schema |
| `components/layout/Sidebar.tsx` | Replace hardcoded params with DynamicParamForm |
| `components/layout/MobileSidebarSheet.tsx` | Same replacement |
| `components/layout/FloatingProgressPill.tsx` | NEW — collapsible progress widget |
| `App.tsx` | Add FloatingProgressPill, recovery useEffect |
| `lib/validation.ts` | Schema-aware validation |
| `types/generated.ts` | Add `param_schema` to StrategyInfo, JSONSchema types |
| `stores/resultsStore.ts` | Verify mapApiToResults field mapping |
