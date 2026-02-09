# Figma Agent Prompt: Task 9 — Grid Search (Heatmaps)

> **Phase:** 5 (Quant Tools)
> **Priority:** 🔴 Critical — This is how quants find optimal parameters.
> **Design Principle:** The heatmap IS the answer. Make it obvious.

---

## 🎯 Objective

Design the **Grid Search Interface** that allows users to:

1. Define parameter ranges to test (e.g., RSI from 10-20, TP from 1%-5%)
2. Run all combinations automatically
3. View results as an interactive heatmap

**Core Principle:** Find the "sweet spot" visually. No spreadsheets needed.

---

## 📐 Layout Overview

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ SIDEBAR                                 MAIN CONTENT                              │
│ ┌──────┐ ┌─────────────────────────────────────────────────────────────────────┐  │
│ │      │ │  ┌─ HEADER ───────────────────────────────────────────────────────┐ │  │
│ │ [«]  │ │  │ 🔥 Grid Search                               [Export Results]  │ │  │
│ │ [⚙]  │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │ [▶]  │ │                                                                     │  │
│ │      │ │  ┌─ PARAMETER SETUP ──────────────────────────────────────────────┐ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  Axis X: [RSI Period ▼]  Range: [10] to [20] Step: [2]        │ │  │
│ │      │ │  │  Axis Y: [Take Profit ▼] Range: [1%] to [5%] Step: [1%]       │ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  Metric: [Net PnL ▼]     Symbol: [DOGE/USDT]                   │ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  Total Combinations: 30   Est. Time: ~5 min                    │ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  [▶ Run Grid Search]                                           │ │  │
│ │      │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ │      │ │  ┌─ HEATMAP ──────────────────────────────────────────────────────┐ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │       10    12    14    16    18    20   ← RSI Period         │ │  │
│ │      │ │  │    ┌─────┬─────┬─────┬─────┬─────┬─────┐                      │ │  │
│ │      │ │  │ 1% │ 🟥  │ 🟥  │ 🟨  │ 🟨  │ 🟨  │ 🟥  │                      │ │  │
│ │      │ │  │ 2% │ 🟨  │ 🟩  │ 🟩  │ 🟩  │ 🟩  │ 🟨  │                      │ │  │
│ │      │ │  │ 3% │ 🟨  │ 🟩  │ 🟢  │ 🟩  │ 🟩  │ 🟨  │  ← Best: RSI=14,TP=3│ │  │
│ │      │ │  │ 4% │ 🟨  │ 🟩  │ 🟩  │ 🟩  │ 🟨  │ 🟥  │                      │ │  │
│ │      │ │  │ 5% │ 🟥  │ 🟨  │ 🟨  │ 🟨  │ 🟥  │ 🟥  │                      │ │  │
│ │      │ │  │    └─────┴─────┴─────┴─────┴─────┴─────┘                      │ │  │
│ │      │ │  │    ↑ Take Profit                                               │ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ └──────┘ └─────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Section 1: Parameter Setup

### Axis Configuration

```
┌───────────────────────────────────────────────────────────────────────┐
│  PARAMETER CONFIGURATION                                              │
│  ─────────────────────────────────────────────────────────────────    │
│                                                                       │
│  X-AXIS PARAMETER                                                     │
│  ┌─────────────────┐  ┌───────┐  ┌───────┐  ┌───────┐                │
│  │ RSI Period    ▼ │  │ Min:10│  │ Max:20│  │ Step:2│                │
│  └─────────────────┘  └───────┘  └───────┘  └───────┘                │
│                                                                       │
│  Y-AXIS PARAMETER                                                     │
│  ┌─────────────────┐  ┌───────┐  ┌───────┐  ┌───────┐                │
│  │ Take Profit % ▼ │  │ Min:1 │  │ Max:5 │  │ Step:1│                │
│  └─────────────────┘  └───────┘  └───────┘  └───────┘                │
│                                                                       │
│  ⚠️ Values: [10, 12, 14, 16, 18, 20] × [1, 2, 3, 4, 5] = 30 runs     │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

### Parameter Dropdown Options

Auto-populated from strategy's `input.*()` parameters:

| Parameter     | Type  | Example Range |
| ------------- | ----- | ------------- |
| RSI Period    | int   | 10-20, step 2 |
| Overbought    | int   | 65-80, step 5 |
| Oversold      | int   | 20-35, step 5 |
| Take Profit % | float | 1-5, step 0.5 |
| Stop Loss %   | float | 1-3, step 0.5 |

### Metric Selector

```
┌───────────────────────────────────────────────────────────────────────┐
│  OPTIMIZE FOR                                                         │
│  ─────────────────────────────────────────────────────────────────    │
│  Metric: [Net PnL ▼]                                                  │
│                                                                       │
│  Options: Net PnL | Sharpe Ratio | Profit Factor | Win Rate          │
│           Max Drawdown | Calmar Ratio | Sortino Ratio                │
└───────────────────────────────────────────────────────────────────────┘
```

### Run Estimation

```
┌───────────────────────────────────────────────────────────────────────┐
│  ESTIMATION                                                           │
│  ─────────────────────────────────────────────────────────────────    │
│  Total Combinations: 30                                               │
│  Estimated Time: ~5 min                                               │
│  Data Required: 10,000 candles (already cached)                       │
│                                                                       │
│  [▶ Run Grid Search]                                                  │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Section 2: Progress Indicator

While grid search is running:

```
┌───────────────────────────────────────────────────────────────────────┐
│  RUNNING GRID SEARCH                                                  │
│  ─────────────────────────────────────────────────────────────────    │
│                                                                       │
│  ███████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  18/30 (60%)       │
│                                                                       │
│  Current: RSI=16, TP=3%                                               │
│  Elapsed: 2:45                                                        │
│  Remaining: ~2:00                                                     │
│                                                                       │
│  [Cancel]                                                             │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Section 3: Heatmap Visualization

### Heatmap Layout

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│  HEATMAP: Net PnL                                                                 │
│  ────────────────────────────────────────────────────────────────────────────     │
│                                                                                   │
│             RSI Period                                                            │
│           10      12      14      16      18      20                              │
│        ┌───────┬───────┬───────┬───────┬───────┬───────┐                         │
│     1% │ -$450 │ -$320 │ +$120 │ +$80  │ +$50  │ -$180 │                         │
│        ├───────┼───────┼───────┼───────┼───────┼───────┤                         │
│     2% │ +$80  │ +$520 │ +$890 │ +$780 │ +$620 │ +$200 │                         │
│  T  3% │ +$220 │ +$780 │+$1,330│ +$950 │ +$820 │ +$350 │  ← BEST                 │
│  P     ├───────┼───────┼───────┼───────┼───────┼───────┤                         │
│  %  4% │ +$150 │ +$650 │ +$920 │ +$710 │ +$450 │ -$80  │                         │
│        ├───────┼───────┼───────┼───────┼───────┼───────┤                         │
│     5% │ -$220 │ +$180 │ +$350 │ +$280 │ -$120 │ -$380 │                         │
│        └───────┴───────┴───────┴───────┴───────┴───────┘                         │
│                                                                                   │
│  Color Scale:                                                                     │
│  [██ -$500] [██ -$250] [██ $0] [██ +$500] [██ +$1000] [██ +$1500]                │
│                                                                                   │
│  ★ Best: RSI=14, TP=3% → +$1,330 (Sharpe: 1.23)                                  │
└───────────────────────────────────────────────────────────────────────────────────┘
```

### Color Scale

| Value Range | Color                   | Meaning       |
| ----------- | ----------------------- | ------------- |
| < -10%      | Dark Red (`#DC2626`)    | Heavy Loss    |
| -10% to 0   | Light Red (`#F87171`)   | Loss          |
| 0 to +5%    | Yellow (`#FBBF24`)      | Break-even    |
| +5% to +15% | Light Green (`#4ADE80`) | Profit        |
| > +15%      | Dark Green (`#16A34A`)  | Strong Profit |

### Cell Hover Tooltip

```
┌─────────────────────────────────────┐
│  RSI Period: 14                     │
│  Take Profit: 3%                    │
│  ─────────────────────────────────  │
│  Net PnL: +$1,330 (+13.3%)         │
│  Sharpe: 1.23                       │
│  Win Rate: 68%                      │
│  Max DD: 5.2%                       │
│  Trades: 24                         │
│  ─────────────────────────────────  │
│  [Load These Settings]              │
└─────────────────────────────────────┘
```

---

## 📊 Section 4: Best Cell Highlight

The cell with the best metric value gets a **special border**:

```
┌─────────────────┐
│     +$1,330     │  ← Gold border + star icon
│      ★ BEST     │
└─────────────────┘
```

### Best Result Summary

```
┌───────────────────────────────────────────────────────────────────────┐
│  ★ OPTIMAL PARAMETERS FOUND                                           │
│  ─────────────────────────────────────────────────────────────────    │
│                                                                       │
│  RSI Period: 14                                                       │
│  Take Profit: 3%                                                      │
│                                                                       │
│  Results:                                                             │
│  • Net PnL: +$1,330 (+13.3%)                                         │
│  • Sharpe Ratio: 1.23                                                 │
│  • Win Rate: 68%                                                      │
│  • Max Drawdown: 5.2%                                                 │
│                                                                       │
│  [Apply These Settings]              [View Full Report]               │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Section 5: 3D Surface View (Optional Advanced)

Toggle between 2D heatmap and 3D surface:

```
┌───────────────────────────────────────────────────────────────────────┐
│  VIEW MODE:  [🔲 Heatmap]  [📊 3D Surface]                            │
│  ─────────────────────────────────────────────────────────────────    │
│                                                                       │
│  3D Surface (rotatable):                                              │
│                                                                       │
│                    ╱╲                                                 │
│                   ╱  ╲                                                │
│              ____╱    ╲____                                          │
│         ____╱              ╲____                                     │
│    ____╱                        ╲____                                │
│   ╱                                  ╲                               │
│  ────────────────────────────────────────                             │
│                                                                       │
│  (Drag to rotate, scroll to zoom)                                     │
└───────────────────────────────────────────────────────────────────────┘
```

> ⚠️ **3D Surface is optional.** Heatmap is the primary view. Only add 3D if time permits.

---

## 🔧 State Management

```typescript
interface GridSearchState {
  // Configuration
  xAxisParam: string;
  xAxisMin: number;
  xAxisMax: number;
  xAxisStep: number;

  yAxisParam: string;
  yAxisMin: number;
  yAxisMax: number;
  yAxisStep: number;

  metric: "net_pnl" | "sharpe" | "profit_factor" | "win_rate" | "max_dd";
  symbol: string;

  // Computed
  totalCombinations: number;
  estimatedTimeMinutes: number;

  // Execution
  isRunning: boolean;
  progress: number; // 0-100
  currentCombination: { x: number; y: number } | null;
  elapsedSeconds: number;

  // Results
  results: GridSearchResult[][] | null; // 2D array [y][x]
  bestResult: {
    x: number;
    y: number;
    xValue: number;
    yValue: number;
    metricValue: number;
    fullResults: BacktestResult;
  } | null;

  // View
  viewMode: "2d" | "3d";
  hoveredCell: { x: number; y: number } | null;
}

interface GridSearchResult {
  xValue: number;
  yValue: number;
  netPnL: number;
  netPnLPct: number;
  sharpe: number;
  profitFactor: number;
  winRate: number;
  maxDrawdownPct: number;
  tradeCount: number;
}
```

---

## 📦 Components to Create

| Component               | Description                           |
| ----------------------- | ------------------------------------- |
| `GridSearch.tsx`        | Main container                        |
| `ParameterSetup.tsx`    | X/Y axis configuration                |
| `MetricSelector.tsx`    | Dropdown for optimization metric      |
| `GridProgressBar.tsx`   | Progress during execution             |
| `Heatmap.tsx`           | 2D color-coded grid                   |
| `HeatmapCell.tsx`       | Individual cell with hover tooltip    |
| `HeatmapColorScale.tsx` | Legend showing value-to-color mapping |
| `BestResultCard.tsx`    | Summary of optimal parameters         |
| `Surface3D.tsx`         | Optional 3D visualization             |

---

## ✅ Acceptance Criteria

- [ ] **Parameter dropdowns** populated from strategy inputs.
- [ ] **Range inputs** (min, max, step) validate correctly.
- [ ] **Combination count** calculated and displayed.
- [ ] **Progress bar** shows real-time progress.
- [ ] **Heatmap** renders with correct color scale.
- [ ] **Hover tooltip** shows full metrics for each cell.
- [ ] **Best cell** highlighted with gold border + star.
- [ ] **Apply Settings** loads optimal params into sidebar.
- [ ] **Export Results** downloads CSV of all combinations.
- [ ] **Cancel** stops grid search mid-execution.

---

## 🚫 Anti-Patterns

- ❌ **No color scale legend** — User must understand what colors mean.
- ❌ **No hover details** — Cell values alone are not enough context.
- ❌ **No best highlight** — Optimal cell must be instantly obvious.
- ❌ **Running >100 combinations without warning** — Show "This may take a while."
- ❌ **No cancel button** — Long-running searches must be interruptible.

---

## 📚 Libraries

| Library                 | Purpose                   |
| ----------------------- | ------------------------- |
| `visx` or `d3`          | Heatmap rendering         |
| `three.js` (optional)   | 3D surface view           |
| `@tanstack/react-query` | Async execution           |
| SQLite                  | Store grid search results |

---

## 🔍 Figma Agent Verification Protocol

**After completing this task, Figma Agent MUST:**

1. **Check for Errors** — Review all components for:

   - Parameter dropdown not showing strategy inputs
   - Range validation not working (min > max)
   - Progress bar stuck or not updating
   - Heatmap colors not matching scale
   - Hover tooltip not appearing
   - Best cell not highlighted

2. **Fix Identified Issues** — Do not mark task complete until:

   - All parameter combinations calculated correctly
   - Color scale matches metric values
   - Best result is visually distinct
   - Apply Settings works correctly

3. **Self-Test Checklist:**
   - [ ] Set RSI 10-20, TP 1-5 → 30 combinations shown
   - [ ] Run Grid Search → Progress updates
   - [ ] Hover cell → Tooltip shows metrics
   - [ ] Best cell has gold border + star
   - [ ] Apply Settings → Sidebar updates
   - [ ] Cancel mid-run → Stops gracefully
