# Refactoring Prompt: Exchange Factory & Environment Separation

## Objective
Implement a robust `ExchangeFactory` that enforces a strict separation between Backtesting (`mock`), Staging (`paper`), and Production (`live`) environments.

## Core Requirement: The Three Modes

The factory function `create_exchange(config: dict) -> IFuturesExchange` must handle three distinct modes defined in `config['bot']['mode']`.

### 1. Mock Mode (`mode='mock'`)
*   **Purpose:** Local Backtesting and Development.
*   **Implementation:** Returns an instance of `MockExchange`.
*   **Behavior:** Fully in-memory, no network calls. Uses `app/backtest/data/` for candle simulation.

### 2. Paper Mode (`mode='paper'`)
*   **Purpose:** Staging / Final Test before Production.
*   **Implementation:** Returns a **Real CCXT Exchange Instance** (e.g., `ccxt.binanceusdm`) connected to the **Testnet**.
*   **Configuration:**
    *   Must load credentials from `config['exchange']['paper']`.
    *   Must set `options={'defaultType': 'future'}`.
    *   **Must** set `exchange.set_sandbox_mode(True)` (or use specific Testnet URLs) to ensure orders do not go to the real market.
*   **Crucial:** This is **NOT** a simulation class. It connects to the exchange's actual Testnet API.

### 3. Live Mode (`mode='live'`)
*   **Purpose:** Production Trading.
*   **Implementation:** Returns a **Real CCXT Exchange Instance** connected to **Mainnet**.
*   **Configuration:**
    *   Must load credentials from `config['exchange']['live']`.
    *   Must set `options={'defaultType': 'future'}`.
    *   Must set `exchange.set_sandbox_mode(False)`.
*   **Safety:** Add a log warning: "WARNING: RUNNING IN LIVE TRADING MODE".

## Implementation Details

### Configuration Structure (Example)
The factory should expect a config structure similar to this:

```yaml
bot:
  mode: "paper" # mock | paper | live

exchange:
  name: "binanceusdm"
  paper:
    api_key: "TESTNET_KEY..."
    secret: "TESTNET_SECRET..."
  live:
    api_key: "REAL_KEY..."
    secret: "REAL_SECRET..."
```

### Factory Code Logic
Refactor `app/services/execution/exchange_factory.py` to follow this logic:

```python
def create_exchange(config: dict) -> IFuturesExchange:
    mode = config.get("bot", {}).get("mode", "mock").lower()
    exchange_name = config.get("exchange", {}).get("name", "binanceusdm")

    # 1. Mock Mode
    if mode == "mock":
        from app.backtest.mock_exchange import MockExchange
        return MockExchange(config)

    # 2. Setup Real Exchange (Paper or Live)
    if mode in ["paper", "live"]:
        # Select credentials based on mode
        creds = config.get("exchange", {}).get(mode, {})
        api_key = creds.get("api_key")
        secret = creds.get("secret")

        if not api_key or not secret:
            raise ValueError(f"Missing API credentials for {mode} mode.")

        # Instantiate CCXT
        exchange_class = getattr(ccxt, exchange_name)
        exchange = exchange_class({
            'apiKey': api_key,
            'secret': secret,
            'options': {'defaultType': 'future'}
        })

        # 3. Configure Paper Mode (Testnet)
        if mode == "paper":
            exchange.set_sandbox_mode(True)
            print(f"Factory: Created {exchange_name} in PAPER (Testnet) mode.")

        # 4. Configure Live Mode
        elif mode == "live":
            exchange.set_sandbox_mode(False)
            print(f"Factory: Created {exchange_name} in LIVE mode. REAL MONEY AT RISK.")

        return exchange

    raise ValueError(f"Unknown mode: {mode}")
```

## Validation
*   Ensure that running in `paper` mode requires valid Testnet keys.
*   Ensure that running in `live` mode requires valid Real keys.
*   Ensure `mock` mode requires no keys.
