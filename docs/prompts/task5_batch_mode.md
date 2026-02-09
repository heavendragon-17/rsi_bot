# Figma Agent Prompt: Task 5 — Batch Mode Parity (Fund Manager View)

> **Phase:** 2 (Reports & Charts)
> **Priority:** 🟡 High — Most strategies are tested across multiple symbols.
> **Design Principle:** A Portfolio is an ecosystem, not a list of trades.

---

## 🎯 Objective

Design the **Batch Mode Results View** that displays when a user runs a strategy across **multiple symbols** (e.g., DOGE, SOL, ETH, BTC all at once).

**Core Principle:** Show **Diversification & Correlation**, not just Performance.

---

## 📐 Layout Overview

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ SIDEBAR (collapsed)                      MAIN CONTENT                             │
│ ┌──────┐ ┌─────────────────────────────────────────────────────────────────────┐  │
│ │      │ │  ┌─ HEADER ───────────────────────────────────────────────────────┐ │  │
│ │ [«]  │ │  │ RSI Strategy • BATCH (12 symbols) [Equal Weight] [Fees: ON]   │ │  │
│ │ [⚙]  │ │  │                                            [Download CSV ↓]   │ │  │
│ │ [▶]  │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ │      │ │  ┌─ PORTFOLIO HERO STATS ─────────────────────────────────────────┐ │  │
│ │      │ │  │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │ │  │
│ │      │ │  │ │Total PnL │ │ Sharpe   │ │ Max DD   │ │Avg Correl│ │ Best   │ │ │  │
│ │      │ │  │ │ +$4,230  │ │   0.89   │ │  8.2%    │ │   0.67   │ │ SOL    │ │ │  │
│ │      │ │  │ │vs Idx+2.1│ │          │ │  $820    │ │ ⚠ High   │ │ +45.2% │ │ │  │
│ │      │ │  │ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘ │ │  │
│ │      │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ │      │ │  ┌─ PORTFOLIO EQUITY + BENCHMARK (Charts First!) ─────────────────┐ │  │
│ │      │ │  │ ┌─────────────────────────────────────────────────────────────┐ │ │  │
│ │      │ │  │ │     [Portfolio Line - BOLD]                                 │ │ │  │
│ │      │ │  │ │     [Benchmark Index - DASHED GRAY]                         │ │ │  │
│ │      │ │  │ │     [Dispersion Range - SHADED AREA]                        │ │ │  │
│ │      │ │  │ │     [Pinned Symbols - Optional Overlays]                    │ │ │  │
│ │      │ │  │ └─────────────────────────────────────────────────────────────┘ │ │  │
│ │      │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ │      │ │  ┌─ CHARTS ROW ───────────────────────────────────────────────────┐ │  │
│ │      │ │  │ ┌─ Underwater Chart ──────┐ ┌─ Correlation Matrix ───────────┐ │ │  │
│ │      │ │  │ │ [Drawdown % over time]  │ │ [Heatmap: Red=High, Blue=Low]  │ │ │  │
│ │      │ │  │ └─────────────────────────┘ └─────────────────────────────────┘ │ │  │
│ │      │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ │      │ │  ┌─ SYMBOL PERFORMANCE TABLE ─────────────────────────────────────┐ │  │
│ │      │ │  │ Symbol │Contrib│ Net PnL │ Win % │ Sharpe │ Pin │ View        │ │  │
│ │      │ │  │ SOL    │ +$1.2k│ +45.2%  │  78%  │  1.23  │ [📌]│ [→ Drill]   │ │  │
│ │      │ │  │ DOGE   │ +$890 │ +32.1%  │  72%  │  0.95  │ [  ]│ [→ Drill]   │ │  │
│ │      │ │  │ BNB    │ -$120 │ -12.3%  │  42%  │ -0.23  │ [  ]│ [→ Drill]   │ │  │
│ │      │ │  └─────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ └──────┘ └─────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## � Section 0: Header Bar

| Element              | Position | Description                                       |
| -------------------- | -------- | ------------------------------------------------- |
| **Strategy Name**    | Left     | "RSI Strategy"                                    |
| **Batch Count**      | Left     | "BATCH (12 symbols)"                              |
| **Allocation Badge** | Center   | `[Equal Weight]` or `[Risk Parity]` or `[Custom]` |
| **Fees Badge**       | Right    | `[Fees: ON]` or `[Fees: OFF]`                     |
| **Download CSV**     | Right    | Exports all symbols                               |

> ⚠️ **Allocation Logic** must be visible. A 50% gain on $10 is irrelevant vs. a 5% gain on $1M.

---

## 📊 Section 1: Portfolio Hero Stats

**Aggregated across ALL symbols.**

| Stat                 | Value Format                             | Color Logic                | Why Hero?                |
| -------------------- | ---------------------------------------- | -------------------------- | ------------------------ |
| **Total PnL**        | `+$4,230 (+8.9%)` with `vs Index: +2.1%` | Green if > Index           | Did we beat B&H?         |
| **Portfolio Sharpe** | `0.89`                                   | Color by value             | Risk-adjusted return     |
| **Max Drawdown**     | `8.2%` with `$820`                       | Always Red                 | Pain tolerance           |
| **Avg Correlation**  | `0.67` with warning if >0.7              | Red if >0.7, Green if <0.3 | **Diversification Risk** |
| **Best Symbol**      | `SOL +45.2%`                             | Always Green               | Top performer            |

> ⚠️ **Avg Correlation** is the key metric that differentiates this from a "List View." If BTC and ETH both crash, correlation = 1.0 = DANGER.

---

## 📊 Section 2: Portfolio Equity + Benchmark (CHARTS FIRST)

**The first thing a manager asks: "Did the portfolio work?"**

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  PORTFOLIO EQUITY (lightweight-charts)                          Height: 250px   │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                                                                           │  │
│  │     ███████████████████████ ← Dispersion Range (Best to Worst symbol)    │  │
│  │     ╱\     /\                                                             │  │
│  │    /  \   /  \     ← Portfolio Strategy (Bold, Primary Color)            │  │
│  │   /    \_/    \____                                                       │  │
│  │  ----____----____----  ← Benchmark Index (Dashed Gray)                   │  │
│  │  ·····················  ← Pinned: SOL (thin, if user pinned)             │  │
│  │                                                                           │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│  Legend: [━ Portfolio] [╌ Benchmark] [░ Dispersion] [· Pinned: SOL]             │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Chart Elements

| Element              | Style                             | Description                                |
| -------------------- | --------------------------------- | ------------------------------------------ |
| **Portfolio Line**   | Bold (3px), `var(--text-primary)` | Combined strategy performance              |
| **Benchmark Index**  | Dashed (2px), `var(--text-muted)` | Equal-weight B&H of same assets            |
| **Dispersion Range** | Shaded area, low opacity          | Shows spread between Best and Worst symbol |
| **Pinned Symbols**   | Thin (1px), unique color          | User-selected overlays (max 3)             |

### Benchmark Calculation

```typescript
// Benchmark = Equal-weight Buy & Hold of all batch symbols
const benchmarkReturn =
  symbols.reduce((sum, sym) => sum + sym.buyHoldReturn, 0) / symbols.length;
```

> ⚠️ **No Spaghetti Charts.** Default shows only Portfolio + Benchmark + Dispersion. Users can "Pin" specific symbols from the table.

---

## 📊 Section 3: Charts Row

### 3a. Underwater Chart (50% width)

Synced with Portfolio Equity above.

```
┌─────────────────────────────────────────┐
│  UNDERWATER (Portfolio Drawdown %)      │
│  0% ────────────────────────────────    │
│      ████████    ██████████████████     │
│ -8%      █████████             █████    │
└─────────────────────────────────────────┘
```

### 3b. Correlation Matrix Heatmap (50% width)

**Purpose:** Show which symbols move together (concentration risk).

```
┌─────────────────────────────────────────┐
│  CORRELATION MATRIX                     │
│        BTC   ETH   SOL   DOGE  BNB      │
│  BTC   1.00  0.92  0.78  0.45  0.81     │
│  ETH   0.92  1.00  0.85  0.52  0.79     │
│  SOL   0.78  0.85  1.00  0.38  0.67     │
│  DOGE  0.45  0.52  0.38  1.00  0.41     │
│  BNB   0.81  0.79  0.67  0.41  1.00     │
│                                         │
│  Color: Red = High (>0.7), Blue = Low   │
└─────────────────────────────────────────┘
```

### Correlation Heatmap Rules

| Correlation | Color                    | Interpretation         |
| ----------- | ------------------------ | ---------------------- |
| >0.7        | Red (`var(--danger)`)    | High — Not diversified |
| 0.3-0.7     | Yellow                   | Moderate               |
| <0.3        | Blue (`var(--info)`)     | Low — Well diversified |
| <0          | Green (`var(--success)`) | Negative — Hedge       |

> ⚠️ **Why Correlation > PnL Bar Chart?** If I run a "diversified portfolio" and all my assets have 0.9 correlation, I'm not diversified. I'm just gambling with extra steps.

---

## 📊 Section 4: Symbol Performance Table

**Sortable, with Contribution column.**

### Columns

| Column           | Width | Description                           |
| ---------------- | ----- | ------------------------------------- |
| Symbol           | 100px | `SOL/USDT`                            |
| **Contribution** | 100px | `+$1,230` (how much $ added to total) |
| Net PnL %        | 80px  | `+45.2%` (individual performance)     |
| Win Rate         | 60px  | `78%`                                 |
| # Trades         | 50px  | `24`                                  |
| Sharpe           | 60px  | `1.23`                                |
| Max DD %         | 60px  | `5.2%`                                |
| **Pin**          | 40px  | 📌 checkbox (adds to chart)           |
| Action           | 60px  | `[→ View]` button                     |

### "Contribution" Column Logic

```typescript
// Contribution = Actual $ added to portfolio
// NOT the same as Net PnL % if allocations differ
contribution = positionSize * returnPct;

// Example:
// SOL: 50% return on $2,000 position = +$1,000 contribution
// BTC: 10% return on $10,000 position = +$1,000 contribution
// Same contribution, different returns!
```

### "Pin" Feature

- Click 📌 to overlay that symbol's equity on the main chart.
- Max 3 pinned symbols (to prevent spaghetti).
- Pinned symbols appear in the chart legend.

---

## 🔍 Section 5: Drill-Down View

Same as before — reuses **Task 4 components** with breadcrumb navigation.

```
[← Back to Portfolio]  >  SOL/USDT
```

---

## 📦 Components to Create

| Component                    | Description                                       |
| ---------------------------- | ------------------------------------------------- |
| `BatchResultsDashboard.tsx`  | Main container for batch mode                     |
| `PortfolioHeroStats.tsx`     | 5-tile aggregate stats (includes Avg Correlation) |
| `PortfolioEquityChart.tsx`   | Multi-line with Dispersion Range                  |
| `CorrelationMatrix.tsx`      | Heatmap with color coding                         |
| `SymbolPerformanceTable.tsx` | Sortable with Contribution & Pin columns          |
| `BatchBreadcrumb.tsx`        | Navigation: `Portfolio > Symbol`                  |

### Reused from Task 4

- `HeroStats.tsx`
- `MetricsGrid.tsx`
- `EquityUnderwaterChart.tsx`
- `TradesTable.tsx`
- `TradeDeepDiveModal.tsx`

---

## 🔧 State Management

```typescript
interface BatchResultsState {
  batchRunId: number;
  symbols: string[];
  allocationMode: "equal_weight" | "risk_parity" | "custom";

  // Portfolio Aggregate
  totalPnL: number;
  totalPnLPct: number;
  benchmarkPnLPct: number; // Equal-weight B&H index
  portfolioSharpe: number;
  portfolioMaxDrawdownPct: number;
  portfolioMaxDrawdownValue: number;
  avgCorrelation: number; // Key diversification metric
  bestSymbol: { symbol: string; pnlPct: number };
  worstSymbol: { symbol: string; pnlPct: number };

  // Per-Symbol Data
  symbolResults: Array<{
    symbol: string;
    contribution: number; // Actual $ impact
    netPnL: number;
    netPnLPct: number;
    winRate: number;
    tradeCount: number;
    sharpe: number;
    maxDrawdownPct: number;
    isPinned: boolean; // For chart overlay
  }>;

  // Correlation Matrix
  correlationMatrix: Array<{
    symbolA: string;
    symbolB: string;
    correlation: number;
  }>;

  // Charts
  portfolioEquityCurve: Array<{ date: string; value: number }>;
  benchmarkEquityCurve: Array<{ date: string; value: number }>;
  dispersionRange: Array<{ date: string; min: number; max: number }>;
  symbolEquityCurves: Record<string, Array<{ date: string; value: number }>>;

  // Drill-Down
  selectedSymbol: string | null; // null = portfolio view

  // Table
  sortColumn: string;
  sortDirection: "asc" | "desc";
  pinnedSymbols: string[]; // Max 3
}
```

---

## ✅ Acceptance Criteria

- [ ] Header shows **Allocation Logic** badge (`[Equal Weight]`).
- [ ] Hero Stats include **Avg Correlation** with warning if >0.7.
- [ ] **Portfolio Equity Chart** is ABOVE the Symbol Table.
- [ ] Chart shows **Portfolio + Benchmark + Dispersion Range**.
- [ ] **Correlation Matrix** heatmap with color coding.
- [ ] Symbol Table has **Contribution** column ($ impact).
- [ ] Symbol Table has **Pin** column for chart overlay.
- [ ] Max 3 pinned symbols allowed.
- [ ] Drill-down reuses Task 4 components.
- [ ] CSV export includes all symbols with Contribution.

---

## 🚫 Anti-Patterns

- ❌ **Spaghetti Chart** — Use Dispersion Range, not 12 overlapping lines.
- ❌ **Missing Correlation** — If all assets have 0.9 correlation, that's not diversification.
- ❌ **Ignoring Contribution** — A 100% return on $10 is irrelevant vs. 1% on $10,000.
- ❌ **Missing Benchmark** — Portfolio vs. Index is the key comparison.
- ❌ **Table above Charts** — The aggregate visual must come FIRST.

---

## 📚 Libraries

| Library                     | Purpose                                |
| --------------------------- | -------------------------------------- |
| `lightweight-charts`        | Portfolio equity with dispersion range |
| `chart.js` or `visx`        | Correlation heatmap                    |
| `@tanstack/react-table`     | Symbol performance table               |
| `react-router` or `zustand` | Drill-down state management            |
