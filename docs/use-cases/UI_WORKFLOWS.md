# UI Workflows - Backtest UI

> **Document Type:** Step-by-Step Workflows  
> **Agent:** documentation-writer  
> **Status:** Phase 1 Documentation

---

## Workflow 1: First-Time Launch 🚀

```mermaid
sequenceDiagram
    participant User
    participant BAT as run_backtest_ui.bat
    participant Conda
    participant PyWebView
    participant React
    
    User->>BAT: Double-click
    BAT->>Conda: activate rsi
    Conda->>PyWebView: python -m app.ui_bridge.main
    PyWebView->>React: Load UI (index.html)
    React->>PyWebView: window.pywebview ready
    PyWebView->>React: Inject API
    React->>User: Dashboard shown
```

### Steps:
1. User double-clicks `run_backtest_ui.bat`
2. Script activates conda environment `rsi`
3. Python launches PyWebView window
4. React UI loads from built assets
5. Dashboard page appears with empty state
6. System scans for data files and strategies

### Expected State:
- Window: 1400x900 (resizable)
- Theme: Last used or default (Cyberpunk Neon)
- Data selector: Populated with CSV files
- Strategy selector: Populated from STRATEGY_MAP

---

## Workflow 2: Run Single Backtest 🎯

```mermaid
flowchart TD
    A[Dashboard] --> B[Select Data File]
    B --> C[Select Strategy]
    C --> D[Review/Edit Parameters]
    D --> E{Happy with config?}
    E -->|No| D
    E -->|Yes| F[Click Run Backtest]
    F --> G[Show Progress]
    G --> H[Display Results]
    H --> I{Save to history?}
    I -->|Auto| J[Saved to DB]
    I -->|Manual| K[User names run]
    K --> J
```

### Step 1: Select Data File
- **Location:** Top of controls panel
- **Action:** Click dropdown → Select CSV file
- **Feedback:** File info displayed (rows, date range)

### Step 2: Select Strategy
- **Location:** Below data selector
- **Action:** Click dropdown → Select strategy
- **Feedback:** Parameter editor loads

### Step 3: Review Parameters
- **Location:** Parameter editor panel
- **Action:** Review default values, modify if needed
- **Feedback:** Changes highlighted, validation shown

### Step 4: Run Backtest
- **Location:** Prominent button at bottom of controls
- **Action:** Click "▶ Run Backtest"
- **Feedback:** 
  - Button changes to "Running..."
  - Progress indicator appears
  - Estimated time shown (if available)

### Step 5: View Results
- **Location:** Main content area
- **Auto-display:**
  - Metrics cards (Net Profit, Win Rate, etc.)
  - Equity curve chart
  - Exit distribution pie
  - Trades table (collapsed by default)

---

## Workflow 3: Edit Strategy Parameters ⚙️

```mermaid
flowchart TD
    A[Select Strategy] --> B[Parameter Editor Loads]
    B --> C[View Current Values]
    C --> D{Default or Override?}
    D -->|Override exists| E[Show Override Values]
    D -->|No override| F[Show Default Values]
    E --> G[Edit Parameters]
    F --> G
    G --> H{Valid?}
    H -->|No| I[Show Errors]
    I --> G
    H -->|Yes| J[Save Button Enabled]
    J --> K[Click Save]
    K --> L[Written to JSON]
    L --> M[Confirmation Toast]
```

### Parameter Editor Features:
| Feature | Description |
|---------|-------------|
| **Grouped Sections** | Indicators, Risk, Exits |
| **Input Types** | Number (with slider), Select |
| **Validation** | Real-time, shows errors inline |
| **Reset Button** | Returns to DEFAULT_CONFIG |
| **Save Button** | Writes to JSON override |

### Example: RSI WMA Retest Parameters
```
📊 Indicator Settings
├── RSI Period: [21] ───────●─── (range: 5-50)
├── RSI WMA Length: [45] ──────●── (range: 10-100)
└── Price EMA Slow: [200] ─────────●── (range: 50-300)

⚠️ Risk Settings
├── SL Buffer %: [0.0] ──●──────── (range: 0-5)
└── Disaster SL Mult: [3.0] ───●──── (range: 1-5)

💰 Exit Settings
├── TP1 R:R: [1.0] ──●────────── (range: 0.5-3)
├── TP2 R:R: [2.0] ───●───────── (range: 1-5)
└── TP3 R:R: [3.0] ────●──────── (range: 1.5-10)
```

---

## Workflow 4: View Results Detail 📊

```mermaid
flowchart TD
    A[Results Summary] --> B{What to explore?}
    B -->|Metrics| C[Hover for tooltips]
    B -->|Equity| D[Zoom/Pan chart]
    B -->|Trades| E[Expand table]
    B -->|Exits| F[View pie chart]
    
    D --> G[Crosshair shows values]
    E --> H[Sort by column]
    E --> I[Filter by exit reason]
    E --> J[Click row for detail]
    J --> K[Trade detail modal]
```

### Metrics Card Interactions:
| Metric | Hover Info | Click Action |
|--------|------------|--------------|
| Net Profit % | "Total return on initial capital" | - |
| Win Rate | "Winning trades / Total trades" | - |
| Sharpe Ratio | "Risk-adjusted returns" | - |
| Max Drawdown | "Largest peak-to-trough decline" | Show drawdown chart |

### Equity Chart Interactions:
- **Zoom:** Scroll wheel or pinch
- **Pan:** Click and drag
- **Crosshair:** Shows date, balance, % change
- **Export:** Right-click → Save as PNG

### Trades Table Interactions:
- **Sort:** Click column header
- **Filter:** Dropdown for exit reason
- **Paginate:** 50 rows per page
- **Export:** "Export CSV" button

---

## Workflow 5: Export Results 📤

```mermaid
flowchart TD
    A[Results View] --> B[Click Export]
    B --> C{Format?}
    C -->|CSV| D[Download trades.csv]
    C -->|JSON| E[Download report.json]
    C -->|HTML| F[Generate HTML report]
    F --> G[Open in browser]
```

### Export Options:
| Format | Content | File |
|--------|---------|------|
| **CSV** | Trades only | `backtest_{run_id}_trades.csv` |
| **JSON** | Full results + config | `backtest_{run_id}_report.json` |
| **HTML** | Full report with charts | `backtest_{run_id}_report.html` |

---

## Workflow 6: Compare Runs 🔄

```mermaid
flowchart TD
    A[History Page] --> B[Select Run A]
    B --> C[Click Compare]
    C --> D[Select Run B]
    D --> E[Comparison View]
    E --> F[Side-by-side metrics]
    E --> G[Overlaid equity curves]
    E --> H[Diff highlights]
```

### Comparison View Features:
- **Metrics Table:** Side-by-side with delta column
- **Color Coding:** Green (better), Red (worse)
- **Equity Overlay:** Both curves on same chart
- **Config Diff:** Parameters that changed

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl + Enter` | Run Backtest |
| `Ctrl + S` | Save Parameters |
| `Ctrl + R` | Reset to Default |
| `Escape` | Close modal/drawer |
| `1-5` | Switch dashboard tabs |

---

## Error States

| Error | Display | Recovery |
|-------|---------|----------|
| **No Data Files** | Empty dropdown + help text | Check `app/backtest/data/` folder |
| **Invalid Config** | Red border + inline error | Fix validation issues |
| **Backtest Failed** | Error toast + details | Check Python console |
| **DB Write Failed** | Warning toast | Results still in memory |
