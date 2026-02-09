# Phase 0: Project Setup

> **Phase Type:** Foundation | **Estimated Time:** 30 min | **Depends On:** Nothing

---

## 🎯 Objective

Scaffold the React frontend project with all dependencies installed.

---

## 📖 Required Reading

Before starting, read:
- `.agent-guide/knowledge/LESSONS_LEARNED.md` (for dependency gotchas)

---

## ✅ Tasks

### Task 0.1: Create UI Directory Structure

Create the following folders at project root:

```
ui/
├── src/
│   ├── components/
│   │   ├── analysis/
│   │   ├── charts/
│   │   ├── common/
│   │   ├── history/
│   │   ├── layout/
│   │   ├── settings/
│   │   └── tables/
│   ├── stores/
│   └── types/
```

### Task 0.2: Create package.json

Create `ui/package.json` with these dependencies:

**Dependencies:**
- react: ^18.3.1
- react-dom: ^18.3.1
- react-is: ^18.3.1 (REQUIRED for recharts)
- zustand: ^5.0.1
- lightweight-charts: ^5.1.0
- recharts: ^3.7.0
- lucide-react: ^0.563.0
- framer-motion: ^12.33.0
- clsx: ^2.1.1
- tailwind-merge: ^3.4.0
- tailwindcss: ^4.0.0
- date-fns: ^4.1.0
- swr: ^2.4.0

**DevDependencies:**
- vite: ^6.0.1
- @vitejs/plugin-react: ^4.3.4
- @tailwindcss/vite: ^4.0.0
- typescript: ~5.6.2
- @types/react: ^18.3.12
- @types/react-dom: ^18.3.1
- @types/node: ^22.10.0
- eslint: ^8.56.0
- @typescript-eslint/eslint-plugin: ^8.54.0
- @typescript-eslint/parser: ^8.54.0
- eslint-plugin-react-hooks: ^7.0.1
- @playwright/test: ^1.58.2

**Scripts:**
```json
{
  "dev": "vite",
  "build": "tsc -b && vite build",
  "lint": "eslint .",
  "preview": "vite preview",
  "test:e2e": "playwright test"
}
```

### Task 0.3: Create Vite Configuration

Create `ui/vite.config.ts`:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
    plugins: [react(), tailwindcss()],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
        },
    },
    build: {
        outDir: 'dist',
        emptyOutDir: true,
    },
    base: './',  // CRITICAL: Required for PyWebView
})
```

### Task 0.4: Create TypeScript Configs

Create `ui/tsconfig.json`:
```json
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ]
}
```

Create `ui/tsconfig.app.json` with:
- Target: ES2020
- Module: ESNext
- JSX: react-jsx
- Strict mode enabled
- Path alias: @/* → ./src/*

Create `ui/tsconfig.node.json` for Vite config.

### Task 0.5: Create Entry Files

Create `ui/index.html`:
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>RSI Bot UI</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Create `ui/src/main.tsx`:
```typescript
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

Create `ui/src/App.tsx` (placeholder):
```typescript
export default function App() {
  return <div>RSI Bot UI - Setup Complete</div>
}
```

Create `ui/src/index.css` with Tailwind v4 imports and theme variables.

### Task 0.6: Create Type Definitions

Create `ui/src/types/pywebview.d.ts` with TypeScript types for `window.pywebview.api`.

### Task 0.7: Install Dependencies

Run:
```bash
cd ui
npm install --legacy-peer-deps
```

**Note:** Use `--legacy-peer-deps` if there are peer dependency conflicts.

---

## 🔍 Verification Checkpoint

Run these commands and verify success:

```bash
cd ui
npm run build
```

**Expected Output:**
- TypeScript compilation succeeds
- Vite build creates `dist/` folder
- `dist/index.html` exists with relative asset paths (./assets/...)

---

## 📤 Report Template

After completing this phase, report to user:

```
## Phase 0 Complete: Project Setup

### Created Files:
- ui/package.json
- ui/vite.config.ts
- ui/tsconfig.json, tsconfig.app.json, tsconfig.node.json
- ui/index.html
- ui/src/main.tsx, App.tsx, index.css
- ui/src/types/pywebview.d.ts

### Verification:
- `npm run build`: ✅ PASSED / ❌ FAILED (reason)

### Issues Encountered:
- (list any issues and how they were resolved)

Awaiting "proceed" command for Phase 1.
```

---

## ⏭️ Next Phase

After user approval, proceed to `PHASE_1_DATABASE.md`
