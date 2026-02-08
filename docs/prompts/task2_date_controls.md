# Figma Agent Prompt: Task 2 — Date Range & Lookback Controls

> **Phase:** 1 (Core Layout & Controls)
> **Priority:** 🔴 Critical Foundation
> **Design Head Status:** ✅ Reviewed & Approved (Compact Tabs)

---

## 🎯 Objective

Design and implement **space-efficient date/time controls** for backtesting. The layout must fit within ~120px height. Users need two modes:

1. **Relative** — "Last N bars/days/hours"
2. **Absolute** — Fixed start and end dates

---

## 📐 UI Layout: Compact Tabs

> ⚠️ **Design Mandate:** No "OR" dividers. Use tabbed layout to preserve vertical space.

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ▾ Date Range                                                  [UTC ▼]   │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ [  Relative (Last X)  ] [  Absolute (Dates)  ]                      │ │ ← Segmented Control
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ ┌─ IF RELATIVE TAB ───────────────────────────────────────────────────┐ │
│ │  [Last]  [  1000  ]  [ Bars   ▼ ]                                   │ │
│ │           ↑ Number    ↑ Unit (Bars/Days/Hours/Weeks)                │ │
│ │                                                                     │ │
│ │  ┌─ Quick Select ──────────────────────────────────────────────┐    │ │
│ │  │ [1D] [1W] [1M] [3M] [YTD] [1Y] [All]                        │    │ │
│ │  └─────────────────────────────────────────────────────────────┘    │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ ┌─ IF ABSOLUTE TAB ───────────────────────────────────────────────────┐ │
│ │  Start: [ 2023-01-01    📅 ]   End: [ 2024-01-01    📅 ]            │ │
│ │          ↑ Text input first, calendar icon as fallback              │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ ℹ️ ~14,400 bars (Est. Data: ~1.2MB)                                  │ │ ← ComputedRangeBadge
│ └─────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Interaction Logic

### Tab Switching

| Active Tab   | Visible Controls               |
| ------------ | ------------------------------ |
| **Relative** | Lookback input + Quick Presets |
| **Absolute** | Start/End date text inputs     |

### Priority Rules

| User Action               | Effect                                      |
| ------------------------- | ------------------------------------------- |
| Click Preset (e.g., "1M") | Lookback = 30 days. Calculated dates shown. |
| Type in Lookback          | Presets deselect. Calculated dates shown.   |
| Switch to Absolute        | Relative fields hidden. Focus Start input.  |
| Type in Date field        | Validate format. Update Computed Range.     |

### Power User Flow

- **Text First:** Absolute date fields are text inputs. User can type `2023-01-01` [Tab] `2024-01-01`. Calendar is a fallback icon.
- **YTD:** The "Year-to-Date" preset is mandatory (most used in finance).

---

## 🌐 Timezone Handling

> ⚠️ **Critical:** A backtest on `2024-01-01` is meaningless without timezone context.

### UI Element

- **Location:** Top-right of section header.
- **Default:** `UTC`.
- **Format:** `[UTC ▼]` dropdown.

### Options

```
UTC (Default)
America/New_York (EST/EDT)
Europe/London (GMT/BST)
Asia/Tokyo (JST)
Asia/Singapore (SGT)
```

### Library

- Use `date-fns-tz` for all date operations.
- Store timezone in state alongside dates.

---

## 🎨 Design Requirements

### Segmented Control (Tabs)

- Active: `bg-accent text-white`.
- Inactive: `bg-surface border-border`.
- Transition: `150ms ease`.

### Lookback Input

- Number field: `w-20` (auto-grow for large numbers).
- Unit Dropdown: Contains `Bars`, `Hours`, `Days`, `Weeks`, `Months`.

### Quick Presets

- Pill buttons: `[1D] [1W] [1M] [3M] [YTD] [1Y] [All]`.
- Selected: Filled accent.
- Hover: Subtle glow.

### Date Text Inputs

- Width: `w-36`.
- Format: `YYYY-MM-DD`.
- Calendar icon: Inside input, right side.
- Validation: Red border if invalid format.

### Timezone Selector

- Small dropdown: `w-24`.
- Muted text: `text-muted`.

### Computed Range Badge

- Read-only, muted.
- Shows: `~14,400 bars (Est. Data: 12MB)`.
- Color-coded by bar count.

---

## ⚠️ Bar Count Thresholds (CTO Approved)

```typescript
function getBarColor(count: number): string {
  if (count > 1_000_000) return "var(--danger)"; // Heavy - may crash browser
  if (count > 100_000) return "var(--warning)"; // Slow
  if (count > 10_000) return "var(--text-secondary)"; // Standard
  return "var(--text-muted)"; // Fast
}
```

---

## 📦 Components to Create

| Component                | Description                          |
| ------------------------ | ------------------------------------ |
| `DateRangeSection.tsx`   | Container with tabs                  |
| `RelativeTab.tsx`        | Lookback + Presets                   |
| `AbsoluteTab.tsx`        | Start/End text inputs                |
| `LookbackInput.tsx`      | Number + Unit dropdown               |
| `PresetPills.tsx`        | Quick select row                     |
| `DateTextInput.tsx`      | Typeable date with calendar fallback |
| `TimezoneSelector.tsx`   | Small dropdown                       |
| `ComputedRangeBadge.tsx` | Read-only summary                    |

---

## 🔧 State Management

```typescript
interface DateRangeState {
  // Mode
  mode: "relative" | "absolute";

  // Timezone
  timezone: string; // e.g., "UTC", "America/New_York"

  // Relative
  preset: "1D" | "1W" | "1M" | "3M" | "YTD" | "1Y" | "All" | null;
  lookbackValue: number | null;
  lookbackUnit: "bars" | "hours" | "days" | "weeks" | "months";

  // Absolute
  startDate: string | null; // ISO format
  endDate: string | null;

  // Computed (derived)
  resolvedStartDate: Date;
  resolvedEndDate: Date;
  estimatedBars: number;
  estimatedDataSize: string; // e.g., "12MB"
}
```

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action                      |
| -------- | --------------------------- |
| `G`      | Focus Start Date input      |
| `P`      | Cycle through Presets       |
| `L`      | Focus Lookback number input |
| `Tab`    | Move between fields         |

---

## ✅ Acceptance Criteria

- [ ] Tabbed layout (Relative vs Absolute).
- [ ] Timezone selector in header.
- [ ] "Bars" unit in Lookback dropdown.
- [ ] "YTD" preset included.
- [ ] Text-first date inputs with calendar fallback.
- [ ] Bar count color-coded.
- [ ] All colors use CSS variables.
- [ ] Max height: ~120px.

---

## 🚫 Anti-Patterns to Avoid

- ❌ No vertical stacking of all controls (kills scroll space).
- ❌ No calendar-only date input (power users prefer typing).
- ❌ No hardcoded timezones (use `date-fns-tz`).
- ❌ No emojis as icons.

---

## 📚 Libraries

| Library            | Purpose                |
| ------------------ | ---------------------- |
| `date-fns`         | Date manipulation      |
| `date-fns-tz`      | Timezone handling      |
| `react-datepicker` | Calendar fallback      |
| `clsx`             | Conditional classnames |
