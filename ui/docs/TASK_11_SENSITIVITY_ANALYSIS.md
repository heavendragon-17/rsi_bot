# Task 11: Sensitivity Analysis (Tornado Charts) - COMPLETED ✅

## Overview
Comprehensive sensitivity analysis system that helps traders identify which strategy parameters have the most impact on performance. The system uses tornado charts to visualize parameter sensitivity and provides actionable insights for optimization priorities.

## Implementation Summary

### New Files Created

#### Stores
- `/stores/sensitivityStore.ts` - Complete state management with sensitivity analysis logic

#### Components
- `/components/sensitivity/SensitivityAnalysis.tsx` - Main container with header and layout
- `/components/sensitivity/SensitivityConfig.tsx` - Configuration panel with variation settings
- `/components/sensitivity/TornadoChart.tsx` - Main tornado visualization with sorted results
- `/components/sensitivity/TornadoBar.tsx` - Individual parameter bar with bidirectional impact
- `/components/sensitivity/SensitivityTable.tsx` - Detailed breakdown table with categories
- `/components/sensitivity/RecommendationsPanel.tsx` - Actionable insights and navigation
- `/components/sensitivity/index.ts` - Barrel export file
- `/components/Sensitivity.tsx` - Re-export wrapper

### Modified Files
- `/stores/backtestStore.ts` - Added "sensitivity" mode type
- `/App.tsx` - Added sensitivity mode routing
- `/components/layout/Navbar.tsx` - Added Wind icon button for sensitivity analysis

## Core Features

### 1. Configuration Panel ✅
- **Variation Settings**: ±10%, ±20%, ±30%, or custom percentage
- **Metric Selection**: Net PnL, Sharpe Ratio, Profit Factor, Win Rate
- **Base Settings Display**: Shows current strategy and parameter count
- **Run Summary**: Total tests calculation and time estimate
- **Execute Button**: Run/Cancel with visual state

### 2. Tornado Chart Visualization ✅
- **Sorted Display**: Parameters ordered by total impact (highest first)
- **Bidirectional Bars**:
  - Left bars (red) show negative impact of decreasing parameter
  - Right bars (green) show positive impact of increasing parameter
  - Bars extend from center line (base value)
- **Color Coding**:
  - Red (#EF4444) for negative impact
  - Green (#22C55E) for positive impact
- **Value Labels**: Impact percentages displayed on or near bars
- **Sensitivity Badges**: HIGH/MEDIUM/LOW indicators for each parameter
- **Axis Labels**: Percentage scale with center line at 0%
- **Key Insight Card**: Highlights most sensitive parameter

### 3. Detailed Table ✅
- **Complete Breakdown**: All parameter values and results
- **Columns**:
  - Parameter name with sensitivity badge
  - Low value (-variation%) with result and impact%
  - Base value with result
  - High value (+variation%) with result and impact%
  - Total impact percentage
  - Sensitivity category (🔴/🟡/🟢)
- **Color Coding**: Red/green for negative/positive impacts
- **Highlight**: Top row highlighted as highest impact
- **Legend**: Explains sensitivity categories

### 4. Recommendations Panel ✅
- **Dynamic Insights**: Generated based on analysis results
- **Insight Types**:
  - Highest sensitivity parameter identification
  - Multiple high-sensitivity warning (overfitting risk)
  - Stable parameter identification
  - Asymmetric impact detection
- **Action Buttons**:
  - Link to Grid Search for high-sensitivity parameters
  - Link to Walk-Forward for stability validation
- **Contextual Cards**: Shows next steps with parameter-specific recommendations

### 5. Progress Tracking ✅
- **Real-time Updates**: Shows current parameter being analyzed
- **Progress Bar**: Visual percentage complete
- **Cancellation**: Stop button to abort analysis

### 6. Export Functionality ✅
- **CSV Report**: Complete results with all metrics
- **Includes**:
  - Configuration (variation%, metric)
  - All parameter results (low/base/high values and impacts)
  - Sensitivity categories
  - Generated insights
- **Filename**: `sensitivity_analysis_[timestamp].csv`

## Technical Implementation

### State Management
```typescript
interface SensitivityState {
  variationPercent: number;
  customVariation: string;
  metric: SensitivityMetric;
  isRunning: boolean;
  progress: number;
  currentParam: string;
  results: SensitivityResult[];
  insights: string[];
  baseMetricValue: number;
}
```

### Sensitivity Calculation
- **Low Impact**: (low_metric - base_metric) / base_metric * 100
- **High Impact**: (high_metric - base_metric) / base_metric * 100
- **Total Impact**: |low_impact| + |high_impact|
- **Categories**:
  - HIGH: >20% total impact
  - MEDIUM: 10-20% total impact
  - LOW: <10% total impact

### Mock Data Generation
- Semi-realistic sensitivity patterns
- Different parameters have different sensitivity profiles:
  - RSI Period: High sensitivity (1.5x factor)
  - EMA Fast/Slow: Medium sensitivity (1.2x factor)
  - TP/SL: Medium sensitivity (1.15-1.3x factor)
  - Overbought/Oversold: Low sensitivity (0.6x factor)
- Non-linear impact based on deviation from base

### Insight Generation
- Identifies highest sensitivity parameter
- Warns if multiple high-sensitivity params (overfitting risk)
- Highlights stable parameters
- Detects asymmetric impacts (2x ratio threshold)

## Visual Design

### Color Scheme
- **Red (#EF4444)**: Negative impact / High sensitivity
- **Yellow/Orange (#D97706)**: Medium sensitivity
- **Green (#22C55E)**: Positive impact / Low sensitivity
- **Gray**: Neutral/baseline

### Layout
- Clean card-based design
- Responsive grid for recommendations
- Hover states for detailed information
- Professional financial aesthetic

### Typography
- Clear hierarchy with section headers
- Monospace for numeric values
- Badges for categories
- Icons for visual clarity (Wind, Lightbulb, Flame, TrendingUp)

## Integration

### Navigation
- **Navbar Button**: Wind icon in quant tools section
- **Mode**: "sensitivity" in backtest store
- **Navigation Links**: From recommendations to Grid Search and Walk-Forward

### Data Flow
1. User configures variation % and metric
2. Click "Run Sensitivity Analysis"
3. System tests each parameter at -variation%, base, +variation%
4. Results calculated and sorted by total impact
5. Insights generated based on sensitivity patterns
6. User can export or navigate to optimization tools

## Testing Checklist

✅ Variation selector (±10%, ±20%, ±30%, custom)
✅ Tornado chart shows all parameters sorted by total impact
✅ Bars extend left (low/red) and right (high/green) from center
✅ Color coding correct (red=negative, green=positive)
✅ Sensitivity labels (🔴 HIGH, 🟡 MEDIUM, 🟢 LOW)
✅ Table shows exact values and impacts
✅ Recommendations link to Grid Search and Walk-Forward
✅ Progress bar updates during execution
✅ Export downloads CSV report
✅ Cancel button stops analysis
✅ Empty state displayed before first run
✅ Key insight highlights highest sensitivity param

## Key Metrics

- **Components**: 7 new files
- **Store**: 1 new store file
- **Lines of Code**: ~1,100 lines
- **Features**: 6 major features (config, chart, table, recommendations, progress, export)
- **Integration Points**: 3 (navbar, app routing, store)

## Usage Example

1. **Navigate**: Click Wind icon in navbar
2. **Configure**:
   - Select variation amount (e.g., ±20%)
   - Choose metric (e.g., Net PnL)
3. **Execute**: Click "Run Sensitivity Analysis"
4. **Review**:
   - Tornado chart shows RSI Period has 38% total impact (HIGH)
   - Overbought/Oversold have 5-8% impact (LOW)
5. **Action**: Click "Open Grid Search" to optimize RSI Period
6. **Export**: Download CSV report for documentation

## Design Principles Maintained

✅ **Technical Zen**: Professional, no cartoons
✅ **Show Impact**: Visual bar length represents importance
✅ **Ranked by Importance**: Sorted by total impact descending
✅ **Actionable**: Direct links to optimization tools
✅ **Color Meaning**: Red=danger/negative, Green=positive/stable
✅ **Progressive Disclosure**: Summary → Details → Recommendations

## Next Steps

Users can now:
1. Identify critical parameters for optimization
2. Navigate to Grid Search for precise tuning
3. Use Walk-Forward to validate stability
4. Export analysis for reporting
5. Focus optimization efforts on high-impact parameters

---

**Status**: ✅ COMPLETE - Task 11 fully implemented and integrated
**Date**: February 8, 2026
