# 📦 CONTEXT BUNDLE: RSI Bot Strategy Command Center

> **Paste this into the Figma Agent AFTER the Master Instructions, BEFORE Task 1.**

---

## 🏗️ Technical Stack

| Layer           | Technology                                              |
| --------------- | ------------------------------------------------------- |
| **Frontend**    | React 18 + TypeScript 5                                 |
| **Styling**     | Tailwind CSS v4 (CSS Variables only)                    |
| **State**       | Zustand + `persist` middleware                          |
| **Charts**      | `lightweight-charts` (Candles), `chart.js` (Equity/Pie) |
| **Code Editor** | Monaco Editor (Indicators)                              |
| **Animation**   | Framer Motion (Sidebar transitions only)                |
| **Database**    | SQLite (local `backtest.db`)                            |

---

## 🎨 CSS Variables (Mandatory)

**Rule: No hardcoded colors. All components use these tokens.**

```css
/* Backgrounds */
--bg-primary     /* #0F172A (Dark) | #FEF7ED (Light) */
--bg-secondary   /* Cards, sidebars */
--bg-surface     /* Glass: rgba(..., 0.6) + backdrop-blur */
--bg-elevated    /* Modals, dropdowns */

/* Text (WCAG AA Validated) */
--text-primary   /* Headings, values (Contrast ≥7:1) */
--text-secondary /* Body text (Contrast ≥4.5:1) */
--text-muted     /* Hints, labels */

/* Interactive */
--accent         /* Buttons, links, active states */
--accent-hover   /* Hover */

/* Semantic (Trading) */
--success        /* Profit, long, green */
--success-light  /* Light variant */
--danger         /* Loss, short, red */
--danger-light   /* Light variant */
--warning        /* Amber for rate limits */

/* Structure */
--border         /* Dividers */
--glow           /* Box-shadow glow */
```

**Performance Mode:** When `.performance-mode` class is on `<html>`:

- Disable all `backdrop-filter`.
- Use solid `--bg-secondary` instead of transparent surfaces.

---

## 💾 Database Tables (SQLite)

### Quick Reference

| Table            | Purpose                | Load Pattern        |
| ---------------- | ---------------------- | ------------------- |
| `runs`           | Backtest run metadata  | Always              |
| `run_configs`    | Input parameters       | Always              |
| `run_results`    | Scalar metrics (fast)  | Dashboard list      |
| `run_timeseries` | Equity/Drawdown (BLOB) | **Lazy load only**  |
| `trades`         | Individual trades      | On-click drill-down |
| `themes`         | CSS palettes           | App startup         |

### Key Columns

**`run_results`** (Fast metrics for list views):

```
net_profit, net_profit_pct, win_rate, max_drawdown_pct
sharpe_ratio, sortino_ratio, calmar_ratio, profit_factor
total_trades, avg_win, avg_loss, expectancy
```

**`run_timeseries`** (Heavy data - lazy load):

```
equity_curve   BLOB   -- zlib compressed JSON
drawdown_curve BLOB   -- zlib compressed JSON
```

**`trades`** (Per-trade detail):

```
entry_time, exit_time, symbol, side
entry_price, exit_price, pnl, exit_reason
```

**`themes`** (N-theme support):

```
name, display_name, is_dark, css_variables (JSON)
```

---

## 🛠️ Ergonomic Rules (CTO-Approved)

| Rule                  | Implementation                                                    |
| --------------------- | ----------------------------------------------------------------- |
| **Collapsed Sidebar** | Use **Flyout Tooltip** (not inline text). Appears on hover.       |
| **Scroll Fade**       | Use gradient + `pointer-events: none` to avoid click blocking.    |
| **Locked State**      | Use `filter: grayscale(80%)` + `cursor: not-allowed`. No opacity. |
| **Validation**        | Real-time. Use `parseFloat()` for decimals, not `parseInt()`.     |
| **Persistence**       | Zustand `persist` to `localStorage`.                              |
| **Keyboard**          | `Ctrl+Enter` = Run. `G` = Go to Date. `Escape` = Cancel.          |

---

## 🗺️ 13-Task Roadmap

| #   | Task               | Key Deliverable                                  |
| --- | ------------------ | ------------------------------------------------ |
| 1   | **Sidebar Layout** | Collapsible, sticky RUN, Flyout tooltip          |
| 2   | **Date Controls**  | Presets, Lookback, Calendar picker               |
| 3   | **Data Modal**     | Pre-download progress, symbol status             |
| 4   | **Single Report**  | Hero stats, Equity chart, Exit pie, Trades table |
| 5   | **Batch Parity**   | Portfolio overview + Symbol drill-down           |
| 6   | **Indicators**     | Monaco code editor, upload/paste tabs            |
| 7   | **Themes**         | N-theme dropdown, DB-driven                      |
| 8   | **History**        | Run list, tag system, compare mode               |
| 9   | **Grid Search**    | Param sweep, heatmap viz                         |
| 10  | **Walk-Forward**   | Train/Test/Validate splits                       |
| 11  | **Sensitivity**    | Single-param fragility chart                     |
| 12  | **Export**         | CSV download, per-trade notes                    |
| 13  | **Architecture**   | Mermaid diagrams, API docs                       |

---

## ✅ Acknowledgment

After reading this, tell the user:

> **"Context Bundle received. I understand the tech stack, theming rules, and database schema. Ready for Task 1."**
