# PLAN: Figma UI V3 — Strategy Command Center (Final Architecture)

> **Goal:** Build a professional-grade Backtest UI with database storage, grid search, and quant testing methodologies.

---

## 🎯 Scope

| UI                  | Focus                                       | Runs On       | Status               |
| ------------------- | ------------------------------------------- | ------------- | -------------------- |
| **Backtest UI**     | Configure, run, compare, optimize backtests | Local machine | ✅ **Implement Now** |
| **Live Trading UI** | Monitor positions, edit live params         | VPS           | 📐 **Design Only**   |

---

## 🔴 Global Agent Instructions

```
CRITICAL RULES FOR FIGMA AGENT:
1. SEARCH THE INTERNET for inspiration (TradingView, Binance, QuantConnect).
2. USE EXTERNAL LIBRARIES freely (Framer Motion, Chart.js, Lottie, Monaco Editor).
3. REMIND yourself of the active theme's color palette before designing.
4. NO EMOJIS as icons. Use Heroicons/Lucide SVGs only.
5. This is a PROFESSIONAL QUANT TOOL — prioritize data density over minimalism.
6. Themes are stored in DATABASE. Load CSS variables from `themes` table.
```

---

## 🏗️ Architecture

### System Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          LOCAL MACHINE                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────────┐     ┌──────────────────────────────────────────────┐  │
│   │  React UI   │────▸│  Python Backend (subprocess)                 │  │
│   │  (localhost │     │  - cli/run_backtest_cli.py                   │  │
│   │   :3000)    │◂────│  - cli/grid_search_cli.py                    │  │
│   │             │     │  - cli/db_manager.py                         │  │
│   └─────────────┘     └──────────────────────────────────────────────┘  │
│         │                            │                                  │
│         │                            ▼                                  │
│         │             ┌──────────────────────────────────────────────┐  │
│         │             │  SQLite Database (backtest.db)               │  │
│         │             │  - runs, run_configs, run_results            │  │
│         │             │  - run_timeseries (lazy load)                │  │
│         └────────────▸│  - trades, tags, comparisons                 │  │
│                       │  - themes (scalable N themes)                │  │
│                       └──────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Folder Structure

```
rsi_bot/
├── app/
│   ├── backtest/
│   ├── strategies/
│   └── cli/
│       ├── run_backtest_cli.py
│       ├── grid_search_cli.py
│       └── db_manager.py
│
├── ui/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── stores/
│   │   └── themes/           # Theme loader from DB
│   └── package.json
│
├── data/
│   └── backtest.db
│
└── docs/
    ├── ARCHITECTURE.md
    └── DATABASE.md
```

---

## � Task Breakdown (13 Tasks)

### Phase 1: Core Layout & Controls (Tasks 1-3)

#### Task 1: Collapsible Sidebar Layout

**Prompt File:** `prompts/task1_layout.md`

**Scope:**

- No wizard. All settings in collapsible sidebar.
- Main content: Results dashboard OR empty state.
- Navbar: [History | Compare | Settings | Theme Selector]
- **1-click iteration:** Change param → RUN → Results update.

**Acceptance Criteria:**

- [ ] Sidebar with collapsible sections
- [ ] RUN button always visible
- [ ] No page transitions for parameter changes

---

#### Task 2: Date Range & Lookback Controls

**Prompt File:** `prompts/task2_date_controls.md`

**Scope:**

- Calendar picker (Start + End).
- Quick Lookback: Input + unit (mins/hours/days/weeks).
- Presets: 7d, 30d, 90d, 1y.

**Acceptance Criteria:**

- [ ] Calendar picker works
- [ ] Lookback input supports custom units
- [ ] Presets auto-fill lookback

---

#### Task 3: Pre-Download Data Modal

**Prompt File:** `prompts/task3_predownload.md`

**Scope:**

- Modal before backtest runs.
- Check existing data freshness.
- Animated progress bar.

**Acceptance Criteria:**

- [ ] Modal shows symbol list with download status
- [ ] Progress bar is smooth
- [ ] Skip button if data exists

---

### Phase 2: Reports & Charts (Tasks 4-5)

#### Task 4: Report Enhancements (Single + Batch Parity)

**Prompt File:** `prompts/task4_reports.md`

**Scope:**
The Batch Mode report MUST match the Single Mode report in data density and polish. Here is the explicit mapping:

##### 4.1 Single Mode Report Structure (Source of Truth)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ HERO STATS (Animated Numbers)                                           │
│ ┌─────────┬─────────┬─────────┬─────────┐                               │
│ │Net Profit│Win Rate │Max DD   │Sharpe   │                               │
│ └─────────┴─────────┴─────────┴─────────┘                               │
├─────────────────────────────────────────────────────────────────────────┤
│ METRICS GRID (2 rows × 5 columns)                                       │
│ ┌────────┬────────┬────────┬────────┬────────┐                          │
│ │Sortino │Calmar  │Vol     │PF      │Expect  │                          │
│ ├────────┼────────┼────────┼────────┼────────┤                          │
│ │Avg Win │Avg Loss│Big Win │Big Loss│Consec W│                          │
│ └────────┴────────┴────────┴────────┴────────┘                          │
├─────────────────────────────────────────────────────────────────────────┤
│ CHARTS ROW                                                              │
│ ┌───────────────────────────────┬───────────────────────────────┐       │
│ │   Equity Curve (Area Chart)   │   Exit Reasons (Pie Chart)    │       │
│ └───────────────────────────────┴───────────────────────────────┘       │
├─────────────────────────────────────────────────────────────────────────┤
│ TRADES TABLE                                                            │
│ ┌────────┬────────┬────────┬────────┬────────┬────────┬────────┬──────┐ │
│ │Entry   │Exit    │Symbol  │Side    │Entry $ │Exit $  │Size $  │PnL   │ │
│ │Time    │Time    │        │        │        │        │        │      │ │
│ └────────┴────────┴────────┴────────┴────────┴────────┴────────┴──────┘ │
│                                                                         │
│ Click row → Deep Dive Modal with CANDLESTICK CHART                      │
└─────────────────────────────────────────────────────────────────────────┘
```

##### 4.2 Batch Mode Report (Must Include ALL of Single Mode)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ [Sidebar: Symbol List with mini PnL badges]                             │
│ ┌────────────────────┐                                                  │
│ │ 📊 Overview        │◄── Aggregated stats across all symbols           │
│ │ ────────────────── │                                                  │
│ │ BTC/USDT  +13.3%  │                                                  │
│ │ ETH/USDT  +9.2%   │                                                  │
│ │ DOGE/USDT +8.1%   │                                                  │
│ └────────────────────┘                                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ IF "Overview" selected:                                                 │
│   Show AGGREGATED Portfolio Stats:                                      │
│   - Total Net Profit (sum of all symbols)                               │
│   - Portfolio Return %                                                  │
│   - Avg Drawdown                                                        │
│   - Total Trades                                                        │
│   - Portfolio Equity Curve (aggregated balance over time)               │
│   - Symbol Performance Table (ranked by PnL)                            │
│                                                                         │
│ IF specific symbol selected (e.g., "BTC/USDT"):                         │
│   Show EXACT SAME UI as Single Mode Report above.                       │
│   - Same Hero Stats                                                     │
│   - Same Metrics Grid                                                   │
│   - Same Charts (Equity + Exit Pie)                                     │
│   - Same Trades Table                                                   │
│   - Same Deep Dive Modal with Candlestick                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

##### 4.3 Agent Instructions (Explicit)

```
AGENT MUST:
1. Create a SINGLE reusable ResultsDashboard component.
2. Use this component for BOTH Single Mode AND Batch Individual Symbol view.
3. Batch Overview page is a SEPARATE component with aggregated stats.
4. When user clicks a symbol in Batch sidebar, render ResultsDashboard
   with that symbol's data.
5. Candlestick chart library: use "lightweight-charts" (TradingView).
6. ALL trade rows must include: Entry Time, EXIT TIME, Size USD, PnL.
```

**Acceptance Criteria:**

- [ ] Single Mode has all 10+ metrics from HTML template
- [ ] Single Mode has Equity Curve + Exit Pie charts
- [ ] Single Mode trades table has Exit Time + Size $ columns
- [ ] Single Mode Deep Dive has candlestick chart
- [ ] Batch Overview has aggregated Portfolio stats
- [ ] Batch Individual (click symbol) shows EXACT same UI as Single Mode
- [ ] Reusable `ResultsDashboard` component used in both

---

#### Task 5: Indicator Import System

**Prompt File:** `prompts/task5_indicators.md`

**Scope:**

- Modal: Paste Code / Upload File tabs.
- Global Apply checkbox.
- Monaco Editor for syntax highlighting.

**Acceptance Criteria:**

- [ ] Modal with tabbed interface
- [ ] Syntax highlighting for Python/Pine
- [ ] Global toggle works

---

### Phase 3: Theming & History (Tasks 6-7)

#### Task 6: Scalable Theming System (N Themes)

**Prompt File:** `prompts/task6_theming.md`

**Scope:**
The theming system must support **unlimited themes** stored in the database. Do NOT hardcode themes.

##### 6.1 Theme Data Source

```sql
-- Themes are stored in database
SELECT name, display_name, is_dark, css_variables FROM themes;
```

##### 6.2 Theme Selector UI

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Navbar: [...other items...]  [Theme: ▼ Cyberpunk Neon]                 │
│                               ┌─────────────────────────┐               │
│                               │ ● Cyberpunk Neon (Dark) │ ◄─ Current    │
│                               │ ○ Beach Paradise (Light)│               │
│                               │ ○ Midnight Ocean (Dark) │               │
│                               │ ────────────────────────│               │
│                               │ + Add Custom Theme      │ ◄─ Future     │
│                               └─────────────────────────┘               │
└─────────────────────────────────────────────────────────────────────────┘
```

##### 6.3 CSS Variables (Loaded from DB)

```javascript
// On theme change, inject CSS variables from database
function applyTheme(theme) {
  const root = document.documentElement;
  const vars = JSON.parse(theme.css_variables);
  Object.entries(vars).forEach(([key, value]) => {
    root.style.setProperty(key, value);
  });
}
```

##### 6.4 Theme Token Reference

All components MUST use these CSS variables (no hardcoded colors):

```css
/* Backgrounds */
var(--bg-primary)      /* Main background */
var(--bg-secondary)    /* Cards, panels */
var(--bg-surface)      /* Glass surfaces with opacity */

/* Text */
var(--text-primary)    /* Headings, important text */
var(--text-secondary)  /* Body text */
var(--text-muted)      /* Hints, placeholders */

/* Accents */
var(--accent)          /* Primary buttons, links */
var(--accent-hover)    /* Hover state */

/* Status */
var(--success)         /* Profit, positive numbers */
var(--success-light)   /* Lighter variant */
var(--danger)          /* Loss, negative numbers */
var(--danger-light)    /* Lighter variant */

/* Borders & Effects */
var(--border)          /* Border colors */
var(--glow)            /* Glow effects, shadows */
```

##### 6.5 Agent Instructions (Explicit)

```
AGENT MUST:
1. Load themes from SQLite database (themes table).
2. Theme selector is a DROPDOWN, not a toggle (supports N themes).
3. Show theme swatch (small color preview) next to each theme name.
4. Indicate (Dark) or (Light) mode for each theme.
5. Store selected theme in localStorage for persistence.
6. On app load, apply stored theme from localStorage.
7. ALL color values in components must use CSS variables, NO HARDCODING.
```

**Acceptance Criteria:**

- [ ] Themes loaded from database
- [ ] Dropdown selector (not toggle)
- [ ] Theme swatches visible
- [ ] All 3 seed themes work (Cyberpunk, Beach, Midnight)
- [ ] Theme persists across sessions (localStorage)
- [ ] Adding new theme to DB auto-shows in dropdown

---

#### Task 7: Run History & Comparison

**Prompt File:** `prompts/task7_history.md`

**Scope:**

- History Panel: Load from SQLite (run_results, not run_timeseries).
- Tagging: "Promising" / "Baseline" / "Failed".
- Compare Mode: Select 2 runs → side-by-side diff.
- Diff highlighting: Green = better, Red = worse.

**Acceptance Criteria:**

- [ ] History panel loads fast (scalar metrics only)
- [ ] Tags persist to database
- [ ] Compare mode highlights metric diffs

---

### Phase 4: Advanced Features (Tasks 8-10)

#### Task 8: Grid Search (Parameter Sweep)

**Prompt File:** `prompts/task8_grid_search.md`

**Scope:**

- Multi-value input: `RSI = 14, 21, 28`.
- Run all combinations automatically.
- Results table ranked by Profit Factor.
- Heatmap visualization (RSI vs Timeframe).

**Acceptance Criteria:**

- [ ] Multi-value input parses correctly
- [ ] All combinations run
- [ ] Results sortable by any metric
- [ ] Heatmap works for 2-param sweep

---

#### Task 9: Export & Annotations

**Prompt File:** `prompts/task9_export.md`

**Scope:**

- Export CSV button.
- Per-trade notes (click row → add note).
- Filter by tag/note.

**Acceptance Criteria:**

- [ ] CSV export downloads correctly
- [ ] Trade notes save to DB
- [ ] Filter by tag works

---

#### Task 10: Architecture Diagram

**Prompt File:** `prompts/task10_architecture.md`

**Scope:**

- Create `docs/ARCHITECTURE.md` with Mermaid diagrams.
- Document API contract (CLI stdin/stdout format).

**Acceptance Criteria:**

- [ ] System diagram in Mermaid
- [ ] CLI contract documented
- [ ] Data flow documented

---

### Phase 5: Quant Methodologies (Tasks 11-12)

#### Task 11: Walk-Forward Optimization

**Prompt File:** `prompts/task11_walkforward.md`

**Scope:**

- Split data: Train (60%) → Test (20%) → Validate (20%).
- Run optimization on Train, verify on Test.
- Final check on Validate (untouched data).
- Display in-sample vs out-of-sample Sharpe.

**Acceptance Criteria:**

- [ ] Data split works correctly
- [ ] In-sample / out-of-sample metrics displayed
- [ ] Validation results shown separately

---

#### Task 12: Sensitivity Analysis

**Prompt File:** `prompts/task12_sensitivity.md`

**Scope:**

- Vary one parameter, keep others fixed.
- Chart: X = Parameter Value, Y = Profit Factor.
- Identify "fragile" parameters (steep drop-off).

**Acceptance Criteria:**

- [ ] Single-param sweep works
- [ ] Sensitivity chart renders
- [ ] Fragile params highlighted

---

### Phase 6: Live UI Architecture (Design Only)

#### Task 13: Live UI Architecture Doc

**Prompt File:** `prompts/task13_live_arch.md`

**Scope:**

- VPS deployment diagram.
- FastAPI routes: `/api/positions`, `/api/config`.
- WebSocket for real-time trades.
- SSH tunnel access for team.
- **No implementation** — documentation only.

**Acceptance Criteria:**

- [ ] Architecture diagram complete
- [ ] API routes documented
- [ ] WebSocket events documented

---

## ⏱️ Timeline

| Phase                | Tasks       | Effort    |
| -------------------- | ----------- | --------- |
| **1: Core**          | Tasks 1-3   | 3 prompts |
| **2: Reports**       | Tasks 4-5   | 2 prompts |
| **3: Theme/History** | Tasks 6-7   | 2 prompts |
| **4: Advanced**      | Tasks 8-10  | 3 prompts |
| **5: Quant**         | Tasks 11-12 | 2 prompts |
| **6: Live Arch**     | Task 13     | 1 prompt  |

**Total: 13 prompts**

---

## ✅ Verification Checklist

- [ ] Sidebar layout works (no wizard frustration)
- [ ] Date + Lookback inputs functional
- [ ] Pre-download modal shows progress
- [ ] SQLite database stores runs correctly
- [ ] TEXT columns for money values (Decimal precision)
- [ ] run_timeseries table for lazy loading
- [ ] git_hash and version tracked per run
- [ ] fee_tier and slippage_model in run_configs
- [ ] Single Mode report complete (all stats + charts)
- [ ] Batch Individual report MATCHES Single Mode
- [ ] Theme dropdown (not toggle) supports N themes
- [ ] Themes loaded from database
- [ ] All components use CSS variables only
- [ ] Run history loads fast (scalar metrics)
- [ ] Compare mode highlights diffs
- [ ] Grid search runs all combos
- [ ] Export CSV works
- [ ] Walk-forward split is correct
- [ ] Sensitivity chart renders
