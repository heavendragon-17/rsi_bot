# Figma Agent Prompt: Task 4 — Results Dashboard & Equity Curve

> **Phase:** 2 (Reports & Charts)
> **Priority:** 🔴 Critical — This is where the user judges their strategy.
> **Design Head Note:** "Beautiful, brutal, and honest."

---

## 🎯 Objective

Design the **Results Dashboard** that displays after a backtest completes. This is the "moment of truth" — the user sees if their strategy is Alpha or Garbage.

**Design Principle:** Information density over minimalism. Quants want data, not decoration.

---

## 📐 Layout Overview

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ SIDEBAR (collapsed)                      MAIN CONTENT                             │
│ ┌──────┐ ┌─────────────────────────────────────────────────────────────────────┐  │
│ │      │ │  ┌─ HEADER ───────────────────────────────────────────────────────┐ │  │
│ │ [«]  │ │  │ RSI Strategy • DOGE/USDT • 1h    [Fees: ON] [Download CSV ↓]  │ │  │
│ │ [⚙]  │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │ [▶]  │ │                                                                     │  │
│ │      │ │  ┌─ HERO STATS ───────────────────────────────────────────────────┐ │  │
│ │      │ │  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐   │ │  │
│ │      │ │  │  │ Net Profit │ │Profit Fact │ │  Max DD    │ │   Sharpe   │   │ │  │
│ │      │ │  │  │  +$1,330   │ │    1.95    │ │   2.78%    │ │    0.23    │   │ │  │
│ │      │ │  │  │vs B&H:+8.2%│ │ GW / GL    │ │   $278     │ │            │   │ │  │
│ │      │ │  │  └────────────┘ └────────────┘ └────────────┘ └────────────┘   │ │  │
│ │      │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ │      │ │  ┌─ METRICS GRID (2×5) ───────────────────────────────────────────┐ │  │
│ │      │ │  │ Sharpe  │ Sortino │ Calmar │ Volatility │ Win Rate    │ │  │
│ │      │ │  │  0.23   │  0.31   │  4.79  │   9.86%    │ 83.3% (30/36)│ │  │
│ │      │ │  ├─────────┼─────────┼────────┼────────────┼───────────────│ │  │
│ │      │ │  │ Avg Win │Avg Loss │ Best   │ Worst      │ Consec Wins   │ │  │
│ │      │ │  │ $91.11  │-$233.82 │$349.82 │ -$297.17   │      8        │ │  │
│ │      │ │  └─────────┴─────────┴────────┴────────────┴───────────────┘ │  │
│ │      │ │                                                                     │  │
│ │      │ │  ┌─ EQUITY + UNDERWATER (Stacked Charts) ────────────────────────┐ │  │
│ │      │ │  │  ┌─ Equity Curve ─────────────────────────────────────────┐   │ │  │
│ │      │ │  │  │     [Area Chart - Balance over time]                   │   │ │  │
│ │      │ │  │  │     Height: 200px                                      │   │ │  │
│ │      │ │  │  └────────────────────────────────────────────────────────┘   │ │  │
│ │      │ │  │  ┌─ Underwater Chart (Drawdown %) ────────────────────────┐   │ │  │
│ │      │ │  │  │     [Inverted Area - RED. Shows pain duration]         │   │ │  │
│ │      │ │  │  │     Height: 80px. Synced X-axis.                       │   │ │  │
│ │      │ │  │  └────────────────────────────────────────────────────────┘   │ │  │
│ │      │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ │      │ │  ┌─ EXIT REASONS + ACTIVE FILTER ─────────────────────────────────┐ │  │
│ │      │ │  │  ┌─ Donut ────────────────┐  ┌─ Filter Badge ────────────────┐ │ │  │
│ │      │ │  │  │ [Click slice to filter]│  │ [×] Filter: Stop Loss (6 tr) │ │ │  │
│ │      │ │  │  └────────────────────────┘  └────────────────────────────────┘ │ │  │
│ │      │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ │      │ │  ┌─ TRADES TABLE ─────────────────────────────────────────────────┐ │  │
│ │      │ │  │ # │ Entry Time  │ Symbol │ Side │ Entry $ │ PnL   │ Exit Reason│ │  │
│ │      │ │  │ 1 │ 2025-10-28  │ DOGE   │ LONG │ $0.201  │+$40.00│ LOCK_PROFIT│ │  │
│ │      │ │  │   │ ... (click row for Deep Dive)                              │ │  │
│ │      │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ └──────┘ └─────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## � Section 0: Header Bar

### Required Elements

| Element           | Position | Description                                            |
| ----------------- | -------- | ------------------------------------------------------ |
| **Strategy Name** | Left     | "RSI Strategy"                                         |
| **Symbol + TF**   | Left     | "DOGE/USDT • 1h"                                       |
| **Fees Badge**    | Right    | `[Fees: ON]` or `[Fees: OFF]` — **Critical for trust** |
| **Download CSV**  | Right    | `[Download CSV ↓]` button — **Escape hatch**           |

### Fees Badge Logic

```typescript
// The "Liar's Toggle" — Users must know if profits are real or fantasy
<Badge variant={feesEnabled ? "success" : "warning"}>
  Fees: {feesEnabled ? "ON" : "OFF"}
</Badge>
```

> ⚠️ **If Fees are OFF, the Net Profit is a lie.** Make this visually obvious.

---

## 📊 Section 1: Hero Stats (REVISED)

**Win Rate is DEMOTED.** Quants know a 90% win rate with one massive loss = bankruptcy.

| Stat              | Value Format                               | Color Logic                               | Why Hero?                              |
| ----------------- | ------------------------------------------ | ----------------------------------------- | -------------------------------------- |
| **Net Profit**    | `+$1,330.41 (+13.3%)` with `vs B&H: +8.2%` | Green if > B&H, Red if < B&H              | **Context is King.** Beat the market?  |
| **Profit Factor** | `1.95` with `GW / GL` subtitle             | Green if >1.5, Yellow if 1-1.5, Red if <1 | **True robustness measure.**           |
| **Max Drawdown**  | `2.78%` with `$278` dollar value           | Always Red (it's risk)                    | Pain tolerance.                        |
| **Sharpe Ratio**  | `0.23`                                     | Green if >1, Yellow if 0-1, Red if <0     | **Industry standard "business card."** |

### Animation

- Numbers **count up** from 0 on page load (500ms duration).
- Use `framer-motion` or `react-countup`.

---

## 📊 Section 2: Metrics Grid (REVISED)

Win Rate moved here. Two rows of 5 metrics.

### Row 1: Risk-Adjusted Performance

| Metric         | Format         |
| -------------- | -------------- |
| Sortino Ratio  | `0.31`         |
| Calmar Ratio   | `4.79`         |
| Volatility     | `9.86%`        |
| **Expectancy** | `$36.96/trade` |
| Consec Wins    | `8`            |

### Row 2: Trade Statistics

| Metric       | Format                          |
| ------------ | ------------------------------- |
| Avg Win      | `$91.11` (Green)                |
| Avg Loss     | `-$233.82` (Red)                |
| Best Trade   | `$349.82` (Green)               |
| Worst Trade  | `-$297.17` (Red)                |
| **Win Rate** | `83.3%` with `(30/36)` subtitle |

---

## 📊 Section 3: Equity + Underwater Charts (STACKED)

> ⚠️ **The Underwater Chart is mandatory.** Quants need to see pain duration, not just profit.

### Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  EQUITY CURVE + BENCHMARK (lightweight-charts)                 Height: 200px │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │         ╱\                                                             │  │
│  │        /  \    ╱\    /\     ← Strategy (Solid Green/Red)              │  │
│  │   ____/    \__/  \__/  \____/\____                                    │  │
│  │  ----____----____----____----____  ← Buy & Hold (Gray Dashed)         │  │
│  │                                                                        │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  UNDERWATER CHART (lightweight-charts - Inverted Area)         Height: 80px │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ 0% ─────────────────────────────────────────────────────────────────  │  │
│  │      ██████         ████████████████                                  │  │
│  │-5%       ███████████                ██████████████████████ ← Pain     │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ← Synced X-Axis (Zoom/Pan together) →                                      │
│  Legend: [━ Strategy] [╌ Buy & Hold]                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Benchmark Line (MANDATORY)

> ⚠️ **Context is King.** Without the benchmark, +13% profit is meaningless. If B&H made +50%, you underperformed.

| Element         | Style                                                         |
| --------------- | ------------------------------------------------------------- |
| Strategy Line   | Solid, `var(--success)` or `var(--danger)` based on final PnL |
| Buy & Hold Line | Dashed, `var(--text-muted)` (Gray)                            |
| Legend          | Below chart: `[━ Strategy: +13.3%] [╌ Buy & Hold: +8.2%]`     |

### Underwater Chart Rules

- **Y-Axis:** Inverted (0% at top, -50% at bottom).
- **Fill:** `var(--danger)` with low opacity.
- **Sync:** X-axis must sync with Equity Curve (zoom/pan together).
- **Tooltip:** Show duration: "In drawdown for 23 days (2.8% depth)".

---

## 📊 Section 4: Exit Reasons + Active Filter

### Donut Chart

- Click on a slice to filter the Trades Table.
- Slices: TP1, TP2, TP3, Lock Profit, SL, Disaster SL.

### Active Filter Badge (MANDATORY)

> ⚠️ **This prevents user confusion.** Without it, users think trades are missing.

```
┌─────────────────────────────────────────┐
│  [×] Filter: Stop Loss (6 trades)       │  ← Dismissible chip
└─────────────────────────────────────────┘
```

- **Position:** Next to the Donut OR above the Trades Table header.
- **Format:** `[×] Filter: {Exit Reason} ({count} trades)`.
- **Action:** Click `×` to clear filter.

---

## 📊 Section 5: Trades Table

### Columns

| Column      | Width | Format                 |
| ----------- | ----- | ---------------------- |
| #           | 40px  | Row number             |
| Entry Time  | 140px | `YYYY-MM-DD HH:mm`     |
| Exit Time   | 140px | `YYYY-MM-DD HH:mm`     |
| Symbol      | 100px | `DOGE/USDT`            |
| Side        | 60px  | `LONG` / `SHORT` badge |
| Entry $     | 80px  | `$0.20115`             |
| Exit $      | 80px  | `$0.20172`             |
| Size $      | 80px  | Position size in USD   |
| PnL         | 80px  | `+$40.00` (colored)    |
| Exit Reason | 100px | Badge (TP1, SL, etc.)  |

### Features

- **Sortable:** Click column header to sort.
- **Pagination:** 25 rows per page.
- **Row Click:** Opens **Deep Dive Modal**.
- **Filter Badge:** Shown above table when filter is active.

---

## 🔍 Section 6: Deep Dive Modal (FIXED LAYOUT)

> ⚠️ **No infinite stacking of indicators.** Use a fixed 1+1 layout.

### Chart Layout Strategy

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ Trade #124: DOGE/USDT (LONG)                                    [×] Close    │
├───────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌─ VIEW TABS ──────────────────────────────────────────────────────────────┐ │
│  │ [Price + EMAs]  [Oscillators (RSI)]  [Volume]                            │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  ┌─ MAIN CHART PANE (Fixed Height: 300px) ──────────────────────────────────┐ │
│  │                                                                          │ │
│  │     [Candlestick Chart - TradingView Style]                              │ │
│  │                                                                          │ │
│  │     Overlays (always visible):                                           │ │
│  │     - EMA21 (blue), EMA200 (orange)                                      │ │
│  │                                                                          │ │
│  │     Markers:                                                             │ │
│  │     ▲ Entry (Green arrow)                                                │ │
│  │     ▼ Exit (Red/Green based on PnL)                                      │ │
│  │     --- SL Level (Red dashed line)                                       │ │
│  │     --- TP1/TP2/TP3 Levels (Green dashed lines)                          │ │
│  │     --- Lock Profit Level (Cyan dashed line)                             │ │
│  │                                                                          │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  ┌─ SUB-CHART PANE (Fixed Height: 100px) ───────────────────────────────────┐ │
│  │                                                                          │ │
│  │     [Content depends on selected tab]                                    │ │
│  │     - "Oscillators": RSI + EMA9 + WMA45                                  │ │
│  │     - "Volume": Volume bars                                              │ │
│  │                                                                          │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  ┌─ TRADE SUMMARY ──────────────────────────────────────────────────────────┐ │
│  │ Entry: $0.20115 @ 2025-10-28 13:45                                       │ │
│  │ Exit:  $0.20172 @ 2025-10-28 21:30  (Hold: 7.8h)                         │ │
│  │ PnL:   +$40.00 (+2.8%)    Exit: LOCK_PROFIT (0.2R)                       │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  ┌─ NOTES ──────────────────────────────────────────────────────────────────┐ │
│  │ [Textarea for user annotations]                                          │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  [← Previous Trade]                                    [Next Trade →]         │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Fixed Layout Rules

| Rule                   | Implementation                            |
| ---------------------- | ----------------------------------------- |
| **1 Main + 1 Sub**     | Only 2 chart panes. No infinite stacking. |
| **Tabs for Switching** | User selects what to see in the sub-pane. |
| **Fixed Heights**      | Main: 300px, Sub: 100px. Never grows.     |

---

## 📦 Components to Create

| Component                   | Description                             |
| --------------------------- | --------------------------------------- |
| `ResultsDashboard.tsx`      | Main container                          |
| `HeaderBar.tsx`             | Fees badge, CSV download                |
| `HeroStats.tsx`             | 4-card animated stats (revised metrics) |
| `MetricsGrid.tsx`           | 2×5 compact metrics table               |
| `EquityUnderwaterChart.tsx` | Stacked: Equity + Underwater            |
| `ExitReasonsChart.tsx`      | Donut chart with filter callback        |
| `ActiveFilterBadge.tsx`     | Dismissible filter chip                 |
| `TradesTable.tsx`           | Sortable, paginated, filtered           |
| `TradeDeepDiveModal.tsx`    | Slideout with tabbed charts             |
| `CandlestickChart.tsx`      | TradingView-style chart                 |
| `TradeNotes.tsx`            | Textarea for annotations                |

---

## 🔧 State Management

```typescript
interface ResultsState {
  runId: number;

  // Integrity
  feesEnabled: boolean;
  slippageEnabled: boolean;

  // Hero Stats
  netProfit: number;
  netProfitPct: number;
  benchmarkProfitPct: number; // Buy & Hold return for comparison
  profitFactor: number;
  grossWin: number;
  grossLoss: number;
  maxDrawdownPct: number;
  maxDrawdownValue: number;
  sharpeRatio: number;

  // Metrics Grid
  sortinoRatio: number;
  calmarRatio: number;
  volatility: number;
  expectancy: number;
  maxConsecWins: number;
  winRate: number;
  winCount: number;
  lossCount: number;
  avgWin: number;
  avgLoss: number;
  largestWin: number;
  largestLoss: number;

  // Charts
  equityCurve: Array<{ date: string; balance: number }>;
  underwaterCurve: Array<{ date: string; drawdownPct: number }>;
  exitReasons: Record<string, number>;

  // Filter
  activeFilter: string | null; // e.g., "SL", "TP1", null

  // Trades
  trades: Trade[];
  filteredTrades: Trade[]; // Derived
  selectedTradeId: number | null;

  // Modal
  tradeModalTab: "price" | "oscillators" | "volume";
}
```

---

## ✅ Acceptance Criteria

- [ ] Header shows **Fees: ON/OFF** badge.
- [ ] Header has **Download CSV** button.
- [ ] Hero Stats: Net Profit (with **vs B&H**), **Profit Factor**, Max DD, **Sharpe Ratio**.
- [ ] **Expectancy** demoted to Metrics Grid.
- [ ] Win Rate in Metrics Grid (not Hero).
- [ ] **Underwater Chart** below Equity Curve (synced X-axis).
- [ ] **Benchmark line** (B&H) on Equity Chart.
- [ ] Exit Reasons filter shows **Active Filter Badge**.
- [ ] Deep Dive Modal uses **tabbed layout** (1 Main + 1 Sub).
- [ ] All colors use CSS variables.
- [ ] Light/Dark mode compatible.

---

## 🚫 Anti-Patterns

- ❌ **Win Rate as Hero** — It's a vanity metric. Use Profit Factor.
- ❌ **Infinite chart stacking** — Fixed 1+1 layout only.
- ❌ **Filter without feedback** — Must show Active Filter Badge.
- ❌ **No CSV export** — Trust requires data portability.
- ❌ **Unlabeled fees** — Users must know if profits include costs.

---

## 📚 Libraries

| Library                 | Purpose                                                           |
| ----------------------- | ----------------------------------------------------------------- |
| `lightweight-charts`    | **ALL line/area charts** (Candles, Equity, Underwater, Benchmark) |
| `chart.js`              | **Donut chart ONLY** (Exit Reasons)                               |
| `react-countup`         | Animated hero stats                                               |
| `react-window`          | Virtualized trades table                                          |
| `framer-motion`         | Modal animations                                                  |
| `@tanstack/react-table` | Sortable, paginated, filtered table                               |
| `file-saver`            | CSV download                                                      |

> ⚠️ **Library Unification:** Use `lightweight-charts` for all line/area charts to ensure consistent zoom/crosshair behavior and handle large datasets (10k+ points) performantly.
