# Refactoring Prompt: Exchange Abstraction & DI Architecture

## Objective
Refactor the trading bot's execution layer to implement a robust Dependency Injection (DI) architecture. This will enable seamless switching between Mock (Backtest), Paper (Testnet), and Live execution modes using a Factory pattern.

The goal is to maintain **exact logic parity** with the current system while preparing the codebase for future enhancements (like "Candle Close" exits and Hyperliquid integration).

## Core Requirements

1.  **Architecture:**
    *   Replace direct exchange instantiation with an `ExchangeFactory`.
    *   Inject `IFuturesExchange` into `PortfolioManager` and `BacktestEngine`.
    *   Standardize risk parameters via `RiskTypes`.

2.  **Logic Parity:**
    *   The refactored code must produce **identical backtest results** to the legacy code when configured with `LIMIT_ORDER` triggers.
    *   Implement the *capability* for "Candle Close" exits (`on_candle` logic) but keep the default configuration as `LIMIT_ORDER` (Legacy Wick/Limit logic) for now.

3.  **New Components:**
    *   `app/core/risk_types.py`: Enums and Dataclasses.
    *   `app/services/execution/exchange_factory.py`: Factory for creating exchanges.
    *   `app/services/execution/hyperliquid_adapter.py`: Stub adapter.

## Step-by-Step Implementation Instructions

### Step 1: Define Core Types
Create `app/core/risk_types.py`.
*   **Enum `ExitTrigger`**: Values `CANDLE_CLOSE`, `LIMIT_ORDER`, `WICK`.
*   **Dataclass `TPLevel`**: Fields `percentage` (Decimal), `trigger` (ExitTrigger).
*   **Dataclass `RiskParams`**: Fields `sl_trigger` (ExitTrigger), `tp_trigger` (ExitTrigger), `sl_distance_pct` (Decimal), `tp_levels` (List[TPLevel]).

### Step 2: Refactor Interfaces (`app/core/interfaces.py`)
*   **Rename** `IExchange` to `IFuturesExchange`.
*   **Add Methods** to `IFuturesExchange`:
    *   `set_leverage(symbol: str, leverage: int) -> None`
    *   `get_position(symbol: str) -> Optional[Position]`
    *   `place_stop_loss(symbol: str, amount: Decimal, price: Decimal) -> Dict`
*   **Update `IStrategy`**:
    *   Add abstract method `get_risk_params() -> RiskParams`.

### Step 3: Update Strategies
*   **`app/strategies/base.py`**:
    *   Add abstract `get_risk_params` to `BaseStrategy`.
*   **`app/strategies/rsi_no_retest.py`**:
    *   Implement `get_risk_params`.
    *   Define a constant `RISK_CONFIG` in the class.
    *   **Crucial**: Configure `sl_trigger` and `tp_trigger` to `ExitTrigger.LIMIT_ORDER` to ensure backward compatibility for this refactor.

### Step 4: Refactor Portfolio Manager (`app/core/portfolio.py`)
*   Update `__init__` to accept `IFuturesExchange`.
*   **Implement `on_candle(self, candle: Candle)`**:
    *   This method checks for "Candle Close" exits.
    *   Logic: If `sl_trigger` is `CANDLE_CLOSE` and `close <= sl_price`, execute market close.
    *   *Note*: Since we config strategy to `LIMIT_ORDER`, this logic won't trigger yet, preserving parity.
*   **Update `on_signal`**:
    *   If `sl_trigger` is `LIMIT_ORDER`: Place a real `STOP_LOSS` order on the exchange (Legacy behavior).
    *   If `sl_trigger` is `CANDLE_CLOSE`: Place a "Disaster SL" (e.g., 3x distance) on the exchange and manage the real SL internally in `on_candle`.

### Step 5: Update Backtest Engine (`app/backtest/engine.py`)
*   Refactor `__init__` to accept an `exchange` instance (Dependency Injection) instead of creating `MockExchange` internally.
*   Update the main loop:
    1.  Call `exchange.update_candle(...)` (Matches legacy wick checks for Limit orders).
    2.  Call `portfolio.on_candle(...)` (New Logic capability).
    3.  Call `portfolio.on_signal(...)`.

### Step 6: Create Exchange Factory (`app/services/execution/exchange_factory.py`)
*   Create function `create_exchange(config: dict) -> IFuturesExchange`.
*   Based on `config['bot']['mode']`:
    *   `'mock'` or `'paper'`: Return `MockExchange`.
    *   `'live'`: Return `BinanceAdapter` or `HyperliquidAdapter`.

### Step 7: Update Adapters
*   **`app/backtest/mock_exchange.py`**:
    *   Implement `IFuturesExchange`.
    *   Ensure `place_stop_loss` and `set_leverage` are implemented.
*   **`app/services/execution/hyperliquid_adapter.py`**:
    *   Create a stub class implementing `IFuturesExchange`.

### Step 8: Verification
*   Run the batch backtest using `python app/backtest/run_batch_analysis.py`.
*   Compare the results with the baseline report (`app/backtest/report/batch_report.html`).
*   **Expectation**: The Total Net Profit and other metrics must be **identical** (or extremely close due to float precision).

## Constraints
*   **Do not** change the core trading logic of `RsiNoRetestStrategy`.
*   **Do not** enable `CANDLE_CLOSE` triggers yet (keep config as `LIMIT_ORDER`).
*   Ensure all imports are updated to reflect the renamed interface.
