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

- **Top tab bar**: Mode switching (Backtest, Portfolio, Batch, Grid Search, Walk-Forward, Sensitivity, History, Signal Review)
- **Sidebar**: Always shows the same shared configuration regardless of mode. In "Portfolio" mode, the symbol selector expands to allow multiple symbol selection.
- **Main content area**: Mode-specific content and mode-specific config (grid axes, walk-forward windows, portfolio aggregation settings, etc.)

### Signal Review workspace

The `signal-review` mode is a full-page workspace with no normal backtest
sidebar. It has one shared implementation with M5/M15 tabs and a saved
`Good Signals` filter. The list is server-paginated and displays trigger time,
timeframe, trigger-close price, quality, human outcome, and note presence.

Selecting a row opens a full-page detail view with newer/older navigation. It
renders the exact Telegram card, the structured signal snapshot, objective
forward observations, review controls, and a Lightweight Charts market replay.
The chart has trigger-timeframe candles, EMA21, RSI21/EMA9/WMA45, a trigger
marker, crosshair, wheel zoom, drag pan, synchronized price/oscillator scales,
and lazy forward loading.

Review is deliberately staged: the initial chart stops at the trigger close.
Saving `GOOD`, `BAD`, or `UNCERTAIN` unlocks forward candles and enables
`WIN`, `LOSS`, and `SKIP`. Notes are debounced and saved server-side; the
quality and outcome labels are separate fields so a visually good alert can
still lose and a profitable alert can still be marked poor quality.

### Timeframe Selector

The Asset Config section exposes a row of preset pills (`1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`) plus a free-form text input that accepts any Binance-compatible timeframe string of the form `\d+[mhdw]` (e.g. `3m`, `2h`, `12h`, `1w`). The same controls are mirrored in `MobileSidebarSheet.tsx`. The store derives bars-per-day from the timeframe string via `barsPerDayFor()` so the relative-date sync and bar estimate work for any value, not just the presets.

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
| `signalReviewStore` | BTC M5/M15 replay list, detail, chart, review, and SSE orchestration | None |
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
