# Phase 7: Frontend Analysis Tools

> **Phase Type:** Frontend | **Estimated Time:** 2 hours | **Depends On:** Phase 6

---

## 🎯 Objective

Build the analysis UI components: Grid Search, Walk-Forward, Sensitivity Analysis, and Run Comparison.

---

## 📖 Required Reading

Before starting, read:
- `.agent-guide/knowledge/COMPONENT_SPECS.md` (analysis sections)
- Phase 3 backend features (for API understanding)

---

## ✅ Tasks

### Task 7.1: Optimization Dashboard

Create `ui/src/components/analysis/OptimizationDashboard.tsx`:

**Purpose:** Container for all analysis tools with tabbed interface.

**Behavior:**
- Tabs: Grid Search | Walk-Forward | Sensitivity
- Each tab shows corresponding panel
- Clean, dark interface

### Task 7.2: Grid Search Panel

Create `ui/src/components/analysis/GridSearchPanel.tsx`:

**Purpose:** Configure and run grid search.

**UI Elements:**
- Strategy selector
- Parameter grid builder (add parameter → set values)
- Run button with loading state
- Results table (sortable by any metric)
- Heatmap visualization (optional)

**Behavior:**
1. User selects strategy
2. User adds parameters to test (e.g., RSI: 10,14,20)
3. User clicks Run
4. Loading state while running
5. Results display in table sorted by profit
6. Click row to view details

**API Integration:**
```typescript
const results = await window.pywebview.api.run_grid_search({
  strategy_name: selectedStrategy,
  symbol: selectedSymbol,
  data_file: selectedFile,
  param_grid: { rsi_period: [10, 14, 20], tp: [0.02, 0.03] },
  base_config: {}
});
```

### Task 7.3: Walk-Forward Panel

Create `ui/src/components/analysis/WalkForwardPanel.tsx`:

**Purpose:** Configure and run walk-forward analysis.

**UI Elements:**
- Strategy selector
- Window configuration:
  - Train period (days)
  - Test period (days)
  - Step size (days)
- Run button
- Results visualization:
  - Timeline showing IS/OOS periods
  - Bar chart of OOS profits per window
  - Aggregate stats

**Behavior:**
1. User configures windows
2. User clicks Run
3. Progress indicator (multiple windows)
4. Results show efficiency per window
5. Aggregate stats at bottom

### Task 7.4: Sensitivity Analysis Panel

Create `ui/src/components/analysis/SensitivityAnalysis.tsx`:

**Purpose:** Visualize parameter sensitivity.

**UI Elements:**
- Strategy selector
- Parameter to analyze (dropdown)
- Value range (min, max, step)
- Metric to measure (profit/win_rate/sharpe)
- Run button
- Line chart showing metric vs parameter value
- Stability score display

**Behavior:**
1. User selects parameter and range
2. User clicks Run
3. Line chart shows how metric changes
4. Highlight optimal point
5. Show stability score

### Task 7.5: History Filters

Create `ui/src/components/history/HistoryFilters.tsx`:

**Purpose:** Filter run history.

**Filters:**
- Strategy (multi-select)
- Symbol (multi-select)
- Date range (start/end)
- Profit range (min/max)

**Behavior:**
- Filters apply to RunHistoryTable
- Debounced to avoid too many API calls
- Clear filters button

### Task 7.6: Comparison View

Create `ui/src/components/history/ComparisonView.tsx`:

**Purpose:** Compare two runs side-by-side.

**UI Elements:**
- Run 1 selector (or use selected from table)
- Run 2 selector
- Compare button
- Side-by-side metrics
- Overlay chart (both equity curves)
- Difference highlight

**API Integration:**
```typescript
const comparison = await window.pywebview.api.compare_runs(runId1, runId2);
```

### Task 7.7: Connect to App

Add Optimization tab to routing:

```typescript
case 'optimization':
  return <OptimizationDashboard />
```

Update History page to include:
- HistoryFilters at top
- ComparisonView accessible via button

---

## 🔍 Verification Checkpoint

1. **Grid Search:**
   - Configure parameters
   - Run search
   - Results display
   - Sort by different columns

2. **Walk-Forward:**
   - Configure windows
   - Run analysis
   - See timeline visualization

3. **Sensitivity:**
   - Select parameter and range
   - Run analysis
   - See line chart

4. **Comparison:**
   - Select two runs
   - Compare side-by-side

---

## 📤 Report Template

```
## Phase 7 Complete: Frontend Analysis Tools

### Created Files:
- ui/src/components/analysis/OptimizationDashboard.tsx
- ui/src/components/analysis/GridSearchPanel.tsx
- ui/src/components/analysis/WalkForwardPanel.tsx
- ui/src/components/analysis/SensitivityAnalysis.tsx
- ui/src/components/analysis/index.ts
- ui/src/components/history/HistoryFilters.tsx
- ui/src/components/history/ComparisonView.tsx
- ui/src/components/history/index.ts

### Features Working:
- Grid Search: ✅ / ❌
- Walk-Forward: ✅ / ❌
- Sensitivity: ✅ / ❌
- History Filters: ✅ / ❌
- Run Comparison: ✅ / ❌

Awaiting "proceed" command for Phase 8.
```

---

## ⏭️ Next Phase

After user approval, proceed to `PHASE_8_POLISH.md`
