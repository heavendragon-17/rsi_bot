# Figma Agent Prompt: Task 13 — Desktop/Mobile Responsive Documentation

> **Phase:** 6 (Final) ⭐ **FINAL TASK** > **Priority:** 🔴 Critical — Ship quality requires documentation.
> **Design Principle:** Design once, display everywhere. Document all breakpoints.

---

## 🎯 Objective

Create the **Responsive Design Documentation** that includes:

1. Breakpoint specifications for all components
2. Mobile-first layout adaptations
3. Touch-optimized interactions
4. Component behavior at each breakpoint

**Core Principle:** Every component must work from 375px to 2560px. No exceptions.

---

## 📐 Breakpoint System

### Standard Breakpoints

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│  BREAKPOINT SYSTEM                                                                │
│  ────────────────────────────────────────────────────────────────────────────     │
│                                                                                   │
│  ┌──────────┬──────────┬────────────────┬─────────────────────────────────────┐  │
│  │ Name     │ Width    │ Target Device  │ Sidebar Behavior                    │  │
│  ├──────────┼──────────┼────────────────┼─────────────────────────────────────┤  │
│  │ xs       │ < 640px  │ Mobile phones  │ Hidden (sheet on demand)            │  │
│  │ sm       │ 640-768  │ Large phones   │ Hidden (sheet on demand)            │  │
│  │ md       │ 768-1024 │ Tablets        │ Collapsed (icons only)              │  │
│  │ lg       │ 1024-1280│ Small laptops  │ Collapsed (icons + labels on hover) │  │
│  │ xl       │ 1280-1536│ Desktops       │ Expanded (full sidebar)             │  │
│  │ 2xl      │ ≥ 1536   │ Large monitors │ Expanded (full sidebar)             │  │
│  └──────────┴──────────┴────────────────┴─────────────────────────────────────┘  │
│                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘
```

### CSS Variables for Breakpoints

```css
:root {
  --breakpoint-xs: 0px;
  --breakpoint-sm: 640px;
  --breakpoint-md: 768px;
  --breakpoint-lg: 1024px;
  --breakpoint-xl: 1280px;
  --breakpoint-2xl: 1536px;
}
```

---

## 📊 Section 1: Sidebar Responsiveness

### Desktop (≥ 1280px)

```
┌──────────────────────────────────────────────────────────────────┐
│ ┌────────────────┐  ┌──────────────────────────────────────────┐ │
│ │ SIDEBAR        │  │ MAIN CONTENT                             │ │
│ │ ────────────   │  │                                          │ │
│ │ [«] Collapse   │  │  Hero Stats                              │ │
│ │                │  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐     │ │
│ │ Strategy       │  │  │ PnL  │ │ Win% │ │Sharpe│ │ DD   │     │ │
│ │ Settings       │  │  └──────┘ └──────┘ └──────┘ └──────┘     │ │
│ │ Theme          │  │                                          │ │
│ │ History        │  │  Charts...                               │ │
│ │                │  │                                          │ │
│ │ Width: 280px   │  │                                          │ │
│ └────────────────┘  └──────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### Tablet (768-1024px)

```
┌──────────────────────────────────────────────────────────────────┐
│ ┌────┐  ┌────────────────────────────────────────────────────┐   │
│ │ 🔽 │  │ MAIN CONTENT                                       │   │
│ │ ⚙️ │  │                                                    │   │
│ │ ▶️ │  │  Hero Stats (2x2 grid)                             │   │
│ │ 📜 │  │  ┌──────────────┐ ┌──────────────┐                 │   │
│ │    │  │  │ PnL          │ │ Win Rate     │                 │   │
│ │    │  │  └──────────────┘ └──────────────┘                 │   │
│ │ 64 │  │  ┌──────────────┐ ┌──────────────┐                 │   │
│ │ px │  │  │ Sharpe       │ │ Max DD       │                 │   │
│ │    │  │  └──────────────┘ └──────────────┘                 │   │
│ │    │  │                                                    │   │
│ └────┘  └────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### Mobile (< 768px)

```
┌─────────────────────────────────────┐
│ ┌─────────────────────────────────┐ │
│ │ ☰ Backtest Pro         [▶ Run]  │ │  ← Fixed header with menu
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ Hero Stats (1 column, scroll)   │ │
│ │ ┌───────────────────────────┐   │ │
│ │ │ Net PnL: +$1,330 (+13.3%) │   │ │
│ │ └───────────────────────────┘   │ │
│ │ ┌───────────────────────────┐   │ │
│ │ │ Win Rate: 68%             │   │ │
│ │ └───────────────────────────┘   │ │
│ │ ┌───────────────────────────┐   │ │
│ │ │ Sharpe: 1.23              │   │ │
│ │ └───────────────────────────┘   │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ Chart (full width, scrollable)  │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ Trades Table (card view)        │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ [☰] [📊] [⚙️] [📜]              │ │  ← Bottom nav
│ └─────────────────────────────────┘ │
└─────────────────────────────────────┘
```

---

## 📊 Section 2: Component-by-Component Responsiveness

### Hero Stats Grid

| Breakpoint | Layout | Columns     |
| ---------- | ------ | ----------- |
| xs, sm     | Stack  | 1 column    |
| md         | Grid   | 2 columns   |
| lg         | Grid   | 4 columns   |
| xl, 2xl    | Grid   | 4-5 columns |

### Charts

| Breakpoint | Behavior                                         |
| ---------- | ------------------------------------------------ |
| xs, sm     | Full width, horizontal scroll for long timelines |
| md         | Full width, compact legend                       |
| lg+        | Side-by-side charts possible                     |

### Tables

| Breakpoint | Behavior                    |
| ---------- | --------------------------- |
| xs, sm     | Card view (stacked)         |
| md         | Horizontal scroll if needed |
| lg+        | Full table with all columns |

---

## 📊 Section 3: Mobile Bottom Navigation

```
┌───────────────────────────────────────────────────────────────────────┐
│  MOBILE BOTTOM NAV (xs, sm only)                                      │
│  ─────────────────────────────────────────────────────────────────    │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │  [📊]        [⚙️]        [▶️]        [📜]        [☰]           │  │
│  │ Dashboard  Settings    Run       History     More             │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  • Active tab highlighted with accent color                           │
│  • Height: 56px (safe for thumb reach)                               │
│  • Icons: 24px, Labels: 10px                                         │
│  • Bottom safe area padding for notched devices                      │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Section 4: Mobile Sheet (Sidebar Replacement)

When user taps ☰ on mobile:

```
┌─────────────────────────────────────┐
│                                     │
│ ┌─────────────────────────────────┐ │  ← Dimmed content behind
│ │░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│ │
│ │░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ ─────────── (drag handle)       │ │
│ │                                 │ │
│ │ SETTINGS                        │ │
│ │ ─────────────────────────────── │ │
│ │ Strategy: [RSI No Retest ▼]     │ │
│ │ Symbol: [DOGE/USDT ▼]           │ │
│ │ Timeframe: [1H ▼]               │ │
│ │                                 │ │
│ │ RSI Period: [14]                │ │
│ │ Overbought: [70]                │ │
│ │ Oversold: [30]                  │ │
│ │                                 │ │
│ │ [▶ Run Backtest]                │ │
│ │                                 │ │
│ └─────────────────────────────────┘ │
└─────────────────────────────────────┘
```

### Sheet Behavior

| Gesture     | Action                |
| ----------- | --------------------- |
| Drag down   | Close sheet           |
| Tap outside | Close sheet           |
| Drag up     | Expand to full screen |

---

## 📊 Section 5: Touch Optimizations

### Touch Target Sizes

```
┌───────────────────────────────────────────────────────────────────────┐
│  TOUCH TARGET REQUIREMENTS                                            │
│  ─────────────────────────────────────────────────────────────────    │
│                                                                       │
│  Minimum touch target: 44 × 44 px (iOS) / 48 × 48 dp (Android)       │
│                                                                       │
│  ┌──────────────────────┬─────────────┬─────────────────────────────┐ │
│  │ Element              │ Min Size    │ Padding                     │ │
│  ├──────────────────────┼─────────────┼─────────────────────────────┤ │
│  │ Buttons              │ 44 × 44     │ px-4 py-3                   │ │
│  │ Icon buttons         │ 44 × 44     │ p-2.5                       │ │
│  │ List items           │ 44 × auto   │ py-3                        │ │
│  │ Dropdown items       │ 44 × auto   │ py-3 px-4                   │ │
│  │ Table rows (mobile)  │ 56 × auto   │ py-4                        │ │
│  │ Bottom nav items     │ 56 × 56     │ centered                    │ │
│  └──────────────────────┴─────────────┴─────────────────────────────┘ │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

### Gesture Interactions

| Gesture             | Usage                         |
| ------------------- | ----------------------------- |
| **Swipe left**      | Delete trade (with undo)      |
| **Swipe right**     | Quick actions (tag, annotate) |
| **Long press**      | Context menu                  |
| **Pinch/zoom**      | Charts only                   |
| **Pull to refresh** | Reload data                   |

---

## 📊 Section 6: Responsive Typography

```
┌───────────────────────────────────────────────────────────────────────┐
│  TYPOGRAPHY SCALE                                                     │
│  ─────────────────────────────────────────────────────────────────    │
│                                                                       │
│  ┌──────────────┬─────────────┬─────────────┬─────────────────────┐   │
│  │ Element      │ Mobile      │ Tablet      │ Desktop             │   │
│  ├──────────────┼─────────────┼─────────────┼─────────────────────┤   │
│  │ Page Title   │ 24px (1.5r) │ 28px (1.75) │ 32px (2rem)         │   │
│  │ Section Head │ 18px (1.125)│ 20px (1.25) │ 24px (1.5rem)       │   │
│  │ Hero Stat    │ 28px        │ 32px        │ 36px                │   │
│  │ Body Text    │ 14px        │ 14px        │ 16px (1rem)         │   │
│  │ Small/Muted  │ 12px        │ 12px        │ 14px (0.875rem)     │   │
│  │ Tiny         │ 10px        │ 10px        │ 12px (0.75rem)      │   │
│  └──────────────┴─────────────┴─────────────┴─────────────────────┘   │
│                                                                       │
│  Use clamp() for fluid typography:                                    │
│  font-size: clamp(1.5rem, 2vw + 1rem, 2rem);                         │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Section 7: Responsive Modals

### Desktop Modal

```
┌───────────────────────────────────────────────────────────────────────┐
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
│ ░░░░░░┌─────────────────────────────────────────────────────┐░░░░░░░░ │
│ ░░░░░░│ MODAL TITLE                                   [×]   │░░░░░░░░ │
│ ░░░░░░├─────────────────────────────────────────────────────┤░░░░░░░░ │
│ ░░░░░░│                                                     │░░░░░░░░ │
│ ░░░░░░│  Modal content...                                   │░░░░░░░░ │
│ ░░░░░░│                                                     │░░░░░░░░ │
│ ░░░░░░│  [Cancel]                          [Confirm]        │░░░░░░░░ │
│ ░░░░░░└─────────────────────────────────────────────────────┘░░░░░░░░ │
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
└───────────────────────────────────────────────────────────────────────┘
```

### Mobile Modal (Full Screen)

```
┌─────────────────────────────────────┐
│ ┌─────────────────────────────────┐ │
│ │ [←] Modal Title           [×]   │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │                                 │ │
│ │ Modal content...                │ │
│ │ (scrollable)                    │ │
│ │                                 │ │
│ │                                 │ │
│ │                                 │ │
│ │                                 │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ [Confirm]                       │ │  ← Sticky footer
│ └─────────────────────────────────┘ │
└─────────────────────────────────────┘
```

---

## 📊 Section 8: Responsive Specifications per Task

### Quick Reference Table

| Task                  | Desktop                 | Tablet         | Mobile         |
| --------------------- | ----------------------- | -------------- | -------------- |
| **T1 Sidebar**        | 280px expanded          | 64px icons     | Bottom sheet   |
| **T2 Date Controls**  | Inline row              | Inline row     | Stacked        |
| **T3 Download Modal** | Centered modal          | Full screen    | Full screen    |
| **T4 Results**        | 4-col hero, side charts | 2-col, stacked | 1-col, stacked |
| **T5 Batch Mode**     | Portfolio + table       | Tabbed view    | Card list      |
| **T6 Pine Script**    | Side-by-side            | Stacked        | Stacked        |
| **T7 Themes**         | Grid 4 cols             | Grid 2 cols    | Grid 2 cols    |
| **T8 History**        | Full table              | Scrollable     | Card view      |
| **T9 Grid Search**    | Full heatmap            | Scroll         | Scroll         |
| **T10 Walk-Forward**  | Timeline + results      | Stacked        | Stacked        |
| **T11 Sensitivity**   | Tornado full            | Tornado scroll | Tornado scroll |
| **T12 Export**        | Dropdown menu           | Dropdown menu  | Full sheet     |

---

## 🔧 Implementation Checklist

### Tailwind Classes to Use

```css
/* Container with responsive padding */
.container {
  @apply px-4 md:px-6 lg:px-8 max-w-7xl mx-auto;
}

/* Responsive grid */
.hero-grid {
  @apply grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4;
}

/* Show/hide based on breakpoint */
.desktop-only {
  @apply hidden lg:block;
}
.mobile-only {
  @apply block lg:hidden;
}

/* Responsive typography */
.page-title {
  @apply text-2xl md:text-3xl lg:text-4xl font-bold;
}
```

---

## ✅ Acceptance Criteria

- [ ] **Sidebar** collapses to icons at md, bottom sheet on mobile.
- [ ] **Hero Stats** reflow: 4 cols → 2 cols → 1 col.
- [ ] **Tables** become card view on mobile.
- [ ] **Modals** become full screen on mobile.
- [ ] **Touch targets** ≥ 44px on mobile.
- [ ] **Bottom nav** appears on mobile only.
- [ ] **Charts** remain readable with pinch/zoom.
- [ ] **Typography** scales fluidly across breakpoints.
- [ ] **No horizontal scroll** except for charts/tables.
- [ ] **Safe area** padding on notched devices.

---

## 🚫 Anti-Patterns

- ❌ **Fixed widths** — Use relative/fluid units.
- ❌ **Desktop-only features** — All features must work on mobile.
- ❌ **Tiny touch targets** — Minimum 44px.
- ❌ **Hidden content** — Use progressive disclosure, not hiding.
- ❌ **Ignoring notches** — Use `env(safe-area-inset-*)`.

---

## 📚 Testing Requirements

### Device Matrix

| Device      | Screen      | Test Focus                |
| ----------- | ----------- | ------------------------- |
| iPhone 14   | 390 × 844   | Touch, notch, bottom nav  |
| iPhone SE   | 375 × 667   | Small screen, compact UI  |
| iPad        | 768 × 1024  | Collapsed sidebar, 2-col  |
| iPad Pro    | 1024 × 1366 | Split view, expanded      |
| MacBook Air | 1280 × 800  | Standard desktop          |
| 27" Monitor | 2560 × 1440 | Large screen, full layout |

---

## 🔍 Figma Agent Verification Protocol

**After completing this task, Figma Agent MUST:**

1. **Check for Errors** — Review all components for:

   - Horizontal scroll appearing unexpectedly
   - Touch targets smaller than 44px
   - Content hidden by notch/safe area
   - Typography unreadable at any breakpoint
   - Sidebar not adapting correctly

2. **Fix Identified Issues** — Do not mark task complete until:

   - All breakpoints tested (375, 768, 1024, 1280, 1536+)
   - No horizontal scroll on mobile
   - Bottom nav works on mobile
   - Modals full-screen on mobile

3. **Self-Test Checklist:**
   - [ ] Resize to 375px → Bottom nav appears
   - [ ] Resize to 768px → Sidebar collapses to icons
   - [ ] Resize to 1280px → Sidebar fully expanded
   - [ ] Hero stats reflow correctly at each breakpoint
   - [ ] Tables become cards on mobile
   - [ ] Modals full-screen on mobile
   - [ ] Touch targets ≥ 44px on all buttons
