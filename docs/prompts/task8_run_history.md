# Figma Agent Prompt: Task 8 — Run History & Diff-Highlighting

> **Phase:** 4 (History)
> **Priority:** 🟡 High — Users need to track what changed between runs.
> **Design Principle:** History is not a log. It's a time machine.

---

## 🎯 Objective

Design the **Run History System** that allows users to:

1. View all past backtest runs
2. Compare two runs side-by-side
3. See **what changed** (parameter diffs) between runs

**Core Principle:** Make it trivial to answer: "What did I change, and did it help?"

---

## 📐 Layout Overview

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ SIDEBAR                                 MAIN CONTENT                              │
│ ┌──────┐ ┌─────────────────────────────────────────────────────────────────────┐  │
│ │      │ │  ┌─ HEADER ───────────────────────────────────────────────────────┐ │  │
│ │ [«]  │ │  │ 📜 Run History                          [Clear All History]    │ │  │
│ │ [⚙]  │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │ [▶]  │ │                                                                     │  │
│ │      │ │  ┌─ HISTORY TABLE ────────────────────────────────────────────────┐ │  │
│ │      │ │  │ ☐ │ Run #  │ Date/Time      │ Strategy │ Symbol  │ Net PnL    │ │  │
│ │      │ │  │───┼────────┼────────────────┼──────────┼─────────┼────────────│ │  │
│ │      │ │  │ ☐ │ #42    │ Feb 8, 14:23   │ RSI v2   │ DOGE    │ ▲ +$1,330  │ │  │
│ │      │ │  │ ☑ │ #41    │ Feb 8, 13:45   │ RSI v2   │ DOGE    │ ▼ -$450    │ │  │
│ │      │ │  │ ☑ │ #40    │ Feb 8, 12:10   │ RSI v1   │ DOGE    │ ▲ +$820    │ │  │
│ │      │ │  │ ☐ │ #39    │ Feb 7, 18:30   │ RSI v1   │ SOL     │ ▲ +$2,100  │ │  │
│ │      │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ │      │ │  ┌─ COMPARE PANEL (2 selected) ───────────────────────────────────┐ │  │
│ │      │ │  │ [Compare Selected (2)]  [Load #41]  [Delete Selected]          │ │  │
│ │      │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ └──────┘ └─────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Section 1: History Table

### Table Columns

| Column        | Width | Description                     |
| ------------- | ----- | ------------------------------- |
| **Checkbox**  | 40px  | Multi-select for compare/delete |
| **Run #**     | 60px  | Auto-increment ID               |
| **Date/Time** | 120px | `Feb 8, 14:23` format           |
| **Strategy**  | 100px | Strategy name + version         |
| **Symbol**    | 80px  | `DOGE/USDT` (or `BATCH`)        |
| **Net PnL**   | 100px | `▲ +$1,330` or `▼ -$450`        |
| **Actions**   | 80px  | `[Load] [Delete]`               |

### Row States

| State                   | Visual                     |
| ----------------------- | -------------------------- |
| **Default**             | Normal row                 |
| **Hover**               | Light highlight            |
| **Selected (checkbox)** | Blue left border + bg tint |
| **Profitable**          | Green text for PnL         |
| **Loss**                | Red text for PnL           |

### Pagination

```
Showing 1-20 of 156 runs         [← Prev]  [1] [2] [3] ... [8]  [Next →]
```

---

## 📊 Section 2: Compare Panel (Sticky Bottom)

Appears when **2 runs** are selected:

```
┌───────────────────────────────────────────────────────────────────────┐
│  2 runs selected                                                      │
│  ─────────────────────────────────────────────────────────────────    │
│  [Compare Selected]    [Load #41]    [Delete Selected]                │
│                                                                       │
│  💡 Tip: Select exactly 2 runs to compare parameter changes.          │
└───────────────────────────────────────────────────────────────────────┘
```

### Button States

| Selection | Compare Button                  |
| --------- | ------------------------------- |
| 0 runs    | Hidden                          |
| 1 run     | Disabled: "Select 2 to compare" |
| 2 runs    | **Enabled**: "Compare Selected" |
| 3+ runs   | Disabled: "Select exactly 2"    |

---

## 📊 Section 3: Compare Modal (Diff View)

When user clicks `[Compare Selected]`:

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ COMPARE RUNS: #40 vs #41                                              [×] Close  │
├───────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─ PARAMETER DIFF ──────────────────────────────────────────────────────────────┐│
│  │                                                                               ││
│  │  ⚡ 3 parameters changed                                                      ││
│  │  ─────────────────────────────────────────────────────────────────────────    ││
│  │  ┌─────────────────┬────────────────┬────────────────┬───────────────────┐    ││
│  │  │ Parameter       │ Run #40        │ Run #41        │ Impact            │    ││
│  │  ├─────────────────┼────────────────┼────────────────┼───────────────────┤    ││
│  │  │ RSI Period      │ 14             │ 21 ← CHANGED   │ ▼ -$1,270         │    ││
│  │  │ Overbought      │ 70             │ 75 ← CHANGED   │                   │    ││
│  │  │ Take Profit %   │ 3%             │ 5% ← CHANGED   │                   │    ││
│  │  │ Stop Loss %     │ 2%             │ 2%             │ (unchanged)       │    ││
│  │  │ Symbol          │ DOGE/USDT      │ DOGE/USDT      │ (unchanged)       │    ││
│  │  └─────────────────┴────────────────┴────────────────┴───────────────────┘    ││
│  │                                                                               ││
│  └───────────────────────────────────────────────────────────────────────────────┘│
│                                                                                   │
│  ┌─ RESULTS COMPARISON ──────────────────────────────────────────────────────────┐│
│  │                                                                               ││
│  │  ┌───────────────────────────────┬───────────────────────────────────────┐    ││
│  │  │         RUN #40               │              RUN #41                  │    ││
│  │  ├───────────────────────────────┼───────────────────────────────────────┤    ││
│  │  │ Net PnL: +$820                │ Net PnL: -$450                        │    ││
│  │  │ Win Rate: 68%                 │ Win Rate: 52%                         │    ││
│  │  │ Profit Factor: 1.85           │ Profit Factor: 0.78                   │    ││
│  │  │ Max Drawdown: 5.2%            │ Max Drawdown: 12.1%                   │    ││
│  │  │ Sharpe: 1.12                  │ Sharpe: -0.23                         │    ││
│  │  └───────────────────────────────┴───────────────────────────────────────┘    ││
│  │                                                                               ││
│  │  Winner: Run #40 (RSI 14 > RSI 21)                                           ││
│  │                                                                               ││
│  └───────────────────────────────────────────────────────────────────────────────┘│
│                                                                                   │
│  [Close]                                              [Restore Run #40 Settings]  │
│                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘
```

### Diff Highlighting

| Change Type   | Visual                        |
| ------------- | ----------------------------- |
| **Changed**   | Yellow bg + "← CHANGED" label |
| **Unchanged** | Gray text, muted              |
| **Better**    | Green arrow ▲                 |
| **Worse**     | Red arrow ▼                   |

---

## 📊 Section 4: Load Run (Restore Settings)

When user clicks `[Load #40]` or `[Restore Run #40 Settings]`:

```
┌───────────────────────────────────────────────────────────────────────┐
│  RESTORE SETTINGS FROM RUN #40?                                       │
│  ─────────────────────────────────────────────────────────────────    │
│                                                                       │
│  This will update your current settings to match Run #40:             │
│                                                                       │
│  • RSI Period: 14                                                     │
│  • Overbought: 70                                                     │
│  • Take Profit: 3%                                                    │
│  • Stop Loss: 2%                                                      │
│  • Symbol: DOGE/USDT                                                  │
│  • Timeframe: 1H                                                      │
│                                                                       │
│  [Cancel]                                    [Restore & Run Backtest] │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Section 5: Quick Filters

```
┌───────────────────────────────────────────────────────────────────────┐
│  FILTERS                                                              │
│  ─────────────────────────────────────────────────────────────────    │
│  Strategy: [All ▼]    Symbol: [All ▼]    Date: [Last 7 days ▼]       │
│                                                                       │
│  [Profitable Only]    [Show Batch Runs]    [Search: ___________]     │
└───────────────────────────────────────────────────────────────────────┘
```

### Filter Options

| Filter              | Options                                    |
| ------------------- | ------------------------------------------ |
| **Strategy**        | All, RSI v1, RSI v2, ...                   |
| **Symbol**          | All, DOGE, SOL, BTC, ...                   |
| **Date**            | Today, Last 7 days, Last 30 days, All time |
| **Profitable Only** | Toggle                                     |
| **Show Batch Runs** | Toggle                                     |
| **Search**          | Free text search                           |

---

## 🔧 State Management

```typescript
interface HistoryState {
  // Table
  runs: HistoryRun[];
  selectedRunIds: Set<number>;
  isLoading: boolean;

  // Pagination
  currentPage: number;
  totalPages: number;
  totalRuns: number;

  // Filters
  filters: {
    strategy: string | null;
    symbol: string | null;
    dateRange: "today" | "7days" | "30days" | "all";
    profitableOnly: boolean;
    showBatchRuns: boolean;
    searchQuery: string;
  };

  // Compare Modal
  compareModalOpen: boolean;
  compareRuns: [HistoryRun, HistoryRun] | null;

  // Actions
  toggleRunSelection: (id: number) => void;
  compareSelected: () => void;
  loadRun: (id: number) => void;
  deleteRuns: (ids: number[]) => void;
}

interface HistoryRun {
  id: number;
  runNumber: number;
  timestamp: string;
  strategyName: string;
  strategyVersion: string;
  symbol: string;
  isBatch: boolean;

  // Parameters snapshot
  parameters: Record<string, any>;

  // Results summary
  netPnL: number;
  netPnLPct: number;
  winRate: number;
  profitFactor: number;
  maxDrawdownPct: number;
  sharpeRatio: number;
  tradeCount: number;
}
```

---

## 📦 Components to Create

| Component                 | Description                     |
| ------------------------- | ------------------------------- |
| `RunHistory.tsx`          | Main container                  |
| `HistoryTable.tsx`        | Paginated table with checkboxes |
| `HistoryRow.tsx`          | Individual row with actions     |
| `HistoryFilters.tsx`      | Filter bar                      |
| `ComparePanel.tsx`        | Sticky bottom action bar        |
| `CompareModal.tsx`        | Side-by-side diff view          |
| `ParameterDiff.tsx`       | Highlights changed parameters   |
| `RestoreConfirmModal.tsx` | Confirmation dialog             |

---

## ✅ Acceptance Criteria

- [ ] History table shows all past runs with pagination.
- [ ] **Checkboxes** allow multi-select (max 2 for compare).
- [ ] **Compare button** only enabled when exactly 2 selected.
- [ ] **Compare modal** shows parameter diff with highlighting.
- [ ] **Changed parameters** highlighted in yellow.
- [ ] **Results comparison** shows side-by-side metrics.
- [ ] **Load Run** restores settings and optionally re-runs.
- [ ] **Filters** work: strategy, symbol, date, profitable.
- [ ] **Delete** removes selected runs with confirmation.
- [ ] **Clear All** removes entire history with confirmation.
- [ ] PnL shows ▲/▼ with green/red coloring.

---

## 🚫 Anti-Patterns

- ❌ **No diff highlighting** — Changed values must be obvious.
- ❌ **Compare 3+ runs** — Limit to exactly 2 for clarity.
- ❌ **No pagination** — Will break with 100+ runs.
- ❌ **No filters** — Finding old runs becomes impossible.
- ❌ **Delete without confirm** — Dangerous UX.

---

## 📚 Libraries

| Library                 | Purpose                    |
| ----------------------- | -------------------------- |
| `@tanstack/react-table` | Sortable, paginated table  |
| `diff`                  | Parameter diff calculation |
| SQLite                  | Run history storage        |

---

## 🔍 Figma Agent Verification Protocol

**After completing this task, Figma Agent MUST:**

1. **Check for Errors** — Review all components for:

   - Table pagination not working
   - Compare modal not showing diff
   - Filters not updating table
   - Delete not removing rows
   - Load Run not restoring settings

2. **Fix Identified Issues** — Do not mark task complete until:

   - All filter combinations work
   - Compare diff highlights correctly
   - Pagination displays correct counts
   - Delete has confirmation dialog

3. **Self-Test Checklist:**
   - [ ] Select 2 runs → Compare shows diff
   - [ ] Changed params highlighted yellow
   - [ ] Load Run → Settings restored
   - [ ] Delete Run → Row removed (with confirm)
   - [ ] Filter by symbol → Table updates
   - [ ] Paginate → Next page loads correctly
