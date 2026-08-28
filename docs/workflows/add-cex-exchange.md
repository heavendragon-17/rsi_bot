# Add a CEX Exchange (CCXT)

> Add a new centralized exchange supported by the CCXT library (e.g., OKX, Bybit, KuCoin).
> Reference implementation: `app/trading/exchange/binance_adapter.py`

## Prerequisites

- Read `docs/02_architecture/system-overview.md` — understand the layer
  boundaries
- Read `docs/08_execution_and_oms/exchange-adapters.md` — understand
  `IExchange`, normalized orders, and existing adapters
- Verify the exchange is in CCXT: `python -c "import ccxt; print(ccxt.exchanges)"`

## Steps

### 1. Choose the CCXT class name and credential prefix

Check [CCXT docs](https://docs.ccxt.com/) for the exchange's futures class name (e.g., `okx`, `bybit`, `dydx`). Decide an env prefix (e.g., `OKX`, `BYBIT`). This becomes `{PREFIX}_API_KEY` / `{PREFIX}_SECRET_KEY`.

### 2. Register in EXCHANGE_CONFIG

File: `app/trading/exchange/factory.py`

Add an entry to the `EXCHANGE_CONFIG` dict (line ~33):

```python
EXCHANGE_CONFIG = {
    'binanceusdm': { 'ccxt_class': 'binanceusdm', 'env_prefix': 'BINANCE' },
    'binance':     { 'ccxt_class': 'binanceusdm', 'env_prefix': 'BINANCE' },
    'okx':         { 'ccxt_class': 'okx',          'env_prefix': 'OKX' },     # new
}
```

The key must match what the user sets in `config.yaml` under `exchange.name`.

### 3. Create an adapter class

File: `app/trading/exchange/{name}_adapter.py`

Model on `app/trading/exchange/binance_adapter.py`. The adapter must:

- **Implement `IExchange`** from `app/core/interfaces.py` — all 9 abstract methods:
  - `fetch_ohlcv`, `create_order`, `fetch_order`, `cancel_order`
  - `set_leverage`, `fetch_positions`, `fetch_balance`, `fetch_open_orders`, `cancel_all_orders`
- **Wrap CCXT** with `threading.Lock` for thread safety (the live bot calls from multiple threads)
- **Translate normalized order types** to exchange-native params:
  - `market` → CCXT `market`
  - `limit` → CCXT `limit`
  - `stop_market` → exchange-specific stop order (check CCXT docs for the exchange)
  - `stop_limit` → exchange-specific stop-limit
  - `trailing_stop` → exchange-specific trailing (with `callbackRate` param)
  - All exit orders pass `params={'reduceOnly': True}`
- **Catch CCXT exceptions** and re-raise as `ExchangeError` hierarchy from `app/core/exceptions.py`
- **Use `structlog.get_logger()`** — never `print()`
- **Load credentials** from env: `{PREFIX}_API_KEY` / `{PREFIX}_SECRET_KEY` for live, `{PREFIX}_TESTNET_API_KEY` / `{PREFIX}_TESTNET_SECRET_KEY` for paper
- **Handle paper mode** via `set_sandbox_mode(True)` on the CCXT instance (same pattern as BinanceAdapter)

### 4. Update factory routing

File: `app/trading/exchange/factory.py`

Currently line ~126 always creates `BinanceAdapter` for any CCXT exchange. To support multiple CEX adapters, update the `if exchange_name in EXCHANGE_CONFIG:` block to route to the correct adapter class. Options:

- Add an `adapter_module` / `adapter_class` key to each `EXCHANGE_CONFIG` entry
- Or use a local dict mapping: `'okx' → OkxAdapter`, `'binanceusdm' → BinanceAdapter`

### 5. Add credentials to `.env`

```
OKX_API_KEY=your_key_here
OKX_SECRET_KEY=your_secret_here
OKX_TESTNET_API_KEY=your_testnet_key
OKX_TESTNET_SECRET_KEY=your_testnet_secret
```

### 6. Update `config.yaml`

```yaml
exchange:
  name: okx   # must match EXCHANGE_CONFIG key
bot:
  mode: paper  # paper uses testnet creds, live uses mainnet creds
```

## Testing

1. Write `tests/test_{name}_adapter.py` modeled on `tests/test_binance_adapter.py`
2. Test order type translation for all 5 normalized types (`market`, `limit`, `stop_market`, `stop_limit`, `trailing_stop`)
3. Test that `reduceOnly=True` is passed through for exit orders
4. Test that CCXT exceptions are caught and re-raised as `ExchangeError`
5. Test thread safety: concurrent `create_order` calls don't crash
6. Verify factory routing: `python -c "from app.trading.exchange.factory import create_exchange; print(create_exchange({'bot': {'mode': 'mock'}, 'exchange': {'name': 'okx'}}))"` — should fail gracefully in mock mode (mock doesn't use adapters)
7. Run `pytest tests/ -v` — all existing tests must still pass

## Documentation Impact

Consult `docs/INDEX.md` → "Code Path → Documentation File" table:

- `app/trading/exchange/` modified → update
  **`docs/08_execution_and_oms/exchange-adapters.md`** with the adapter,
  credentials, capabilities, and exchange-specific behavior
- `app/trading/exchange/factory.py` modified → document the new factory/config
  selection in the same adapter reference
- If `app/core/interfaces.py` changed → also update
  **`docs/02_architecture/`**
