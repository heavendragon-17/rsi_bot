# Phase 5: Frontend Components

> **Phase Type:** Frontend | **Estimated Time:** 2 hours | **Depends On:** Phase 4

---

## 🎯 Objective

Build the main UI components: Dashboard, Backtest Runner, Run History, and Forms.

---

## 📖 Required Reading

Before starting, read:
- `.agent-guide/knowledge/COMPONENT_SPECS.md`
- `.agent-guide/knowledge/FIGMA_MIGRATION.md`
- `docs/frontend/COMPONENT_MANIFEST.md`

---

## ✅ Tasks

### Task 5.1: Dashboard Stats

Create `ui/src/components/DashboardStats.tsx`:

**Purpose:** Display key metrics cards.

**Behavior:**
- Show cards for: Total Profit, Win Rate, Total Trades, Profit Factor
- Each card: Icon, Label, Value, Change indicator (optional)
- Use lucide-react icons
- Style with CSS variables

**Reference:** `Designstrategycommandcenter/src/components/` for design

### Task 5.2: Backtest Runner

Create `ui/src/components/BacktestRunner.tsx`:

**Purpose:** Form to configure and execute backtest.

**Behavior:**
- Strategy selector dropdown
- Data file selector dropdown
- Date range inputs (start/end)
- Parameter editor (dynamic based on strategy config schema)
- Run button
- Loading state while running
- Show toast on success/error

**Integration:**
- Call `window.pywebview.api.run_backtest(config)`
- On success, refresh history and show results

### Task 5.3: Dynamic Form

Create `ui/src/components/DynamicForm.tsx`:

**Purpose:** Render form fields based on config schema.

**Behavior:**
- Accept schema: `{ field_name: { type, default, min, max, options } }`
- Render appropriate input: number, text, select, checkbox
- Handle validation
- Return form values

### Task 5.4: Run History Table

Create `ui/src/components/RunHistoryTable.tsx`:

**Purpose:** Display list of past backtest runs.

**Behavior:**
- Table columns: ID, Strategy, Symbol, Dates, Profit, Win Rate, Trades, Actions
- Sortable columns
- Click row to view details
- Actions: View, Compare, Delete

**Integration:**
- Load data from `window.pywebview.api.get_run_history()`
- Store in useDataStore

### Task 5.5: Strategy Config Editor

Create `ui/src/components/StrategyConfigEditor.tsx`:

**Purpose:** Edit strategy parameters.

**Behavior:**
- Load config via `get_strategy_config(strategyName)`
- Render using DynamicForm
- Save/Reset buttons
- Save to JSON override file via `save_strategy_config()`

### Task 5.6: Create Dashboard Page

Create `ui/src/pages/Dashboard.tsx` (or in components):

**Layout:**
```
┌─────────────────────────────────────┐
│ Header (Strategy + Data + Run)      │
├─────────────────────────────────────┤
│ DashboardStats (4 metric cards)     │
├───────────────────┬─────────────────┤
│ Charts (Phase 6)  │ Recent Runs     │
└───────────────────┴─────────────────┘
```

### Task 5.7: Create History Page

Create `ui/src/pages/History.tsx` (or in components):

**Layout:**
```
┌─────────────────────────────────────┐
│ Filters (Phase 7)                   │
├─────────────────────────────────────┤
│ RunHistoryTable (full width)        │
├─────────────────────────────────────┤
│ Run Details Panel (when selected)   │
└─────────────────────────────────────┘
```

### Task 5.8: Update App.tsx Routing

Connect pages to tabs:

```typescript
case 'dashboard':
  return <Dashboard />
case 'history':
  return <History />
```

---

## 🔍 Verification Checkpoint

1. **Dashboard displays:**
   - Metric cards (can show placeholder data)
   - Backtest form functional

2. **History page:**
   - Table loads run history
   - Click row shows details

3. **Backtest execution:**
   - Fill form, click Run
   - Loading state appears
   - Success toast on completion
   - History refreshes

```bash
python main_ui.py --debug
```

Test full flow in PyWebView.

---

## 📤 Report Template

```
## Phase 5 Complete: Frontend Components

### Created Files:
- ui/src/components/DashboardStats.tsx
- ui/src/components/BacktestRunner.tsx
- ui/src/components/DynamicForm.tsx
- ui/src/components/RunHistoryTable.tsx
- ui/src/components/StrategyConfigEditor.tsx
- ui/src/pages/Dashboard.tsx
- ui/src/pages/History.tsx

### Features Working:
- Dashboard stats display: ✅ / ❌
- Backtest form: ✅ / ❌
- Run backtest: ✅ / ❌
- History table: ✅ / ❌
- Row selection: ✅ / ❌

### Known Issues:
- (list any issues)

Awaiting "proceed" command for Phase 6.
```

---

## ⏭️ Next Phase

After user approval, proceed to `PHASE_6_FRONTEND_CHARTS.md`
