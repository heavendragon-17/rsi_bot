# User Stories - Backtest UI

> **Document Type:** User Stories & Acceptance Criteria  
> **Agent:** documentation-writer  
> **Status:** Phase 1 Documentation

---

## User Persona: Strategy Tester

| Attribute | Value |
|-----------|-------|
| **Name** | "Strategy Tester" |
| **Role** | Quantitative trader, strategy developer |
| **Technical Skills** | Advanced TA, Python beginner (can `git pull`) |
| **Pain Points** | Complex CLI, no visual feedback, risk of editing Python files |
| **Goals** | Quick iteration on strategy parameters, visual performance analysis |

---

## Epic 1: Run Backtest 🚀

### US-001: Select Data File
**As a** Strategy Tester  
**I want to** select a CSV data file from a dropdown  
**So that** I don't need to remember file paths or use terminal

**Acceptance Criteria:**
- [ ] Dropdown shows all `.csv` files in `app/backtest/data/`
- [ ] Each option displays: filename, symbol (inferred), timeframe
- [ ] File size and modification date shown as secondary info
- [ ] Selection persists across sessions

---

### US-002: Select Strategy
**As a** Strategy Tester  
**I want to** choose a strategy from a dropdown  
**So that** I can see all available options without reading code

**Acceptance Criteria:**
- [ ] Dropdown shows all strategies from `STRATEGY_MAP`
- [ ] Each option displays: name, description
- [ ] Currently selected strategy is highlighted
- [ ] Selecting strategy loads its parameter editor

---

### US-003: Edit Parameters in Form
**As a** Strategy Tester  
**I want to** edit strategy parameters in a visual form  
**So that** I don't need to edit Python files

**Acceptance Criteria:**
- [ ] Form auto-generates from strategy's `DEFAULT_CONFIG`
- [ ] Input types match data types (number, slider, select)
- [ ] Changes are staged (not saved until explicit save)
- [ ] "Reset to Default" button restores original values
- [ ] Validation shows errors for invalid inputs

---

### US-004: Run Backtest with Feedback
**As a** Strategy Tester  
**I want to** click "Run Backtest" and see progress  
**So that** I know the system is working

**Acceptance Criteria:**
- [ ] Big, prominent "Run Backtest" button
- [ ] Button disables during execution
- [ ] Progress indicator shows current state
- [ ] Estimated time remaining (if calculable)
- [ ] Error messages display clearly on failure

---

### US-005: View Results Summary
**As a** Strategy Tester  
**I want to** see results in charts and tables  
**So that** I can quickly understand performance

**Acceptance Criteria:**
- [ ] Key metrics displayed prominently (cards/tiles)
- [ ] Equity curve chart loads automatically
- [ ] Trades table available for drill-down
- [ ] Results persist (saved to database)

---

## Epic 2: Configure Strategy ⚙️

### US-010: Edit Strategy Parameters
**As a** Strategy Tester  
**I want to** edit strategy-specific params (RSI period, WMA length)  
**So that** I can test different configurations

**Acceptance Criteria:**
- [ ] Form shows all configurable parameters
- [ ] Numeric inputs have min/max bounds
- [ ] Grouped by category (indicators, risk, exits)
- [ ] Tooltips explain each parameter

---

### US-011: Save to JSON Override
**As a** Strategy Tester  
**I want to** changes saved to JSON override files  
**So that** Python strategy files remain untouched

**Acceptance Criteria:**
- [ ] Save writes to `config/strategy_overrides/{name}.json`
- [ ] Original `.py` files never modified by UI
- [ ] Save confirmation shows file path
- [ ] Override file is human-readable JSON

---

### US-012: Reset to Default
**As a** Strategy Tester  
**I want to** reset to DEFAULT_CONFIG with one click  
**So that** I can start fresh after experiments

**Acceptance Criteria:**
- [ ] "Reset to Default" button clearly visible
- [ ] Confirmation dialog prevents accidental reset
- [ ] Deletes or clears JSON override file
- [ ] Form refreshes with default values

---

### US-020: Edit Global Settings
**As a** Strategy Tester  
**I want to** edit global settings (initial balance, leverage) separately  
**So that** I keep strategy params and run params organized

**Acceptance Criteria:**
- [ ] Separate "Settings" page or section
- [ ] Global settings: initial_balance, leverage, risk_per_trade
- [ ] Changes saved to `config/config.yaml`
- [ ] Validation for numeric bounds

---

## Epic 3: View Results 📊

### US-030: Equity Curve Chart
**As a** Strategy Tester  
**I want to** see equity curve chart  
**So that** I can visualize portfolio growth over time

**Acceptance Criteria:**
- [ ] Chart uses lightweight-charts library
- [ ] Crosshair shows value at any point
- [ ] Zoom and pan supported
- [ ] Export as PNG option

---

### US-031: Exit Distribution Chart
**As a** Strategy Tester  
**I want to** see exit distribution (TP1/TP2/TP3/SL) pie chart  
**So that** I understand how trades are closing

**Acceptance Criteria:**
- [ ] Pie chart shows percentage per exit reason
- [ ] Colors match TP (green variants) and SL (red)
- [ ] Hover shows count and percentage
- [ ] Legend clearly labeled

---

### US-032: Trades Table
**As a** Strategy Tester  
**I want to** see trades table with PnL per trade  
**So that** I can analyze individual trades

**Acceptance Criteria:**
- [ ] Table shows: entry/exit time, price, PnL, exit reason
- [ ] Sortable by any column
- [ ] Pagination for large datasets (50 per page)
- [ ] Export to CSV option

---

### US-033: Key Metrics Cards
**As a** Strategy Tester  
**I want to** see key metrics prominently displayed  
**So that** I can quickly assess performance

**Acceptance Criteria:**
- [ ] Display: Net Profit %, Win Rate, Sharpe Ratio, Max Drawdown
- [ ] Color coding: green for good, red for bad
- [ ] Tooltips explain each metric
- [ ] Comparison with previous run (optional)

---

## Epic 4: Run History 📁

### US-040: View Run History
**As a** Strategy Tester  
**I want to** see a list of past backtest runs  
**So that** I can compare different configurations

**Acceptance Criteria:**
- [ ] List shows: run name, strategy, date, net profit %
- [ ] Sortable by date or performance
- [ ] Filterable by strategy or symbol
- [ ] Click to view full details

---

### US-041: Compare Two Runs
**As a** Strategy Tester  
**I want to** compare two runs side-by-side  
**So that** I can see which configuration is better

**Acceptance Criteria:**
- [ ] Select 2 runs for comparison
- [ ] Side-by-side metrics comparison
- [ ] Highlight differences (better/worse)
- [ ] Overlay equity curves on same chart

---

## Epic 5: Advanced Analysis (Deferred) 🔬

> ⚠️ **Note:** These features depend on Phase 2 backend implementation

### US-050: Grid Search
**As a** Strategy Tester  
**I want to** run Grid Search across parameter ranges  
**So that** I can find optimal configurations

**Deferred:** Requires `grid_search.py` backend module

---

### US-051: Walk-Forward Optimization
**As a** Strategy Tester  
**I want to** run Walk-Forward tests  
**So that** I can avoid overfitting

**Deferred:** Requires `walk_forward.py` backend module

---

### US-052: Sensitivity Analysis
**As a** Strategy Tester  
**I want to** see Sensitivity Analysis  
**So that** I know which parameters are fragile

**Deferred:** Requires `sensitivity.py` backend module

---

## Priority Matrix

| Priority | User Stories | Phase |
|----------|--------------|-------|
| **P0 (Must)** | US-001, US-002, US-003, US-004, US-005 | Phase 1 |
| **P1 (Should)** | US-010, US-011, US-012, US-030, US-031, US-032, US-033 | Phase 1 |
| **P2 (Could)** | US-020, US-040, US-041 | Phase 2 |
| **P3 (Future)** | US-050, US-051, US-052 | Phase 3 |
