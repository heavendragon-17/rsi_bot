# Figma Agent Prompt: Task 10 — Walk-Forward Optimization

> **Phase:** 5 (Quant Tools)
> **Priority:** 🔴 Critical — This is how quants avoid curve-fitting.
> **Design Principle:** Show time, not just results. The past is training, the future is truth.

---

## 🎯 Objective

Design the **Walk-Forward Optimization Interface** that allows users to:

1. Split data into rolling In-Sample (IS) and Out-of-Sample (OOS) windows
2. Optimize on IS, validate on OOS, then "walk forward"
3. See if strategy holds up in unseen data

**Core Principle:** A strategy that only works on training data is worthless. Prove it works on fresh data.

---

## 🧠 What is Walk-Forward?

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  WALK-FORWARD CONCEPT                                                           │
│  ───────────────────────────────────────────────────────────────────────────    │
│                                                                                 │
│  WINDOW 1:  [======= IS =======][=== OOS ===]                                  │
│  WINDOW 2:       [======= IS =======][=== OOS ===]                             │
│  WINDOW 3:            [======= IS =======][=== OOS ===]                        │
│  WINDOW 4:                 [======= IS =======][=== OOS ===]                   │
│             └────────────────────────────────────────────────────┘              │
│                           Full data range                                       │
│                                                                                 │
│  IS = In-Sample (optimize here)                                                 │
│  OOS = Out-of-Sample (validate here — this is the REAL test)                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📐 Layout Overview

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ SIDEBAR                                 MAIN CONTENT                              │
│ ┌──────┐ ┌─────────────────────────────────────────────────────────────────────┐  │
│ │      │ │  ┌─ HEADER ───────────────────────────────────────────────────────┐ │  │
│ │ [«]  │ │  │ 🚶 Walk-Forward Optimization                 [Export Results]  │ │  │
│ │ [⚙]  │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │ [▶]  │ │                                                                     │  │
│ │      │ │  ┌─ CONFIGURATION ────────────────────────────────────────────────┐ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  IS Window: [60] days    OOS Window: [20] days                 │ │  │
│ │      │ │  │  Step Size: [20] days    Total Windows: 8                      │ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  Optimize: [RSI Period ▼]  Range: [10]-[20] Step: [2]         │ │  │
│ │      │ │  │  Metric: [Sharpe Ratio ▼]                                      │ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  [▶ Run Walk-Forward]                                          │ │  │
│ │      │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ │      │ │  ┌─ TIMELINE VISUALIZATION ───────────────────────────────────────┐ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  ┌──W1──┐ ┌──W2──┐ ┌──W3──┐ ┌──W4──┐ ┌──W5──┐ ┌──W6──┐        │ │  │
│ │      │ │  │  │IS│OOS│ │IS│OOS│ │IS│OOS│ │IS│OOS│ │IS│OOS│ │IS│OOS│        │ │  │
│ │      │ │  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘        │ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  Best IS Param:  14    14    12    14    16    14             │ │  │
│ │      │ │  │  OOS Result:     +5%   +3%   -2%   +4%   +1%   +6%            │ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ │      │ │  ┌─ RESULTS SUMMARY ──────────────────────────────────────────────┐ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  OOS Win Rate: 5/6 (83%)    Avg OOS Return: +2.8%             │ │  │
│ │      │ │  │  Verdict: ✅ ROBUST                                            │ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ └──────┘ └─────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Section 1: Configuration Panel

### Window Settings

```
┌───────────────────────────────────────────────────────────────────────┐
│  WINDOW CONFIGURATION                                                 │
│  ─────────────────────────────────────────────────────────────────    │
│                                                                       │
│  In-Sample (IS) Window:     [60] days   ← Training period            │
│  Out-of-Sample (OOS) Window:[20] days   ← Validation period          │
│  Step Size (Walk Forward):  [20] days   ← How far to advance         │
│                                                                       │
│  ─────────────────────────────────────────────────────────────────    │
│  Total Data Range: Jan 1 - Dec 31, 2024 (365 days)                   │
│  Windows Generated: 8                                                 │
│  ─────────────────────────────────────────────────────────────────    │
│                                                                       │
│  ⚠️ Recommended: IS >= 3× OOS for stable optimization                │
└───────────────────────────────────────────────────────────────────────┘
```

### Parameter to Optimize

```
┌───────────────────────────────────────────────────────────────────────┐
│  OPTIMIZATION TARGET                                                  │
│  ─────────────────────────────────────────────────────────────────    │
│                                                                       │
│  Parameter: [RSI Period ▼]                                            │
│  Range: [10] to [20]   Step: [2]                                      │
│                                                                       │
│  Optimize For: [Sharpe Ratio ▼]                                       │
│                                                                       │
│  Options: Sharpe | Net PnL | Profit Factor | Sortino                 │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Section 2: Timeline Visualization

### Window Blocks

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│  WALK-FORWARD TIMELINE                                                            │
│  ────────────────────────────────────────────────────────────────────────────     │
│                                                                                   │
│  Jan 1                                                              Dec 31        │
│  ├────────────────────────────────────────────────────────────────────────┤      │
│                                                                                   │
│  ┌────────────┬──────┐                                                            │
│  │     IS     │ OOS  │  Window 1: Jan 1 - Mar 1                                  │
│  │   60 days  │20 day│  Best Param: RSI = 14                                     │
│  │  Sharpe:1.2│+5.2% │  IS Sharpe: 1.2 → OOS Return: +5.2%                       │
│  └────────────┴──────┘                                                            │
│         ╲                                                                         │
│          ╲  (Step: 20 days)                                                       │
│           ╲                                                                       │
│  ┌────────────┬──────┐                                                            │
│  │     IS     │ OOS  │  Window 2: Jan 21 - Mar 21                                │
│  │   60 days  │20 day│  Best Param: RSI = 14                                     │
│  │  Sharpe:1.1│+3.1% │  IS Sharpe: 1.1 → OOS Return: +3.1%                       │
│  └────────────┴──────┘                                                            │
│         ╲                                                                         │
│          ╲  (continues...)                                                        │
│                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘
```

### Compact View (All Windows)

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│  ALL WINDOWS                                                                      │
│  ────────────────────────────────────────────────────────────────────────────     │
│                                                                                   │
│  ┌─W1─┐ ┌─W2─┐ ┌─W3─┐ ┌─W4─┐ ┌─W5─┐ ┌─W6─┐ ┌─W7─┐ ┌─W8─┐                        │
│  │████│ │████│ │████│ │████│ │████│ │████│ │████│ │████│                        │
│  │░░░░│ │░░░░│ │░░░░│ │░░░░│ │░░░░│ │░░░░│ │░░░░│ │░░░░│                        │
│  └────┘ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘                        │
│   RSI   RSI   RSI   RSI   RSI   RSI   RSI   RSI                                 │
│   =14   =14   =12   =14   =16   =14   =14   =12                                 │
│                                                                                   │
│   +5%   +3%   -2%   +4%   +1%   +6%   +2%   +3%                                  │
│   ✅    ✅    ❌    ✅    ✅    ✅    ✅    ✅                                     │
│                                                                                   │
│  Legend: ████ = IS (training)   ░░░░ = OOS (validation)                          │
└───────────────────────────────────────────────────────────────────────────────────┘
```

### Color Coding

| OOS Result       | Color  | Icon |
| ---------------- | ------ | ---- |
| Positive         | Green  | ✅   |
| Negative         | Red    | ❌   |
| Neutral (< 0.5%) | Yellow | ⚠️   |

---

## 📊 Section 3: Results Summary

### Robustness Score

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│  WALK-FORWARD RESULTS                                                             │
│  ────────────────────────────────────────────────────────────────────────────     │
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │                                                                             │  │
│  │  OOS WIN RATE                    AVG OOS RETURN          ROBUSTNESS        │  │
│  │  ┌───────────────┐               ┌───────────────┐       ┌─────────────┐   │  │
│  │  │    7 / 8      │               │    +2.8%      │       │ ✅ ROBUST   │   │  │
│  │  │    (87%)      │               │   per window  │       │             │   │  │
│  │  └───────────────┘               └───────────────┘       └─────────────┘   │  │
│  │                                                                             │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                   │
│  ┌─ DETAILED METRICS ──────────────────────────────────────────────────────────┐  │
│  │                                                                             │  │
│  │  Total OOS Return: +22.4%                                                   │  │
│  │  Best Window: W6 (+6.0%, RSI=14)                                            │  │
│  │  Worst Window: W3 (-2.0%, RSI=12)                                           │  │
│  │  Most Common Best Param: RSI = 14 (5/8 windows)                             │  │
│  │  Parameter Stability: High (std = 1.2)                                      │  │
│  │                                                                             │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                   │
│  [View Detailed Report]              [Apply RSI=14 to Strategy]                   │
└───────────────────────────────────────────────────────────────────────────────────┘
```

### Robustness Verdict

| OOS Win Rate | Verdict     | Color  |
| ------------ | ----------- | ------ |
| ≥ 70%        | ✅ ROBUST   | Green  |
| 50-70%       | ⚠️ MARGINAL | Yellow |
| < 50%        | ❌ OVERFIT  | Red    |

---

## 📊 Section 4: Equity Curve Comparison

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│  EQUITY COMPARISON: IS vs OOS                                                     │
│  ────────────────────────────────────────────────────────────────────────────     │
│                                                                                   │
│  ┌───────────────────────────────────────────────────────────────────────────┐    │
│  │                                                                           │    │
│  │      ╱╲                                                                   │    │
│  │     ╱  ╲     ← IS Equity (training performance)                          │    │
│  │    ╱    ╲╱╲                                                               │    │
│  │   ╱        ╲                                                              │    │
│  │  ----____----____  ← OOS Equity (validation performance)                 │    │
│  │                                                                           │    │
│  │  W1    W2    W3    W4    W5    W6    W7    W8                            │    │
│  └───────────────────────────────────────────────────────────────────────────┘    │
│                                                                                   │
│  Legend: [━ IS (In-Sample)]  [╌ OOS (Out-of-Sample)]                             │
│                                                                                   │
│  ⚠️ If OOS consistently underperforms IS, strategy may be overfit.               │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔧 State Management

```typescript
interface WalkForwardState {
  // Configuration
  isWindowDays: number;
  oosWindowDays: number;
  stepSizeDays: number;

  paramToOptimize: string;
  paramMin: number;
  paramMax: number;
  paramStep: number;

  optimizeMetric: "sharpe" | "net_pnl" | "profit_factor" | "sortino";

  // Computed
  totalWindows: number;
  estimatedTimeMinutes: number;

  // Execution
  isRunning: boolean;
  currentWindow: number;
  progress: number;

  // Results
  windows: WalkForwardWindow[];
  summary: {
    oosWinRate: number;
    oosWinCount: number;
    avgOosReturn: number;
    totalOosReturn: number;
    bestWindow: { index: number; return: number; param: number };
    worstWindow: { index: number; return: number; param: number };
    mostCommonParam: { value: number; count: number };
    paramStability: "high" | "medium" | "low";
    verdict: "robust" | "marginal" | "overfit";
  } | null;
}

interface WalkForwardWindow {
  index: number;
  isStartDate: string;
  isEndDate: string;
  oosStartDate: string;
  oosEndDate: string;

  // Optimization result
  bestParam: number;
  isMetricValue: number; // e.g., IS Sharpe

  // Validation result
  oosReturn: number;
  oosReturnPct: number;
  isPositive: boolean;
}
```

---

## 📦 Components to Create

| Component                   | Description               |
| --------------------------- | ------------------------- |
| `WalkForward.tsx`           | Main container            |
| `WindowConfig.tsx`          | IS/OOS/Step inputs        |
| `ParamOptimizeConfig.tsx`   | Parameter range config    |
| `TimelineVisualization.tsx` | Window blocks with IS/OOS |
| `WindowBlock.tsx`           | Individual window visual  |
| `WalkForwardProgress.tsx`   | Progress during execution |
| `ResultsSummary.tsx`        | Win rate, verdict card    |
| `EquityCurveComparison.tsx` | IS vs OOS chart           |

---

## ✅ Acceptance Criteria

- [ ] **IS/OOS/Step inputs** with validation (IS >= 3× OOS recommended).
- [ ] **Window count** calculated and displayed.
- [ ] **Timeline visualization** shows overlapping IS/OOS blocks.
- [ ] **Each window** shows best param + OOS result.
- [ ] **Color coding** for positive/negative OOS.
- [ ] **Summary** shows OOS win rate + verdict.
- [ ] **Verdict** is ROBUST (≥70%), MARGINAL (50-70%), OVERFIT (<50%).
- [ ] **Equity comparison** shows IS vs OOS performance.
- [ ] **Apply best param** loads most common param into strategy.
- [ ] **Progress bar** updates during execution.

---

## 🚫 Anti-Patterns

- ❌ **No OOS validation** — The whole point is OOS, not IS.
- ❌ **Single backtest** — Must run multiple windows to prove robustness.
- ❌ **No verdict** — User must see ROBUST/MARGINAL/OVERFIT clearly.
- ❌ **Confusing timeline** — Window blocks must clearly show IS vs OOS.
- ❌ **No stability metric** — If best param varies wildly, strategy is unstable.

---

## 📚 Libraries

| Library              | Purpose                    |
| -------------------- | -------------------------- |
| `lightweight-charts` | Equity curve comparison    |
| `d3` or `visx`       | Timeline visualization     |
| SQLite               | Store walk-forward results |

---

## 🔍 Figma Agent Verification Protocol

**After completing this task, Figma Agent MUST:**

1. **Check for Errors** — Review all components for:

   - Window count calculation incorrect
   - Timeline blocks overlapping incorrectly
   - OOS results not color-coded
   - Verdict not matching win rate thresholds
   - Progress bar not updating

2. **Fix Identified Issues** — Do not mark task complete until:

   - All windows display correctly
   - IS/OOS clearly distinguishable
   - Verdict matches win rate rules
   - Equity comparison renders

3. **Self-Test Checklist:**
   - [ ] Set IS=60, OOS=20, Step=20 → Windows calculated
   - [ ] Run Walk-Forward → Progress updates
   - [ ] Each window shows best param + OOS result
   - [ ] Positive OOS = green ✅, Negative = red ❌
   - [ ] Win rate ≥70% → ROBUST verdict
   - [ ] Apply Best Param → Strategy updated
