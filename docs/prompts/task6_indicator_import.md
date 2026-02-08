# Figma Agent Prompt: Task 6 — Pine Script Translator

> **Phase:** 3 (Tools & Themes)
> **Priority:** 🔴 Critical — Users copy-paste from TradingView. They don't code.
> **Design Principle:** Paste → Parse → Verify. Zero configuration.

---

## 🎯 Objective

Design the **Pine Script Translator** that allows users to paste TradingView Pine Script and automatically extracts the indicator name, settings, and parameters.

**Core Principle:** This is a Translator, not an IDE. No coding required.

---

## 👥 User Persona

| Attribute        | Description                                               |
| ---------------- | --------------------------------------------------------- |
| **Coding Skill** | None. Copy-paste only.                                    |
| **Source**       | TradingView indicators (free & paid)                      |
| **Expectation**  | Paste code → See it work                                  |
| **Pain Points**  | "What is a parameter?" "Where do I put the period value?" |

---

## 📐 Layout Overview

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ SIDEBAR                                 MAIN CONTENT                              │
│ ┌──────┐ ┌─────────────────────────────────────────────────────────────────────┐  │
│ │      │ │  ┌─ HEADER ───────────────────────────────────────────────────────┐ │  │
│ │ [«]  │ │  │ 📊 Import Indicator                    [Your Indicators (3)]   │ │  │
│ │ [⚙]  │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │ [▶]  │ │                                                                     │  │
│ │      │ │  ┌─ STEP 1: PASTE ────────────────────────────────────────────────┐ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  ┌──────────────────────────────────────────────────────────┐  │ │  │
│ │      │ │  │  │ // Paste your TradingView Pine Script here...           │  │ │  │
│ │      │ │  │  │ //@version=5                                             │  │ │  │
│ │      │ │  │  │ indicator("My RSI", overlay=false)                       │  │ │  │
│ │      │ │  │  │ length = input.int(14, "RSI Length")                     │  │ │  │
│ │      │ │  │  │ ...                                                      │  │ │  │
│ │      │ │  │  └──────────────────────────────────────────────────────────┘  │ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  [Parse Script →]                                              │ │  │
│ │      │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ │      │ │  ┌─ STEP 2: VERIFY (Auto-Extracted) ──────────────────────────────┐ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  ✅ Detected: "My RSI" (Oscillator)                            │ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  ┌─ EXTRACTED PARAMETERS ──────────────────────────────────┐   │ │  │
│ │      │ │  │  │ RSI Length      [14    ]  (from input.int)              │   │ │  │
│ │      │ │  │  │ Overbought      [70    ]  (from input.int)              │   │ │  │
│ │      │ │  │  │ Oversold        [30    ]  (from input.int)              │   │ │  │
│ │      │ │  │  │ Source          [close ▼] (from input.source)           │   │ │  │
│ │      │ │  │  └─────────────────────────────────────────────────────────┘   │ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  ⚠️ 1 Warning: 'plot()' color is hardcoded (won't theme)      │ │  │
│ │      │ │  │                                                                │ │  │
│ │      │ │  │  [← Back]                              [Save Indicator →]      │ │  │
│ │      │ │  └────────────────────────────────────────────────────────────────┘ │  │
│ │      │ │                                                                     │  │
│ └──────┘ └─────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 User Flow (3 Steps Only)

```
┌─────────┐      ┌─────────┐      ┌─────────┐
│  PASTE  │ ──→  │  PARSE  │ ──→  │  SAVE   │
│         │      │ (Auto)  │      │         │
└─────────┘      └─────────┘      └─────────┘
     ↓                ↓                ↓
  Textarea       Shows Name       Saved to DB
  for code       + Params         Ready to use
```

---

## 📊 Step 1: Paste Zone

### UI Elements

```
┌───────────────────────────────────────────────────────────────────────┐
│  PASTE YOUR PINE SCRIPT                                               │
│  ─────────────────────────────────────────────────────────────────    │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │ // Paste your TradingView Pine Script here...                   │  │
│  │                                                                  │  │
│  │                                                                  │  │
│  │                                        Height: 300px, scrollable │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  💡 Tip: Copy the FULL script from TradingView's "Pine Editor" tab   │
│                                                                       │
│  [Parse Script →]                                                     │
└───────────────────────────────────────────────────────────────────────┘
```

### Paste Zone Rules

| Element         | Description                                                            |
| --------------- | ---------------------------------------------------------------------- |
| **Textarea**    | Plain textarea (NOT Monaco). No syntax highlighting needed.            |
| **Height**      | 300px with scroll                                                      |
| **Placeholder** | `// Paste your TradingView Pine Script here...`                        |
| **Tip**         | Always show: "Copy the FULL script from TradingView's Pine Editor tab" |
| **Button**      | `[Parse Script →]` — triggers parsing                                  |

> ⚠️ **No Monaco Editor.** Users don't edit code. They paste and verify. Keep it simple.

---

## 📊 Step 2: Verify (Auto-Extracted Results)

After clicking `[Parse Script →]`, the system parses the Pine Script using Regex/AST and displays:

### 2a. Detected Indicator

```
┌───────────────────────────────────────────────────────────────────────┐
│  ✅ DETECTED INDICATOR                                                │
│  ─────────────────────────────────────────────────────────────────    │
│  Name: "My RSI"                                                       │
│  Type: Oscillator (overlay=false)                                     │
│  Version: Pine Script v5                                              │
└───────────────────────────────────────────────────────────────────────┘
```

### Parsing Rules

| Pine Script Pattern      | Extracted Value   |
| ------------------------ | ----------------- |
| `indicator("Name", ...)` | Name = "Name"     |
| `strategy("Name", ...)`  | Name = "Name"     |
| `overlay=true`           | Type = Overlay    |
| `overlay=false`          | Type = Oscillator |
| `//@version=5`           | Version = v5      |

---

### 2b. Extracted Parameters

**Auto-extracted from `input.*()` functions.**

```
┌───────────────────────────────────────────────────────────────────────┐
│  EXTRACTED PARAMETERS                                                 │
│  ─────────────────────────────────────────────────────────────────    │
│  ┌─────────────────┬─────────────┬─────────────────────────────────┐  │
│  │ Parameter       │ Value       │ Source                          │  │
│  ├─────────────────┼─────────────┼─────────────────────────────────┤  │
│  │ RSI Length      │ [14    ]    │ input.int(14, "RSI Length")     │  │
│  │ Overbought      │ [70    ]    │ input.int(70, "Overbought")     │  │
│  │ Oversold        │ [30    ]    │ input.int(30, "Oversold")       │  │
│  │ Source          │ [close ▼]   │ input.source(close, "Source")   │  │
│  │ Show Signals    │ [✓]         │ input.bool(true, "Show Signals")│  │
│  └─────────────────┴─────────────┴─────────────────────────────────┘  │
│                                                                       │
│  ✏️ Adjust defaults above, or leave as-is.                           │
└───────────────────────────────────────────────────────────────────────┘
```

### Parameter Parsing Rules

| Pine Script Input                             | UI Input Type                                        |
| --------------------------------------------- | ---------------------------------------------------- |
| `input.int(default, "label")`                 | Number input                                         |
| `input.float(default, "label")`               | Decimal input                                        |
| `input.bool(default, "label")`                | Checkbox                                             |
| `input.string(default, "label")`              | Text input                                           |
| `input.source(close, "label")`                | Dropdown: `open, high, low, close, hl2, hlc3, ohlc4` |
| `input.color(color.red, "label")`             | Color picker                                         |
| `input(default, "label", type=input.integer)` | (Legacy v4 syntax)                                   |

---

### 2c. Warnings & Errors

```
┌───────────────────────────────────────────────────────────────────────┐
│  ⚠️ WARNINGS                                                          │
│  ─────────────────────────────────────────────────────────────────    │
│  • 'plot()' color is hardcoded — won't adapt to theme                 │
│  • Uses 'security()' — may require additional data subscription       │
│                                                                       │
│  ❌ ERRORS (if any)                                                   │
│  ─────────────────────────────────────────────────────────────────    │
│  • Could not detect indicator name. Please add: indicator("Name")     │
│  • Uses unsupported function: 'request.financial()'                   │
└───────────────────────────────────────────────────────────────────────┘
```

### Warning/Error Categories

| Category                 | Severity   | Example                                |
| ------------------------ | ---------- | -------------------------------------- |
| **Hardcoded colors**     | ⚠️ Warning | `plot(rsi, color=color.red)`           |
| **External data**        | ⚠️ Warning | `security()`, `request.financial()`    |
| **Missing name**         | ❌ Error   | No `indicator()` or `strategy()` found |
| **Unsupported function** | ❌ Error   | `alertcondition()`, `barcolor()`       |
| **Version mismatch**     | ⚠️ Warning | v3 syntax in v5 script                 |

---

## 📊 Step 3: Save

### Success State

```
┌───────────────────────────────────────────────────────────────────────┐
│  ✅ INDICATOR SAVED                                                   │
│  ─────────────────────────────────────────────────────────────────    │
│                                                                       │
│  "My RSI" has been added to your indicators.                          │
│                                                                       │
│  You can now select it in the Strategy Settings panel.                │
│                                                                       │
│  [← Add Another]                              [Go to Settings →]      │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 📦 Indicator Library Section

### My Indicators Grid

```
┌───────────────────────────────────────────────────────────────────────┐
│  YOUR INDICATORS (3)                                                  │
│  ─────────────────────────────────────────────────────────────────    │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐            │
│  │ My RSI         │ │ BB_Custom      │ │ MACD_Div       │            │
│  │ Oscillator     │ │ Overlay        │ │ Oscillator     │            │
│  │ ✅ Ready       │ │ ✅ Ready       │ │ ⚠️ 1 Warning   │            │
│  │ [Edit] [Del]   │ │ [Edit] [Del]   │ │ [Edit] [Del]   │            │
│  └────────────────┘ └────────────────┘ └────────────────┘            │
│                                                                       │
│  [+ Import New Indicator]                                             │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 🔧 State Management

```typescript
interface PineTranslatorState {
  // Step 1: Paste
  rawPineScript: string;
  isParsing: boolean;

  // Step 2: Verify (auto-extracted)
  parsedIndicator: ParsedIndicator | null;
  parseErrors: ParseError[];
  parseWarnings: ParseWarning[];

  // User adjustments to defaults
  parameterOverrides: Record<string, any>;

  // Step 3: Save
  isSaving: boolean;
  savedIndicators: SavedIndicator[];
}

interface ParsedIndicator {
  name: string;
  type: "oscillator" | "overlay";
  version: string; // "v5", "v4", etc.
  parameters: ExtractedParameter[];
  rawCode: string;
}

interface ExtractedParameter {
  name: string; // "RSI Length"
  variableName: string; // "length" (from Pine code)
  type: "int" | "float" | "bool" | "string" | "source" | "color";
  defaultValue: any;
  pineSource: string; // "input.int(14, 'RSI Length')"
}

interface ParseError {
  message: string;
  line?: number;
  severity: "error";
}

interface ParseWarning {
  message: string;
  line?: number;
  severity: "warning";
}

interface SavedIndicator {
  id: string;
  name: string;
  type: "oscillator" | "overlay";
  parameters: ExtractedParameter[];
  parameterValues: Record<string, any>; // User's saved defaults
  rawCode: string;
  createdAt: string;
  status: "ready" | "warning" | "error";
  warningCount: number;
}
```

---

## 🔍 Parser Implementation (Backend)

### Regex Patterns for Extraction

```python
# Indicator/Strategy name
INDICATOR_PATTERN = r'indicator\s*\(\s*["\']([^"\']+)["\']'
STRATEGY_PATTERN = r'strategy\s*\(\s*["\']([^"\']+)["\']'

# Overlay detection
OVERLAY_PATTERN = r'overlay\s*=\s*(true|false)'

# Version detection
VERSION_PATTERN = r'//@version=(\d+)'

# Input extraction (v5 syntax)
INPUT_INT = r'input\.int\s*\(\s*(\d+)\s*,\s*["\']([^"\']+)["\']'
INPUT_FLOAT = r'input\.float\s*\(\s*([\d.]+)\s*,\s*["\']([^"\']+)["\']'
INPUT_BOOL = r'input\.bool\s*\(\s*(true|false)\s*,\s*["\']([^"\']+)["\']'
INPUT_SOURCE = r'input\.source\s*\(\s*(\w+)\s*,\s*["\']([^"\']+)["\']'

# Legacy v4 input syntax
LEGACY_INPUT = r'input\s*\(\s*([^,]+)\s*,\s*["\']([^"\']+)["\']'
```

---

## 📦 Components to Create

| Component             | Description                     |
| --------------------- | ------------------------------- |
| `PineTranslator.tsx`  | Main container with 3-step flow |
| `PasteZone.tsx`       | Simple textarea for paste       |
| `ParsedResults.tsx`   | Shows detected name + params    |
| `ParameterEditor.tsx` | Editable defaults table         |
| `WarningsList.tsx`    | Shows warnings/errors           |
| `IndicatorGrid.tsx`   | Saved indicators grid           |
| `IndicatorCard.tsx`   | Card for each saved indicator   |

---

## ✅ Acceptance Criteria

- [ ] **Paste zone** accepts raw Pine Script (plain textarea, no Monaco).
- [ ] **Parse button** extracts indicator name, type, version.
- [ ] **Parameters auto-detected** from `input.*()` functions.
- [ ] **Parameter table** allows editing default values.
- [ ] **Warnings** shown for hardcoded colors, external data.
- [ ] **Errors** shown for missing name, unsupported functions.
- [ ] **Save** stores indicator with parameters to SQLite.
- [ ] **Indicator grid** shows all saved indicators with status.
- [ ] **Edit** allows re-parsing and parameter adjustment.
- [ ] Saved indicators appear in Strategy Settings dropdown.

---

## 🚫 Anti-Patterns

- ❌ **Monaco Editor** — Users don't edit code. Plain textarea is enough.
- ❌ **Manual parameter config** — Extract from `input.*()` automatically.
- ❌ **Python output** — Keep Pine Script as-is. Translate at runtime.
- ❌ **No validation feedback** — Always show what was detected.
- ❌ **Complex multi-step wizard** — 3 steps max: Paste → Verify → Save.

---

## 📚 Libraries

| Library        | Purpose                          |
| -------------- | -------------------------------- |
| Backend Python | Regex/AST parsing of Pine Script |
| React          | Frontend state management        |
| SQLite         | Store indicators with parameters |

---

## 🔐 Security Note

Pine Script is stored as-is. The actual execution/translation happens at backtest runtime, not in the browser. The UI only handles:

1. Paste & Parse (extract metadata)
2. Store in database
3. Display in Settings dropdown

Execution is always backend-controlled.
