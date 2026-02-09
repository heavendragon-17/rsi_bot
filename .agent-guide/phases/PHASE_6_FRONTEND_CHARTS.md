# Phase 6: Frontend Charts

> **Phase Type:** Frontend | **Estimated Time:** 2 hours | **Depends On:** Phase 5

---

## 🎯 Objective

Implement data visualization components: equity charts, drawdown charts, pie charts, and trades table.

---

## 📖 Required Reading

Before starting, read:
- `.agent-guide/knowledge/COMPONENT_SPECS.md` (chart sections)
- `.agent-guide/knowledge/FIGMA_MIGRATION.md`

---

## ✅ Tasks

### Task 6.1: Equity Chart

Create `ui/src/components/charts/EquityChart.tsx`:

**Library:** lightweight-charts (TradingView)

**Purpose:** Display equity curve over time.

**Behavior:**
- Line chart showing portfolio value
- X-axis: time
- Y-axis: equity value
- Zoom and pan enabled
- Tooltip on hover
- Responsive sizing

**Data source:**
```typescript
const data = await window.pywebview.api.get_run_timeseries(runId);
// data.equity_curve: Array<[timestamp, value]>
```

**Key features:**
- Handle large datasets efficiently
- Show grid lines
- Format axis labels

### Task 6.2: Drawdown Chart

Create `ui/src/components/charts/DrawdownChart.tsx`:

**Library:** lightweight-charts

**Purpose:** Display drawdown percentage over time.

**Behavior:**
- Area chart (filled below line)
- X-axis: time
- Y-axis: drawdown percentage (negative values)
- Red/orange color scheme
- Highlight max drawdown point

**Data source:**
```typescript
const data = await window.pywebview.api.get_run_timeseries(runId);
// data.drawdown_curve: Array<[timestamp, percentage]>
```

### Task 6.3: Exit Pie Chart

Create `ui/src/components/charts/ExitPieChart.tsx`:

**Library:** recharts

**Purpose:** Show distribution of trade exit reasons.

**Behavior:**
- Pie chart with segments for: TP (green), SL (red), Signal (blue), Timeout (gray)
- Labels with percentages
- Legend
- Tooltip on hover

**Data source:**
```typescript
const trades = await window.pywebview.api.get_trades(runId);
// Count trades by exit_reason
const distribution = {
  tp: trades.filter(t => t.exit_reason === 'tp').length,
  sl: trades.filter(t => t.exit_reason === 'sl').length,
  // etc.
};
```

### Task 6.4: Trades Table

Create `ui/src/components/tables/TradesTable.tsx`:

**Purpose:** Display all trades for a run.

**Columns:**
- # (index)
- Entry Time
- Exit Time
- Side (Long/Short with color)
- Entry Price
- Exit Price
- Quantity
- P&L (green/red based on value)
- Exit Reason

**Features:**
- Sortable columns
- Pagination (10/25/50 per page)
- Search/filter
- Export button (CSV)

**Data source:**
```typescript
const trades = await window.pywebview.api.get_trades(runId);
```

### Task 6.5: Charts Container

Create `ui/src/components/charts/ChartsContainer.tsx`:

**Purpose:** Layout container for multiple charts.

**Layout:**
```
┌─────────────────────────────────────┐
│ Equity Chart (60% height)           │
├─────────────────────────────────────┤
│ Drawdown Chart (40% height)         │
└─────────────────────────────────────┘
```

Or side-by-side on wide screens.

### Task 6.6: Integrate into Dashboard

Update Dashboard page to include:
- ChartsContainer (for selected run)
- ExitPieChart (sidebar or below stats)
- TradesTable (expandable section)

**Workflow:**
1. User runs backtest
2. Dashboard updates with new run
3. Charts load automatically
4. User can click "View Trades" to expand TradesTable

### Task 6.7: Create Index Exports

Create `ui/src/components/charts/index.ts`:
```typescript
export { EquityChart } from './EquityChart'
export { DrawdownChart } from './DrawdownChart'
export { ExitPieChart } from './ExitPieChart'
```

Create `ui/src/components/tables/index.ts`:
```typescript
export { TradesTable } from './TradesTable'
```

---

## 🔍 Verification Checkpoint

1. **Charts render:**
   - Run a backtest
   - Equity chart displays
   - Drawdown chart displays
   - Both are interactive (zoom, hover)

2. **Pie chart:**
   - Shows trade exit distribution
   - Colors are correct
   - Legend visible

3. **Trades table:**
   - Loads all trades
   - Pagination works
   - Sorting works

```bash
python main_ui.py --debug
```

Run backtest and verify all visualizations.

---

## 📤 Report Template

```
## Phase 6 Complete: Frontend Charts

### Created Files:
- ui/src/components/charts/EquityChart.tsx
- ui/src/components/charts/DrawdownChart.tsx
- ui/src/components/charts/ExitPieChart.tsx
- ui/src/components/charts/ChartsContainer.tsx
- ui/src/components/charts/index.ts
- ui/src/components/tables/TradesTable.tsx
- ui/src/components/tables/index.ts

### Features Working:
- Equity chart: ✅ / ❌
- Drawdown chart: ✅ / ❌
- Exit pie chart: ✅ / ❌
- Trades table: ✅ / ❌
- Chart interactivity: ✅ / ❌

### Known Issues:
- (list any issues)

Awaiting "proceed" command for Phase 7.
```

---

## ⏭️ Next Phase

After user approval, proceed to `PHASE_7_FRONTEND_ANALYSIS.md`
