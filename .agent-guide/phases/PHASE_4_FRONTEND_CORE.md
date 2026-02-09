# Phase 4: Frontend Core

> **Phase Type:** Frontend | **Estimated Time:** 1.5 hours | **Depends On:** Phase 2

---

## 🎯 Objective

Create the foundational frontend infrastructure: stores, types, layout, and navigation.

---

## 📖 Required Reading

Before starting, read:
- `.agent-guide/knowledge/TAILWIND_THEME.md`
- `.agent-guide/knowledge/API_REFERENCE.md` (for TypeScript types)

---

## ✅ Tasks

### Task 4.1: Create TypeScript Types

Create `ui/src/types/pywebview.d.ts`:

Define types for all API methods:

```typescript
declare global {
  interface Window {
    pywebview: {
      api: {
        // Data
        get_data_files: () => Promise<string[]>;
        get_strategies: () => Promise<string[]>;
        
        // Config
        get_strategy_config: (strategyName: string) => Promise<StrategyConfig>;
        save_strategy_config: (strategyName: string, config: StrategyConfig) => Promise<boolean>;
        get_global_config: () => Promise<GlobalConfig>;
        save_global_config: (config: GlobalConfig) => Promise<boolean>;
        
        // Backtest
        run_backtest: (config: BacktestConfig) => Promise<BacktestResult>;
        get_run_history: () => Promise<RunSummary[]>;
        get_run_details: (runId: number) => Promise<RunDetails>;
        get_run_timeseries: (runId: number) => Promise<TimeseriesData>;
        get_trades: (runId: number) => Promise<Trade[]>;
        
        // Analysis
        run_grid_search: (config: GridSearchConfig) => Promise<GridSearchResult[]>;
        run_walk_forward: (config: WalkForwardConfig) => Promise<WalkForwardResult>;
        run_sensitivity: (config: SensitivityConfig) => Promise<SensitivityResult>;
        compare_runs: (runId1: number, runId2: number) => Promise<ComparisonResult>;
        
        // Export
        export_results: (runId: number, format: 'csv' | 'json') => Promise<string>;
        
        // Themes
        get_themes: () => Promise<string[]>;
        get_active_theme: () => Promise<string>;
        set_active_theme: (themeName: string) => Promise<boolean>;
      }
    }
  }
}

// Define these interfaces based on API contracts
interface StrategyConfig { ... }
interface BacktestConfig { ... }
interface BacktestResult { ... }
// etc.

export {}
```

### Task 4.2: Create Zustand Stores

**Store 1: `ui/src/stores/useUIStore.ts`**

```typescript
import { create } from 'zustand'

type TabType = 'dashboard' | 'history' | 'optimization' | 'settings';

interface UIState {
  activeTab: TabType;
  isLoading: boolean;
  toasts: Toast[];
  setActiveTab: (tab: TabType) => void;
  setLoading: (loading: boolean) => void;
  addToast: (toast: Toast) => void;
  removeToast: (id: string) => void;
}

export const useUIStore = create<UIState>((set) => ({
  activeTab: 'dashboard',
  isLoading: false,
  toasts: [],
  setActiveTab: (tab) => set({ activeTab: tab }),
  setLoading: (loading) => set({ isLoading: loading }),
  addToast: (toast) => set((state) => ({ toasts: [...state.toasts, toast] })),
  removeToast: (id) => set((state) => ({ toasts: state.toasts.filter(t => t.id !== id) })),
}))
```

**Store 2: `ui/src/stores/useConfigStore.ts`**

Manage:
- Available strategies list
- Currently selected strategy
- Strategy config/parameters
- Global config

**Store 3: `ui/src/stores/useDataStore.ts`**

Manage:
- Available data files
- Run history
- Current run details
- Current run timeseries/trades

### Task 4.3: Create Layout Components

**Reference:** Look at `Designstrategycommandcenter/src/components/` for styling.

**Layout.tsx:**
- Full-screen container
- Sidebar on left
- Main content on right
- Uses CSS grid or flexbox

**Sidebar.tsx:**
- Navigation tabs: Dashboard, History, Optimization, Settings
- Uses icons from lucide-react
- Highlights active tab
- Fixed width (~240px)

**Header.tsx:**
- Strategy selector dropdown
- Data file selector
- Run button (triggers backtest)

### Task 4.4: Create Common Components

**Toast.tsx:**
- Notification component
- Types: success, error, warning, info
- Auto-dismiss after 3-5 seconds

**Modal.tsx:**
- Reusable modal wrapper
- Title, content, actions
- Close on backdrop click

**LoadingSpinner.tsx:**
- Simple spinner component
- Used during async operations

**EmptyState.tsx:**
- Shown when no data
- Icon + message + optional action

### Task 4.5: Update App.tsx

Create routing logic:

```typescript
import { useUIStore } from './stores/useUIStore'
import { Layout, Sidebar } from './components/layout'

export default function App() {
  const activeTab = useUIStore((state) => state.activeTab)
  
  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return <div>Dashboard (Phase 5)</div>
      case 'history':
        return <div>History (Phase 5)</div>
      case 'optimization':
        return <div>Optimization (Phase 7)</div>
      case 'settings':
        return <div>Settings (Phase 8)</div>
    }
  }
  
  return (
    <Layout>
      <Sidebar />
      <main>{renderContent()}</main>
    </Layout>
  )
}
```

### Task 4.6: Update index.css

Add Tailwind v4 theme:

```css
@import "tailwindcss";

@theme {
  --color-primary: #3b82f6;
  --color-primary-hover: #2563eb;
  --color-bg: #0f172a;
  --color-surface: #1e293b;
  --color-surface-hover: #334155;
  --color-border: #334155;
  --color-text: #f8fafc;
  --color-text-muted: #94a3b8;
  --color-success: #10b981;
  --color-danger: #ef4444;
  --color-warning: #f59e0b;
}

:root {
  --color-primary: #3b82f6;
  --color-bg: #0f172a;
  --color-surface: #1e293b;
  --color-text: #f8fafc;
}

body {
  margin: 0;
  background-color: var(--color-bg);
  color: var(--color-text);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
```

---

## 🔍 Verification Checkpoint

```bash
cd ui
npm run build
npm run dev
```

Open in browser (or wait for PyWebView):
- App should show layout with sidebar
- Clicking tabs should switch content (placeholder divs)
- No console errors

**PyWebView test:**
```bash
python main_ui.py
```
- Window should open
- Layout should be visible

---

## 📤 Report Template

```
## Phase 4 Complete: Frontend Core

### Created Files:
- ui/src/types/pywebview.d.ts
- ui/src/stores/useUIStore.ts
- ui/src/stores/useConfigStore.ts
- ui/src/stores/useDataStore.ts
- ui/src/components/layout/Layout.tsx
- ui/src/components/layout/Sidebar.tsx
- ui/src/components/layout/Header.tsx
- ui/src/components/common/Toast.tsx
- ui/src/components/common/Modal.tsx
- ui/src/components/common/LoadingSpinner.tsx
- ui/src/components/common/EmptyState.tsx
- Updated: ui/src/App.tsx, ui/src/index.css

### Verification:
- `npm run build`: ✅ / ❌
- Layout renders: ✅ / ❌
- Tab navigation works: ✅ / ❌
- PyWebView window opens: ✅ / ❌

Awaiting "proceed" command for Phase 5.
```

---

## ⏭️ Next Phase

After user approval, proceed to `PHASE_5_FRONTEND_COMPONENTS.md`
