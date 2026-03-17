# UI Backtest Sidebar — Bug Report

**Date:** 2026-03-11
**Branch:** `fix/backtest-sl-wrong`
**Scope:** All bugs found in the backtest sidebar UI and its supporting components.

---

## Bug 1 — `Code` icon not imported → sidebar crashes when collapsed

### What it is
The `Code` icon from `lucide-react` is used in the collapsed sidebar icon list but was removed from the import statement (likely during the Pine Translator cleanup commit). Because `Sidebar.tsx` has `// @ts-nocheck` on line 1, TypeScript is silenced and the missing import is not caught at build time. At runtime, when the user collapses the sidebar, React tries to render `<Code ... />` where `Code` is `undefined`, which throws:

```
React.createElement: type is invalid -- expected a string (for built-in components)
or a class/function (for composite components) but got: undefined.
```

This crashes the entire sidebar component tree.

### How to reproduce
1. Start the UI (`npm run dev`)
2. Open the sidebar (it is open by default)
3. Click the collapse/chevron button (top of sidebar) to collapse it
4. **Result:** The sidebar goes blank / React error boundary triggers

### Files involved
- **`ui/src/components/layout/Sidebar.tsx`**
  - Line 1: `// @ts-nocheck` — suppresses the error at compile time
  - Lines 3–15: Import block — `Code` is NOT listed
  - Line 497: `<Code size={20} ... />` — usage of undefined identifier

### Root cause
The Pine Translator feature was removed (the component files were deleted in a recent commit), but not all references were cleaned up. `Code` was part of the icon set used in the collapsed sidebar for the "Pine" nav item.

### Fix required
Either:
- **Option A (remove the icon):** Delete lines 496–501 in `Sidebar.tsx` (the `<Code>` icon block inside the collapsed view).
- **Option B (keep icon, fix import):** Add `Code` back to the lucide-react import on line 3.

Since Pine Translator is removed, Option A is correct. Also remove `// @ts-nocheck` once all TypeScript errors are fixed.

---

## Bug 2 — `PineTranslator` component undefined → app crashes on pine mode

### What it is
`App.tsx` renders `<PineTranslator />` when `mode === "pine"`, but the component was never imported and the source files were deleted. When a user navigates to pine mode, React throws `ReferenceError: PineTranslator is not defined`, crashing the entire app (not just the component).

### How to reproduce
1. Start the UI
2. In the sidebar, look for a "pine" mode button or navigate to `mode = "pine"` via any other path
3. **Result:** The app white-screens with an uncaught ReferenceError

### Files involved
- **`ui/src/App.tsx`**
  - Line 42: `{showPine && <PineTranslator />}` — renders undefined component
  - Lines 32, 48: `showPine` is computed from `mode === "pine"` and also used in the empty state guard

- **Deleted files (no longer exist in repo):**
  - `ui/src/components/pine/PineTranslator.tsx`
  - `ui/src/components/pine/IndicatorLibrary.tsx`
  - `ui/src/components/pine/ParsedResults.tsx`
  - `ui/src/components/pine/PasteZone.tsx`

- **`ui/src/stores/backtestStore.ts`**
  - Line 24: `"pine"` is still a valid value in the `mode` type union — users can end up in pine mode

### Fix required
1. In `App.tsx`, remove or guard the `PineTranslator` render:
   ```tsx
   // Remove line 42 entirely:
   {showPine && <PineTranslator />}
   ```
2. In `backtestStore.ts` line 24, remove `"pine"` from the mode union type.
3. In `Sidebar.tsx`, ensure no button sets `mode` to `"pine"` (search for `setMode("pine")`).
4. In `App.tsx` line 32 and 48, remove all `showPine` references.

---

## Bug 3 — `timezone` / `setTimezone` not in store → timezone selector broken, crashes on use

### What it is
`TimezoneSelector.tsx` destructures `timezone` and `setTimezone` from `useBacktestStore()`, but neither of these fields exists in `BacktestState` or the store's implementation. The component has `// @ts-nocheck` which prevents TypeScript from catching this.

**On render:** `timezone` resolves to `undefined`. The selector shows no label (empty string). The `Select` component gets `value={undefined}`.

**On user interaction:** When the user opens the dropdown and picks a timezone, `onValueChange={setTimezone}` fires, but `setTimezone` is `undefined`, throwing: `TypeError: setTimezone is not a function`. This crashes the `DateRangeSection`, which is always visible in the expanded sidebar.

`TimezoneSelector` is rendered unconditionally inside `DateRangeSection` (line 18), which is rendered inside the "Date Range" `CollapsibleSection` in `Sidebar.tsx` (line 349).

### How to reproduce
1. Start the UI with the sidebar expanded
2. Look at the Date Range section — the timezone selector shows nothing (blank label)
3. Click the timezone selector dropdown
4. Select any timezone
5. **Result:** `TypeError: setTimezone is not a function`

### Files involved
- **`ui/src/components/date-controls/TimezoneSelector.tsx`**
  - Line 1: `// @ts-nocheck`
  - Line 16: `const { timezone, setTimezone } = useBacktestStore();` — both are `undefined`
  - Line 22: `onValueChange={setTimezone}` — crashes when called
  - Lines 18–19: `selectedLabel` silently resolves to `undefined`

- **`ui/src/stores/backtestStore.ts`**
  - `BacktestState` interface (lines 17–87): no `timezone` field
  - Store implementation (lines 100–487): no `timezone` state, no `setTimezone` action

- **`ui/src/components/date-controls/DateRangeSection.tsx`**
  - Line 18: `<TimezoneSelector />` — rendered unconditionally

### Fix required
Either:
- **Option A (add timezone to store):** Add `timezone: string` to `BacktestState`, initialize to `"UTC"`, add `setTimezone: (tz: string) => void` action. Add to `partialize` if persistence is needed.
- **Option B (remove timezone feature):** Delete `TimezoneSelector.tsx`, remove its import and usage from `DateRangeSection.tsx`. The timezone concept does not currently affect the backtest engine (dates are stored as plain `DD-MM-YYYY` strings).

---

## Bug 4 — Strategy params stored as strings after user edits → backend error / wrong results

### What it is
This is the **primary cause of the Run Backtest button appearing to not work** after a user edits any parameter.

`ValidatedInput` always calls `onChangeValue(e.target.value)` where `e.target.value` is always a **string**. In `Sidebar.tsx`, all parameter inputs use:

```tsx
// Example — RSI Period
<ValidatedInput
  value={params.rsi_period}             // number from store (e.g. 14)
  onChangeValue={(v) => setParam("rsi_period", v)}  // v is string "14", not number 14
/>
```

`setParam` is typed as `(key: string, value: number)` but `// @ts-nocheck` silences the mismatch. After the user edits the input and types the same value back, `params.rsi_period` is now the string `"14"` instead of the number `14`.

When the backtest runs, `params: state.params` is JSON-serialized as `{"rsi_period": "14"}` (string in JSON) and sent to the backend. The backend schema `params: dict[str, Any]` accepts it without error. But then the strategy's `RsiNoRetestConfig.from_dict(params)` calls `cls(**filtered)` which sets the frozen dataclass field `rsi_period: int = "14"` — Python dataclasses don't enforce types at runtime. When the strategy passes this to pandas (e.g. `df.rolling(window=cfg.rsi_period)` or `ta.rsi(df["close"], length="14")`), it throws a `ValueError` or `TypeError`, causing the backtest run to fail on the backend.

**The user sees:** A toast error from the frontend (the SSE stream receives an `error` event, or `startBacktest` returns an error) with a generic message, or the run silently fails.

### How to reproduce
1. Start the UI and ensure data is downloaded for BTC/USDT 1h
2. Edit the "RSI Period" field — change it from 14 to any other value (e.g., type "21" then clear and type "14" back)
3. Click "Run Backtest"
4. **Result:** Backend error / toast error. If using default values without editing, it works. Once any param is edited, it breaks.

### Files involved
- **`ui/src/components/layout/Sidebar.tsx`** — `// @ts-nocheck` line 1
  - Lines 405–437: All `ValidatedInput` usages pass `onChangeValue={(v) => setParam(key, v)}`
    - Line 409: `setParam("rsi_period", v)` — v is string
    - Line 415: `setParam("ema_fast", v)` — v is string
    - Line 421: `setParam("ema_slow", v)` — v is string
    - Line 427: `setParam("tp1_rr", v)` — v is string
    - Line 434: `setParam("sl_buffer_pct", v)` — v is string

- **`ui/src/components/ui/ValidatedInput.tsx`**
  - Line 10: `onChangeValue: (value: string) => void` — correctly typed as string
  - Line 47: `onChange={(e) => onChangeValue(e.target.value)}` — always passes string

- **`ui/src/stores/backtestStore.ts`**
  - Line 67: `setParam: (key: string, value: number) => void` — expects number, receives string
  - Line 139–140: `setParam: (key, value) => set((s) => ({ params: { ...s.params, [key]: value } }))` — stores whatever is passed, no coercion

- **`app/strategies/rsi_no_retest.py`**
  - Lines 66–70: `RsiNoRetestConfig.from_dict(params)` — no type coercion, passes raw values to the frozen dataclass

### Fix required
In `backtestStore.ts`, coerce the value to a number in `setParam`:
```ts
setParam: (key, value) =>
  set((s) => ({ params: { ...s.params, [key]: Number(value) } })),
```
Or coerce in `runBacktest` before sending:
```ts
params: Object.fromEntries(
  Object.entries(state.params).map(([k, v]) => [k, Number(v)])
),
```
Also fix the TypeScript call sites in `Sidebar.tsx` by parsing the string before passing it, or update the `onChangeValue` call to `(v) => setParam(key, parseFloat(v))`.

---

## Bug 5 — AbsoluteTab date auto-fill never triggers (format mismatch)

### What it is
`AbsoluteTab.tsx` fetches the available data range for the selected symbol/timeframe and tries to auto-fill the date inputs if they are still at the "default" values. The comparison uses `YYYY-MM-DD` format:

```ts
if (
  currentStore.startDate === "2024-01-01" &&  // YYYY-MM-DD
  currentStore.endDate   === "2024-12-31"     // YYYY-MM-DD
) {
```

But the store initializes dates in `DD-MM-YYYY` format:
```ts
startDate: "01-01-2024",   // backtestStore.ts line 113
endDate:   "31-12-2024",   // backtestStore.ts line 114
```

And `syncRelativeDates()` always writes dates in `DD-MM-YYYY` format too (lines 218–222 of backtestStore.ts). The comparison therefore **never matches**, so the auto-fill silently does nothing. Users switching to Absolute mode and expecting the inputs to snap to the actual data range will see the stale defaults instead.

### How to reproduce
1. Download data for BTC/USDT 1h (e.g. 300 bars)
2. Switch to Absolute tab in the Date Range section
3. **Expected:** Date inputs snap to the actual range of downloaded data
4. **Actual:** Date inputs show the default values "01-01-2024" / "31-12-2024"

### Files involved
- **`ui/src/components/date-controls/AbsoluteTab.tsx`**
  - Lines 26–27: The comparison uses hardcoded `"2024-01-01"` / `"2024-12-31"` (YYYY-MM-DD)

- **`ui/src/stores/backtestStore.ts`**
  - Lines 113–114: Defaults are `"01-01-2024"` / `"31-12-2024"` (DD-MM-YYYY)
  - Lines 217–224: `syncRelativeDates` format function also writes DD-MM-YYYY

### Fix required
Update the comparison in `AbsoluteTab.tsx` to match the store format, **or** (better) remove the brittle hardcoded-date check entirely and just always auto-fill when data range is available:

```ts
// Replace lines 24-31 with:
if (res.available && res.date_range) {
  const s = res.date_range.start.split("T")[0]; // "2024-01-01"
  const e = res.date_range.end.split("T")[0];   // "2024-12-31"
  setDataRange({ start: s, end: e });

  // Convert to DD-MM-YYYY for the store
  const toStoreFmt = (iso: string) => {
    const [y, m, d] = iso.split("-");
    return `${d}-${m}-${y}`;
  };
  currentStore.setStartDate(toStoreFmt(s));
  currentStore.setEndDate(toStoreFmt(e));
}
```

---

## Bug 6 — LookbackInput `handleChange` drops intermediate empty input state

### What it is
When the user clears the lookback number input entirely to type a new value, `handleChange` does nothing (the `else if (e.target.value === "")` branch is a no-op comment). The controlled input value stays bound to `lookbackValue` from the store, so the input immediately snaps back to its previous value on the next render, preventing the user from clearing and retyping the field.

```ts
const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
  const val = parseInt(e.target.value);
  if (!isNaN(val) && val > 0) {
    setLookbackValue(val);
  } else if (e.target.value === "") {
    // Allow temporary empty state while typing, handled by UI not crashing
    // but store expects number. <-- does nothing, input snaps back
  }
};
```

### How to reproduce
1. Click the lookback number input (shows e.g. "300")
2. Select all and delete the content
3. **Expected:** Input shows empty so you can type a new number
4. **Actual:** Input immediately jumps back to "300" because the store value didn't change

### Files involved
- **`ui/src/components/date-controls/LookbackInput.tsx`**
  - Lines 38–45: `handleChange` — empty input branch is a no-op

### Fix required
Use local React state for the raw input string, and only commit to the store on valid values. Pattern:
```tsx
const [inputVal, setInputVal] = useState(String(lookbackValue));

// Sync if store changes externally (e.g. preset pills)
useEffect(() => { setInputVal(String(lookbackValue)); }, [lookbackValue]);

const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
  setInputVal(e.target.value);
  const val = parseInt(e.target.value);
  if (!isNaN(val) && val > 0) {
    setLookbackValue(val);
  }
};
```
Then use `value={inputVal}` on the `<input>` element instead of `value={lookbackValue || ""}`.

---

## Bug 7 — Double data check: runs fail when backend is unreachable, UX is confusing

### What it is
Data freshness is checked **twice** before a backtest runs — once in `Sidebar.tsx` `handleRunRequest` and again inside `backtestStore.ts` `runBacktest`. The two checks have inconsistent error handling:

**Sidebar check** (`Sidebar.tsx` lines 127–148):
- If `checkDataStatus` throws an uncaught exception (e.g. network error), the `catch` block calls `executeRun()` unconditionally, bypassing the data check entirely.
- If `allFresh === false`, it opens the data prep modal.

**Store check** (`backtestStore.ts` lines 359–363, single mode):
- `checkDataStatus` internally catches all network errors and returns `allFresh: false` (via `.catch(() => null)`), so it never throws.
- If `allFresh === false`, it throws `"No data for symbol. Download data first."` which becomes a toast error.

**Problematic interaction:**
When the backend is unreachable:
1. Sidebar's `checkDataStatus` silently returns `allFresh: false`
2. Sidebar opens the data prep modal with `setPrepState("downloading")`
3. The modal shows a download progress UI, but the download API is also unreachable
4. User is stuck with a broken modal and no clear error message

When the sidebar `catch` fires and calls `executeRun()` directly (e.g. if something else throws):
1. `runBacktest()` checks data again → fails → shows toast error
2. User sees an error toast with no context about why the sidebar even tried to run

### Files involved
- **`ui/src/components/layout/Sidebar.tsx`**
  - Lines 126–148: `handleRunRequest` — first data check, catch calls `executeRun()`
- **`ui/src/stores/backtestStore.ts`**
  - Lines 359–363: Second data check in `runBacktest()` single mode
  - Lines 246–248: Second data check in batch mode
  - Lines 309–311: Second data check in portfolio mode
- **`ui/src/lib/data-utils.ts`**
  - Lines 55–57: `.catch(() => null)` silently converts network errors to `allFresh: false`

### Fix required
Remove the redundant data check from inside `runBacktest()` — the check belongs only at the Sidebar/UI layer (before showing the run button). The store's job is to run the backtest, not to gate it. Also fix the `catch` block in `handleRunRequest` to not blindly call `executeRun()` on any error:

```ts
// In Sidebar.tsx handleRunRequest, replace the catch block:
} catch (e) {
  toast.error("Could not check data status. Is the backend running?");
  return;  // Do NOT call executeRun()
}
```

---

## Summary

| # | Severity | File(s) | Effect | Status |
|---|----------|---------|--------|--------|
| 1 | CRASH | `Sidebar.tsx:497` | Sidebar crashes when collapsed | Open |
| 2 | CRASH | `App.tsx:42` | App crashes on pine mode | Open |
| 3 | HIGH | `TimezoneSelector.tsx:16`, `backtestStore.ts` | Timezone selector broken; crashes on use | Open |
| 4 | HIGH | `Sidebar.tsx:405–437`, `backtestStore.ts:67,139` | **Run Backtest fails after editing params** — string values sent to backend | Open |
| 5 | MEDIUM | `AbsoluteTab.tsx:26` | Date auto-fill never fires | Open |
| 6 | MEDIUM | `LookbackInput.tsx:38` | Cannot clear and retype lookback value | Open |
| 7 | LOW | `Sidebar.tsx:146`, `backtestStore.ts:359` | Confusing UX when backend unreachable | Open |

### Notes
- Bugs 1, 2, 3, 4 are masked by `// @ts-nocheck` at the top of their respective files. After all fixes are applied, remove `// @ts-nocheck` from `Sidebar.tsx`, `DateRangeSection.tsx`, and `TimezoneSelector.tsx` and fix the resulting TypeScript errors properly.
- Bug 4 is the most impactful for day-to-day usage — default param values work (they are numbers), but any user who edits a parameter and then clicks Run will hit backend failures.
- Bugs 1–3 were introduced by the Pine Translator removal commit that deleted component files without cleaning all references.
