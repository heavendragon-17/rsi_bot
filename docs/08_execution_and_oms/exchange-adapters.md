# Exchange Adapters

> All exchange adapter implementations: BinanceAdapter, MockExchange, PaperExchange, and DEX auto-discovery.

---

## BinanceAdapter (`app/services/execution/cex/binance_adapter.py`)

CCXT wrapper implementing `IFuturesExchange`. Used for `paper` and `live` modes.

### Thread Safety
Single `threading.Lock` on `self._lock` — all exchange API calls are serialized through this lock. `fetch_ticker()` is the only exception (not thread-critical).

### Symbol Normalization (`_to_external_symbol()`)

| Input | Output |
|-------|--------|
| `BTC/USDT:USDT` | `BTC/USDT:USDT` (unchanged) |
| `BTC/USDT` | `BTC/USDT:USDT` |
| `BTCUSDT` | `BTC/USDT:USDT` |

### Credential Loading

| Mode | Env Vars |
|------|----------|
| `paper` | `BINANCE_TESTNET_API_KEY`, `BINANCE_TESTNET_SECRET_KEY` |
| `live` | `BINANCE_API_KEY`, `BINANCE_SECRET_KEY` |

Paper mode calls `set_sandbox_mode(True)` to route to Binance testnet.

### Order Type Translation

| Normalized | Binance CCXT | Extra Params |
|------------|-------------|-------------|
| `market` | `MARKET` | — |
| `limit` | `LIMIT` | `timeInForce: GTC` |
| `stop_market` | `STOP_MARKET` | `stopPrice` from params |
| `stop_limit` | `STOP` | `stopPrice` from params |
| `trailing_stop` | `TRAILING_STOP_MARKET` | `callbackRate` from params |

### Exception Mapping

CCXT exceptions are caught and re-raised as custom types:

| CCXT Exception | Custom Exception |
|----------------|-----------------|
| `InsufficientFunds` | `InsufficientFundsError` |
| `InvalidOrder` | `OrderRejectedError` |
| `OrderNotFound` | `OrderNotFoundError` |
| `NetworkError` | `ConnectionError` |
| `RateLimitExceeded` | `RateLimitError` |

---

## MockExchange (`app/services/execution/mock_exchange.py`)

In-memory order simulation for backtesting. Implements `IFuturesExchange`.

### Behavior
- **Entry orders** (`market`): Instant fill at signal price
- **SL orders** (`stop_market`): Triggered when candle's low/high crosses `stopPrice`
- **TP orders** (`limit`): Triggered when candle's high/low crosses limit price
- **Fees**: taker 0.05%, maker 0.02% (applied to balance)
- **Leverage**: Applied to position sizing (notional = amount × price, margin = notional / leverage)

### Candle Update (`update_candle()`)
Each candle, MockExchange checks all pending orders against OHLC:
1. Check SL stop_market orders: triggered if wick crosses stopPrice
2. Check TP limit orders: triggered if wick crosses limit price
3. Process fills in order, update balance

### Key Differences from Live
- No slippage (fills at exact price)
- No partial fills (all-or-nothing)
- No rate limits
- No network latency

---

## PaperExchange (`app/paper/exchange.py`)

Tick-by-tick order simulation against live aggTrade data. Implements `IFuturesExchange`.

### Behavior
- **Entry**: Fill on kline open (not at signal price — simulates next-bar entry)
- **SL/TP**: Checked tick-by-tick against live aggTrade prices
- **Order queue**: FIFO — orders are checked in submission order
- **Fees**: taker 0.04%, maker 0.02%

### Use Case
Used in `sim` mode for realistic simulation against live market data without risking real funds.

---

## DEX Auto-Discovery

Custom DEX adapters are auto-discovered by the exchange factory via `importlib`:

```
app/services/execution/dex/{name}_adapter.py → class {Name}Adapter
```

**Convention**: `lighter` → `lighter_adapter.py` → `LighterAdapter`

No factory modification needed. The adapter just needs to:
1. Exist at the correct path with the correct class name
2. Implement `IFuturesExchange`
3. Accept `config` in constructor

### LighterAdapter (`app/services/execution/dex/lighter_adapter.py`)

Lighter DEX adapter using the Lighter SDK. Credentials via `LIGHTER_*` env vars. Supports testnet and mainnet via `LIGHTER_BASE_URL` or automatic URL selection based on `config.bot.mode`.

---

## Factory (`app/services/execution/exchange_factory.py`)

`create_exchange(config) → IFuturesExchange`

| Mode | Result |
|------|--------|
| `mock` | `MockExchange(initial_balance, leverage)` |
| `sim` | `PaperExchange(config)` |
| `paper` | `BinanceAdapter(config)` with sandbox mode |
| `live` | `BinanceAdapter(config)` on mainnet |

For non-standard exchange names (not in `EXCHANGE_CONFIG`), calls `_load_custom_adapter()` for DEX auto-discovery.
