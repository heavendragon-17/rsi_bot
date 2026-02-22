# Add a CEX Exchange (CCXT)

> Add a new centralized exchange supported by the CCXT library (e.g., OKX, Bybit, KuCoin).
> Reference implementation: `app/services/execution/cex/binance_adapter.py`

## Prerequisites

- Read `docs/architecture.md` — understand `IFuturesExchange` and the normalized order vocabulary
- Read `docs/live-bot.md` — understand exchange adapter section and exchange modes
- Verify the exchange is in CCXT: `python -c "import ccxt; print(ccxt.exchanges)"`

## Steps

### 1. Choose the CCXT class name and credential prefix

Check [CCXT docs](https://docs.ccxt.com/) for the exchange's futures class name (e.g., `okx`, `bybit`, `dydx`). Decide an env prefix (e.g., `OKX`, `BYBIT`). This becomes `{PREFIX}_API_KEY` / `{PREFIX}_SECRET_KEY`.

### 2. Register in EXCHANGE_CONFIG

File: `app/services/execution/exchange_factory.py`

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

File: `app/services/execution/cex/{name}_adapter.py`

Model on `app/services/execution/cex/binance_adapter.py`. The adapter must:

- **Implement `IFuturesExchange`** from `app/core/interfaces.py` — all 9 abstract methods:
  - `fetch_ohlcv`, `create_order`, `fetch_order`, `cancel_order` (from `IExchange`)
  - `set_leverage`, `fetch_positions`, `fetch_balance`, `fetch_open_orders`, `cancel_all_orders` (from `IFuturesExchange`)
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

File: `app/services/execution/exchange_factory.py`

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
6. Verify factory routing: `python -c "from app.services.execution.exchange_factory import create_exchange; print(create_exchange({'bot': {'mode': 'mock'}, 'exchange': {'name': 'okx'}}))"` — should fail gracefully in mock mode (mock doesn't use adapters)
7. Run `pytest tests/ -v` — all existing tests must still pass

## Documentation Impact

Consult `docs/INDEX.md` → "Code Path → Documentation File" table:

- `app/services/execution/cex/` modified → update **`docs/live-bot.md`**: add a row to the Exchange Adapters table for the new adapter, document any exchange-specific quirks
- `app/services/execution/exchange_factory.py` modified → update **`docs/live-bot.md`**: note the new `EXCHANGE_CONFIG` entry
- If `app/core/interfaces.py` was modified → also update **`docs/architecture.md`**
