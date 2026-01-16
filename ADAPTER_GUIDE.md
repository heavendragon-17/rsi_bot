# Non-CCXT Exchange Adapter Guide

## Objective
This guide defines the standard for implementing adapters for exchanges that are **not** supported by the CCXT library (e.g., Lighter, specific DEXs). The goal is to wrap the exchange's native SDK so that it "looks and feels" exactly like a CCXT exchange to the rest of the trading bot.

## Compliance Checklist

Any new adapter class (e.g., `LighterAdapter`) **must** implement the `IFuturesExchange` interface and adhere to the following strict behaviors:

1.  **Inheritance:** Must inherit from `IFuturesExchange`.
2.  **Constructor:** `__init__(self, config: dict)`
    *   Initialize the native SDK (e.g., `lighter_client = Client(...)`).
3.  **Method Signatures:** Match CCXT exactly (using `float` for prices/amounts).
    *   `fetch_balance(params={}) -> dict`
    *   `create_order(symbol, type, side, amount, price=None, params={}) -> dict`
    *   `cancel_order(id, symbol=None, params={}) -> dict`
    *   `fetch_order(id, symbol=None, params={}) -> dict`
    *   `fetch_positions(symbols=None, params={}) -> list`
4.  **Return Data Structure:**
    *   **Balance:** `{'free': {'USDT': 100.0}, 'used': {'USDT': 0.0}, 'total': {'USDT': 100.0}}`
    *   **Order:** See `MOCK_EXCHANGE_SPEC.md` for the exact dictionary structure.
5.  **Exception Handling:**
    *   Catch SDK-specific exceptions (e.g., `lighter.error.BalanceError`) and **raise** strict `ccxt` exceptions (e.g., `ccxt.InsufficientFunds`).

## Implementation Example: `LighterAdapter`

Use this pattern when implementing the adapter.

```python
import ccxt
from app.core.interfaces import IFuturesExchange
# from lighter.client import Client  <-- Native SDK

class LighterAdapter(IFuturesExchange):
    def __init__(self, config: dict):
        self.api_key = config['api_key']
        # self.client = Client(api_key=...)

    def fetch_balance(self, params={}) -> dict:
        try:
            # 1. Call Native SDK
            # native_bal = self.client.get_balance()
            native_bal = {"usdc": 1000.0, "locked": 50.0} # Example response

            # 2. Map to CCXT Standard
            return {
                'info': native_bal,
                'free': {'USDC': native_bal['usdc']},
                'used': {'USDC': native_bal['locked']},
                'total': {'USDC': native_bal['usdc'] + native_bal['locked']}
            }
        except Exception as e:
            # 3. Map Exceptions
            raise ccxt.ExchangeError(f"Lighter fetch_balance failed: {e}")

    def create_order(self, symbol: str, type: str, side: str, amount: float, price: float = None, params={}) -> dict:
        # 1. Map Symbol
        # Lighter might use "ETH-PERP" instead of "ETH/USDT"
        market_symbol = symbol.replace("/", "-")

        try:
            # 2. Call Native SDK
            if type == 'limit':
                # response = self.client.create_limit_order(market_symbol, side, size=amount, price=price)
                pass
            elif type == 'market':
                # response = self.client.create_market_order(market_symbol, side, size=amount)
                pass

            # 3. Construct CCXT Order Dict
            # Ensure strictly standard keys: id, status, filled, etc.
            return {
                'id': '12345', # str(response['id'])
                'symbol': symbol,
                'status': 'open',
                'type': type,
                'side': side,
                'price': price,
                'amount': amount,
                'filled': 0.0,
                'remaining': amount,
                'info': {} # response
            }
        except Exception as e:
            raise ccxt.ExchangeError(f"Lighter create_order failed: {e}")

    # ... Implement other methods similarly ...
```

## Data Type Boundary (Gateway Rule)

*   **Incoming (SDK -> Adapter):** The SDK likely returns floats or strings. The Adapter must return standard Python `float` in the dictionary values to match CCXT.
*   **Outgoing (Adapter -> SDK):** The Adapter receives `float` from the `PortfolioManager` (which converted from `Decimal`). The Adapter passes these floats to the SDK.
*   **Decimal Safety:** Do **not** use `Decimal` inside the Adapter's public return values. The `PortfolioManager` is responsible for converting the Adapter's float outputs back to `Decimal` for internal calculation.
