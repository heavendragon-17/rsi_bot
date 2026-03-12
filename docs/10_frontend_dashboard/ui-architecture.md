# UI Architecture

> React frontend architecture: navigation, Zustand stores, comparison modes, and export system.

---

## Navigation & Layout

```
┌──────────────────────────────────────────────────────────┐
│  [Backtest] [Batch] [Grid Search] [Walk-Forward]         │
│  [Sensitivity] [History]                                  │
├──────────────────────────────────────────────────────────┤
│  Sidebar (shared config)  │  Main content area (mode)    │
│  - Symbol selector        │                               │
│  - Strategy selector      │  (mode-specific content)      │
│  - Timeframe, dates       │                               │
│  - Capital, leverage      │                               │
│  - Strategy params        │                               │
│  - [Run] button           │                               │
└───────────────────────────┴──────────────────────────────┘
```

- **Top tab bar**: Mode switching (Backtest, Portfolio, Batch, Grid Search, Walk-Forward, Sensitivity, History)
- **Sidebar**: Always shows the same shared configuration regardless of mode. In "Portfolio" mode, the symbol selector expands to allow multiple symbol selection.
- **Main content area**: Mode-specific content and mode-specific config (grid axes, walk-forward windows, portfolio aggregation settings, etc.)

---

## Zustand Stores

| Store | Purpose | Persistence |
|-------|---------|-------------|
| `backtestStore` | Config + run orchestration | localStorage (config only) |
| `resultsStore` | Single backtest and portfolio results | None (loaded from API) |
| `historyStore` | Paginated run history | None (loaded from API) |
| `batchResultsStore` | Multi-symbol batch results | localStorage (flag only) |
| `gridSearchStore` | Grid search config + results | None |
| `walkForwardStore` | Walk-forward config + results | None |
| `sensitivityStore` | Sensitivity config + results | None |
| `exportStore` | Export config + trade annotations | localStorage (all) |
| `dataPrepStore` | Data download tracking | None |
| `themeStore` | UI themes (3 hardcoded) | None |


**SSE pattern**: `engineStore.ts` for SSE integration — session as param, SSE in `await new Promise`, `onerror` handler.

---

## Run History & Comparison

### History Page
- Server-side pagination + filtering (strategy, symbol, status, profitable_only, search)
- Failed runs visible with `status='failed'` and error message on click

### Comparison Modes

| Mode | Runs | Content |
|------|------|---------|
| Detailed | Exactly 2 | Overlay equity curves + metrics diff table + trade overlap timeline |
| Metrics | N (unlimited) | Metrics columns table only (no charts) |

---

## Export System

| Format | Content |
|--------|---------|
| CSV | Trade list with columns: trade_id, symbol, side, entry/exit times, prices, pnl, exit_reason, hold_time, SL/TP prices |
| JSON | Full run config + metrics + trades (reproducible) |

Summary row at CSV bottom: total trades, win rate, total PnL, avg PnL.

### Trade Annotations
- **Notes**: Free-text commentary per trade
- **Tags**: `star`, `review`, `learning`, `idea`, `lucky`, `unlucky`
- Stored in `exportStore` (localStorage), included in exports
