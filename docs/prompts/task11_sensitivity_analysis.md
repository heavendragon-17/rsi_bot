# Figma Agent Prompt: Task 11 — Sensitivity Analysis (Tornado Charts)

> **Phase:** 5 (Quant Tools)
> **Priority:** 🟡 High — Understand which parameters matter most.
> **Design Principle:** Show impact, not just values. Rank by importance.

---

## 🎯 Objective

Design the **Sensitivity Analysis Interface** that allows users to:

1. See how much each parameter affects the strategy
2. Identify which parameters are "fragile" (small change = big impact)
3. Prioritize which parameters to optimize

**Core Principle:** Not all parameters are equal. Some break your strategy, others are noise.

---

## 🧠 What is Sensitivity Analysis?

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  SENSITIVITY = How much does the OUTPUT change when you tweak the INPUT?        │
│  ───────────────────────────────────────────────────────────────────────────    │
│                                                                                 │
│  Example:                                                                       │
│  • RSI Period: 14 → 16 causes PnL to drop from +$1,330 to +$820 (−38%)         │
│  • Overbought: 70 → 75 causes PnL to change from +$1,330 to +$1,280 (−4%)      │
│                                                                                 │
│  Conclusion: RSI Period is HIGH SENSITIVITY, Overbought is LOW SENSITIVITY     │
│  → Focus optimization efforts on RSI Period, Overbought is stable.             │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📐 Layout Overview

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ SIDEBAR                                 MAIN CONTENT                              │
│ ┌──────┐ ┌─────────────────────────────────────────────────────────────────────┐  │
│ │      │ │  ┌─ HEADER ───────────────────────────────────────────────────────┐ │  │
│ │ [«]  │ │  │ 🌪️ Sensitivity Analysis                       [Export Report]  │ │  │
│ │ [⚙]  │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │ [▶]  │ │                                                                     │  │
│ │      │ │  ┌─ CONFIGURATION ────────────────────────────────────────────────┐ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  Base Settings: [Current Strategy ▼]                           │ │  │
│ │      │ │  │  Variation: [±10%] [±20%] [±30%] [Custom]                      │ │  │
│ │      │ │  │  Metric: [Net PnL ▼]                                           │ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  [▶ Run Sensitivity Analysis]                                  │ │  │
│ │      │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ │      │ │  ┌─ TORNADO CHART ────────────────────────────────────────────────┐ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  RSI Period     ◀════════════════════════════════════▶ ±38%   │ │  │
│ │      │ │  │  Stop Loss      ◀═══════════════════════▶                ±22%   │ │  │
│ │      │ │  │  Take Profit    ◀════════════════▶                       ±15%   │ │  │
│ │      │ │  │  Overbought     ◀═══════▶                                ±8%    │ │  │
│ │      │ │  │  Oversold       ◀═════▶                                  ±5%    │ │  │
│ │      │ │  │                 └─────────┴─────────┴─────────┴─────────┘       │ │  │
│ │      │ │  │                 -40%    -20%      0%     +20%    +40%           │ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ └──────┘ └─────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Section 1: Configuration Panel

### Variation Settings

```
┌───────────────────────────────────────────────────────────────────────┐
│  SENSITIVITY CONFIGURATION                                           │
│  ─────────────────────────────────────────────────────────────────    │
│                                                                       │
│  Base Settings: [Current Strategy ▼]                                  │
│                 (RSI=14, OB=70, OS=30, TP=3%, SL=2%)                 │
│                                                                       │
│  Variation Amount:                                                    │
│  [±10%]  [±20%]  [±30%]  [Custom: ___]                               │
│    ○      ●        ○                                                 │
│                                                                       │
│  For each parameter, we will test:                                    │
│  • Base − 20% (e.g., RSI = 11.2)                                     │
│  • Base (e.g., RSI = 14)                                             │
│  • Base + 20% (e.g., RSI = 16.8)                                     │
│                                                                       │
│  Metric to Measure: [Net PnL ▼]                                       │
│                                                                       │
│  Total Runs: 15 (5 params × 3 values)                                │
│                                                                       │
│  [▶ Run Sensitivity Analysis]                                        │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Section 2: Tornado Chart

### Main Visualization

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│  TORNADO CHART: Impact on Net PnL                                                 │
│  ────────────────────────────────────────────────────────────────────────────     │
│                                                                                   │
│  PARAMETER           LOW (-20%)              BASE              HIGH (+20%)        │
│  ─────────────────────────────────────────────────────────────────────────────    │
│                                                                                   │
│  RSI Period     ██████████████████████████████│█████████████████████████████████  │
│  (11→14→17)     -$510 (-38%)                  │                      +$420 (+32%) │
│                 ◀════════════════════════════│═══════════════════════════════▶   │
│                                               │                                   │
│  Stop Loss      ████████████████████│        │            │████████████████████  │
│  (1.6%→2%→2.4%) -$290 (-22%)        │        │            │         +$180 (+14%) │
│                 ◀══════════════════│════════│════════════│══════════════════▶   │
│                                               │                                   │
│  Take Profit    ██████████████│               │                    │█████████████│
│  (2.4%→3%→3.6%) -$200 (-15%)  │               │                    │   +$160(+12%)│
│                 ◀═════════════│═══════════════│════════════════════│═══════════▶ │
│                                               │                                   │
│  Overbought     ███████│                      │                          │███████│
│  (56→70→84)     -$106(-8%)                    │                          +$95(+7%)│
│                 ◀══════│══════════════════════│══════════════════════════│══════▶│
│                                               │                                   │
│  Oversold       █████│                        │                            │█████│
│  (24→30→36)     -$66(-5%)                     │                          +$53(+4%)│
│                 ◀════│════════════════════════│════════════════════════════│════▶│
│                                               │                                   │
│                 └──────────────────────┴──────┴──────┴──────────────────────┘     │
│                            -40%        -20%     0%    +20%        +40%            │
│                                                                                   │
│  📊 INSIGHT: RSI Period has the HIGHEST sensitivity. Handle with care.           │
└───────────────────────────────────────────────────────────────────────────────────┘
```

### Tornado Chart Design

| Element          | Description                                                      |
| ---------------- | ---------------------------------------------------------------- | --- | --- | ---- | ------------ |
| **Left Bar**     | Impact of LOW value (−20%) — typically negative, shown in red    |
| **Right Bar**    | Impact of HIGH value (+20%) — typically positive, shown in green |
| **Center Line**  | Base value (0% change)                                           |
| **Sorted Order** | Parameters sorted by TOTAL IMPACT (                              | low | +   | high | ) descending |
| **Labels**       | Show actual values (e.g., "RSI: 11→14→17")                       |

### Color Coding

| Direction              | Color             | Meaning                            |
| ---------------------- | ----------------- | ---------------------------------- |
| Low impact (negative)  | Red (`#EF4444`)   | Decreasing param hurts performance |
| High impact (positive) | Green (`#22C55E`) | Increasing param helps performance |
| Neutral                | Gray              | Little to no impact                |

---

## 📊 Section 3: Sensitivity Table

Detailed breakdown below the chart:

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│  DETAILED SENSITIVITY                                                             │
│  ────────────────────────────────────────────────────────────────────────────     │
│                                                                                   │
│  ┌─────────────────┬───────────┬───────────┬───────────┬───────────┬───────────┐  │
│  │ Parameter       │ Low Value │ Low PnL   │ Base PnL  │ High PnL  │ Sensitivity│  │
│  ├─────────────────┼───────────┼───────────┼───────────┼───────────┼───────────┤  │
│  │ RSI Period      │ 11        │ +$820     │ +$1,330   │ +$1,750   │ 🔴 HIGH   │  │
│  │ Stop Loss %     │ 1.6%      │ +$1,040   │ +$1,330   │ +$1,510   │ 🟡 MEDIUM │  │
│  │ Take Profit %   │ 2.4%      │ +$1,130   │ +$1,330   │ +$1,490   │ 🟡 MEDIUM │  │
│  │ Overbought      │ 56        │ +$1,224   │ +$1,330   │ +$1,425   │ 🟢 LOW    │  │
│  │ Oversold        │ 24        │ +$1,264   │ +$1,330   │ +$1,383   │ 🟢 LOW    │  │
│  └─────────────────┴───────────┴───────────┴───────────┴───────────┴───────────┘  │
│                                                                                   │
│  Sensitivity Categories:                                                          │
│  🔴 HIGH (>20% impact) — Critical parameter, optimize carefully                  │
│  🟡 MEDIUM (10-20% impact) — Important, worth tuning                             │
│  🟢 LOW (<10% impact) — Stable, less optimization needed                         │
│                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Section 4: Spider Chart (Optional)

Alternative visualization for multi-parameter sensitivity:

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│  SPIDER CHART: Parameter Sensitivity                                              │
│  ────────────────────────────────────────────────────────────────────────────     │
│                                                                                   │
│                           RSI Period                                              │
│                               ●                                                   │
│                              /│\                                                  │
│                             / │ \                                                 │
│                            /  │  \                                                │
│           Oversold  ●─────●   │   ●─────● Take Profit                            │
│                            \  │  /                                                │
│                             \ │ /                                                 │
│                              \│/                                                  │
│                               ●                                                   │
│                           Stop Loss                                               │
│                                                                                   │
│  Legend: [── Low Impact]  [── Medium]  [── High (outer ring)]                    │
│                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘
```

> ⚠️ **Spider Chart is optional.** Tornado Chart is the primary view.

---

## 📊 Section 5: Recommendations Panel

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│  💡 RECOMMENDATIONS                                                               │
│  ────────────────────────────────────────────────────────────────────────────     │
│                                                                                   │
│  Based on sensitivity analysis:                                                   │
│                                                                                   │
│  1. 🔴 RSI Period is your most sensitive parameter.                              │
│     → Small changes cause large swings in profit.                                │
│     → Use Grid Search to find the exact optimal value.                           │
│     → Consider Walk-Forward to validate stability.                               │
│                                                                                   │
│  2. 🟢 Overbought and Oversold are stable.                                       │
│     → Current values (70/30) are robust.                                         │
│     → Low priority for optimization.                                             │
│                                                                                   │
│  [Run Grid Search on RSI Period]     [View Walk-Forward for RSI Period]          │
│                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔧 State Management

```typescript
interface SensitivityState {
  // Configuration
  variationPercent: number; // 10, 20, 30, or custom
  metric: "net_pnl" | "sharpe" | "profit_factor" | "win_rate";

  // Execution
  isRunning: boolean;
  progress: number;

  // Results
  results: SensitivityResult[];
  insights: string[];
}

interface SensitivityResult {
  paramName: string;
  paramDisplayName: string;

  // Values tested
  lowValue: number;
  baseValue: number;
  highValue: number;

  // Results
  lowMetric: number;
  baseMetric: number;
  highMetric: number;

  // Computed
  lowImpactPct: number; // (low - base) / base * 100
  highImpactPct: number; // (high - base) / base * 100
  totalImpact: number; // |lowImpact| + |highImpact|
  sensitivity: "high" | "medium" | "low";
}
```

---

## 📦 Components to Create

| Component                  | Description                   |
| -------------------------- | ----------------------------- |
| `SensitivityAnalysis.tsx`  | Main container                |
| `SensitivityConfig.tsx`    | Variation % selector          |
| `TornadoChart.tsx`         | Main tornado visualization    |
| `TornadoBar.tsx`           | Individual parameter bar      |
| `SensitivityTable.tsx`     | Detailed breakdown table      |
| `SpiderChart.tsx`          | Optional spider visualization |
| `RecommendationsPanel.tsx` | Actionable insights           |

---

## ✅ Acceptance Criteria

- [ ] **Variation selector** allows ±10%, ±20%, ±30%, custom.
- [ ] **Tornado chart** shows all parameters sorted by total impact.
- [ ] **Bars** extend left (low) and right (high) from center.
- [ ] **Color coding**: red for negative impact, green for positive.
- [ ] **Sensitivity labels**: 🔴 HIGH, 🟡 MEDIUM, 🟢 LOW.
- [ ] **Table** shows exact values and PnL for each test.
- [ ] **Recommendations** link to Grid Search and Walk-Forward.
- [ ] **Progress bar** updates during execution.
- [ ] **Export** downloads sensitivity report.

---

## 🚫 Anti-Patterns

- ❌ **Unsorted tornado** — Must sort by total impact (highest first).
- ❌ **No sensitivity categories** — User must see HIGH/MEDIUM/LOW.
- ❌ **No actionable insights** — Must suggest next steps (Grid Search, etc.).
- ❌ **Only showing numbers** — Visual impact (bar length) is critical.
- ❌ **Missing center line** — Base value must be clearly marked.

---

## 📚 Libraries

| Library        | Purpose                   |
| -------------- | ------------------------- |
| `visx` or `d3` | Tornado and Spider charts |
| `recharts`     | Alternative for tornado   |
| SQLite         | Store sensitivity results |

---

## 🔍 Figma Agent Verification Protocol

**After completing this task, Figma Agent MUST:**

1. **Check for Errors** — Review all components for:

   - Tornado bars not centered correctly
   - Wrong sorting order (must be by total impact)
   - Colors inverted (red should be negative)
   - Sensitivity categories not matching thresholds
   - Table values not matching chart

2. **Fix Identified Issues** — Do not mark task complete until:

   - Bars extend symmetrically from center
   - Highest impact parameter is at top
   - Labels show correct values
   - Recommendations link to other tools

3. **Self-Test Checklist:**
   - [ ] Set ±20% variation → Parameters tested at ±20%
   - [ ] Run Analysis → Progress updates
   - [ ] Tornado shows RSI at top (highest impact)
   - [ ] Red bars extend left, green extend right
   - [ ] Table shows 🔴/🟡/🟢 categories
   - [ ] Click "Run Grid Search" → Navigates correctly
