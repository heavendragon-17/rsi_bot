# Phase 8: Polish & QA

> **Phase Type:** Final | **Estimated Time:** 1.5 hours | **Depends On:** Phase 7

---

## 🎯 Objective

Finalize the application: themes, export, settings, and quality assurance.

---

## 📖 Required Reading

Before starting, read:
- `.agent-guide/knowledge/TAILWIND_THEME.md` (theming section)
- `docs/use-cases/USER_STORIES.md` (verify all stories complete)

---

## ✅ Tasks

### Task 8.1: Theme Selector

Create `ui/src/components/settings/ThemeSelector.tsx`:

**Purpose:** Switch between UI themes.

**Behavior:**
- Display theme options (dark, light, midnight)
- Click to apply
- Persist selection via `set_active_theme()`
- Update CSS variables on theme change

**Implementation:**
```typescript
const handleThemeChange = async (theme: string) => {
  await window.pywebview.api.set_active_theme(theme);
  // Apply theme to :root CSS variables
  applyTheme(theme);
};
```

### Task 8.2: Global Config Form

Create `ui/src/components/settings/GlobalConfigForm.tsx`:

**Purpose:** Edit global settings from config.yaml.

**Fields:**
- Default symbol
- Default timeframe
- Initial balance
- Commission rate
- Other settings from config.yaml

**Behavior:**
- Load via `get_global_config()`
- Edit fields
- Save via `save_global_config()`
- Show toast on save

### Task 8.3: Export Functionality

Add export buttons to:
- **Dashboard:** Export current run results
- **History:** Export selected runs
- **TradesTable:** Export trades as CSV

**Implementation:**
```typescript
const handleExport = async (format: 'csv' | 'json') => {
  const path = await window.pywebview.api.export_results(runId, format);
  addToast({ type: 'success', message: `Exported to ${path}` });
};
```

### Task 8.4: Settings Page

Create Settings page layout:

```
┌─────────────────────────────────────┐
│ Global Configuration                │
│ [GlobalConfigForm]                  │
├─────────────────────────────────────┤
│ Theme                               │
│ [ThemeSelector]                     │
├─────────────────────────────────────┤
│ About                               │
│ Version, links, credits             │
└─────────────────────────────────────┘
```

### Task 8.5: Error Handling

Add error boundaries and fallbacks:
- Wrap main app in ErrorBoundary
- Show friendly error messages
- Log errors for debugging

### Task 8.6: Loading States

Review all async operations:
- Backtest running
- Data loading
- API calls

Ensure consistent loading indicators.

### Task 8.7: User Story Verification

Go through `docs/use-cases/USER_STORIES.md` and verify each story:

| ID | Story | Status |
|----|-------|--------|
| US-001 | Select Data File | ✅ / ❌ |
| US-002 | Select Strategy | ✅ / ❌ |
| US-003 | Edit Parameters | ✅ / ❌ |
| US-004 | Run Backtest | ✅ / ❌ |
| US-005 | View Results | ✅ / ❌ |
| ... | ... | ... |

### Task 8.8: Final Build Test

```bash
cd ui
npm run build
npm run lint
```

Fix any TypeScript or ESLint errors.

### Task 8.9: End-to-End Test

```bash
python main_ui.py
```

Manual test checklist:
- [ ] App launches successfully
- [ ] All tabs accessible
- [ ] Can run a backtest
- [ ] Charts display correctly
- [ ] Grid search works
- [ ] Walk-forward works
- [ ] Sensitivity works
- [ ] Run comparison works
- [ ] Theme switching works
- [ ] Settings save correctly
- [ ] Export works

---

## 🔍 Verification Checkpoint

All features complete and working:

1. **Core functionality** (from earlier phases)
2. **Themes** switching works
3. **Settings** save and persist
4. **Export** generates files
5. **No console errors**
6. **Clean ESLint output**
7. **All user stories satisfied**

---

## 📤 Final Report Template

```
## Phase 8 Complete: Polish & QA

### FINAL PROJECT STATUS: ✅ COMPLETE

### Created Files (This Phase):
- ui/src/components/settings/ThemeSelector.tsx
- ui/src/components/settings/GlobalConfigForm.tsx
- ui/src/components/settings/index.ts
- Updated: App.tsx, various export buttons

### Feature Checklist:
- [x] Dashboard with stats
- [x] Backtest runner
- [x] Run history with filters
- [x] Equity chart
- [x] Drawdown chart
- [x] Exit pie chart
- [x] Trades table
- [x] Grid search
- [x] Walk-forward analysis
- [x] Sensitivity analysis
- [x] Run comparison
- [x] Theme switching
- [x] Global settings
- [x] Export (CSV/JSON)

### Build Status:
- `npm run build`: ✅
- `npm run lint`: ✅ (x warnings)
- `python main_ui.py`: ✅

### User Stories:
- Completed: X / Total: Y

---

## 🎉 PROJECT COMPLETE

The Backtest UI is fully functional and ready for use.

### How to Launch:
```bash
cd ui && npm run build
python main_ui.py
```
```

---

## 📁 Cleanup (Optional)

After verification:
- Remove `.agent-guide/` folder (or keep as documentation)
- Commit all changes
- Create release tag

---

**END OF PHASES**
