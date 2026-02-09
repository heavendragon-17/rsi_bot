# Figma Migration Guide

> **For AI Agents** | How to use Designstrategycommandcenter

---

## 📍 Location

Figma-generated UI code: `Designstrategycommandcenter/`

This folder contains React components generated from a Figma design. It's a **reference**, not production code.

---

## 📁 Structure

```
Designstrategycommandcenter/
├── src/
│   ├── App.tsx           # Reference layout
│   ├── index.css         # CSS to adapt
│   ├── main.tsx          # Entry (ignore)
│   ├── components/       # UI components
│   ├── stores/           # State patterns
│   ├── styles/           # Additional styles
│   └── types/            # Type definitions
├── package.json          # Dependencies list
└── vite.config.ts        # Build config (reference)
```

---

## 🎯 What to Use

### ✅ COPY These

1. **CSS Styles (`index.css`)**
   - Color variables
   - Typography
   - Shadows and gradients
   - Animations
   - Copy and adapt to `ui/src/index.css`

2. **Component Structure**
   - Layout patterns
   - Card/panel designs
   - Form styling
   - Table styling

3. **Design Tokens**
   - Color palette
   - Spacing values
   - Border radius
   - Font sizes

### ⚠️ ADAPT These

1. **Component Logic**
   - Copy visual structure
   - Rewrite with real API calls
   - Add proper state management

2. **Type Definitions**
   - Use as reference
   - Update to match actual API

### ❌ DON'T Use

1. **Mock Data** - Replace with real API calls
2. **Hardcoded Values** - Replace with API responses
3. **Fake Interactivity** - Implement real functionality

---

## 🔄 Migration Pattern

### Step 1: Study the Component

Look at a component in `Designstrategycommandcenter/src/components/`:

```typescript
// Example: Original Figma component
export function DashboardCard({ title, value }) {
  return (
    <div className="card-container">
      <h3 className="card-title">{title}</h3>
      <span className="card-value">{value}</span>
    </div>
  )
}
```

### Step 2: Copy Styles

From Figma's `index.css`:
```css
.card-container {
  background: var(--surface);
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.card-title {
  color: var(--text-muted);
  font-size: 14px;
}

.card-value {
  color: var(--text);
  font-size: 32px;
  font-weight: bold;
}
```

### Step 3: Create New Component

In `ui/src/components/`:

```typescript
// New component with real integration
import { useDataStore } from '@/stores/useDataStore'

export function DashboardCard({ title, valueKey }) {
  const data = useDataStore((state) => state.currentRun)
  const value = data?.[valueKey] ?? '--'
  
  return (
    <div className="card-container">
      <h3 className="card-title">{title}</h3>
      <span className="card-value">{value}</span>
    </div>
  )
}
```

### Step 4: Integrate Styles

Either:
1. Copy CSS classes to `ui/src/index.css`
2. Or use Tailwind utility classes

---

## 🎨 CSS Variable Mapping

The Figma code may use different variable names. Map them:

| Figma Variable | Our Variable |
|---------------|--------------|
| `--bg` | `--color-bg` |
| `--surface` | `--color-surface` |
| `--text` | `--color-text` |
| `--primary` | `--color-primary` |

---

## 📋 Component Mapping

| Figma Component | Create As | Phase |
|-----------------|-----------|-------|
| Layout components | `components/layout/` | 4 |
| Dashboard cards | `DashboardStats.tsx` | 5 |
| Forms | `DynamicForm.tsx` | 5 |
| Tables | `RunHistoryTable.tsx`, `TradesTable.tsx` | 5, 6 |
| Charts | `components/charts/` | 6 |
| Analysis panels | `components/analysis/` | 7 |
| Settings forms | `components/settings/` | 8 |

---

## ⚠️ Common Pitfalls

1. **Don't copy-paste blindly** - Figma code has mock data
2. **Check for hardcoded values** - Replace with variables
3. **Verify responsive design** - May need adjustment
4. **Test in PyWebView** - Browser behavior differs slightly

---

## 🔍 Exploration Commands

To understand Figma structure:

```bash
# List components
ls Designstrategycommandcenter/src/components/

# View a component
cat Designstrategycommandcenter/src/components/SomeComponent.tsx

# View CSS
cat Designstrategycommandcenter/src/index.css
```
