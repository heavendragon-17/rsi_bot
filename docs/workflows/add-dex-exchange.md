# Add a DEX Exchange

> Add a new perpetual DEX using a custom SDK or REST API (not available in CCXT).
> Reference implementation: `app/services/execution/dex/lighter_adapter.py`

## Prerequisites

- Read `docs/architecture.md` — understand `IExchange` and order vocabulary
- Read `docs/live-bot.md` — understand exchange adapter section and DEX auto-discovery
- Read the DEX's own API/SDK documentation thoroughly before writing code
- Identify: Does the SDK use async? Does it use different symbol naming (e.g., `BTC-PERP` vs `BTC/USDT`)?

## Steps

### 1. Install the DEX SDK

Add to project dependencies. Test import in isolation first.

Use a try/except import guard so the server starts even without the SDK installed — fail only when the adapter is actually instantiated. See `app/services/execution/dex/lighter_adapter.py` for the pattern:

```python
try:
    from lighter_sdk import LighterClient
except ImportError:
    LighterClient = None  # Fail at __init__ time, not import time
```

### 2. Create the adapter file

File: `app/services/execution/dex/{name}_adapter.py`

**Naming convention is critical** — the factory auto-discovers based on it:
- Filename: `{name}_adapter.py` (lowercase, underscores) — e.g., `vertex_adapter.py`
- Class name: `{Name}Adapter` (first letter capitalized) — e.g., `VertexAdapter`
- Config value: `exchange.name: vertex` — matches `{name}` exactly

See `app/services/execution/exchange_factory.py` lines 63-88 (`_load_custom_adapter`) for the discovery logic.

Model on `app/services/execution/dex/lighter_adapter.py`. Required:

- **Implement ALL `IExchange` abstract methods** (9 methods from `app/core/interfaces.py`):
  - `fetch_ohlcv(symbol, timeframe, limit)`
  - `create_order(symbol, order_type, side, amount, price=None, params=None)`
  - `fetch_order(order_id, symbol)`
  - `cancel_order(order_id, symbol)`
  - `set_leverage(leverage, symbol)`
  - `fetch_positions(symbols=None)`
  - `fetch_balance(params=None)`
  - `fetch_open_orders(symbol=None)`
  - `cancel_all_orders(symbol)`
- **Map normalized order types** to the DEX's native types:
  - `market`, `limit`, `stop_market`, `stop_limit`, `trailing_stop`
  - All exits use `params={'reduceOnly': True}`
- **Map order status strings** to the set `PortfolioManager` expects: `open`, `closed`, `cancelled`
- **Bridge async SDKs**: If the SDK is async, use `asyncio.run()` per call — do NOT share an event loop across threads (see `lighter_adapter.py` pattern)
- **Catch SDK exceptions** and re-raise as `ExchangeError` hierarchy from `app/core/exceptions.py`
- **Load credentials** from environment variables (`os.getenv`)
- **Use `structlog.get_logger()`** for all logging (never `print()`)

### 3. No factory change needed

The factory auto-discovers `app/services/execution/dex/{name}_adapter.py` via `importlib.import_module`. No edit to `exchange_factory.py` is required.

Verify auto-discovery: set `exchange.name: {name}` in `config.yaml` and test the import path:
```python
python -c "from app.services.execution.exchange_factory import _load_custom_adapter; print(_load_custom_adapter('vertex', {}))"
```

### 4. Document required environment variables

Add a docstring at the top of the adapter file listing all required env vars:
```python
"""
Vertex Protocol adapter.

Required env vars:
  VERTEX_SECRET_KEY     — private key for signing
  VERTEX_ACCOUNT_INDEX  — subaccount index (default 0)
"""
```

Add them to `.env`:
```
VERTEX_SECRET_KEY=...
VERTEX_ACCOUNT_INDEX=0
```

### 5. Update `config.yaml`

```yaml
exchange:
  name: vertex   # must match {name} in dex/{name}_adapter.py
bot:
  mode: live     # or paper — adapter handles mode internally
```

## Testing

1. Write `tests/test_{name}_adapter.py`
2. Mock the SDK client — test all 9 `IExchange` methods with mocked responses
3. Test normalized order type → DEX-native translation for all 5 types
4. Test error mapping: SDK-specific exceptions → `ExchangeError` subclasses
5. Test async bridge if applicable: SDK async methods are callable synchronously
6. Test symbol normalization if the DEX uses a different format
7. Run `pytest tests/ -v` — all existing tests must still pass
8. Manual integration test against DEX testnet if available

## Documentation Impact

Consult `docs/INDEX.md` → "Code Path → Documentation File" table:

- New file in `app/services/execution/dex/` → update **`docs/live-bot.md`**: add the new adapter to the DEX Adapters section with its SDK source, required env vars, and any exchange-specific notes
- If `app/core/interfaces.py` was changed → also update **`docs/architecture.md`**
