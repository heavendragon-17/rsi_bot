# Bug Fix: Stop Loss Logic (Wick vs Close)

**Role:** Senior Python Trading Systems Engineer
**Objective:** Fix a logic error in the Backtesting Engine where "Soft Stop Losses" are being triggered by Wicks (Low price) instead of the Candle Close, causing premature exits.

---

## 1. Problem Description
*   **Current Behavior:** The `MockExchange` treats all `STOP_LOSS` orders the same way: if `Candle.Low <= Trigger Price`, it triggers the exit immediately.
*   **Issue:** For "Soft SLs" (Logical Stops), we only want to exit if the candle **Closes** below the price. Wicks below the SL should be ignored if the price recovers by close.
*   **Desired Behavior:**
    *   **Disaster SL:** Keep existing behavior (Trigger on Wick/Low).
    *   **Soft SL:** Only trigger if `Candle.Close <= Trigger Price`.

---

## 2. Required Changes

### A. Portfolio Manager (`app/core/portfolio.py`)
Modify how Stop Loss orders are created to include a flag distinguishing "Soft" from "Hard" stops.
1.  In `_handle_buy_signal`, when creating the `STOP_LOSS` order (if it is a Soft SL):
    *   Add a parameter to the order: `params={"is_soft_sl": True}`.
    *   (Note: If `signal.sl_price` is the Disaster SL, keep it as is. If you are placing an order for the `soft_sl_price`, add the flag).

### B. Mock Exchange (`app/backtest/mock_exchange.py`)
Modify the `update_candle` method to respect the new flag.

1.  **Locate:** The logic loop `for order_id, order in list(self.pending_orders.items()):`.
2.  **Logic Update:**
    *   Check `is_soft_sl = order.get("info", {}).get("is_soft_sl", False)`.
    *   **Condition:**
        *   If `is_soft_sl == True`: Check `if close_dec <= trigger_price`.
        *   If `is_soft_sl == False`: Check `if low_dec <= trigger_price` (Existing logic).
3.  **Fill Price:**
    *   If triggered by Soft SL (Close), the `fill_price` should be the `close_dec` (Close Price), not the trigger price.
    *   If triggered by Hard SL (Wick), the `fill_price` remains the `trigger_price`.

---

## 3. Implementation Checklist
*   [ ] **Portfolio:** Tag Soft SL orders with `is_soft_sl`.
*   [ ] **Exchange:** Implement conditional triggering logic in `update_candle`.
*   [ ] **Verification:** Ensure Disaster SLs (no flag) still trigger on Wicks.

---

## 4. Constraints
*   **Backtesting Only:** This change specifically targets the `MockExchange` logic used in backtests.
*   **Position Retention:** If `Low < Soft_SL` but `Close > Soft_SL`, the position MUST remain open (no exit).
