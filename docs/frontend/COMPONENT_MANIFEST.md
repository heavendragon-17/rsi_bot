# Component Manifest - React UI Inventory

> **Document Type:** Component Architecture  
> **Agent:** frontend-specialist  
> **Status:** Phase 3 Documentation

---

## Overview

This manifest catalogs all React components needed for the Backtest UI, mapping to user stories and defining the implementation approach.

---

## 1. Layout Components

### `App.tsx`
**Purpose:** Root component with routing and providers

```tsx
<ThemeProvider>
  <Router>
    <Layout>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </Layout>
  </Router>
</ThemeProvider>
```

---

### `Layout.tsx`
**Purpose:** Main layout shell with sidebar and header

| Child | Purpose |
|-------|---------|
| `Sidebar` | Navigation + Strategy selector |
| `Header` | Logo, theme toggle, status |
| `MainContent` | Current page content |

---

### `Sidebar.tsx`
**Purpose:** Left navigation panel

**Sections:**
- Navigation links (Dashboard, History, Settings)
- Active strategy indicator
- Run status (idle/running)

---

## 2. Page Components

### `DashboardPage.tsx` (Home)
**User Stories:** US-001 to US-005, US-030 to US-033

| Section | Component | Priority |
|---------|-----------|----------|
| Controls | `BacktestControls` | P0 |
| Results | `ResultsPanel` | P0 |
| Charts | `EquityChart`, `ExitPieChart` | P1 |

---

### `HistoryPage.tsx`
**User Stories:** US-040, US-041

| Section | Component | Priority |
|---------|-----------|----------|
| List | `RunHistoryTable` | P1 |
| Filters | `HistoryFilters` | P2 |
| Compare | `ComparisonView` | P2 |

---

### `SettingsPage.tsx`
**User Stories:** US-020

| Section | Component | Priority |
|---------|-----------|----------|
| Global Config | `GlobalConfigForm` | P2 |
| Themes | `ThemeSelector` | P2 |

---

## 3. Backtest Control Components

### `BacktestControls.tsx`
**Purpose:** Container for backtest configuration

```tsx
<BacktestControls>
  <DataFileSelector />
  <StrategySelector />
  <ParameterEditor />
  <RunButton />
</BacktestControls>
```

---

### `DataFileSelector.tsx`
**User Story:** US-001  
**API:** `get_data_files()`

**Props:**
```tsx
interface Props {
  value: DataFile | null;
  onChange: (file: DataFile) => void;
}
```

**Features:**
- Dropdown with file info (symbol, timeframe, size)
- Last modified date
- File count indicator

---

### `StrategySelector.tsx`
**User Story:** US-002  
**API:** `get_strategies()`

**Props:**
```tsx
interface Props {
  value: Strategy | null;
  onChange: (strategy: Strategy) => void;
}
```

**Features:**
- Dropdown with strategy names
- Description on hover
- Override indicator (has JSON file)

---

### `ParameterEditor.tsx`
**User Stories:** US-003, US-010 to US-012  
**API:** `get_strategy_config()`, `save_strategy_config()`

**Props:**
```tsx
interface Props {
  schema: ParameterSchema[];
  values: Record<string, any>;
  onChange: (key: string, value: any) => void;
  onSave: () => void;
  onReset: () => void;
}
```

**Features:**
- Grouped sections (Indicators, Risk, Exits)
- Type-aware inputs (number, slider, select)
- Validation feedback
- Save/Reset buttons

---

### `ParameterInput.tsx`
**Purpose:** Single parameter input (polymorphic)

**Renders based on `param.type`:**
- `number` → NumberInput with slider
- `select` → Select dropdown
- `boolean` → Toggle switch

---

### `RunButton.tsx`
**User Story:** US-004  
**API:** `run_backtest()`

**States:**
| State | Display |
|-------|---------|
| Idle | "▶ Run Backtest" (green) |
| Running | "Running..." (spinner) |
| Error | "Retry" (red) |

---

## 4. Results Components

### `ResultsPanel.tsx`
**Purpose:** Container for all results displays

```tsx
<ResultsPanel>
  <MetricsCards metrics={results.metrics} />
  <EquityChart data={results.equity_preview} />
  <ExitPieChart data={results.exit_distribution} />
  <TradesTable run_id={results.run_id} />
</ResultsPanel>
```

---

### `MetricsCards.tsx`
**User Story:** US-033

**Metrics Displayed:**

| Metric | Color Logic |
|--------|-------------|
| Net Profit % | green if > 0, red if < 0 |
| Win Rate | green if > 50% |
| Sharpe Ratio | green if > 1.0 |
| Max Drawdown | always red intensity |

---

### `EquityChart.tsx`
**User Story:** US-030  
**API:** `get_run_timeseries()` (lazy load)

**Library:** `lightweight-charts`

**Props:**
```tsx
interface Props {
  preview: [number, number][];  // Initial 100 points
  run_id?: number;              // For full data load
}
```

**Features:**
- Line chart with crosshair
- Zoom/pan support
- Full data load on interaction

---

### `DrawdownChart.tsx`
**User Story:** US-030 (secondary)

**Display:** Area chart showing drawdown %

---

### `ExitPieChart.tsx`
**User Story:** US-031

**Data Format:**
```tsx
{ TP1: 45, TP2: 25, TP3: 10, SL: 20 }
```

**Colors:**
- TP1: Light green
- TP2: Medium green
- TP3: Dark green
- SL: Red

---

### `TradesTable.tsx`
**User Story:** US-032  
**API:** `get_trades()`

**Columns:**
| Column | Sortable | Filter |
|--------|----------|--------|
| Entry Time | ✅ | - |
| Symbol | - | ✅ |
| Side | - | ✅ |
| Entry Price | - | - |
| Exit Price | - | - |
| PnL | ✅ | - |
| Exit Reason | - | ✅ |

**Features:**
- Pagination (50/page)
- CSV export
- Click for trade detail modal

---

## 5. History Components

### `RunHistoryTable.tsx`
**User Story:** US-040  
**API:** `get_run_history()`

**Columns:**
| Column | Content |
|--------|---------|
| Strategy | Name + icon |
| Symbol | XPL/USDT |
| Net Profit % | Colored |
| Win Rate | % |
| Date | Relative |
| Actions | View, Compare, Delete |

---

### `HistoryFilters.tsx`
**Fields:**
- Strategy: dropdown
- Symbol: dropdown
- Date range: date pickers

---

### `ComparisonView.tsx`
**User Story:** US-041  
**API:** `compare_runs()`

**Layout:**
```
┌─────────────┬─────────────┐
│   Run A     │   Run B     │
├─────────────┼─────────────┤
│ Metrics     │ Metrics     │
│ (green if   │ (red if     │
│  better)    │  worse)     │
├─────────────┴─────────────┤
│   Overlaid Equity Curves  │
└───────────────────────────┘
```

---

## 6. Common Components

### `Toast.tsx` / `useToast()`
**Purpose:** Notification system

**Types:** success, error, warning, info

---

### `Modal.tsx`
**Purpose:** Dialog wrapper

**Props:** isOpen, onClose, title, children

---

### `LoadingSpinner.tsx`
**Purpose:** Loading state indicator

---

### `EmptyState.tsx`
**Purpose:** No data placeholder

**Variants:**
- No data files found
- No runs in history
- No results yet

---

## 7. Component → User Story Map

| Component | User Stories |
|-----------|--------------|
| `DataFileSelector` | US-001 |
| `StrategySelector` | US-002 |
| `ParameterEditor` | US-003, US-010-012 |
| `RunButton` | US-004 |
| `ResultsPanel` | US-005 |
| `MetricsCards` | US-033 |
| `EquityChart` | US-030 |
| `ExitPieChart` | US-031 |
| `TradesTable` | US-032 |
| `RunHistoryTable` | US-040 |
| `ComparisonView` | US-041 |
| `GlobalConfigForm` | US-020 |

---

## Cross-Reference

| Document | Purpose |
|----------|---------|
| [USER_STORIES.md](../use-cases/USER_STORIES.md) | Acceptance criteria |
| [STATE_MANAGEMENT.md](./STATE_MANAGEMENT.md) | Zustand stores |
| [MIGRATION_STRATEGY.md](./MIGRATION_STRATEGY.md) | Copy from Figma UI |
