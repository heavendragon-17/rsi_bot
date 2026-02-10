# Sensitivity Analysis - Visual Reference

## Tornado Chart Layout

```
┌────────────────────────────────────────────────────────────────────────────────┐
│  TORNADO CHART: Impact on Net PnL                                              │
│  Sorted by Total Impact                                                        │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│  RSI Period (11 → 14 → 17)                                        🔴 HIGH     │
│  ████████████████████████████│█████████████████████████████████               │
│  -38%                         │                              +32%              │
│                                                                                │
│  Stop Loss % (1.6 → 2.0 → 2.4)                                  🟡 MEDIUM     │
│  ████████████████│             │          │████████████████                    │
│  -22%            │             │          │              +14%                  │
│                                                                                │
│  Take Profit % (2.4 → 3.0 → 3.6)                                🟡 MEDIUM     │
│  ███████████│                  │               │██████████████                 │
│  -15%       │                  │               │            +12%               │
│                                                                                │
│  Overbought (56 → 70 → 84)                                      🟢 LOW        │
│  ████│                        │                       │████                    │
│  -8% │                        │                       │   +7%                  │
│                                                                                │
│  Oversold (24 → 30 → 36)                                        🟢 LOW        │
│  ███│                         │                        │███                    │
│  -5%│                         │                        │  +4%                  │
│                                                                                │
│      └─────────────────────────┴────────────────────────┘                      │
│      -40%        -20%          0%         +20%        +40%                     │
│                                                                                │
│  📊 Key Insight: RSI Period has the highest sensitivity (70% total impact).   │
│     Small changes to this parameter cause large performance swings.           │
└────────────────────────────────────────────────────────────────────────────────┘
```

## Color Coding

- **Left Bars (Red)**: Negative impact when parameter decreases
- **Right Bars (Green)**: Positive impact when parameter increases
- **Badge Colors**:
  - 🔴 RED: HIGH sensitivity (>20% total impact)
  - 🟡 YELLOW: MEDIUM sensitivity (10-20% total impact)
  - 🟢 GREEN: LOW sensitivity (<10% total impact)

## Configuration Panel

```
┌────────────────────────────────────────────────────────────────────────┐
│  SENSITIVITY CONFIGURATION                                             │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  Base Settings: [rsi_no_retest]                                       │
│  Testing 8 parameters with current values as baseline                 │
│                                                                        │
│  Variation Amount:                                                     │
│  [±10%]  [±20%*]  [±30%]  [Custom: ___]                               │
│                                                                        │
│  Each parameter tested at: Base − 20%, Base, Base + 20%               │
│                                                                        │
│  Metric: [Net PnL ($) ▼]                                               │
│                                                                        │
│  Total Tests: 24 (8 params × 3 values)                                │
│  Estimated time: ~5 seconds                                           │
│                                                                        │
│  [▶ Run Sensitivity Analysis]                                         │
└────────────────────────────────────────────────────────────────────────┘
```

## Detailed Table

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  Parameter      Low Val  Low PnL    Base Val  Base PnL   High Val  High PnL   Impact  │
├────────────────────────────────────────────────────────────────────────────────────────┤
│  RSI Period        11    $820         14      $1,330       17      $1,750     70.0%   │
│  [Highest]              -38.3%                                     +31.6%     🔴 HIGH  │
│                                                                                        │
│  Stop Loss %      1.6    $1,040       2.0     $1,330      2.4      $1,510     36.0%   │
│                         -21.8%                                     +13.5%     🟡 MED   │
│                                                                                        │
│  Take Profit %    2.4    $1,130       3.0     $1,330      3.6      $1,490     27.0%   │
│                         -15.0%                                     +12.0%     🟡 MED   │
│                                                                                        │
│  Overbought       56     $1,224       70      $1,330      84       $1,425     15.0%   │
│                          -8.0%                                      +7.1%     🟢 LOW   │
│                                                                                        │
│  Oversold         24     $1,264       30      $1,330      36       $1,383      9.0%   │
│                          -5.0%                                      +4.0%     🟢 LOW   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

## Recommendations Panel

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│  💡 RECOMMENDATIONS                                                                │
├────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                    │
│  🔴 RSI Period is your most sensitive parameter (70% total impact).                │
│     Small changes cause large swings in profit.                                   │
│     → Use Grid Search to find the exact optimal value.                            │
│     → Consider Walk-Forward to validate stability.                                │
│                                                                                    │
│  🟢 Overbought and Oversold are stable parameters.                                │
│     Current values (70/30) are robust.                                            │
│     → Low priority for optimization.                                              │
│                                                                                    │
│  ┌─────────────────────────────────┐  ┌─────────────────────────────────┐        │
│  │ 🔥 Run Grid Search              │  │ 📈 Validate with Walk-Forward   │        │
│  │                                 │  │                                 │        │
│  │ Optimize RSI Period to find    │  │ Test RSI Period stability       │        │
│  │ the exact best value.           │  │ across time periods.            │        │
│  │                                 │  │                                 │        │
│  │ [Open Grid Search]              │  │ [Open Walk-Forward]             │        │
│  └─────────────────────────────────┘  └─────────────────────────────────┘        │
└────────────────────────────────────────────────────────────────────────────────────┘
```

## Key Features

### ✅ Implemented Features

1. **Configuration**
   - Variation selector (±10%, ±20%, ±30%, custom)
   - Metric selection (Net PnL, Sharpe, Profit Factor, Win Rate)
   - Base settings display with parameter count
   - Test count and time estimation

2. **Tornado Chart**
   - Sorted by total impact (highest first)
   - Bidirectional bars (left=negative/red, right=positive/green)
   - Center line at 0% (base value)
   - Impact percentages on/near bars
   - Sensitivity badges (HIGH/MEDIUM/LOW)
   - Hover tooltips with detailed values
   - Key insight card for highest sensitivity param

3. **Detailed Table**
   - All test values and results
   - Impact percentages with color coding
   - Sensitivity categories with emoji indicators
   - Highest impact row highlighted
   - Legend explaining categories

4. **Recommendations**
   - Dynamic insights based on results
   - High sensitivity parameter warnings
   - Stable parameter identification
   - Asymmetric impact detection
   - Direct navigation to Grid Search
   - Direct navigation to Walk-Forward

5. **Progress & Export**
   - Real-time progress bar
   - Current parameter display
   - Cancel button to abort
   - CSV export with full report
   - Insights included in export

### 🎨 Visual Design

- **Professional**: Clean card-based layout
- **Technical Zen**: No cartoons, financial aesthetic
- **Color Meaningful**: Red=danger/negative, Green=positive/stable, Yellow=caution
- **Hierarchy Clear**: Headers, sections, badges, tooltips
- **Responsive**: Works on desktop and larger tablets
- **Themeable**: Uses CSS variables from theme system

### 🔗 Integration

- **Navbar**: Wind icon in quant tools section
- **Mode**: "sensitivity" in routing system
- **Navigation**: Links to Grid Search and Walk-Forward
- **State**: Zustand store with persistence
- **Export**: CSV download with timestamp

---

**Implementation Complete**: All 7 components created, fully integrated, tested against acceptance criteria.
