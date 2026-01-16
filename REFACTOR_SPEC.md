# Refactoring Prompt: Legacy Cleanup & Float/Decimal Standardization

## Objective

Refactor the codebase to eliminate legacy order keys (replacing them with CCXT standard keys), remove deprecated methods, and establish a strict data type policy (Float for Exchange API, Decimal for Core Logic).

## Core Requirements

1.  **CCXT Order Standardization:**

    - **Replace `exit_reason`:**
      - CCXT does not have an `exit_reason` field.
      - **Solution:** Store `exit_reason` inside the `info` dictionary of the order object (e.g., `order['info']['exit_reason']`).
      - Update `PortfolioManager` and `BacktestReporter` to read/write from `info['exit_reason']`.
    - **Replace `trigger_price`:**
      - Rename to `stopPrice` (CCXT standard) or `triggerPrice` (CCXT unified). **Decision:** Use `triggerPrice` as per modern CCXT unified specs.
    - **Replace `order_type`:**
      - Rename to `type` (e.g., `'limit'`, `'market'`).
    - **Remove Custom Keys:**
      - Ensure no other non-standard keys leak into the top level of the order dictionary. Put them in `info` if absolutely necessary.

2.  **Float vs Decimal Policy:**

    - **Exchange Layer (`IFuturesExchange` / Adapters):**
      - **MUST** use `float` for all price/amount inputs and outputs.
      - This aligns with CCXT and most Python SDKs.
    - **Core Layer (`PortfolioManager` / Strategies):**
      - **MUST** use `Decimal` for all internal financial calculations (Risk, PnL, Sizing).
    - **Boundary Layer (The "Gateway"):**
      - `PortfolioManager` is the Gateway.
      - **Outgoing:** Convert `Decimal` -> `float` before calling `exchange.create_order`.
      - **Incoming:** Convert `float` -> `Decimal` immediately when receiving data from `exchange.fetch_balance` or `exchange.fetch_order`.

3.  **Non-CCXT Adapter Pattern:**
    - If integrating a non-CCXT exchange (e.g., Hyperliquid SDK):
      - Create a Wrapper Class implementing `IFuturesExchange`.
      - **Internal:** Call the native SDK (which likely uses floats).
      - **External:** Return strict CCXT-compliant dictionaries (using floats).
      - **Mapping:** Manually map SDK-specific status/keys to CCXT standard (e.g., HL `sz` -> CCXT `amount`).

## Implementation Steps

### 1. Refactor `PortfolioManager`

- **Imports:** `from decimal import Decimal`
- **Helper:** Add `_to_float(decimal_val)` and `_to_decimal(float_val)`.
- **Order Creation:**
  - Convert amounts/prices to float.
  - Move `exit_reason` to `params={'exit_reason': ...}`.
  - Call `exchange.create_order(..., params=params)`.
- **Order Consumption:**
  - When reading `order['info']['exit_reason']`, handle missing keys gracefully.

### 2. Update `MockExchange`

- **Remove** `update_price` (use `update_candle`).
- **Remove** `place_stop_loss` / `place_take_profit` custom methods if they exist as public API (use `create_order` with `params={'stopLoss': ...}` or distinct `type='stop_loss'`). _Correction:_ CCXT uses `create_order` with `params` for SL/TP or specific types. For this Mock, standardize on `create_order(..., params={'stopPrice': ...})`.
- **Update Internal Logic:**
  - Store `triggerPrice` instead of `trigger_price`.
  - Store `type` instead of `order_type`.

### 3. Update Reporting (`app/backtest/reporting.py`)

- Update parsing logic to look for `exit_reason` in `order['info']` (or fallback to top-level for backward compatibility with old logs, if needed, but preferably clean it up).

### 4. Code Cleanup

- Delete unused files or methods identified during refactor.
- Ensure no `float` math exists in `PortfolioManager` (grep check).

## Verification

- Run `app/backtest/run_batch_analysis.py`.
- Ensure the report is generated without errors and metrics match the baseline.
