# Architecture Reference

> **For AI Agents** | Read this after `00_MASTER_GUIDE.md`

---

## 📁 Folder Structure (Detailed)

```
rsi_bot/
│
├── main_ui.py                    # Entry point: python main_ui.py
├── main.py                       # CLI backtest (existing, don't modify)
├── config.yaml                   # Global config (existing)
│
├── ui/                           # [CREATE] React frontend
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tsconfig.app.json
│   ├── tsconfig.node.json
│   ├── index.html
│   ├── src/
│   │   ├── main.tsx              # React entry
│   │   ├── App.tsx               # Root component with routing
│   │   ├── index.css             # Tailwind + CSS variables
│   │   ├── components/
│   │   │   ├── layout/           # Sidebar, Header, Layout
│   │   │   ├── common/           # Toast, Modal, LoadingSpinner
│   │   │   ├── charts/           # EquityChart, DrawdownChart, etc.
│   │   │   ├── analysis/         # GridSearch, WalkForward, Sensitivity
│   │   │   ├── history/          # HistoryFilters, ComparisonView
│   │   │   ├── settings/         # GlobalConfigForm, ThemeSelector
│   │   │   └── tables/           # TradesTable
│   │   ├── stores/               # Zustand stores
│   │   │   ├── useConfigStore.ts
│   │   │   ├── useDataStore.ts
│   │   │   └── useUIStore.ts
│   │   └── types/
│   │       └── pywebview.d.ts    # TypeScript types for window.pywebview
│   └── dist/                     # Built assets (created by npm run build)
│
├── app/
│   ├── __init__.py
│   ├── db/                       # [CREATE] Database layer
│   │   ├── __init__.py
│   │   ├── models.py             # SQLAlchemy ORM models
│   │   ├── repository.py         # CRUD operations
│   │   └── init_db.py            # Database initialization
│   │
│   ├── ui/                       # [CREATE] PyWebView bridge
│   │   ├── __init__.py
│   │   ├── bridge.py             # BacktestUI class, window management
│   │   └── api/
│   │       ├── __init__.py       # BridgeAPI class (exposed to JS)
│   │       ├── backtest.py       # run_backtest, get_run_history, etc.
│   │       ├── config.py         # get/save strategy config
│   │       └── data.py           # get_data_files, get_strategies
│   │
│   ├── backtest/                 # [EXISTS] Core engine - DON'T MODIFY
│   │   ├── backtest.py
│   │   ├── engine.py
│   │   ├── data/                 # CSV files
│   │   └── ...
│   │
│   └── strategies/               # [EXISTS] Strategy implementations - DON'T MODIFY
│       ├── base.py
│       ├── rsi_strategy.py
│       └── ...
│
├── data/                         # Runtime data
│   └── backtest.db               # SQLite database (created at runtime)
│
├── config/                       # Config files
│   └── strategy_overrides/       # JSON overrides for strategies
│
├── docs/                         # [EXISTS] Specifications
│   ├── architecture/
│   ├── backend/
│   ├── frontend/
│   └── use-cases/
│
├── Designstrategycommandcenter/  # [EXISTS] Figma UI reference
│   └── src/
│       ├── components/           # Reference for styling
│       └── index.css             # CSS to copy/adapt
│
└── .agent-guide/                 # This documentation
    ├── phases/
    └── knowledge/
```

---

## 🔧 Tech Stack Details

### Frontend
| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18.3.x | UI framework |
| TypeScript | 5.6.x | Type safety |
| Vite | 6.x | Build tool |
| Tailwind CSS | 4.x | Styling (CSS-first, no config file) |
| Zustand | 5.x | State management |
| lightweight-charts | 5.x | Financial charts |
| recharts | 3.x | Pie charts, bar charts |
| lucide-react | 0.5x | Icons |
| framer-motion | 12.x | Animations |

### Backend
| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.10+ | Runtime |
| PyWebView | 5.x | Desktop window |
| SQLAlchemy | 2.x | ORM |
| SQLite | 3.x | Database |

---

## 🔌 Communication: Frontend ↔ Backend

PyWebView exposes Python methods to JavaScript via `window.pywebview.api`.

### In Python (app/ui/api/__init__.py):
```python
class BridgeAPI:
    def get_strategies(self):
        return ["RSI_Strategy", "MACD_Strategy"]
```

### In JavaScript (React component):
```typescript
const strategies = await window.pywebview.api.get_strategies();
```

### Type Safety (ui/src/types/pywebview.d.ts):
```typescript
declare global {
  interface Window {
    pywebview: {
      api: {
        get_strategies: () => Promise<string[]>;
        // ... other methods
      }
    }
  }
}
```

---

## 🗄️ Database Schema

SQLite database at `data/backtest.db` with these tables:

| Table | Purpose |
|-------|---------|
| `runs` | Backtest run metadata (strategy, symbol, dates) |
| `run_results` | Performance metrics (profit, win_rate, etc.) |
| `run_timeseries` | Equity curve data (BLOB, lazy loaded) |
| `trades` | Individual trade records |
| `themes` | UI theme definitions |

See `docs/DATABASE.md` for full schema.

---

## 🎨 Styling System

### Tailwind CSS v4 (CSS-First)

No `tailwind.config.js`. Configuration via CSS:

```css
/* ui/src/index.css */
@import "tailwindcss";

@theme {
  --color-primary: #3b82f6;
  --color-bg: #0f172a;
  --color-surface: #1e293b;
  --color-text: #f8fafc;
}
```

### CSS Variables (Used in components)

```css
.my-component {
  background-color: var(--color-surface);
  color: var(--color-text);
}
```

---

## 🚫 Constraints Summary

1. **RELATIVE PATHS**: Always use `base: './'` in Vite
2. **NO INLINE STRATEGY EDITS**: Use JSON override files only
3. **LAZY LOAD TIMESERIES**: Don't fetch equity curves in list views
4. **DECIMAL FOR MONEY**: Use `Decimal` in Python, `TEXT` in SQLite
5. **DON'T MODIFY EXISTING**: `app/backtest/` and `app/strategies/` are read-only

---

**Next Step:** Read `02_KNOWLEDGE_INDEX.md`
