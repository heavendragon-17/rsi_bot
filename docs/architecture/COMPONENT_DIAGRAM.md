# Component Diagram - Backtest UI

> **Document Type:** Component Architecture  
> **Agent:** project-planner  
> **Status:** Phase 1 Documentation

---

## 1. React Component Tree

```mermaid
flowchart TB
    App["App.tsx"]
    
    subgraph Layout["Layout Components"]
        Sidebar["Sidebar"]
        Header["Header"]
        MainContent["MainContent"]
    end
    
    subgraph Pages["Page Components"]
        Dashboard["DashboardPage"]
        SingleMode["SingleModePage"]
        GridSearch["GridSearchPage"]
        Settings["SettingsPage"]
        History["HistoryPage"]
    end
    
    subgraph Backtest["Backtest Components"]
        Controls["BacktestControls"]
        DataSelector["DataFileSelector"]
        StrategySelector["StrategySelector"]
        ParamEditor["ParameterEditor"]
        RunButton["RunButton"]
        Progress["ProgressIndicator"]
    end
    
    subgraph Results["Results Components"]
        MetricsCard["MetricsCard"]
        EquityChart["EquityChart"]
        DrawdownChart["DrawdownChart"]
        TradesTable["TradesTable"]
        ExitPieChart["ExitDistributionPie"]
    end
    
    subgraph Advanced["Advanced Components (Deferred)"]
        Heatmap["GridSearchHeatmap"]
        WalkForward["WalkForwardChart"]
        Sensitivity["SensitivityChart"]
    end
    
    App --> Layout
    Layout --> Pages
    Dashboard --> Controls
    Dashboard --> Results
    SingleMode --> Controls
    SingleMode --> Results
    GridSearch --> Controls
    GridSearch --> Advanced
    Controls --> DataSelector
    Controls --> StrategySelector
    Controls --> ParamEditor
    Controls --> RunButton
```

---

## 2. Zustand Store Architecture

```mermaid
flowchart LR
    subgraph Stores["Zustand Stores"]
        BacktestStore["useBacktestStore"]
        ConfigStore["useConfigStore"]
        HistoryStore["useHistoryStore"]
        ThemeStore["useThemeStore"]
        UIStore["useUIStore"]
    end
    
    subgraph State["State Slices"]
        BS_State["dataFiles[], strategies[]<br/>selectedData, selectedStrategy<br/>results, isRunning"]
        CS_State["currentConfig, overrides<br/>globalSettings"]
        HS_State["runs[], filters<br/>selectedRun"]
        TS_State["themes[], activeTheme<br/>cssVariables"]
        US_State["sidebarOpen, modals<br/>toasts"]
    end
    
    BacktestStore --> BS_State
    ConfigStore --> CS_State
    HistoryStore --> HS_State
    ThemeStore --> TS_State
    UIStore --> US_State
```

### Store Responsibilities

| Store | Responsibility | PyWebView API Calls |
|-------|----------------|---------------------|
| `useBacktestStore` | Backtest execution, results | `run_backtest()`, `get_data_files()` |
| `useConfigStore` | Strategy config CRUD | `get_strategy_config()`, `save_strategy_config()` |
| `useHistoryStore` | Run history, comparisons | `get_run_history()`, `get_run_details()` |
| `useThemeStore` | Theme management | `get_themes()`, `set_active_theme()` |
| `useUIStore` | UI state (modals, toasts) | None (local only) |

---

## 3. Python Module Structure

```
app/
├── ui_bridge/                  # PyWebView Integration
│   ├── __init__.py
│   ├── main.py                 # Entry point, window creation
│   ├── backtest_api.py         # BacktestAPI class (js_api)
│   ├── config_api.py           # ConfigAPI class (js_api)
│   └── data_api.py             # DataAPI class (js_api)
│
├── backtest/                   # Backtest Engine (existing)
│   ├── engine.py               # BacktestEngine class
│   ├── reporting.py            # BacktestReporter class
│   └── data/                   # CSV data files
│
├── strategies/                 # Strategy Library (existing)
│   ├── base.py                 # BaseStrategy
│   ├── rsi_wma_retest.py       # RSI WMA Retest strategy
│   └── rsi_no_retest.py        # RSI No Retest strategy
│
├── repository/                 # Data Access (new)
│   ├── __init__.py
│   ├── db.py                   # SQLite connection manager
│   ├── runs_repo.py            # Runs table operations
│   ├── trades_repo.py          # Trades table operations
│   └── themes_repo.py          # Themes table operations
│
└── cli/                        # CLI Tools (new)
    └── db_manager.py           # init, migrate, seed commands
```

---

## 4. PyWebView API Classes

```mermaid
classDiagram
    class BacktestAPI {
        +get_data_files() list~DataFile~
        +get_strategies() list~Strategy~
        +run_backtest(params) BacktestResult
        +cancel_backtest() bool
    }
    
    class ConfigAPI {
        +get_strategy_config(name) StrategyConfig
        +save_strategy_config(name, config) SaveResult
        +reset_to_default(name) StrategyConfig
        +get_global_config() GlobalConfig
        +save_global_config(config) SaveResult
    }
    
    class DataAPI {
        +get_run_history(filters) list~RunSummary~
        +get_run_details(run_id) RunDetails
        +get_run_timeseries(run_id) Timeseries
        +get_trades(run_id) list~Trade~
        +export_results(run_id, format) ExportResult
        +delete_run(run_id) bool
    }
    
    class ThemeAPI {
        +get_themes() list~Theme~
        +get_active_theme() Theme
        +set_active_theme(name) bool
    }
```

---

## 5. Component Migration Map

| Original (Figma UI) | New Location | Status | Notes |
|---------------------|--------------|--------|-------|
| `Designstrategycommandcenter/src/components/` | `ui/src/components/` | PENDING | Direct copy |
| `Designstrategycommandcenter/src/pages/` | `ui/src/pages/` | PENDING | Adapt for local |
| `Designstrategycommandcenter/src/stores/` | `ui/src/stores/` | PENDING | Replace API calls |
| `Designstrategycommandcenter/src/types/` | `ui/src/types/` | PENDING | Add pywebview.d.ts |

---

## 6. Cross-Reference

| Related Document | Purpose |
|------------------|---------|
| [SYSTEM_OVERVIEW.md](./SYSTEM_OVERVIEW.md) | High-level architecture |
| [MIGRATION_STRATEGY.md](../frontend/MIGRATION_STRATEGY.md) | UI migration details |
| [API_CONTRACTS.md](../backend/API_CONTRACTS.md) | PyWebView API surface |
