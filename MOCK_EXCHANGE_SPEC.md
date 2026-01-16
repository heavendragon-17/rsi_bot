# Refactoring Prompt: Standardizing Mock Exchange to CCXT

## Objective
Refactor the `MockExchange` and the core `IFuturesExchange` interface to strictly adhere to the **CCXT Unified API** structure. This standardization will minimize code changes when switching between the local mock environment, paper trading (Testnet), and live execution.

## Core Directives

1.  **Strict CCXT Compliance:**
    *   The `MockExchange` must mimic the methods, return types, and data structures of a CCXT exchange instance.
    *   **Do not** create custom methods (like `update_price`) if a CCXT equivalent exists (or implement them as internal helpers prefixed with `_`).

2.  **Interface Update (`app/core/interfaces.py`):**
    *   Refactor `IFuturesExchange` (created in the previous plan) to match CCXT signatures exactly.
    *   **Required Methods:**
        *   `fetch_balance(params: dict = {}) -> dict`
        *   `create_order(symbol: str, type: str, side: str, amount: float, price: float = None, params: dict = {}) -> dict`
        *   `cancel_order(id: str, symbol: str = None, params: dict = {}) -> dict`
        *   `fetch_order(id: str, symbol: str = None, params: dict = {}) -> dict`
        *   `fetch_open_orders(symbol: str = None, since: int = None, limit: int = None, params: dict = {}) -> List[dict]`
        *   `fetch_positions(symbols: List[str] = None, params: dict = {}) -> List[dict]`
        *   `fetch_ohlcv(symbol: str, timeframe: str, since: int = None, limit: int = None, params: dict = {}) -> List[List[float]]`
    *   **Note:** Types should be standard Python types (`float`, `int`, `str`) or `Decimal` where CCXT uses them (CCXT mostly uses floats/strings, but our internal logic prefers Decimal. *Adapter layer* should handle conversion if necessary, but for this Mock, sticking to float for the external API and Decimal internally is acceptable, OR fully embrace floats if strictly following CCXT. **Decision:** Use `float` for the public API to match CCXT, use `Decimal` internally for math).

3.  **Mock Exchange Implementation (`app/backtest/mock_exchange.py`):**

    *   **Order Structure:** Returned order objects **must** contain these keys:
        ```python
        {
            'id': str,
            'clientOrderId': str,
            'datetime': str,      # ISO8601
            'timestamp': int,     # ms
            'lastTradeTimestamp': int,
            'status': str,        # 'open', 'closed', 'canceled', 'rejected'
            'symbol': str,
            'type': str,          # 'market', 'limit'
            'side': str,          # 'buy', 'sell'
            'price': float,
            'amount': float,
            'filled': float,
            'remaining': float,
            'cost': float,        # filled * price
            'average': float,
            'fee': {
                'currency': str,
                'cost': float,
                'rate': float
            },
            'info': dict          # Raw data
        }
        ```

    *   **Simulation Features:**
        *   **Fees:** Implement `maker` and `taker` fee simulation.
            *   Configurable via `__init__` (e.g., `maker_fee=0.0002`, `taker_fee=0.0005`).
            *   Deduct fees from Quote currency (for Sells) or Base currency (for Buys) - or standard Futures behavior (deduct from margin/balance in Quote). *Futures Standard:* Fees usually deducted from USDT balance.
        *   **Exceptions:**
            *   Raise `ccxt.InsufficientFunds` if margin < required.
            *   Raise `ccxt.OrderNotFound` if cancelling a non-existent ID.
            *   Raise `ccxt.InvalidOrder` for bad parameters (e.g. neg/zero amount).

4.  **Factory Logic Update (`app/services/execution/exchange_factory.py`):**
    *   **Modes:**
        *   `'mock'`: Returns `MockExchange` (Local simulation).
        *   `'paper'`: Returns a **Real Exchange** instance connected to Testnet (e.g., `ccxt.binanceusdm({ 'options': { 'defaultType': 'future' } })` with testnet URLs). **Do not** redirect `'paper'` to `'mock'`.
        *   `'live'`: Returns Real Exchange (Live).

## Implementation Steps

### 1. Update `IFuturesExchange` Interface
Modify `app/core/interfaces.py` to define the abstract base class with the CCXT signatures listed above. Ensure strict type hinting.

### 2. Refactor `MockExchange`
Rewrite `app/backtest/mock_exchange.py`:
*   Inherit from `IFuturesExchange`.
*   **Internal State:**
    *   `self.orders`: Dict[str, dict] (stored by ID).
    *   `self.balance`: Dict (CCXT format: `{'free': {...}, 'used': {...}, 'total': {...}}`).
    *   `self.positions`: Dict[str, dict] (CCXT format).
*   **Methods:**
    *   `create_order`: Validate inputs -> Check Balance -> Create Order Dict -> Store -> Return.
    *   `cancel_order`: Check ID -> Update Status -> Return.
    *   `fetch_balance`: Return standardized dict.
    *   `update_candle` (Internal Helper): This is technically *not* CCXT, but required for the backtest loop to drive the mock. Keep this, but ensure it updates the *internal* state so `fetch_order` returns correct `status` (e.g. 'closed') and `filled` amounts.

### 3. Error Handling Verification
*   Add logic to `create_order`:
    ```python
    if cost > available_balance:
        raise ccxt.InsufficientFunds("Insufficient balance")
    ```
*   Add logic to `cancel_order`:
    ```python
    if id not in self.orders:
        raise ccxt.OrderNotFound(f"Order {id} not found")
    ```

## Example Usage (Verification)
The following code should work with the new `MockExchange`:

```python
exchange = MockExchange()
try:
    # Should look exactly like using ccxt.binance()
    order = exchange.create_order('BTC/USDT', 'limit', 'buy', 1.0, 50000.0)
    print(order['id'], order['status']) # -> '123', 'open'

    # Simulate price move (internal helper)
    exchange.update_candle('BTC/USDT', open=50000, high=51000, low=49000, close=50500, timestamp=1000)

    order = exchange.fetch_order(order['id'])
    print(order['status'], order['filled']) # -> 'closed', 1.0

except ccxt.InsufficientFunds as e:
    print("Error handled correctly")
```
