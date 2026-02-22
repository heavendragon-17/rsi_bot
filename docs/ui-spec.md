# UI Specification

> Navigation, Zustand stores, charts, themes, CSS variables, Pine indicators, export system.

---

## Navigation & Layout

### Mode Switching: Top Tab Bar

```
┌──────────────────────────────────────────────────────────┐
│  [Backtest] [Batch] [Grid Search] [Walk-Forward]         │
│  [Sensitivity] [History]                                  │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  Main content area (mode-specific)                        │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

### Sidebar: Shared Config Only

Always shows the same configuration regardless of mode:
- Symbol selector, Strategy selector, Timeframe selector
- Date range (start/end + lookback presets)
- Capital, leverage, risk percent
- Strategy parameters (RSI period, EMA lengths, TP ratios, etc.)
- **Run button** (at bottom)

Mode-specific configuration (grid axes, walk-forward windows, etc.) lives in the **main content area**.

---

## Zustand Stores

| Store | Purpose | Persistence |
|-------|---------|-------------|
| `backtestStore` | Config + run orchestration | localStorage (config only) |
| `resultsStore` | Single backtest results | None (loaded from API) |
| `historyStore` | Paginated run history | None (loaded from API) |
| `batchResultsStore` | Multi-symbol portfolio results | localStorage (flag only) |
| `gridSearchStore` | Grid search config + results | None |
| `walkForwardStore` | Walk-forward config + results | None |
| `sensitivityStore` | Sensitivity config + results | None |
| `exportStore` | Export config + trade annotations | localStorage (all) |
| `dataPrepStore` | Data download tracking | None |
| `themeStore` | UI themes (3 hardcoded) | None |
| `pineStore` | Custom indicator library | localStorage (saved indicators) |

**Reference pattern**: `engineStore.ts` for SSE integration (session as param, SSE in `await new Promise`, `onerror` handler).

---

## Run History & Comparison

### History Page

- Server-side pagination + filtering (strategy, symbol, status, profitable_only, search)
- Failed runs visible with `status='failed'` and error message on click

### Comparison Modes

| Mode | Runs | Content |
|------|------|---------|
| Detailed comparison | Exactly 2 | Overlay equity curves + metrics diff table + trade overlap timeline |
| Metrics comparison | N (unlimited) | Metrics columns table only (no charts) |

**Detailed comparison view**:
- Overlay equity curves (two on one Lightweight Chart)
- Metrics diff table: Run A vs Run B vs Delta
- Trade overlap timeline: horizontal timeline with position periods

---

## Charts

### TradingView Lightweight Charts v5

Used for candlestick charts and equity curves. Already in `package.json`.

**Key APIs**:
- `chart.addSeries(CandlestickSeries, options)` — price chart
- `createSeriesMarkers(series, [...])` — entry/exit arrows
- `series.createPriceLine({ price, color, title })` — SL/TP horizontal lines
- `chart.addPane({ height })` — separate pane for RSI
- `pane.addSeries(LineSeries, { color })` — indicator lines

### Recharts

Used for bar charts, pie charts, grids, tornado charts.

---

## Themes

### 3 Hardcoded Themes

| Theme | Mode |
|-------|------|
| `cyberpunk-neon` | Dark |
| `beach-paradise` | Light |
| `midnight-ocean` | Dark (Bloomberg style) |

Stored in frontend `themeStore` only. Applied via `document.documentElement.style.setProperty()`.

### CSS Variable Contract

All components MUST use CSS variables. No hardcoded colors.

```css
/* Layer 1: Backgrounds */
--bg-primary       /* Deep base color (body background) */
--bg-secondary     /* Card/panel backgrounds */
--bg-surface       /* Glass surfaces with opacity */
--bg-elevated      /* Modals, dropdowns */

/* Layer 2: Text (WCAG AA validated) */
--text-primary     /* Headings - Contrast ≥ 7:1 */
--text-secondary   /* Body text - Contrast ≥ 4.5:1 */
--text-muted       /* Hints, placeholders - Contrast ≥ 3:1 */

/* Layer 3: Interactive */
--accent           /* Primary buttons, links */
--accent-hover     /* Hover state */
--accent-active    /* Active/pressed state */

/* Layer 4: Semantic (Trading-specific) */
--success          /* Profit, long positions, positive */
--success-light    /* Lighter variant for backgrounds */
--danger           /* Loss, short positions, errors */
--danger-light     /* Lighter variant for backgrounds */
--warning          /* Rate limits, pending states */

/* Layer 5: Structure */
--border           /* Borders, dividers */
--border-focus     /* Focus rings */
--glow             /* Glow effects, shadows */
--overlay          /* Modal overlays */

/* Layer 6: RGB Values (for opacity manipulation) */
--accent-rgb       /* e.g., "139, 92, 246" for rgba() */
--success-rgb
--danger-rgb
```

### Theme Palettes

#### Cyberpunk Neon (Dark)

| Token | Value | Contrast vs bg |
|-------|-------|---------------|
| --bg-primary | #0f172a | — |
| --text-primary | #f8fafc | 15.4:1 |
| --text-secondary | #cbd5e1 | 9.1:1 |
| --accent | #8b5cf6 | 4.6:1 |
| --success | #10b981 | 4.5:1 |
| --danger | #f43f5e | 4.7:1 |

#### Beach Paradise (Light)

| Token | Value | Contrast vs bg |
|-------|-------|---------------|
| --bg-primary | #fef7ed | — |
| --text-primary | #1e293b | 12.6:1 |
| --text-secondary | #475569 | 7.0:1 |
| --accent | #0d9488 | 4.5:1 |
| --success | #059669 | 4.6:1 |
| --danger | #dc2626 | 5.4:1 |

#### Midnight Ocean (Dark - Bloomberg)

| Token | Value | Contrast vs bg |
|-------|-------|---------------|
| --bg-primary | #0a1628 | — |
| --text-primary | #e2e8f0 | 11.8:1 |
| --text-secondary | #94a3b8 | 5.7:1 |
| --accent | #0ea5e9 | 4.8:1 |
| --success | #22c55e | 5.3:1 |
| --danger | #ef4444 | 5.0:1 |

### Performance Mode

Disable `backdrop-filter` for low-latency environments via `.performance-mode` CSS class.

---

## Pine Indicator System

### Purpose

Draw custom indicators on the trade detail chart. Does NOT execute Pine strategies.

### Flow

1. **Paste**: User pastes PineScript code
2. **Verify**: Parser extracts metadata (type: overlay/oscillator, parameters, output plots)
3. **Save**: Stored in localStorage as `SavedIndicator`

### Chart Integration

- **Overlays** (EMA, Bollinger): `LineSeries` on main candlestick pane
- **Oscillators** (RSI, MACD): Own pane via `chart.addPane()`
- Strategy built-in indicators always shown; Pine indicators toggled on/off

### Computation

v1: Compute common indicators (SMA, EMA, RSI, MACD, Bollinger) client-side using JS TA library. Reserve backend computation for complex/custom indicators.

---

## Export System

### Supported Formats (v1)

| Format | Content |
|--------|---------|
| **CSV** | Trade list with all columns |
| **JSON** | Full run config + metrics + trades (reproducible) |

PDF is deferred.

### CSV Columns

trade_id, symbol, side, entry_time, exit_time, entry_price, exit_price, quantity, size_usd, pnl, pnl_pct, exit_reason, hold_time_hours, sl_price, tp1_price, tp2_price, tp3_price

Summary row at bottom: total trades, win rate, total PnL, avg PnL.

### Trade Annotations

- **Notes**: Free-text commentary per trade
- **Tags**: `star`, `review`, `learning`, `idea`, `lucky`, `unlucky`
- Stored in `exportStore` (localStorage)
- Included in CSV/JSON exports
