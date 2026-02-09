# Figma Agent Prompt: Task 7 — Scalable N-Theme System

> **Phase:** 3 (Tools & Themes)
> **Priority:** 🟡 High — Users want personalization.
> **Design Principle:** Themes are data, not code. Add new themes without deploys.

---

## 🎯 Objective

Design the **N-Theme System** that allows:

1. Users to select from multiple pre-built themes
2. Admins to add new themes via database (no code changes)
3. All themes to meet WCAG AA contrast requirements

**Core Principle:** Database-driven theming. Zero hardcoded colors.

---

## 📐 Layout Overview

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ SIDEBAR (Settings section expanded)                                               │
│ ┌──────┐ ┌─────────────────────────────────────────────────────────────────────┐  │
│ │      │ │  ┌─ SETTINGS PANEL ───────────────────────────────────────────────┐ │  │
│ │ [«]  │ │  │                                                                │ │  │
│ │ [⚙]◀─┼─┼──│  APPEARANCE                                                    │ │  │
│ │ [▶]  │ │  │  ─────────────────────────────────────────────────────────────  │ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  Theme                                                         │ │  │
│ │      │ │  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐                   │ │  │
│ │      │ │  │  │ Cyber- │ │ Beach  │ │Midnight│ │ Forest │                   │ │  │
│ │      │ │  │  │ punk   │ │Paradise│ │ Ocean  │ │ Grove  │                   │ │  │
│ │      │ │  │  │ [████] │ │ [████] │ │ [████] │ │ [████] │                   │ │  │
│ │      │ │  │  │  ✓     │ │        │ │        │ │        │                   │ │  │
│ │      │ │  │  └────────┘ └────────┘ └────────┘ └────────┘                   │ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  Performance Mode                                              │ │  │
│ │      │ │  │  [═══════════○] Reduce animations for large datasets           │ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  ─────────────────────────────────────────────────────────────  │ │  │
│ │      │ │  │  DANGER ZONE                                                   │ │  │
│ │      │ │  │  [Reset All Settings]                                          │ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ └──────┘ └─────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Section 1: Theme Selector

### Theme Card Grid

```
┌─────────────────────────────────────────────────────────────────────┐
│  SELECT THEME                                                       │
│  ───────────────────────────────────────────────────────────────    │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────┐ │
│  │  Cyberpunk   │ │    Beach     │ │   Midnight   │ │   Forest    │ │
│  │    Neon      │ │   Paradise   │ │    Ocean     │ │    Grove    │ │
│  │  ┌────────┐  │ │  ┌────────┐  │ │  ┌────────┐  │ │  ┌────────┐ │ │
│  │  │████████│  │ │  │████████│  │ │  │████████│  │ │  │████████│ │ │
│  │  │Primary │  │ │  │████████│  │ │  │████████│  │ │  │████████│ │ │
│  │  │████████│  │ │  │████████│  │ │  │████████│  │ │  │████████│ │ │
│  │  └────────┘  │ │  └────────┘  │ │  └────────┘  │ │  └────────┘ │ │
│  │      ✓       │ │              │ │              │ │             │ │
│  └──────────────┘ └──────────────┘ └──────────────┘ └─────────────┘ │
│                                                                     │
│  Showing 4 of 12 themes                              [View All →]   │
└─────────────────────────────────────────────────────────────────────┘
```

### Theme Card Layout

```
┌────────────────────────┐
│  Theme Name            │
│  ────────────────────  │
│  ┌──────────────────┐  │
│  │ [bg-primary]     │  │  ← Preview swatch
│  │ [bg-secondary]   │  │
│  │ [accent]         │  │
│  │ [success/danger] │  │
│  └──────────────────┘  │
│                        │
│  ✓ Selected            │  ← Checkmark if active
└────────────────────────┘
```

### Card Content

| Element                | Description                                                |
| ---------------------- | ---------------------------------------------------------- |
| **Name**               | Theme name from database                                   |
| **Swatch**             | 4-color preview: bg-primary, bg-secondary, accent, success |
| **Selected Indicator** | Checkmark on active theme                                  |
| **Hover State**        | Subtle border highlight                                    |

---

## 📊 Section 2: Theme Preview Panel

When user **hovers** on a theme card, show live preview:

```
┌─────────────────────────────────────────────────────────────────────┐
│  PREVIEW: Midnight Ocean                                            │
│  ───────────────────────────────────────────────────────────────    │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ ┌─────────────────────────────────────────────────────────┐   │  │
│  │ │ [Mini Dashboard Preview with theme applied]              │   │  │
│  │ │                                                          │   │  │
│  │ │  ┌─────┐ ┌─────┐ ┌─────┐                                │   │  │
│  │ │  │Stat │ │Stat │ │Stat │  ← Uses theme colors           │   │  │
│  │ │  └─────┘ └─────┘ └─────┘                                │   │  │
│  │ │                                                          │   │  │
│  │ │  ┌───────────────────────────────────────────────────┐  │   │  │
│  │ │  │ [Chart with theme colors]                         │  │   │  │
│  │ │  └───────────────────────────────────────────────────┘  │   │  │
│  │ └─────────────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  [Apply Theme]                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

> ⚠️ **Live Preview is Optional.** At minimum, show the color swatch. Full preview is a "nice to have."

---

## 📊 Section 3: Database Schema (Reference)

From `DATABASE.md`:

```sql
CREATE TABLE themes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,         -- "Cyberpunk Neon"
    is_dark_mode BOOLEAN DEFAULT 1,    -- Base mode
    variables TEXT NOT NULL,           -- JSON of CSS variables
    contrast_validated BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### JSON Structure for `variables`

```json
{
  "bg-primary": "#0F172A",
  "bg-secondary": "#1E293B",
  "bg-tertiary": "#334155",
  "text-primary": "#F8FAFC",
  "text-secondary": "#CBD5E1",
  "text-muted": "#64748B",
  "accent": "#F472B6",
  "accent-hover": "#EC4899",
  "success": "#22C55E",
  "warning": "#F59E0B",
  "danger": "#EF4444",
  "info": "#3B82F6",
  "border-default": "#334155",
  "shadow-color": "rgba(0, 0, 0, 0.3)"
}
```

---

## 📊 Section 4: Theme Loading Logic

### On App Load

```typescript
// 1. Check localStorage for saved theme ID
const savedThemeId = localStorage.getItem("themeId");

// 2. Fetch theme from database (or use default)
const theme = await fetchTheme(savedThemeId || "default");

// 3. Apply CSS variables to :root
applyTheme(theme);
```

### Apply Theme Function

```typescript
function applyTheme(theme: Theme) {
  const root = document.documentElement;
  const variables = JSON.parse(theme.variables);

  Object.entries(variables).forEach(([key, value]) => {
    root.style.setProperty(`--${key}`, value);
  });

  // Store in localStorage
  localStorage.setItem("themeId", theme.id);

  // Update Zustand store
  useSettingsStore.getState().setTheme(theme);
}
```

---

## 📊 Section 5: Performance Mode Toggle

```
┌─────────────────────────────────────────────────────────────────────┐
│  PERFORMANCE MODE                                                   │
│  ───────────────────────────────────────────────────────────────    │
│  [═══════════○] Reduce animations for large datasets                │
│                                                                     │
│  When enabled:                                                      │
│  • Chart animations disabled                                        │
│  • Table virtualization more aggressive                             │
│  • Hover effects simplified                                         │
└─────────────────────────────────────────────────────────────────────┘
```

### Performance Mode Overrides

```css
/* When performance mode is ON */
:root.performance-mode {
  --transition-speed: 0ms;
  --animation-duration: 0ms;
}
```

---

## 📊 Section 6: View All Themes Modal

When user clicks `[View All →]`:

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ ALL THEMES (12)                                                       [×] Close  │
├───────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─ DARK THEMES ─────────────────────────────────────────────────────────────────┐│
│  │ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐          ││
│  │ │ Cyberpunk    │ │ Midnight     │ │ Deep Space   │ │ Noir         │          ││
│  │ │ [████████]   │ │ [████████]   │ │ [████████]   │ │ [████████]   │          ││
│  │ │ ✓ Selected   │ │              │ │              │ │              │          ││
│  │ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘          ││
│  └───────────────────────────────────────────────────────────────────────────────┘│
│                                                                                   │
│  ┌─ LIGHT THEMES ────────────────────────────────────────────────────────────────┐│
│  │ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐          ││
│  │ │ Beach        │ │ Forest       │ │ Paper        │ │ Sepia        │          ││
│  │ │ [████████]   │ │ [████████]   │ │ [████████]   │ │ [████████]   │          ││
│  │ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘          ││
│  └───────────────────────────────────────────────────────────────────────────────┘│
│                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘
```

### Grouped by Light/Dark

| Section          | Themes                 |
| ---------------- | ---------------------- |
| **Dark Themes**  | `is_dark_mode = true`  |
| **Light Themes** | `is_dark_mode = false` |

---

## 🔧 State Management

```typescript
interface ThemeState {
  // Current theme
  currentTheme: Theme | null;
  isLoading: boolean;

  // All available themes
  themes: Theme[];

  // Performance mode
  performanceMode: boolean;

  // Actions
  setTheme: (theme: Theme) => void;
  fetchThemes: () => Promise<void>;
  togglePerformanceMode: () => void;
}

interface Theme {
  id: string;
  name: string;
  isDarkMode: boolean;
  variables: Record<string, string>;
  contrastValidated: boolean;
  createdAt: string;
}
```

---

## 📦 Components to Create

| Component                   | Description                    |
| --------------------------- | ------------------------------ |
| `ThemeSettings.tsx`         | Main settings panel section    |
| `ThemeSelector.tsx`         | Grid of theme cards            |
| `ThemeCard.tsx`             | Individual theme preview card  |
| `ThemePreview.tsx`          | Live preview panel (optional)  |
| `AllThemesModal.tsx`        | Full theme browser modal       |
| `PerformanceModeToggle.tsx` | Toggle switch with description |

---

## ✅ Acceptance Criteria

- [ ] Theme cards show **name + 4-color swatch**.
- [ ] **Click** on card applies theme immediately.
- [ ] **Selected theme** shows checkmark indicator.
- [ ] Themes loaded from **database**, not hardcoded.
- [ ] Theme persisted in **localStorage**.
- [ ] **Performance mode** toggle disables animations.
- [ ] **View All** modal groups themes by Light/Dark.
- [ ] All themes meet **WCAG AA contrast** (4.5:1 for text).
- [ ] Theme applies to **all components** (charts, tables, modals).
- [ ] **No flash** on page load (theme applied before render).

---

## 🚫 Anti-Patterns

- ❌ **Hardcoded themes** — All themes must come from database.
- ❌ **Flash of wrong theme** — Load theme before first paint.
- ❌ **No contrast validation** — All themes must pass WCAG AA.
- ❌ **Performance mode breaks UI** — Only reduce animations, not functionality.
- ❌ **Theme not persisted** — Must survive page refresh.

---

## 📚 Libraries

| Library                  | Purpose                             |
| ------------------------ | ----------------------------------- |
| `zustand`                | Theme state management with persist |
| `color-contrast-checker` | Validate WCAG AA compliance         |
| SQLite                   | Theme storage                       |

---

## 🎨 Pre-Built Themes (Required)

Ship with at least 4 themes:

| Theme              | Mode  | Primary Colors               |
| ------------------ | ----- | ---------------------------- |
| **Cyberpunk Neon** | Dark  | Pink accent, dark blue bg    |
| **Beach Paradise** | Light | Warm sand, ocean blue accent |
| **Midnight Ocean** | Dark  | Deep blue, cyan accent       |
| **Forest Grove**   | Light | Green accent, cream bg       |

> ⚠️ All themes must be defined in `CSS_VARIABLES.md` and inserted into the `themes` table on first run.

---

## 🔍 Figma Agent Verification Protocol

**After completing this task, Figma Agent MUST:**

1. **Check for Errors** — Review all components for:

   - Missing CSS variable references
   - Contrast violations (WCAG AA)
   - Theme not applying to all components
   - localStorage persistence failures
   - Flash of unstyled content (FOUC)

2. **Fix Identified Issues** — Do not mark task complete until:

   - All theme variables resolve correctly
   - Contrast ratios validated (4.5:1 minimum)
   - Theme persists across page refresh
   - No visual flickering on load

3. **Self-Test Checklist:**
   - [ ] Switch theme → All components update
   - [ ] Refresh page → Same theme loads
   - [ ] Toggle performance mode → Animations disabled
   - [ ] Open modal → Modal uses theme colors
   - [ ] View chart → Chart uses theme colors
