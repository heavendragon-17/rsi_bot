# Component Specifications

> **For AI Agents** | Behavioral specs for UI components

---

## 📐 Layout Components

### Layout.tsx

**Purpose:** Main app container with sidebar and content area.

**Behavior:**
- Full viewport height
- Sidebar fixed on left (240px)
- Content area fills remaining space
- Responsive: sidebar collapses on mobile

---

### Sidebar.tsx

**Purpose:** Navigation and branding.

**Elements:**
- Logo/title at top
- Nav items: Dashboard, History, Optimization, Settings
- Active item highlighted
- Icons from lucide-react

**Behavior:**
- Click item → update activeTab in useUIStore
- Current tab visually distinct

---

### Header.tsx

**Purpose:** Top bar with selectors and actions.

**Elements:**
- Strategy dropdown
- Data file dropdown
- Run Backtest button
- Loading indicator

---

## 📊 Dashboard Components

### DashboardStats.tsx

**Purpose:** Display 4 key metric cards.

**Cards:**
- Total Profit (with trend arrow)
- Win Rate (percentage)
- Total Trades (count)
- Profit Factor (ratio)

**Behavior:**
- Updates when new run completes
- Green/red colors based on value
- Skeleton loading state

---

### BacktestRunner.tsx

**Purpose:** Form to configure and run backtest.

**Fields:**
- Strategy (dropdown from get_strategies)
- Data file (dropdown from get_data_files)
- Date range (start/end date pickers)
- Parameters (dynamic from strategy config)

**Actions:**
- Run button triggers run_backtest
- Show loading during execution
- Toast on success/error

---

## 📈 Chart Components

### EquityChart.tsx

**Purpose:** Line chart of portfolio value over time.

**Library:** lightweight-charts

**Behavior:**
- Load data from get_run_timeseries
- Zoom and pan enabled
- Crosshair with tooltip
- Responsive to container size

---

### DrawdownChart.tsx

**Purpose:** Area chart showing drawdown percentage.

**Behavior:**
- Red/orange filled area
- Negative values (0 to -X%)
- Same time axis as equity chart
- Highlight max drawdown point

---

### ExitPieChart.tsx

**Purpose:** Pie chart of exit reasons.

**Library:** recharts

**Segments:**
- Take Profit (green)
- Stop Loss (red)
- Signal (blue)
- Timeout (gray)

**Behavior:**
- Calculate from trades data
- Show percentages
- Legend visible
- Tooltip on hover

---

## 📋 Table Components

### RunHistoryTable.tsx

**Purpose:** List all past runs.

**Columns:**
- ID
- Strategy
- Symbol
- Date Range
- Profit
- Win Rate
- Trades
- Actions (View, Compare, Delete)

**Behavior:**
- Sortable columns
- Click row to select/view
- Multi-select for comparison
- Pagination if >20 rows

---

### TradesTable.tsx

**Purpose:** All trades for a run.

**Columns:**
- # (index)
- Entry Time
- Exit Time
- Side (Long/Short with color badge)
- Entry Price
- Exit Price
- Quantity
- P&L (green/red)
- Exit Reason

**Behavior:**
- Pagination (10/25/50)
- Sortable
- Search/filter
- Export CSV button

---

## 🔬 Analysis Components

### GridSearchPanel.tsx

**Purpose:** Configure and run parameter optimization.

**Elements:**
- Strategy selector
- Parameter grid builder:
  - Add parameter button
  - For each: name dropdown, values input
- Run button
- Results table (sortable)

**Behavior:**
1. Select strategy
2. Add parameters with test values
3. Run search
4. Display results sorted by profit
5. Click row to view details

---

### WalkForwardPanel.tsx

**Purpose:** Rolling window analysis.

**Elements:**
- Train period input (days)
- Test period input (days)
- Step size input (days)
- Run button
- Timeline visualization
- Results table

**Behavior:**
- Show IS/OOS windows visually
- Display efficiency per window
- Aggregate stats at bottom

---

### SensitivityAnalysis.tsx

**Purpose:** Single parameter sensitivity.

**Elements:**
- Parameter dropdown
- Value range (min, max, step)
- Metric dropdown (profit/win_rate/sharpe)
- Run button
- Line chart of results

**Behavior:**
- Chart shows metric vs parameter value
- Highlight optimal point
- Display stability score

---

### ComparisonView.tsx

**Purpose:** Side-by-side run comparison.

**Elements:**
- Run 1 selector
- Run 2 selector
- Compare button
- Metrics table (side by side)
- Overlay equity chart

**Behavior:**
- Show both runs' metrics
- Highlight differences
- Overlay both equity curves

---

## ⚙️ Settings Components

### GlobalConfigForm.tsx

**Purpose:** Edit global settings.

**Fields:** (from config.yaml)
- Default symbol
- Default timeframe
- Initial balance
- Commission rate

**Actions:**
- Save button
- Reset to defaults

---

### ThemeSelector.tsx

**Purpose:** Switch UI themes.

**Elements:**
- Theme cards/buttons
- Visual preview
- Current selection indicator

**Behavior:**
- Click to apply theme
- Persist via set_active_theme
- Immediate visual update

---

## 🔔 Common Components

### Toast.tsx

**Purpose:** Notification popups.

**Types:** success, error, warning, info

**Behavior:**
- Appear at top-right
- Auto-dismiss after 3-5s
- Click to dismiss
- Stack multiple toasts

---

### Modal.tsx

**Purpose:** Dialog wrapper.

**Props:**
- isOpen: boolean
- onClose: function
- title: string
- children: ReactNode

**Behavior:**
- Backdrop click closes
- Escape key closes
- Focus trap inside

---

### LoadingSpinner.tsx

**Purpose:** Loading indicator.

**Variants:**
- Small (inline)
- Medium (button)
- Large (full screen overlay)

---

### EmptyState.tsx

**Purpose:** No data placeholder.

**Props:**
- icon: ReactNode
- message: string
- action?: { label, onClick }

**Behavior:**
- Centered in container
- Optional action button
