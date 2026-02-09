# Tailwind Theme System

> **For AI Agents** | CSS variables and theming for Tailwind CSS v4

---

## 🎨 Tailwind CSS v4 (CSS-First)

Tailwind v4 uses **CSS-first configuration**. No `tailwind.config.js` needed.

All configuration goes in CSS files via `@theme` directive.

---

## 📄 Base Setup

In `ui/src/index.css`:

```css
@import "tailwindcss";

@theme {
  /* Primary colors */
  --color-primary: #3b82f6;
  --color-primary-hover: #2563eb;
  
  /* Background colors */
  --color-bg: #0f172a;
  --color-surface: #1e293b;
  --color-surface-hover: #334155;
  
  /* Border */
  --color-border: #334155;
  
  /* Text */
  --color-text: #f8fafc;
  --color-text-muted: #94a3b8;
  
  /* Status colors */
  --color-success: #10b981;
  --color-danger: #ef4444;
  --color-warning: #f59e0b;
  --color-info: #3b82f6;
}

/* Also set as CSS variables for non-Tailwind use */
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

## 🎯 Using Theme Colors

### In Tailwind Classes

```html
<div class="bg-surface text-text border-border">
  <button class="bg-primary hover:bg-primary-hover">
    Click me
  </button>
</div>
```

### In CSS

```css
.my-component {
  background-color: var(--color-surface);
  border: 1px solid var(--color-border);
  color: var(--color-text);
}

.my-component:hover {
  background-color: var(--color-surface-hover);
}
```

---

## 🌙 Theme Definitions

### Dark Theme (Default)

```css
--color-bg: #0f172a;           /* Slate 900 */
--color-surface: #1e293b;      /* Slate 800 */
--color-surface-hover: #334155; /* Slate 700 */
--color-border: #334155;
--color-text: #f8fafc;         /* Slate 50 */
--color-text-muted: #94a3b8;   /* Slate 400 */
--color-primary: #3b82f6;      /* Blue 500 */
```

### Light Theme

```css
--color-bg: #ffffff;
--color-surface: #f1f5f9;      /* Slate 100 */
--color-surface-hover: #e2e8f0; /* Slate 200 */
--color-border: #cbd5e1;       /* Slate 300 */
--color-text: #0f172a;         /* Slate 900 */
--color-text-muted: #64748b;   /* Slate 500 */
--color-primary: #2563eb;      /* Blue 600 */
```

### Midnight Theme

```css
--color-bg: #020617;           /* Slate 950 */
--color-surface: #0f172a;      /* Slate 900 */
--color-surface-hover: #1e293b; /* Slate 800 */
--color-border: #1e293b;
--color-text: #e2e8f0;         /* Slate 200 */
--color-text-muted: #64748b;
--color-primary: #6366f1;      /* Indigo 500 */
```

---

## 🔄 Theme Switching

### JavaScript Implementation

```typescript
const themes = {
  dark: {
    '--color-bg': '#0f172a',
    '--color-surface': '#1e293b',
    '--color-text': '#f8fafc',
    '--color-primary': '#3b82f6',
    // ... all colors
  },
  light: {
    '--color-bg': '#ffffff',
    '--color-surface': '#f1f5f9',
    '--color-text': '#0f172a',
    '--color-primary': '#2563eb',
  },
  midnight: {
    '--color-bg': '#020617',
    '--color-surface': '#0f172a',
    '--color-text': '#e2e8f0',
    '--color-primary': '#6366f1',
  },
};

export function applyTheme(themeName: string) {
  const theme = themes[themeName];
  if (!theme) return;
  
  const root = document.documentElement;
  Object.entries(theme).forEach(([property, value]) => {
    root.style.setProperty(property, value);
  });
}
```

### Store Integration

```typescript
// In useUIStore
interface UIState {
  theme: string;
  setTheme: (theme: string) => void;
}

// When theme changes
setTheme: async (theme) => {
  await window.pywebview.api.set_active_theme(theme);
  applyTheme(theme);
  set({ theme });
}
```

---

## 📏 Common Patterns

### Cards

```css
.card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 24px;
}
```

### Buttons

```css
.btn-primary {
  background: var(--color-primary);
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 8px;
  cursor: pointer;
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}
```

### Status Badges

```css
.badge-success { background: var(--color-success); }
.badge-danger { background: var(--color-danger); }
.badge-warning { background: var(--color-warning); }
```

---

## ⚠️ Important Notes

1. **No tailwind.config.js** - All config in CSS
2. **Use @theme directive** - Tailwind v4 specific
3. **Set :root variables too** - For non-Tailwind usage
4. **Test theme switching** - Ensure all components update
