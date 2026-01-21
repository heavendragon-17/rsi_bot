# Debugging Feature Request: SL Mismatch Visualization in Backtest Reports

**Role:** Senior Python Trading Systems Engineer
**Objective:** Enhance the backtesting reporting infrastructure to debug a specific discrepancy: The Stop Loss (SL) price calculated by the strategy signal does not match the actual execution price, leading to unexpected exits and potential risk calculation errors.

---

## 1. Problem Statement
*   **Observation:** The chart shows candles never closing below the expected SL price, yet the system triggers an SL exit at an unwanted price.
*   **Hypothesis:** There is a mismatch between the SL price calculated in the Signal/Risk module and the physical SL order placed by the Portfolio Manager.
*   **Goal:** Visualize this mismatch side-by-side in the HTML report table for every trade.

---

## 2. Required Changes

### A. Data Capture (PortfolioManager & MockExchange)
You need to persist the original signal data through the trade lifecycle so it's available for reporting.

1.  **PortfolioManager (`app/core/portfolio.py`):**
    *   When creating a `Position` (in `_handle_buy_signal`), store:
        *   `signal_sl_price`: The `signal.sl_price` (Disaster SL) or `signal.soft_sl_price`.
        *   `initial_risk_pct`: The calculated risk percentage at entry.
    *   When closing a position (full or partial), pass these stored values into the `exit_reason` or a new metadata dictionary sent to the exchange.

2.  **MockExchange (`app/backtest/mock_exchange.py`):**
    *   Update the `trade_history` storage.
    *   Ensure that when a trade is closed, the record includes:
        *   `signal_sl_price` (from the position data).
        *   `executed_sl_price` (the actual fill price if SL was hit).
        *   `position_size` (amount).
        *   `expected_risk` (Calculated: `(Entry - SignalSL) * Amount`).
        *   `realized_risk` (Calculated: `(Entry - Exit) * Amount` if negative).

### B. Reporting Logic (`app/backtest/reporting.py`)
Modify `BacktestReporter` to include these new fields in the `round_trips` DataFrame and the HTML output.

1.  **`_build_round_trips`:**
    *   Extract `signal_sl_price`, `expected_risk`, and `realized_risk` from the trade info.
    *   Add them to the returned round-trip dictionary.

2.  **`_generate_html_report`:**
    *   Update the `trades-table` HTML generation.
    *   **Add New Columns:**
        *   `Pos Size` (Position Amount)
        *   `Signal SL` (The expected SL price)
        *   `Exec SL` (The actual exit price - only relevant if SL hit)
        *   `Exp Risk` (Expected $ Loss)
        *   `Real Risk` (Actual $ PnL if negative)
    *   **Formatting:**
        *   Highlight `Real Risk` in **red** if it significantly exceeds `Exp Risk` (> 5% difference), indicating slippage or logic error.

---

## 3. Output Format (Table Column Specification)
The HTML table should now look like this:

| # | Entry Time | Symbol | ... | **Pos Size** | **Signal SL** | **Exec SL** | **Exp Risk ($)** | **Real Risk ($)** | Exit Reason |
|---|---|---|---|---|---|---|---|---|---|
| 1 | ... | BTC | ... | 0.5 | 50000 | 49800 | -100 | -200 | SL |

---

## 4. Implementation constraints
*   **No functional changes to strategy logic:** Only add data logging and reporting.
*   **Backwards compatibility:** Ensure the code doesn't crash if old trade history data is missing these new fields (use `N/A` or `0`).
*   **File Scope:**
    *   `app/core/portfolio.py`
    *   `app/backtest/mock_exchange.py`
    *   `app/backtest/reporting.py`
