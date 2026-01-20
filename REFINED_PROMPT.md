# Feature Request: Limit Order Entry with Timeout and Dynamic Position Management

**Role:** Senior Python Trading Systems Engineer
**Objective:** Refactor the execution logic to switch from immediate Market Entries to Limit Order Entries with a timeout mechanism and dynamic SL/TP updates. This includes updates to the live runner, portfolio manager, and backtesting infrastructure.

---

## 1. Context & Architecture
*   **Target Files:**
    *   `app/core/portfolio.py` (`PortfolioManager` class)
    *   `app/core/runner.py` (`MultiSymbolRunner._run_symbol_loop`)
    *   `app/backtest/engine.py` (`BacktestEngine.run`)
    *   `app/backtest/mock_exchange.py` (`MockExchange.update_candle`)
*   **Current State:** The bot currently executes a MARKET BUY immediately. The Mock Exchange only supports LIMIT SELLs (for SL/TP) but lacks LIMIT BUY logic.
*   **Desired State:** The bot should place a LIMIT BUY at the signal price (EMA21). The system (live and backtest) must monitor this order, handle timeouts, and sync partial fills.

---

## 2. Detailed Requirements

### A. Entry Logic (PortfolioManager)
Modify `_handle_buy_signal` to:
1.  **Price:** Use `signal.price` (which represents the EMA21) as the Limit Order price.
2.  **Order Type:** Place a `LIMIT` order instead of `MARKET`.
3.  **State Management:**
    *   Store the `entry_order_id`.
    *   Store the `entry_candle_timestamp` (the timestamp of the candle that triggered the signal).
    *   Store the `initial_order_amount`.
    *   Mark the status as "PENDING_ENTRY".

### B. Signal Blocking (MultiSymbolRunner & BacktestEngine)
1.  In the execution loop, check if the `PortfolioManager` has a `pending_entry_order`.
2.  **If Pending:** Skip the `strategy.analyze()` step. Do **not** look for new signals while trying to enter.
3.  **Instead:** Call a new maintenance method `portfolio.check_pending_entry(current_candle_timestamp)`.

### C. Maintenance & Timeout Logic (PortfolioManager.check_pending_entry)
Create a method `check_pending_entry(self, current_candle_timestamp)` that handles two main responsibilities:

#### 1. Timeout Handler (5 Candles)
*   Calculate `candles_elapsed = current_candle_timestamp - entry_candle_timestamp` (in terms of timeframe units).
*   **Condition:** If `candles_elapsed >= 5`:
    *   **Case A: 0% Filled:**
        *   Cancel the Limit Order.
        *   Reset internal state (clear `entry_order_id`).
        *   Resume searching for signals.
    *   **Case B: Partially Filled:**
        *   Cancel the *remaining* amount on the Limit Order.
        *   Treat the *filled* amount as the final active position.
        *   Update SL and TP orders to match this final filled size immediately.
        *   Transition state to "ACTIVE_POSITION".

#### 2. Dynamic SL/TP Sync (Throttle: 60 Seconds)
*   **Optimization:** To save API calls, only run this check if `time.time() - last_check_time > 60` seconds (Live Mode only).
*   **Action:**
    *   Fetch the specific Limit Order status from the exchange.
    *   Compare `current_filled_amount` vs `last_known_filled_amount`.
    *   **If Changed:**
        *   Update (or create) the Stop Loss and Take Profit orders to match the `current_filled_amount`.
        *   *Note:* Ensure you handle the math correctly so you don't place SLs for 0 amount.

---

## 3. Backtesting Infrastructure Updates

### `app/backtest/mock_exchange.py`
The current `MockExchange` lacks logic to trigger BUY Limit orders.
- [ ] In `update_candle`:
    - [ ] Add logic to check for `BUY` Limit orders.
    - [ ] **Condition:** If `Candle.Low <= Limit Price`, trigger the fill.
    - [ ] Ensure `exit_reason` is correctly propagated.

### `app/backtest/engine.py`
The backtest loop currently only calls `strategy.analyze`.
- [ ] In the main simulation loop:
    - [ ] Add the same check as `MultiSymbolRunner`:
    - [ ] `if portfolio.has_pending_entry(): portfolio.check_pending_entry(ts); continue`
    - [ ] Else: `strategy.analyze(...)`

---

## 4. Implementation Checklist

### `app/core/portfolio.py`
- [ ] Add `self.pending_entry` dictionary/object to `__init__`.
- [ ] Refactor `_handle_buy_signal` to place `LIMIT` order.
- [ ] Implement `check_pending_entry(current_candle_timestamp)`.

### `app/core/runner.py`
- [ ] In `_run_symbol_loop`: Add `check_pending_entry` logic and signal blocking.

### `app/backtest/mock_exchange.py`
- [ ] Implement `BUY` Limit Order triggering logic in `update_candle`.

### `app/backtest/engine.py`
- [ ] Update main loop to call `check_pending_entry` to support the new timeout logic in backtests.

---

## 5. Key Constraints
*   **Efficiency:** Do not query the exchange on every loop iteration. Use the 60s timer for partial fill checks.
*   **Safety:** Ensure that if the limit order is cancelled (Case B), the SL/TP are definitely updated to match the exposure.
*   **Price:** The Limit Price is **fixed** at the moment of the signal (Signal Candle EMA21).
*   **Consistency:** Backtests must behave exactly like live trading (blocking signals during pending entry).
