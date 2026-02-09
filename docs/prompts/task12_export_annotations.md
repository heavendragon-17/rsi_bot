# Figma Agent Prompt: Task 12 — Export System & Trade Annotations

> **Phase:** 6 (Final)
> **Priority:** 🟡 High — Users need to share and document their work.
> **Design Principle:** Export everything, annotate anything, remember context.

---

## 🎯 Objective

Design the **Export System** and **Trade Annotations** that allows users to:

1. Export reports in multiple formats (PDF, CSV, PNG, JSON)
2. Add personal notes to individual trades
3. Flag trades for review or learning

**Core Principle:** Data without context is noise. Let users add meaning.

---

## 📐 Layout Overview

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ SIDEBAR                                 MAIN CONTENT                              │
│ ┌──────┐ ┌─────────────────────────────────────────────────────────────────────┐  │
│ │      │ │  ┌─ HEADER ───────────────────────────────────────────────────────┐ │  │
│ │ [«]  │ │  │ 📊 Results Dashboard                              [Export ▼]  │ │  │
│ │ [⚙]  │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │ [▶]  │ │                                                                     │  │
│ │      │ │  ┌─ TRADES TABLE ─────────────────────────────────────────────────┐ │  │
│ │      │ │  │ # │ Entry    │ Exit     │ PnL    │ Tags │ Notes │ Actions    │ │  │
│ │      │ │  │───┼──────────┼──────────┼────────┼──────┼───────┼────────────│ │  │
│ │      │ │  │ 1 │ Feb 1... │ Feb 2... │ +$120  │ 🌟   │ 📝    │ [📝][🏷️]  │ │  │
│ │      │ │  │ 2 │ Feb 3... │ Feb 4... │ -$45   │ ⚠️   │       │ [📝][🏷️]  │ │  │
│ │      │ │  │ 3 │ Feb 5... │ Feb 6... │ +$230  │      │ 📝    │ [📝][🏷️]  │ │  │
│ │      │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ └──────┘ └─────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Section 1: Export Dropdown Menu

### Export Button & Menu

```
┌─────────────────────────────────────────┐
│  [Export ▼]                             │
│  ─────────────────────────────────────  │
│                                         │
│  📄 Full Report (PDF)                   │
│     Complete dashboard with charts      │
│                                         │
│  📊 Trades Only (CSV)                   │
│     All trades with annotations         │
│                                         │
│  🖼️ Charts (PNG)                        │
│     Equity curve + drawdown             │
│                                         │
│  🔧 Raw Data (JSON)                     │
│     Full backtest data for analysis     │
│                                         │
│  ─────────────────────────────────────  │
│  📦 Export All (ZIP)                    │
│     PDF + CSV + PNG + JSON              │
│                                         │
└─────────────────────────────────────────┘
```

### Export Options

| Format   | Contents                                        | Use Case                              |
| -------- | ----------------------------------------------- | ------------------------------------- |
| **PDF**  | Hero stats, equity chart, drawdown, trade list  | Sharing with team, documentation      |
| **CSV**  | Columns: Date, Entry, Exit, PnL, %, Tags, Notes | Analysis in Excel, further processing |
| **PNG**  | Equity curve, drawdown chart, heatmaps          | Presentations, social sharing         |
| **JSON** | Full backtest result object                     | API integration, custom analysis      |
| **ZIP**  | All of the above bundled                        | Complete backup                       |

---

## 📊 Section 2: Export Configuration Modal

When user clicks any export option:

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ EXPORT: Full Report (PDF)                                             [×] Close  │
├───────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  FILE NAME                                                                        │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │ RSI_Strategy_DOGE_2024-02-08                                                │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                   │
│  INCLUDE SECTIONS                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │ ☑ Hero Statistics                                                          │  │
│  │ ☑ Equity Curve                                                             │  │
│  │ ☑ Drawdown Chart                                                           │  │
│  │ ☑ Trade List (with annotations)                                            │  │
│  │ ☐ Parameter Settings                                                       │  │
│  │ ☐ Monthly Breakdown                                                        │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                   │
│  PAGE SIZE                                                                        │
│  [A4 ▼]   [Portrait ▼]                                                           │
│                                                                                   │
│  THEME                                                                            │
│  [Current Theme ▼]   [Light Background ▼]                                        │
│                                                                                   │
│  [Cancel]                                             [Generate PDF →]            │
│                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Section 3: Trade Annotations

### Annotation Column in Trade Table

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│  TRADE LIST                                                                       │
│  ────────────────────────────────────────────────────────────────────────────     │
│                                                                                   │
│  ┌────┬──────────┬──────────┬────────┬──────────┬───────────┬─────────────────┐  │
│  │ #  │ Entry    │ Exit     │ PnL    │ Tags     │ Notes     │ Actions         │  │
│  ├────┼──────────┼──────────┼────────┼──────────┼───────────┼─────────────────┤  │
│  │ 1  │ Feb 1    │ Feb 2    │ +$120  │ 🌟       │ [view]    │ [📝] [🏷️]      │  │
│  │    │ 0.1523   │ 0.1589   │ +4.3%  │          │           │                 │  │
│  ├────┼──────────┼──────────┼────────┼──────────┼───────────┼─────────────────┤  │
│  │ 2  │ Feb 3    │ Feb 4    │ -$45   │ ⚠️ 📚    │           │ [📝] [🏷️]      │  │
│  │    │ 0.1520   │ 0.1491   │ -1.9%  │          │           │                 │  │
│  ├────┼──────────┼──────────┼────────┼──────────┼───────────┼─────────────────┤  │
│  │ 3  │ Feb 5    │ Feb 6    │ +$230  │ 🌟 💡     │ [view]    │ [📝] [🏷️]      │  │
│  │    │ 0.1480   │ 0.1598   │ +8.0%  │          │           │                 │  │
│  └────┴──────────┴──────────┴────────┴──────────┴───────────┴─────────────────┘  │
│                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘
```

### Tag Icons

| Tag          | Icon | Meaning                           |
| ------------ | ---- | --------------------------------- |
| **Star**     | 🌟   | Best trade, worth studying        |
| **Warning**  | ⚠️   | Review this, something went wrong |
| **Learning** | 📚   | Educational, learned something    |
| **Idea**     | 💡   | New idea emerged from this trade  |
| **Lucky**    | 🍀   | Got lucky, not repeatable         |
| **Unlucky**  | 💀   | Bad luck, not a strategy flaw     |

---

## 📊 Section 4: Add Note Modal

When user clicks [📝] on a trade:

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ ADD NOTE: Trade #3                                                    [×] Close  │
├───────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  TRADE SUMMARY                                                                    │
│  ─────────────────────────────────────────────────────────────────────────────    │
│  Entry: Feb 5, 2024 @ $0.1480   →   Exit: Feb 6, 2024 @ $0.1598                  │
│  PnL: +$230 (+8.0%)                                                              │
│  Duration: 1 day 4 hours                                                         │
│                                                                                   │
│  YOUR NOTE                                                                        │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │ This was a perfect setup. RSI dropped to 28 (below 30), then price held    │  │
│  │ at EMA21 support. Volume confirmed the bounce. Should look for more       │  │
│  │ setups like this where RSI is near oversold AND price is at support.      │  │
│  │                                                                            │  │
│  │ Key lesson: Confluence matters more than single indicators.               │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                   │
│  TAGS                                                                             │
│  [🌟 Star] [⚠️ Review] [📚 Learning] [💡 Idea] [🍀 Lucky] [💀 Unlucky]          │
│      ✓                       ✓          ✓                                        │
│                                                                                   │
│  [Cancel]                                                    [Save Note]          │
│                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Section 5: View Note Popover

When user hovers/clicks [view] on a trade with notes:

```
┌─────────────────────────────────────────────────────────────────┐
│  TRADE #3 NOTE                                       [Edit] [×] │
│  ───────────────────────────────────────────────────────────    │
│                                                                 │
│  🌟 📚 💡                                                       │
│                                                                 │
│  This was a perfect setup. RSI dropped to 28 (below 30),       │
│  then price held at EMA21 support. Volume confirmed the        │
│  bounce. Should look for more setups like this where RSI       │
│  is near oversold AND price is at support.                     │
│                                                                 │
│  Key lesson: Confluence matters more than single indicators.   │
│                                                                 │
│  ───────────────────────────────────────────────────────────    │
│  Added: Feb 8, 2024 at 14:23                                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 Section 6: Bulk Tag/Export

### Bulk Actions Bar (appears when trades selected)

```
┌───────────────────────────────────────────────────────────────────────┐
│  3 trades selected                                                    │
│  ─────────────────────────────────────────────────────────────────    │
│  [Add Tag ▼]   [Remove Tag ▼]   [Export Selected]   [Clear Selection] │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Section 7: Filter by Tags

### Tag Filter in Trade Table Header

```
┌───────────────────────────────────────────────────────────────────────┐
│  FILTERS: Tags                                                        │
│  ─────────────────────────────────────────────────────────────────    │
│  [All] [🌟 Starred] [⚠️ Review] [📚 Learning] [💡 Ideas] [Has Notes]  │
│   ●                     ●                                             │
│                                                                       │
│  Showing 8 of 24 trades                                               │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 🔧 State Management

```typescript
interface ExportState {
  isExporting: boolean;
  exportFormat: "pdf" | "csv" | "png" | "json" | "zip" | null;
  exportProgress: number;

  // Export config
  exportConfig: {
    fileName: string;
    includeSections: {
      heroStats: boolean;
      equityCurve: boolean;
      drawdownChart: boolean;
      tradeList: boolean;
      parameterSettings: boolean;
      monthlyBreakdown: boolean;
    };
    pageSize: "a4" | "letter";
    orientation: "portrait" | "landscape";
    theme: "current" | "light" | "dark";
  };
}

interface AnnotationState {
  // Currently editing
  editingTradeId: string | null;

  // Filters
  tagFilters: Set<TradeTag>;
  showOnlyWithNotes: boolean;

  // Bulk selection
  selectedTradeIds: Set<string>;
}

interface TradeAnnotation {
  tradeId: string;
  note: string;
  tags: TradeTag[];
  createdAt: string;
  updatedAt: string;
}

type TradeTag = "star" | "review" | "learning" | "idea" | "lucky" | "unlucky";
```

---

## 📦 Components to Create

| Component                   | Description             |
| --------------------------- | ----------------------- |
| `ExportDropdown.tsx`        | Main export menu        |
| `ExportConfigModal.tsx`     | Format-specific options |
| `TradeAnnotationColumn.tsx` | Tags + notes in table   |
| `AddNoteModal.tsx`          | Note editor with tags   |
| `NotePopover.tsx`           | Quick note view         |
| `TagFilter.tsx`             | Filter trades by tags   |
| `BulkActionsBar.tsx`        | Multi-select actions    |
| `ExportProgress.tsx`        | Progress during export  |

---

## ✅ Acceptance Criteria

- [ ] **Export dropdown** shows all format options.
- [ ] **PDF export** includes selected sections with theme.
- [ ] **CSV export** includes all columns + annotations.
- [ ] **PNG export** saves charts as images.
- [ ] **JSON export** outputs complete backtest data.
- [ ] **ZIP export** bundles all formats.
- [ ] **Add Note modal** allows text + tag selection.
- [ ] **Tags** display as icons in trade table.
- [ ] **Filter by tags** works correctly.
- [ ] **Bulk actions** apply to selected trades.
- [ ] **Notes persist** in SQLite database.
- [ ] **Export includes annotations** in output.

---

## 🚫 Anti-Patterns

- ❌ **Export without progress** — Long exports must show progress.
- ❌ **Notes lost on refresh** — Must persist to database.
- ❌ **Tags not visible** — Must be obvious in trade table.
- ❌ **No filter by tags** — Users must find tagged trades easily.
- ❌ **Export ignores annotations** — Notes and tags must be included.

---

## 📚 Libraries

| Library                 | Purpose            |
| ----------------------- | ------------------ |
| `jspdf` + `html2canvas` | PDF generation     |
| `papaparse`             | CSV generation     |
| `html2canvas`           | PNG chart export   |
| `jszip`                 | ZIP bundling       |
| SQLite                  | Annotation storage |

---

## 🔍 Figma Agent Verification Protocol

**After completing this task, Figma Agent MUST:**

1. **Check for Errors** — Review all components for:

   - Export dropdown not opening
   - PDF generation failing
   - Notes not saving to database
   - Tags not displaying in table
   - Filters not working
   - Bulk actions not applying

2. **Fix Identified Issues** — Do not mark task complete until:

   - All export formats work
   - Notes persist after refresh
   - Tags show in trade table
   - Filters update table correctly

3. **Self-Test Checklist:**
   - [ ] Click Export → Dropdown shows 5 options
   - [ ] Export PDF → File downloads with charts
   - [ ] Add note to trade → Notes saves
   - [ ] Refresh page → Note still visible
   - [ ] Add tag 🌟 → Star icon in table
   - [ ] Filter by 🌟 → Only starred trades shown
   - [ ] Select 3 trades → Bulk actions bar appears
