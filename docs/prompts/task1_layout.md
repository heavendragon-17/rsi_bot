# Figma Agent Prompt: Task 1 — Collapsible Sidebar Layout (CTO Revised)

> **Phase:** 1 (Core Layout & Controls)
> **Priority:** 🔴 Critical Foundation
> **Status:** ✅ Approved with Revisions

---

## 🎯 Objective

Design and implement a **collapsible sidebar layout** for the Strategy Command Center. This is the main interface where users configure and run backtests.

**Key Principle:** **1-click iteration.** Users must be able to change any parameter and run immediately — no wizards, no page transitions.

---

## � CTO Directives (MANDATORY)

| Directive               | Requirement                                                                                  |
| ----------------------- | -------------------------------------------------------------------------------------------- |
| **Information Density** | Glassmorphism must NOT reduce readability. Use higher opacity (`bg-surface/60`) for sidebar. |
| **Collapsed State**     | Show "Summary Ribbon" with active config: `BTC-1h-RSI21`                                     |
| **Keyboard First**      | `Ctrl+Enter` = Run Backtest. Display shortcut hint on button.                                |
| **Validation**          | Real-time. Red border on invalid input BEFORE clicking RUN.                                  |
| **State Persistence**   | Zustand `persist` middleware. Refresh = same params.                                         |
| **Locked State**        | Sidebar disabled during backtest. Progress bar IN the RUN button.                            |

---

## �📐 Layout Structure

```
┌─────────────────────────────────────────────────────────────────────────┐
│ NAVBAR (Fixed Top)                                                      │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ [Logo] | History | Compare | Settings | [⚡ Perf] | [Theme: ▼]     │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
├────────────────────┬────────────────────────────────────────────────────┤
│ SIDEBAR (320px)    │              MAIN CONTENT                          │
│                    │                                                    │
│ [«] Collapse btn   │  ┌──────────────────────────────────────────────┐  │
│                    │  │                                              │  │
│ ▾ Mode             │  │   Empty State:                               │  │
│   ○ Single Pair    │  │   "Run your first backtest"                  │  │
│   ○ Portfolio Batch│  │   [Load Recent Config] ← CTO Requirement     │  │
│                    │  │                                              │  │
│ ▾ Symbol           │  │         OR                                   │  │
│   [BTC/USDT    ▼]  │  │                                              │  │
│                    │  │   [Results Dashboard]                        │  │
│ ▾ Timeframe        │  │                                              │  │
│   [15m][1h][4h]    │  └──────────────────────────────────────────────┘  │
│                    │                                                    │
│ ▾ Date Range       │                                                    │
│   (Task 2)         │                                                    │
│                    │                                                    │
│ ▾ Strategy         │                                                    │
│   [rsi_no_retest▼] │                                                    │
│                    │                                                    │
│ ▾ Parameters [↺]   │ ← Reset to Default icon                            │
│   RSI Period: [21] │                                                    │
│   EMA Fast:   [21] │                                                    │
│   EMA Slow:  [200] │                                                    │
│   ...              │                                                    │
│ ░░░░░░░░░░░░░░░░░░ │ ← Scroll fade mask                                 │
│                    │                                                    │
│ ▾ Risk Settings    │                                                    │
│   Capital: [$10000]│                                                    │
│   Leverage: [10x]  │                                                    │
│   Risk %:   [2%]   │                                                    │
│                    │                                                    │
│ ┌────────────────┐ │                                                    │
│ │ 🚀 RUN ⌘↵     │ │ ← Keyboard shortcut hint                           │
│ └────────────────┘ │                                                    │
└────────────────────┴────────────────────────────────────────────────────┘
```

---

## 🎯 Collapsed Sidebar State (Flyout Tooltip)

> ⚠️ **Design Fix:** A 60px bar cannot fit horizontal text. Use **Flyout Tooltip** instead.

**Default State (60px icon bar):**

```
┌──────┬────────────────────────────────────────────────────────────────┐
│ [»]  │                                                                │
│ [⚙]  │                              MAIN CONTENT                      │
│ [▶]  │                                                                │
└──────┴────────────────────────────────────────────────────────────────┘
```

**On Hover (Flyout Tooltip appears to the right):**

```
┌──────┬────────────────────────────────────────────────────────────────┐
│ [»]  │                                                                │
│ [⚙]──┤ ┌────────────────────────────────────────┐                     │
│ [▶]  │ │ BTC/USDT • 1h • RSI 21 • $10k @ 10x    │ ← Flyout Tooltip    │
│      │ └────────────────────────────────────────┘                     │
└──────┴────────────────────────────────────────────────────────────────┘
```

**Implementation:**

- Tooltip appears on hover over the Strategy icon (⚙).
- **No layout shift** — tooltip overlays content.
- High contrast: `bg-elevated` with `border-accent`.

---

## �🎨 Design Requirements

### Navbar

- **Fixed position** with floating style: `top-4 left-4 right-4 rounded-xl`.
- **Performance Mode Toggle** (⚡ icon): Disables blur/transparency for low-latency feel.
- **Theme dropdown** — loads themes from database.

### Sidebar

- **Width:** 320px (collapsible to 60px icon-only mode).
- **Higher contrast glass:** `bg-surface/60 backdrop-blur-xl` (not /40).
- **Sections:** Each section is a collapsible accordion.
- **Reset Button:** Small icon (↺) next to "Parameters" header.
- **Scroll Fade Mask:** `linear-gradient(transparent, var(--bg-surface))` at bottom.
  > ⚠️ **CRITICAL:** Add `pointer-events: none;` to prevent click blocking!
- **RUN button:** Sticky at bottom with keyboard hint.

```css
/* Scroll Fade Mask (Design Head Fix) */
.scroll-fade-mask {
  position: absolute;
  bottom: 80px; /* Above RUN button */
  left: 0;
  right: 0;
  height: 40px;
  background: linear-gradient(transparent, var(--bg-surface));
  pointer-events: none; /* ← CRITICAL: Allow clicks to pass through */
  z-index: 10;
}
```

### Main Content - Empty State

- Illustration/icon (use Lottie or SVG).
- Text: "Run your first backtest".
- **"Load Recent Config" button** — loads last 5 configs from localStorage.

---

## 🎭 Theme Integration & Performance Mode

### Standard Mode (Glassmorphism ON)

```css
.sidebar {
  background: var(--bg-surface); /* rgba with 60% opacity */
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
}
```

### Performance Mode (Glassmorphism OFF)

```css
.sidebar.performance-mode {
  background: var(--bg-secondary); /* Solid color, no transparency */
  backdrop-filter: none;
}
```

**Toggle stored in:** `localStorage.performanceMode = true/false`

---

## ⌨️ Keyboard Shortcuts

| Shortcut                               | Action                      |
| -------------------------------------- | --------------------------- |
| `Ctrl+Enter` (Win) / `Cmd+Enter` (Mac) | Run Backtest                |
| `Ctrl+R`                               | Reset Parameters to Default |
| `Ctrl+[`                               | Collapse/Expand Sidebar     |
| `Escape`                               | Cancel Running Backtest     |

**Implementation:**

```typescript
useEffect(() => {
  const handleKeyDown = (e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      runBacktest();
    }
  };
  window.addEventListener("keydown", handleKeyDown);
  return () => window.removeEventListener("keydown", handleKeyDown);
}, []);
```

---

## ✅ Real-Time Validation

**Validate on every keystroke, not on submit.**

```typescript
const validateParam = (key: string, value: string): ValidationResult => {
  const rules: Record<string, (v: string) => string | null> = {
    // Integer params (use parseInt)
    rsi_period: (v) => {
      const n = parseInt(v, 10);
      if (isNaN(n) || n < 2) return "RSI period must be ≥ 2";
      if (n > 100) return "RSI period must be ≤ 100";
      return null;
    },
    leverage: (v) => {
      const n = parseInt(v, 10);
      if (isNaN(n) || n < 1 || n > 125) return "Leverage must be 1-125";
      return null;
    },

    // ⚠️ CRITICAL: Decimal params (use parseFloat, not parseInt!)
    // Design Head Fix: parseInt("2.5") returns 2, silently altering strategy logic
    risk_percent: (v) => {
      const n = parseFloat(v);
      if (isNaN(n) || n <= 0) return "Risk must be > 0%";
      if (n > 100) return "Risk cannot exceed 100%";
      return null;
    },
    tp1_rr: (v) => {
      const n = parseFloat(v);
      if (isNaN(n) || n <= 0) return "TP1 R:R must be > 0";
      return null;
    },
    sl_buffer_pct: (v) => {
      const n = parseFloat(v);
      if (isNaN(n) || n < 0) return "SL buffer cannot be negative";
      return null;
    },
    // ... more rules
  };

  const error = rules[key]?.(value);
  return { isValid: !error, error };
};
```

**Visual feedback:**

```css
.input-error {
  border-color: var(--danger);
  box-shadow: 0 0 0 3px rgba(var(--danger-rgb), 0.2);
}

.input-error-message {
  color: var(--danger);
  font-size: 0.75rem;
  margin-top: 0.25rem;
}
```

---

## � State Persistence (Zustand)

```typescript
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface BacktestStore {
  // Mode
  mode: "single" | "batch";
  setMode: (mode: "single" | "batch") => void;

  // Symbol
  symbol: string;
  setSymbol: (symbol: string) => void;

  // Strategy
  strategy: string;
  params: Record<string, number | string>;
  setParam: (key: string, value: number | string) => void;
  resetParams: () => void; // Reset to strategy defaults

  // Risk
  capital: number;
  leverage: number;
  riskPercent: number;

  // Run State
  isRunning: boolean;
  runProgress: number; // 0-100
  runBacktest: () => Promise<void>;
  cancelBacktest: () => void;

  // Recent Configs
  recentConfigs: BacktestConfig[];
  loadConfig: (config: BacktestConfig) => void;
}

export const useBacktestStore = create<BacktestStore>()(
  persist(
    (set, get) => ({
      // ... implementation
    }),
    {
      name: "backtest-config", // localStorage key
      partialize: (state) => ({
        // Only persist these fields
        mode: state.mode,
        symbol: state.symbol,
        strategy: state.strategy,
        params: state.params,
        capital: state.capital,
        leverage: state.leverage,
        riskPercent: state.riskPercent,
        recentConfigs: state.recentConfigs,
      }),
    }
  )
);
```

---

## 🔒 Locked State During Backtest

> ⚠️ **Design Head Fix:** Use grayscale filter instead of opacity.
> Opacity makes text unreadable when user wants to check running settings.
> Grayscale keeps text high-contrast but clearly indicates "read-only".

When `isRunning === true`:

```
┌────────────────────┐
│ SIDEBAR (Locked)   │ ← Grayscale + not-allowed cursor
│                    │
│ ▾ Mode (disabled)  │
│   ● Single Pair    │  ← Still readable!
│                    │
│ ▾ Symbol (disabled)│
│   [BTC/USDT    ▼]  │
│                    │
│ ... (all disabled) │
│                    │
│ ┌────────────────┐ │
│ │ ████████░░ 67% │ │ ← Progress bar INSIDE button
│ │   RUNNING...   │ │
│ │   [Cancel]     │ │ ← Small cancel link (remains clickable)
│ └────────────────┘ │
└────────────────────┘
```

**CSS for locked state (Design Head Approved):**

```css
.sidebar.locked {
  pointer-events: none;
  filter: grayscale(80%); /* Keep text readable, but muted */
  cursor: not-allowed;
}

.sidebar.locked::after {
  content: "";
  position: absolute;
  inset: 0;
  cursor: not-allowed; /* Show "no" cursor on hover */
}

.sidebar.locked .run-button {
  pointer-events: auto; /* Allow cancel */
  filter: none; /* RUN button stays colorful */
}
```

---

## 📦 Components to Create

| Component                   | Description                                        |
| --------------------------- | -------------------------------------------------- |
| `Layout.tsx`                | Main layout with navbar, sidebar, content          |
| `Navbar.tsx`                | Fixed top navbar with theme dropdown + perf toggle |
| `Sidebar.tsx`               | Collapsible sidebar with accordion sections        |
| `SummaryRibbon.tsx`         | Config summary for collapsed state                 |
| `CollapsibleSection.tsx`    | Reusable accordion component                       |
| `ValidatedInput.tsx`        | Input with real-time validation                    |
| `RunButton.tsx`             | Sticky button with progress states                 |
| `EmptyState.tsx`            | Empty state with "Load Recent" option              |
| `PerformanceModeToggle.tsx` | Disables visual effects                            |

---

## ✅ Acceptance Criteria

- [ ] Navbar floats with rounded corners.
- [ ] **Performance Mode toggle** disables glassmorphism.
- [ ] Theme dropdown loads themes from database.
- [ ] Sidebar collapses to icon + **Summary Ribbon**.
- [ ] **Reset to Default** button in Parameters section.
- [ ] RUN button has **keyboard shortcut hint** (`Ctrl+Enter`).
- [ ] **Real-time validation** with red borders on error.
- [ ] **State persists** across page refresh.
- [ ] **Locked state** during backtest with progress in button.
- [ ] Scroll fade mask at bottom of sidebar.
- [ ] Empty state has **"Load Recent Config"** button.
- [ ] All colors use CSS variables.

---

## 🚫 Anti-Patterns to Avoid

- ❌ No wizard/step-by-step flow.
- ❌ No emojis as icons — use Heroicons/Lucide.
- ❌ No hardcoded colors — use CSS variables only.
- ❌ No layout shift on hover.
- ❌ No validation only on submit — validate in real-time.
- ❌ No losing state on refresh.

---

## 📚 References

- **TradingView** — Sidebar with collapsible sections.
- **Bloomberg Terminal** — Information density, keyboard-first.
- **QuantConnect** — Backtest configuration panel.
