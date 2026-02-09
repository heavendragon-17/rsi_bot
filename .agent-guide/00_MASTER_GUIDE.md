# RSI Bot Backtest UI - Master Guide

> **For AI Agents** | **Version:** 1.0 | **Last Updated:** 2026-02-09

---

## 🎯 Project Objective

Build a **desktop application UI** for backtesting trading strategies. The UI wraps around an existing Python backtest engine and displays results through a modern React interface.

**Stack:**
- **Frontend:** React 18 + TypeScript + Tailwind CSS v4 + Vite
- **Desktop:** PyWebView (embeds React in native window)
- **Backend:** Python 3.10+ (existing backtest engine)
- **Database:** SQLite (for storing backtest runs)

---

## 📖 How to Use This Guide

### 1. Read Order (MANDATORY)

```
1. THIS FILE (00_MASTER_GUIDE.md) - You are here
2. 01_ARCHITECTURE.md - Understand folder structure
3. 02_KNOWLEDGE_INDEX.md - Learn when to load knowledge docs
4. phases/PHASE_0_SETUP.md - Start first phase
```

### 2. Phase Execution Rules

**CRITICAL:** Execute ONE phase at a time. After each phase:
1. Complete all tasks in the phase document
2. Run the verification checkpoint
3. **STOP and report** to the user
4. Wait for explicit "proceed" command before next phase

**DO NOT:**
- Skip phases
- Combine multiple phases
- Auto-proceed without user approval

### 3. Knowledge Loading (Lazy)

Do NOT read all knowledge docs upfront. Each phase doc will tell you:
- Which knowledge docs to read for that phase
- Why you need them

This prevents context overload.

---

## 🏗️ What We're Building

### High-Level Architecture

```
┌─────────────────────────────────────────────────────┐
│                 PyWebView Window                     │
│  ┌───────────────────────────────────────────────┐  │
│  │              React Frontend (ui/)              │  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────────────┐  │  │
│  │  │Sidebar  │ │Dashboard│ │ Charts/Analysis │  │  │
│  │  │         │ │ Stats   │ │                 │  │  │
│  │  └─────────┘ └─────────┘ └─────────────────┘  │  │
│  └───────────────────────────────────────────────┘  │
│                        ↕ JS API                      │
│  ┌───────────────────────────────────────────────┐  │
│  │           Python Bridge (app/ui/)              │  │
│  │     get_strategies(), run_backtest(), etc.     │  │
│  └───────────────────────────────────────────────┘  │
│                        ↕                             │
│  ┌───────────────────────────────────────────────┐  │
│  │        Backtest Engine (app/backtest/)         │  │
│  │    Existing Python code - DO NOT MODIFY        │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### Key Insight: Figma Migration

The folder `Designstrategycommandcenter/` contains **UI code generated from Figma**.
- It has React components with styling
- It does NOT have real backend integration
- **Your job:** Copy styles/structure, rewrite logic to integrate with Python backend

---

## 📁 Target Folder Structure

After all phases complete, the project should look like:

```
rsi_bot/
├── main_ui.py                 # Entry point (python main_ui.py)
├── ui/                        # React frontend (NEW)
│   ├── src/
│   │   ├── components/        # All UI components
│   │   ├── stores/            # Zustand state management
│   │   ├── types/             # TypeScript definitions
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   ├── dist/                  # Built assets (npm run build)
│   ├── package.json
│   └── vite.config.ts
├── app/
│   ├── db/                    # Database layer (RECREATE)
│   │   ├── models.py          # SQLAlchemy models
│   │   └── repository.py      # CRUD operations
│   ├── ui/                    # PyWebView bridge (RECREATE)
│   │   ├── bridge.py          # Window management
│   │   └── api/               # API methods exposed to JS
│   ├── backtest/              # EXISTS - don't modify
│   └── strategies/            # EXISTS - don't modify
├── docs/                      # Specs and plans (EXISTS)
├── data/                      # SQLite DB location
│   └── backtest.db
└── Designstrategycommandcenter/  # Figma reference (EXISTS)
```

---

## 🔢 Phases Overview

| Phase | Name | Creates | Depends On |
|-------|------|---------|------------|
| 0 | Setup | `ui/` scaffold, deps | Nothing |
| 1 | Database | `app/db/` models, repos | Phase 0 |
| 2 | Bridge | `app/ui/` bridge, APIs | Phase 1 |
| 3 | Backend Features | Grid search, walk-forward | Phase 2 |
| 4 | Frontend Core | Stores, types, layout | Phase 2 |
| 5 | Frontend Components | Dashboard, forms, tables | Phase 4 |
| 6 | Frontend Charts | Equity, drawdown, pie | Phase 5 |
| 7 | Frontend Analysis | Analysis tool UIs | Phase 6 |
| 8 | Polish | Themes, export, QA | Phase 7 |

---

## ⚠️ Critical Constraints

1. **PyWebView Compatibility**
   - All asset paths must be RELATIVE (`./assets/...` not `/assets/...`)
   - Set `base: './'` in vite.config.ts

2. **Dependencies**
   - `recharts` requires `react-is` - install explicitly
   - Use `--legacy-peer-deps` if npm conflicts arise

3. **Database Location**
   - SQLite database goes in `data/backtest.db`
   - Use `TEXT` for monetary values, `Decimal` in Python

4. **Existing Code**
   - `app/backtest/` and `app/strategies/` already exist
   - Do NOT modify these - only integrate with them

5. **Config Safety**
   - Never edit `.py` strategy files from UI
   - Use JSON override files in `config/strategy_overrides/`

---

## 📚 Reference Documents

All project specifications are in `docs/`:
- `docs/architecture/` - System design
- `docs/backend/` - API contracts, feature gaps
- `docs/frontend/` - Component manifest
- `docs/use-cases/` - User stories

The knowledge docs in `.agent-guide/knowledge/` are distilled summaries optimized for AI agents.

---

## ✅ Success Criteria

The project is complete when:
1. `npm run build` passes in `ui/`
2. `python main_ui.py` launches the app
3. All features from `docs/backend/FEATURE_GAPS.md` are implemented
4. All components from `docs/frontend/COMPONENT_MANIFEST.md` exist
5. User can run a backtest and see results in charts

---

**Next Step:** Read `01_ARCHITECTURE.md`
