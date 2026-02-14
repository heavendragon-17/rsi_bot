# Strategy Command UI — Complete Codebase Flow

> **Tech Stack:** React 18 + TypeScript + Zustand + Vite + Tailwind CSS  
> **Purpose:** A backtesting dashboard for cryptocurrency trading strategies with advanced optimization tools.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Entry Point & Bootstrap](#2-entry-point--bootstrap)
3. [Layout System](#3-layout-system)
4. [Mode-Based Routing](#4-mode-based-routing)
5. [State Management (Zustand Stores)](#5-state-management-zustand-stores)
6. [Feature Modules](#6-feature-modules)
7. [Utility Libraries](#7-utility-libraries)
8. [Data Flow Diagrams](#8-data-flow-diagrams)
9. [File Reference Map](#9-file-reference-map)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    main.tsx (Entry)                      │
│                         ↓                               │
│                      App.tsx                            │
│              ┌─────────┴─────────┐                      │
│           Layout              DataPrepModal             │
│        ┌────┴────┐                                      │
│     Navbar   Sidebar   Main Content Area                │
│                        (mode-based rendering)           │
│                                                         │
│  ┌──────────────────────────────────────────────┐       │
│  │ Modes:                                        │       │
│  │  single → ResultsDashboard                    │       │
│  │  batch  → BatchResultsDashboard               │       │
│  │  pine   → PineTranslator                      │       │
│  │  history → RunHistory                         │       │
│  │  grid-search → GridSearch                     │       │
│  │  grid-search-results → GridSearchResults      │       │
│  │  walk-forward → WalkForward                   │       │
│  │  sensitivity → SensitivityAnalysis            │       │
│  │  settings → SettingsPage                      │       │
│  │  (none)  → EmptyState                         │       │
│  └──────────────────────────────────────────────┘       │
│                                                         │
│  ┌──────────────────────────────────────────────┐       │
│  │ Zustand Stores (11 total):                    │       │
│  │  backtestStore, resultsStore,                 │       │
│  │  batchResultsStore, gridSearchStore,          │       │
│  │  walkForwardStore, sensitivityStore,           │       │
│  │  historyStore, pineStore, exportStore,         │       │
│  │  themeStore, dataPrepStore                     │       │
│  └──────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Entry Point & Bootstrap

### `main.tsx`

- Renders `<App />` into the DOM root element.
- Imports global CSS (`index.css`).

### `App.tsx`

- **On mount:** Fetches available themes via `themeStore.fetchThemes()`.
- **Reads state:** `mode` from `backtestStore`, `hasResults` from `resultsStore`, `hasBatchResults` from `batchResultsStore`.
- **Renders:** `<Layout>` wrapper with mode-conditional children + always-present `<DataPrepModal>`.

---

## 3. Layout System

### `Layout.tsx` — Shell Container

```
┌───────────────────────────────────────────┐
│  Navbar (fixed top, rounded, floating)    │
├──────────┬────────────────────────────────┤
│          │                                │
│ Sidebar  │    Main Content Area           │
│ (fixed,  │    (rounded card, backdrop)    │
│ 320px    │                                │
│ or 60px  │    {children} passed from App  │
│ when     │                                │
│ collapsed│                                │
│          │                                │
├──────────┴────────────────────────────────┤
│  MobileNav (bottom, mobile only)          │
└───────────────────────────────────────────┘
```

### Key Layout Components

| Component              | File                            | Purpose                                                                                                                                                                                      |
| ---------------------- | ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Navbar**             | `layout/Navbar.tsx`             | App logo ("Strategy Command"), quick-access mode buttons (Grid Search, Walk-Forward, Sensitivity, History), theme toggle, performance mode toggle, settings button, DevTools                 |
| **Sidebar**            | `layout/Sidebar.tsx`            | Main configuration panel — mode selector (Single/Batch/Pine tabs), symbol/strategy/timeframe pickers, strategy parameter inputs, date range controls, Run button. Collapsible (320px ↔ 60px) |
| **MobileNav**          | `layout/MobileNav.tsx`          | Bottom navigation bar for mobile screens                                                                                                                                                     |
| **MobileSidebarSheet** | `layout/MobileSidebarSheet.tsx` | Slide-out sidebar sheet for mobile                                                                                                                                                           |
| **RunButton**          | `layout/RunButton.tsx`          | Animated run/execute button with loading state                                                                                                                                               |

### Sidebar Flow

```
User opens app
  → Sidebar shows mode tabs: [Single] [Batch] [Pine]
  → User selects mode → backtestStore.setMode(mode)
  → User configures:
      • Symbol: BTC/USDT
      • Strategy: rsi_no_retest
      • Timeframe: 1h
      • Parameters: rsi_period=14, ema_fast=9, etc.
      • Date Range: relative (30 days) or absolute
      • Capital/Leverage/Risk
  → User clicks "Run Backtest" → Sidebar.executeRun()
      → Opens DataPrepModal (data download check)
      → Generates mock results
      → Saves to history
      → Results display in main area
```

---

## 4. Mode-Based Routing

The app uses **state-based routing** instead of URL routing. The `mode` field in `backtestStore` determines which component renders in the main content area.

| Mode                  | Component               | Trigger                      |
| --------------------- | ----------------------- | ---------------------------- |
| `single` + results    | `ResultsDashboard`      | Run single backtest          |
| `batch` + results     | `BatchResultsDashboard` | Run batch backtest           |
| `pine`                | `PineTranslator`        | Click Pine tab in sidebar    |
| `history`             | `RunHistory`            | Click History in navbar      |
| `grid-search`         | `GridSearch`            | Click Grid Search in navbar  |
| `grid-search-results` | `GridSearchResults`     | Grid search completes        |
| `walk-forward`        | `WalkForward`           | Click Walk-Forward in navbar |
| `sensitivity`         | `SensitivityAnalysis`   | Click Sensitivity in navbar  |
| `settings`            | `SettingsPage`          | Click Settings in navbar     |
| _(none of above)_     | `EmptyState`            | No results, no mode selected |

---

## 5. State Management (Zustand Stores)

All stores use Zustand with `persist` middleware (localStorage). Each store is a self-contained state + actions module.

### 5.1 `backtestStore.ts` — Central Configuration Hub

**Role:** The "brain" of the app. Holds all backtest configuration.

| State               | Type                                                                                    | Purpose                               |
| ------------------- | --------------------------------------------------------------------------------------- | ------------------------------------- |
| `mode`              | `"single" \| "batch" \| "pine" \| ...`                                                  | Current app mode (routing)            |
| `symbol`            | `string`                                                                                | Trading pair (e.g., "BTC/USDT")       |
| `strategy`          | `string`                                                                                | Strategy name (e.g., "rsi_no_retest") |
| `timeframe`         | `string`                                                                                | Candle interval ("1h", "4h", etc.)    |
| `params`            | `{rsi_period, ema_fast, ema_slow, tp1_rr, tp2_rr, sl_buffer_pct, overbought, oversold}` | Strategy parameters                   |
| `capital`           | `string`                                                                                | Starting capital                      |
| `leverage`          | `string`                                                                                | Leverage multiplier                   |
| `riskPercent`       | `string`                                                                                | Risk per trade %                      |
| `startDate/endDate` | `Date`                                                                                  | Date range                            |
| `batchSymbols`      | `string[]`                                                                              | Symbols for batch mode                |
| `isSidebarOpen`     | `boolean`                                                                               | Sidebar collapsed state               |

**Key Actions:** `setMode()`, `setParam()`, `runBacktest()`, `resetParams()`, `resetToDefaults()`, `getEstimatedBars()`, `getDaysDuration()`

---

### 5.2 `resultsStore.ts` — Single Backtest Results

**Role:** Holds all metrics and data from a single-pair backtest run.

**Data stored:**

- **Hero Stats:** netProfit, profitFactor, maxDrawdown, sharpeRatio, sortinoRatio, calmarRatio
- **Metrics Grid:** winRate, winCount, lossCount, avgWin, avgLoss, bestTrade, worstTrade, expectancy
- **Charts:** equityCurve[], benchmarkCurve[], underwaterCurve[]
- **Trades:** Complete trade list with filtering by exit reason (TP1/TP2/TP3/SL/LOCK_PROFIT/DISASTER_SL)

**Key Action:** `generateMockResults(capital)` — Simulates 150 trades with realistic PnL distribution.

---

### 5.3 `batchResultsStore.ts` — Multi-Symbol Batch Results

**Role:** Portfolio-level results when backtesting across multiple symbols simultaneously.

**Data stored:**

- **Portfolio Metrics:** portfolioNetProfit, portfolioWinRate, portfolioSharpe, portfolioMaxDrawdown
- **Per-Symbol:** symbolResults[] with individual PnL, equity curves, trades
- **Correlation:** correlationMatrix[] between symbol pairs
- **Portfolio Equity:** Combined equity curve and benchmark comparison

**Key Actions:** `generateMockBatchResults()`, `togglePin()`, `selectSymbol()`

---

### 5.4 `gridSearchStore.ts` — Grid Search Optimization

**Role:** Exhaustive parameter sweep across two axes.

**Config:** xAxis param (e.g., rsi_period 10→20 step 2), yAxis param (e.g., tp1_rr 1→5 step 1), metric to optimize (sharpe/PnL/win rate)

**Execution Flow:**

1. `calculateCombinations()` → Determines total grid size (e.g., 6×5 = 30)
2. `runGridSearch()` → Iterates through all combinations, generates mock results, builds 2D results matrix
3. Results stored as heatmap data with `bestResult` highlighted
4. `applyBestSettings()` → Writes winning params back to `backtestStore`

---

### 5.5 `walkForwardStore.ts` — Walk-Forward Optimization

**Role:** Validates strategy robustness by testing on unseen data.

**Config:** IS window (days), OOS window (days), step size, parameter to optimize, range, metric

**Execution Flow:**

1. `calculateWindows()` → Computes window count from date range / step size
2. `runWalkForward()` → For each window: optimize on IS data → validate on OOS data
3. `calculateSummary()` → OOS win rate, most common best param, stability score, verdict
4. `applyBestParam()` → Writes best param back to `backtestStore.setParam()`

---

### 5.6 `sensitivityStore.ts` — Sensitivity Analysis (Tornado Chart)

**Role:** Measures how each parameter affects the strategy's performance.

**Config:** variation percent (±20%), metric to analyze

**Execution Flow:**

1. `runSensitivityAnalysis()` → For each parameter: test at base, base-variation%, base+variation%
2. Calculate impact percentages and classify sensitivity (high/medium/low)
3. `generateInsights()` → Natural language recommendations

---

### 5.7 `historyStore.ts` — Run History

**Role:** Persistent log of all backtest runs.

**Features:**

- Add runs with auto-incrementing ID and timestamp
- Filter by strategy, symbol, date range, profitable-only
- Search by name/symbol
- Pagination (20 per page)
- **Compare:** Select 2 runs side-by-side
- **Restore:** Load a historical run's parameters back into backtestStore

---

### 5.8 `pineStore.ts` — Pine Script Translator

**Role:** Parse TradingView Pine Script indicators and extract parameters.

**3-Step Wizard:**

1. **Paste:** User pastes Pine Script code
2. **Verify:** `parseCode()` → Extracts indicator name, type (oscillator/overlay), parameters
3. **Save:** Store in indicator library for future use

---

### 5.9 `exportStore.ts` — Export & Annotations

**Role:** PDF/CSV/PNG/JSON export + trade annotations/tagging system.

**Export Config:** file name, sections to include, page size (A4/letter), orientation, theme
**Annotations:** Per-trade notes with tags (star, review, learning, idea, lucky, unlucky)
**Bulk Actions:** Select multiple trades, bulk add/remove tags

---

### 5.10 `themeStore.ts` — Theme Engine

**Role:** CSS variable-based theming with 5 pre-built themes.

**Built-in Themes:**
| Theme | Mode | Accent |
|-------|------|--------|
| Cyberpunk Neon | Dark | Cyan (#00D4FF) |
| Arctic Frost | Light | Teal (#0891B2) |
| Midnight Ocean | Dark | Green (#16A34A) |
| Deep Space | Dark | White (#FAFAFA) |
| Paper | Light | Brown (#8D6E63) |

**Actions:** `fetchThemes()`, `setTheme()`, `applyTheme()` (sets CSS variables on `:root`), `togglePerformanceMode()` (disables animations)

---

### 5.11 `dataPrepStore.ts` — Data Download Manager

**Role:** Manages market data download states before running backtests.

**States:** checking → ready → downloading → complete/error
**Per-symbol tracking:** download progress, bytes downloaded, freshness status

---

## 6. Feature Modules

### 6.1 Single Backtest Results (`results/`)

| Component                   | Purpose                                                       |
| --------------------------- | ------------------------------------------------------------- |
| `ResultsDashboard.tsx`      | Container for all results components                          |
| `HeaderBar.tsx`             | Strategy name, timeframe, run metadata                        |
| `HeroStats.tsx`             | Large KPI cards (Net Profit, Sharpe, Max DD, Profit Factor)   |
| `MetricsGrid.tsx`           | Detailed metrics in grid layout                               |
| `EquityUnderwaterChart.tsx` | Equity curve + underwater drawdown chart (lightweight-charts) |
| `ExitReasonsChart.tsx`      | Bar chart showing exit reason distribution                    |
| `TradesTable.tsx`           | Full trade list with sorting, filtering, annotations          |

### 6.2 Batch Results (`results/batch/`)

| Component                    | Purpose                                    |
| ---------------------------- | ------------------------------------------ |
| `BatchResultsDashboard.tsx`  | Portfolio-level dashboard container        |
| `BatchHeaderBar.tsx`         | Run metadata header                        |
| `PortfolioHeroStats.tsx`     | Portfolio KPIs                             |
| `PortfolioEquityChart.tsx`   | Combined equity curve with dispersion band |
| `SymbolPerformanceTable.tsx` | Per-symbol results table with pin/select   |
| `CorrelationMatrix.tsx`      | Symbol correlation heatmap                 |

### 6.3 Grid Search (`grid-search/`)

| Component               | Purpose                                |
| ----------------------- | -------------------------------------- |
| `ParameterSetup.tsx`    | X/Y axis parameter configuration       |
| `GridProgressBar.tsx`   | Progress bar during grid search        |
| `Heatmap.tsx`           | 2D heatmap of results                  |
| `HeatmapCell.tsx`       | Individual cell with color coding      |
| `HeatmapColorScale.tsx` | Legend for heatmap colors              |
| `MetricSelector.tsx`    | Dropdown to switch viewed metric       |
| `BestResultCard.tsx`    | Highlight card for optimal combination |

### 6.4 Walk-Forward (`walk-forward/`)

| Component                   | Purpose                                          |
| --------------------------- | ------------------------------------------------ |
| `WindowConfig.tsx`          | IS/OOS window size + step configuration          |
| `ParamOptimizeConfig.tsx`   | Parameter range + metric selection               |
| `WalkForwardProgress.tsx`   | Progress indicator during run                    |
| `TimelineVisualization.tsx` | Visual timeline of windows (green/red blocks)    |
| `WindowBlock.tsx`           | Individual window detail (IS period, OOS result) |
| `ResultsSummary.tsx`        | Summary card with verdict + Apply button         |
| `EquityCurveComparison.tsx` | IS vs OOS equity curves chart                    |

### 6.5 Sensitivity Analysis (`sensitivity/`)

| Component                  | Purpose                               |
| -------------------------- | ------------------------------------- |
| `SensitivityConfig.tsx`    | Variation % and metric configuration  |
| `TornadoChart.tsx`         | Tornado chart container               |
| `TornadoBar.tsx`           | Individual parameter impact bar       |
| `SensitivityTable.tsx`     | Detailed results table                |
| `RecommendationsPanel.tsx` | AI-generated insights/recommendations |

### 6.6 Pine Script Translator (`pine/`)

| Component              | Purpose                      |
| ---------------------- | ---------------------------- |
| `PineTranslator.tsx`   | 3-step wizard container      |
| `PasteZone.tsx`        | Code input area              |
| `ParsedResults.tsx`    | Extracted parameters display |
| `IndicatorLibrary.tsx` | Saved indicators list        |

### 6.7 Run History (`history/`)

| Component                 | Purpose                                     |
| ------------------------- | ------------------------------------------- |
| `RunHistory.tsx`          | History page container                      |
| `HistoryFilters.tsx`      | Filter bar (strategy, symbol, date, search) |
| `HistoryTable.tsx`        | Paginated table of past runs                |
| `HistoryRow.tsx`          | Individual run row with actions             |
| `CompareModal.tsx`        | Side-by-side comparison modal               |
| `ComparePanel.tsx`        | Single run panel in comparison              |
| `ParameterDiff.tsx`       | Parameter difference highlighting           |
| `RestoreConfirmModal.tsx` | Confirmation before restoring parameters    |

### 6.8 Export & Annotations (`export/`)

| Component               | Purpose                                      |
| ----------------------- | -------------------------------------------- |
| `ExportDropdown.tsx`    | Format selector (PDF/CSV/PNG/JSON/ZIP)       |
| `ExportConfigModal.tsx` | Export settings (sections, page size, theme) |
| `ExportProgress.tsx`    | Download progress bar                        |
| `AddNoteModal.tsx`      | Trade annotation editor                      |
| `NotePopover.tsx`       | Quick note preview popover                   |
| `TagFilter.tsx`         | Filter trades by tags                        |
| `BulkActionsBar.tsx`    | Multi-select trade actions                   |

### 6.9 Data Preparation (`data-modal/`)

| Component                 | Purpose                          |
| ------------------------- | -------------------------------- |
| `DataPrepModal.tsx`       | Main modal for data download     |
| `SymbolStatusTable.tsx`   | Per-symbol download status table |
| `AnimatedProgressBar.tsx` | Download progress animation      |
| `ContextFactDisplay.tsx`  | Fun facts shown during download  |
| `TechnicalZenLoader.tsx`  | Loading animation                |

### 6.10 Date Controls (`date-controls/`)

| Component                | Purpose                                       |
| ------------------------ | --------------------------------------------- |
| `DateRangeSection.tsx`   | Container switching between relative/absolute |
| `RelativeTab.tsx`        | Lookback-based date selection                 |
| `AbsoluteTab.tsx`        | Calendar-based date selection                 |
| `LookbackInput.tsx`      | "Last N days/hours/bars" input                |
| `PresetPills.tsx`        | Quick presets (7D, 30D, 90D, 1Y)              |
| `DateTextInput.tsx`      | Manual date entry field                       |
| `ComputedRangeBadge.tsx` | Shows computed date range                     |
| `TimezoneSelector.tsx`   | Timezone picker                               |

### 6.11 Theme System (`theme/`)

| Component                   | Purpose                   |
| --------------------------- | ------------------------- |
| `ThemeSelector.tsx`         | Theme preview cards       |
| `ThemeCard.tsx`             | Individual theme preview  |
| `AllThemesModal.tsx`        | Full theme browser modal  |
| `ThemeSettings.tsx`         | Theme configuration panel |
| `PerformanceModeToggle.tsx` | Animation disable toggle  |

---

## 7. Utility Libraries

| File                  | Purpose                                                               |
| --------------------- | --------------------------------------------------------------------- |
| `lib/utils.ts`        | `cn()` — Tailwind class merging helper (clsx + tailwind-merge)        |
| `lib/validation.ts`   | Parameter validation (min/max/step checks)                            |
| `lib/data-utils.ts`   | Data transformation helpers                                           |
| `lib/pine-parser.ts`  | Pine Script lexer/parser — extracts indicator metadata and parameters |
| `lib/csv-export.ts`   | CSV file generation from trade data                                   |
| `lib/export-utils.ts` | PDF/PNG/JSON export logic                                             |
| `lib/mock-history.ts` | Mock data generator for history entries                               |

---

## 8. Data Flow Diagrams

### 8.1 Single Backtest Flow

```
User configures (Sidebar)
    ↓
backtestStore.setSymbol/setStrategy/setParam/etc.
    ↓
User clicks "Run" → Sidebar.executeRun()
    ↓
dataPrepStore.openModal() → Check/download data
    ↓
resultsStore.generateMockResults(capital)
    ↓
historyStore.addRun(snapshot)
    ↓
backtestStore.setMode("single")
    ↓
App.tsx renders <ResultsDashboard />
    ↓
  ├── HeroStats (reads resultsStore)
  ├── MetricsGrid (reads resultsStore)
  ├── EquityUnderwaterChart (reads resultsStore.equityCurve)
  ├── ExitReasonsChart (reads resultsStore.exitReasons)
  └── TradesTable (reads resultsStore.trades)
```

### 8.2 Batch Backtest Flow

```
User selects Batch mode + symbols
    ↓
backtestStore.setBatchSymbols(symbols)
    ↓
User clicks "Run" → batchResultsStore.generateMockBatchResults()
    ↓
backtestStore.setMode("batch")
    ↓
App.tsx renders <BatchResultsDashboard />
    ↓
  ├── PortfolioHeroStats
  ├── PortfolioEquityChart
  ├── SymbolPerformanceTable
  └── CorrelationMatrix
```

### 8.3 Grid Search Flow

```
User clicks Grid Search (Navbar)
    ↓
backtestStore.setMode("grid-search")
    ↓
App.tsx renders <GridSearch />
    ↓
  ├── ParameterSetup (x/y axis + ranges)
  └── User clicks "Run Grid Search"
        ↓
      gridSearchStore.runGridSearch()
        ↓
      Loop: for each (x,y) combination
        → Generate mock result
        → Update progress
        ↓
      gridSearchStore.bestResult found
        ↓
      backtestStore.setMode("grid-search-results")
        ↓
      App.tsx renders <GridSearchResults />
        ↓
        ├── Heatmap + HeatmapCells
        ├── BestResultCard
        └── "Apply" → gridSearchStore.applyBestSettings()
                       → backtestStore.setParam(x, bestX)
                       → backtestStore.setParam(y, bestY)
```

### 8.4 Walk-Forward Flow

```
User clicks Walk-Forward (Navbar)
    ↓
backtestStore.setMode("walk-forward")
    ↓
App.tsx renders <WalkForward />
    ↓
  ├── WindowConfig → walkForwardStore.setIsWindowDays/etc.
  ├── ParamOptimizeConfig → walkForwardStore.setParamRange/etc.
  └── User clicks "Run Walk-Forward"
        ↓
      walkForwardStore.runWalkForward()
        ↓
      Loop: for each time window
        → Optimize IS → best param
        → Validate OOS → return %
        → Store result
        ↓
      walkForwardStore.calculateSummary()
        ↓
      Display:
        ├── TimelineVisualization (green/red blocks)
        ├── ResultsSummary (win rate, verdict)
        ├── EquityCurveComparison (IS vs OOS chart)
        └── "Apply to Strategy" → walkForwardStore.applyBestParam()
                                   → backtestStore.setParam(param, value)
```

### 8.5 Cross-Store Communication

```
┌──────────────────┐      setParam()       ┌──────────────────┐
│ gridSearchStore   │─────────────────────→ │  backtestStore   │
│ walkForwardStore  │─────────────────────→ │                  │
└──────────────────┘                        └──────────────────┘
                                                    ↑
┌──────────────────┐     restoreRun()       ┌───────┴──────────┐
│  historyStore    │─────────────────────→  │  backtestStore   │
└──────────────────┘                        └──────────────────┘

┌──────────────────┐     fetchThemes()      ┌──────────────────┐
│    App.tsx       │─────────────────────→  │   themeStore     │
└──────────────────┘                        └──────────────────┘
                                                    ↓
                                            CSS :root variables
```

---

## 9. File Reference Map

### Directory Structure

```
ui/
├── index.html                          # HTML shell
├── vite.config.ts                      # Vite bundler config
├── package.json                        # Dependencies
├── tsconfig.json                       # TypeScript config
└── src/
    ├── main.tsx                        # React entry point
    ├── App.tsx                         # Root component + routing
    ├── index.css                       # Global CSS + Tailwind + CSS vars
    │
    ├── stores/                         # 11 Zustand stores
    │   ├── backtestStore.ts            # Central config (mode, params, dates)
    │   ├── resultsStore.ts             # Single backtest results
    │   ├── batchResultsStore.ts        # Multi-symbol portfolio results
    │   ├── gridSearchStore.ts          # Grid search optimization
    │   ├── walkForwardStore.ts         # Walk-forward validation
    │   ├── sensitivityStore.ts         # Parameter sensitivity analysis
    │   ├── historyStore.ts             # Run history & comparison
    │   ├── pineStore.ts                # Pine Script parser
    │   ├── exportStore.ts              # Export config & annotations
    │   ├── themeStore.ts               # Theme engine (5 themes)
    │   └── dataPrepStore.ts            # Data download manager
    │
    ├── components/
    │   ├── layout/                     # Shell: Navbar, Sidebar, Mobile
    │   ├── dashboard/                  # EmptyState placeholder
    │   ├── results/                    # Single backtest result views
    │   │   └── batch/                  # Portfolio batch result views
    │   ├── grid-search/                # Heatmap + parameter setup
    │   ├── walk-forward/               # Timeline + equity comparison
    │   ├── sensitivity/                # Tornado chart + recommendations
    │   ├── pine/                       # Pine Script translator wizard
    │   ├── history/                    # Run history + compare modal
    │   ├── export/                     # Export config + annotations
    │   ├── data-modal/                 # Data download modal
    │   ├── date-controls/              # Date range pickers
    │   ├── theme/                      # Theme selector + cards
    │   ├── settings/                   # Settings page
    │   ├── ui/                         # 51 shared UI primitives
    │   ├── dev/                        # DevTools component
    │   └── figma/                      # Figma reference
    │
    ├── lib/                            # Utility functions
    │   ├── utils.ts                    # cn() class merging
    │   ├── validation.ts               # Param validation
    │   ├── data-utils.ts               # Data transforms
    │   ├── pine-parser.ts              # Pine Script parser
    │   ├── csv-export.ts               # CSV generation
    │   ├── export-utils.ts             # PDF/PNG/JSON export
    │   └── mock-history.ts             # Mock data generator
    │
    ├── types/                          # TypeScript type definitions
    └── styles/                         # Additional style files
```

### Key Dependencies

| Package                   | Purpose                                                  |
| ------------------------- | -------------------------------------------------------- |
| `react` / `react-dom`     | UI framework                                             |
| `zustand`                 | State management                                         |
| `lightweight-charts`      | Financial charting (equity curves)                       |
| `lucide-react`            | Icon library                                             |
| `tailwind-merge` / `clsx` | CSS class utilities                                      |
| `@radix-ui/*`             | Accessible UI primitives (Select, Label, Progress, etc.) |
| `sonner`                  | Toast notifications                                      |
| `vite`                    | Build tooling                                            |

---

> **Note:** Currently all backtest execution uses **mock data generation**. The stores contain `generateMockResults()` functions that simulate realistic trading outcomes. The architecture is designed to be swapped with real API calls to the Python backtesting engine when backend integration is ready.
