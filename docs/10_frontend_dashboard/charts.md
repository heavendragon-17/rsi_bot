# Charts

> TradingView Lightweight Charts and Recharts usage in the backtest UI.

---

## TradingView Lightweight Charts v5

Used for candlestick charts, equity curves, and trade detail views.

### Key APIs

```typescript
// Candlestick chart
const series = chart.addSeries(CandlestickSeries, options);

// Entry/exit markers
createSeriesMarkers(series, [
  { time, position: 'belowBar', shape: 'arrowUp', color: 'green', text: 'Entry' },
  { time, position: 'aboveBar', shape: 'arrowDown', color: 'red', text: 'Exit' }
]);

// SL/TP horizontal lines
series.createPriceLine({ price: 42500, color: 'red', title: 'SL', lineStyle: 2 });
series.createPriceLine({ price: 43500, color: 'green', title: 'TP1', lineStyle: 2 });

// Separate pane for oscillators
const pane = chart.addPane({ height: 150 });
pane.addSeries(LineSeries, { color: '#8b5cf6' });
```

### Trade Detail Chart Layout

```
┌─────────────────────────────────────────────┐
│  Candlestick + EMA overlay + Pine overlays  │
│  ▲ Entry marker   ▼ Exit marker             │
│  --- TP1/TP2 lines (green dashed)           │
│  --- SL line (red dashed)                   │
├─────────────────────────────────────────────┤
│  RSI oscillator pane                         │
│  --- 70 overbought / 30 oversold            │
├─────────────────────────────────────────────┤
│  [Pine oscillator panes, if toggled on]     │
└─────────────────────────────────────────────┘
```

Data: `GET /api/trades/{trade_id}/chart` returns OHLCV candles (50 before entry to 10 after exit), indicator arrays, and trade metadata.

---

## Recharts

Used for statistical charts: bar charts, pie charts, heatmap grids, tornado charts.

- Grid search results → heatmap grid
- Sensitivity analysis → tornado chart
- Monthly returns → bar chart
- Exit reason distribution → pie chart
