# Pine Indicator System

> Custom indicators drawn on trade detail charts. Does NOT execute Pine strategies.

---

## Purpose

Users can paste PineScript code to add custom indicator overlays on the trade detail chart. This is visualization-only — no trading logic execution.

## Flow

1. **Paste**: User pastes PineScript code in the indicator editor
2. **Verify**: Parser extracts metadata:
   - Type: `overlay` (draws on price chart) or `oscillator` (separate pane)
   - Parameters (inputs)
   - Output plots (lines, fills)
3. **Save**: Stored in localStorage as `SavedIndicator` via `pineStore`

## Chart Integration

| Type | Rendering |
|------|-----------|
| Overlay (EMA, Bollinger) | `LineSeries` on main candlestick pane |
| Oscillator (RSI, MACD) | Own pane via `chart.addPane()` |

Strategy built-in indicators are always shown. Pine indicators are toggled on/off by the user.

## Computation

v1: Common indicators (SMA, EMA, RSI, MACD, Bollinger) computed client-side using a JavaScript TA library. Complex/custom indicators reserved for future backend computation.
