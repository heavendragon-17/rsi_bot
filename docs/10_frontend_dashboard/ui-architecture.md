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
sidebar. It opens on the latest completed replay run, defaults to signals that
still need review, and keeps every list request scoped to the selected run so
rerunning a historical window cannot mix duplicate events into the review
queue. The list is server-paginated and displays trigger time, timeframe,
trigger-close price, quality, human outcome, and note presence.

Dataset preparation is data-aware. The launcher first shows the aligned
intersection of the canonical M5, M15, H1, and H4 CSV coverage, including the
row count for each source. Reviewers choose **all available data** or a bounded
30-day, 90-day, or one-year preset; arbitrary manual dates are not exposed.
The store resumes the visible progress stream after a page refresh when the
same API process still owns an active run. Interrupted database rows are
reported as failed instead of leaving the page permanently busy.

Selecting a row opens a full-page detail view that shows the reviewer's queue
position and uses **Previous** / **Next signal** navigation. A completed outcome
makes the Next signal action visually primary. The exact Telegram card,
structured signal snapshot, objective forward observations, and Lightweight
Charts market replay remain supporting evidence below the review controls.

The detail view presents the market replay and an optional **TP/SL trade plan**
side by side on desktop, with the chart on the left and the exchange-style
controls on the right. The signal candle close is a read-only entry; the
reviewer enters both long take-profit and stop-loss prices before deciding
whether the chart is good, bad, or uncertain. Saving the plan draws both levels
on the price chart and stores the plan while future candles are still hidden.
After an explicit quality label unlocks the future, the native signal-timeframe
candles are evaluated and the result records the first level touched and
elapsed time, or reports an open/no-data/ambiguous same-candle state. This is
an objective OHLC observation only: it does not calculate 1R, PnL, or overwrite
the manual outcome label.

At the desktop `lg` breakpoint and above, the work area uses an eight-column
chart region and a four-column TP/SL region. Below that breakpoint it stacks
the controls below the chart so both surfaces remain usable on narrower screens.

The human decision surface is a sticky bar above that work area on desktop:
**1. Entry quality** (`GOOD`, `BAD`, `UNCERTAIN`) followed by an optional
**2. Manual outcome** (`WIN`, `LOSS`, `SKIP`). Buttons use explicit labels,
icons, selected states, and at least 40–48 px heights. Notes and autosave state
remain in the same decision surface.

The chart can switch independently between the run's native **M5**, **M15**,
**H1**, and **H4** sources without changing the selected signal or its human
review. It shows price candles with EMA21/EMA200 and a synchronized oscillator
pane with RSI21, EMA9(RSI21), and WMA45(RSI21), plus the signal price, marker,
crosshair, wheel zoom, drag pan, and lazy forward loading. For a timeframe that
does not close exactly at the M5/M15 signal timestamp, the marker uses the
latest fully closed native candle at or before that timestamp and the UI labels
that point-in-time anchor explicitly.

Unlocking future inspection loads 2,000 candles in the currently selected chart
timeframe but keeps a readable signal-centered viewport. Panning to the loaded
edge appends another 2,000 candles using that chart timeframe's duration and
preserves the current logical range instead of jumping back to the signal.

Review is deliberately staged: the initial chart stops at the trigger close.
Saving `GOOD`, `BAD`, or `UNCERTAIN` unlocks the 2,000-candle future window and
enables `WIN`, `LOSS`, and `SKIP`. Notes are debounced and saved server-side;
label and note writes are serialized so a response cannot overwrite an unsent draft.
Ordinary note/outcome saves update the current list locally instead of
reloading and reconstructing the chart. The quality and outcome labels are
separate fields so a visually good alert can still lose and a profitable alert
can still be marked poor quality.

### Timeframe Selector

The Asset Config section exposes a row of preset pills (`1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`) plus a free-form text input that accepts any Binance-compatible timeframe string of the form `\d+[mhdw]` (e.g. `3m`, `2h`, `12h`, `1w`). The same controls are mirrored in `MobileSidebarSheet.tsx`. The store derives bars-per-day from the timeframe string via `barsPerDayFor()` so the relative-date sync and bar estimate work for any value, not just the presets.

### Theme-aware native controls

The application supports both light and dark theme families. Native `select`
controls use the browser's dark color scheme whenever the root has the `dark`
class, and their `option`/`optgroup` rows receive explicit theme background and
foreground colors. This prevents Windows Chromium from combining a white native
popup with inherited light text while leaving light-theme controls unchanged.

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
| `signalReviewStore` | BTC M5/M15 signal list plus M5/M15/H1/H4 chart, detail, review, and SSE orchestration | None |
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
