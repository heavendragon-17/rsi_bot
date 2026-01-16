# Refactoring Prompt: Multi-Symbol Concurrency & Thread Safety

## Objective
Enable the trading bot to run multiple trading pairs simultaneously using a multi-threaded architecture. This requires ensuring the `MockExchange` (and core logic) is thread-safe to handle concurrent order placements and state updates from multiple strategy threads.

## Core Requirements

1.  **Thread-Safe Exchange:**
    *   The `MockExchange` serves as the shared "server" resource.
    *   It must use `threading.RLock` to protect its internal state (`orders`, `balance`, `positions`, `trade_history`).
    *   Atomic operations for placing orders, cancelling orders, and updating balances.

2.  **Concurrency Architecture:**
    *   **Live/Paper Mode:** Implement a `MultiSymbolRunner` that spawns a separate thread for each symbol.
    *   **Architecture:**
        *   1 Shared `IFuturesExchange` instance.
        *   N Threads, where each thread runs its own `Strategy` loop for a specific symbol.
        *   Each thread may have its own `PortfolioManager` instance (simplest) OR share a locked `PortfolioManager`. *Decision: Share the Exchange, but keep Portfolio/Strategy instances per-symbol to avoid complex state merging.*

3.  **Backtest Implication:**
    *   While the current `BacktestEngine` is sequential, making the Exchange thread-safe prepares it for future parallel backtesting (e.g., running 10 backtests at once).

## Implementation Steps

### 1. Update `MockExchange` for Thread Safety
Modify `app/backtest/mock_exchange.py`:
*   **Import:** `import threading`
*   **Init:** Initialize `self._lock = threading.RLock()`.
*   **Decorate Public Methods:**
    *   Use `with self._lock:` context manager inside *every* public state-modifying or state-reading method:
        *   `create_order`
        *   `cancel_order`
        *   `fetch_balance` (and internal balance/position updates)
        *   `fetch_positions`
        *   `fetch_order`
*   **Internal Helpers:** Ensure internal methods (like `_execute_order`) assume the lock is *already held* by the caller (hence `RLock` is preferred over `Lock`).

### 2. Multi-Symbol Runner (`app/core/runner.py`)
Create a specification for a new runner class:
*   **Class `MultiSymbolRunner`**:
    *   **Init:** Accepts `config`, `strategy_class`, `exchange_factory`.
    *   **Setup:**
        *   Creates **one** shared exchange instance via factory.
        *   Reads `config['symbols']`.
    *   **Run Loop:**
        *   For each symbol, create a `Thread` targeting a `_run_symbol_loop` method.
        *   Start all threads.
        *   Main thread waits (join) or handles signals (Ctrl+C).
    *   **Symbol Loop (`_run_symbol_loop`):**
        *   Instantiates `Strategy(config)`.
        *   Instantiates `PortfolioManager(shared_exchange, config)`.
        *   Runs the standard "fetch candle -> analyze -> execute" loop for that specific symbol.

### 3. Example Thread-Safe Mock Implementation
Provide this pattern to the agent:

```python
import threading
from app.core.interfaces import IFuturesExchange

class ThreadSafeMockExchange(IFuturesExchange):
    def __init__(self, ...):
        self._lock = threading.RLock()
        # ... other init ...

    def create_order(self, ...):
        with self._lock:
            # Check balance
            # Update internal state
            # Return result
            pass

    def fetch_balance(self, ...):
        with self._lock:
            # Return copy of balance dict to prevent external modification issues
            return self.balance.copy()
```

### 4. Verification Plan
*   Create a test script `tests/test_concurrency.py` that:
    1.  Instantiates a `MockExchange`.
    2.  Spawns 10 threads, each placing random buy/sell orders for different symbols.
    3.  Asserts that the final balance equals `Initial - Fees + PnL` and no "Race Condition" exceptions occurred (e.g., negative balance due to double-spend).
