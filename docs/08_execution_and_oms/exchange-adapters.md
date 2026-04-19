# Exchange Adapters

> All exchange adapter implementations: BinanceAdapter, MockExchange, PaperExchange, and DEX auto-discovery.

---

## BinanceAdapter (`app/trading/exchange/binance_adapter.py`)

CCXT wrapper implementing `IExchange`. Used for `paper` and `live` modes.

### Thread Safety

Single `threading.Lock` on `self._lock` — all exchange API calls are serialized through this lock. `fetch_ticker()` is the only exception (not thread-critical).

### Symbol Normalization (`_to_external_symbol()`)

| Input           | Output                      |
| --------------- | --------------------------- |
| `BTC/USDT:USDT` | `BTC/USDT:USDT` (unchanged) |
| `BTC/USDT`      | `BTC/USDT:USDT`             |
| `BTCUSDT`       | `BTC/USDT:USDT`             |

### Credential Loading

| Mode    | Env Vars                                                |
| ------- | ------------------------------------------------------- |
| `paper` | `BINANCE_TESTNET_API_KEY`, `BINANCE_TESTNET_SECRET_KEY` |
| `live`  | `BINANCE_API_KEY`, `BINANCE_SECRET_KEY`                 |

Paper mode calls `set_sandbox_mode(True)` to route to Binance testnet.

### Order Type Translation

| Normalized      | Binance CCXT           | Extra Params               |
| --------------- | ---------------------- | -------------------------- |
| `market`        | `MARKET`               | —                          |
| `limit`         | `LIMIT`                | `timeInForce: GTC`         |
| `stop_market`   | `STOP_MARKET`          | `stopPrice` from params    |
| `stop_limit`    | `STOP`                 | `stopPrice` from params    |
| `trailing_stop` | `TRAILING_STOP_MARKET` | `callbackRate` from params |

### Exception Mapping

CCXT exceptions are caught and re-raised as custom types:

| CCXT Exception      | Custom Exception         |
| ------------------- | ------------------------ |
| `InsufficientFunds` | `InsufficientFundsError` |
| `InvalidOrder`      | `OrderRejectedError`     |
| `OrderNotFound`     | `OrderNotFoundError`     |
| `NetworkError`      | `ConnectionError`        |
| `RateLimitExceeded` | `RateLimitError`         |

---

## MockExchange (`app/backtest/exchange/mock_exchange.py`)

In-memory order simulation for backtesting. Implements `IExchange`.

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

## FillSimulator (`app/trading/exchange/fill_simulator.py`)

Shared fill simulation logic used by both MockExchange (backtest) and SimExchange (sim mode). Provides two fill modes:

- **WickFillMode**: Used by MockExchange — checks if a candle's OHLC wick crosses the order's trigger price.
- **TickFillMode**: Used by SimExchange — checks tick-by-tick against live aggTrade prices.

This avoids duplicating fill logic across exchange implementations.

---

## PaperExchange (`app/trading/exchange/sim/sim_exchange.py`)

Tick-by-tick order simulation against live aggTrade data. Implements `IExchange`.

### Behavior

- **Entry**: Fill on kline open (not at signal price — simulates next-bar entry)
- **SL/TP**: Checked tick-by-tick against live aggTrade prices
- **Order queue**: FIFO — orders are checked in submission order
- **Fees**: taker 0.04%, maker 0.02%
- **Safety guards**:
  - `create_order` rejects any amount ≤ 0.
  - Once `state.is_paused` is set, only `reduceOnly` orders are accepted
    (no new entries).
- **Liquidation** (`app/trading/exchange/sim/sim_liquidation.py`):
  - After each tick, equity = `balance + Σ uPnL` is checked against 0.
  - If equity ≤ 0, every open position is force-closed at the current tick
    price, balance is zeroed, and `is_paused` is set. Pending orders for the
    closed symbols are cancelled. A `LIQUIDATION` fill notification is emitted
    per position. Mirrors the backtest `check_liquidation` so sim can't report
    an impossible negative balance.

### Exit-reason taxonomy reported by sim

Fill reasons emitted via `on_fill`:

| Reason         | Triggered by                                                            |
| -------------- | ----------------------------------------------------------------------- |
| `HARD_SL`      | Original stop_market order fires.                                       |
| `MOVED_SL`     | A replacement stop_market (lock-profit / trailing) fires.              |
| `CANDLE_SL`    | `market + reduceOnly` sent by a candle-close SL signal.                 |
| `TP1/2/3`      | `limit + reduceOnly` TP fills, in order of SL order IDs on the position.|
| `LIQUIDATION`  | `sim_liquidation.check_liquidation` force-close.                        |

`HARD_SL` is distinguished from `MOVED_SL` via `SimPosition.moved_sl`, which
flips `True` the first time `link_sl_to_position` sees a new order id
replacing an existing one. The strategy only moves the stop to a lock-profit
level, so `MOVED_SL` exits are always at-or-above entry by construction — no
separate "profit" label is needed.

### R-multiple and Net P&L accuracy

`link_sl_to_position` computes `initial_risk = |entry − soft_sl| × amount`
where `soft_sl` is the level used for position sizing (passed via
`params["soft_sl_price"]` on the stop_market order). This is the *risk-sizing*
SL, not the wider disaster stop, so reported R-multiples match the configured
`risk_per_trade_pct`.

`close_position_locked` pro-rates `position.entry_fee` for partial closes and
subtracts both the pro-rated entry fee and the exit fee from the reported
`pnl_net`. Balance accounting is unchanged: the entry fee was debited at open,
and balance only changes by `(gross − exit_fee)` at close — so the *displayed*
Net P&L equals the true lifecycle account change across the trade.

### Use Case

Used in `sim` mode for realistic simulation against live market data without risking real funds.

---

## DEX Auto-Discovery

Custom DEX adapters are auto-discovered by the exchange factory via `importlib`:

```
app/trading/exchange/{name}_adapter.py → class {Name}Adapter
```

**Convention**: `lighter` → `lighter_adapter.py` → `LighterAdapter`

No factory modification needed. The adapter just needs to:

1. Exist at the correct path with the correct class name
2. Implement `IExchange`
3. Accept `config` in constructor

### LighterAdapter (`app/trading/exchange/lighter_adapter.py`)

Lighter DEX adapter using the Lighter SDK. Credentials via `LIGHTER_*` env vars. Supports testnet and mainnet via `LIGHTER_BASE_URL` or automatic URL selection based on `config.bot.mode`.

### HyperliquidAdapter (`app/trading/exchange/hyperliquid_adapter.py`)

Hyperliquid DEX adapter built via CCXT. Treats Hyperliquid as a DEX module. Credentials via `HYPERLIQUID_WALLET_ADDRESS` and `HYPERLIQUID_PRIVATE_KEY` env vars. Explicitly rejects `trailing_stop` orders as they are unsupported natively by CCXT for this exchange.

---

## Factory (`app/trading/exchange/factory.py`)

`create_exchange(config) → IExchange`

| Mode    | Result                                     |
| ------- | ------------------------------------------ |
| `mock`  | `MockExchange(initial_balance, leverage)`  |
| `sim`   | `PaperExchange(config)`                    |
| `paper` | `BinanceAdapter(config)` with sandbox mode |
| `live`  | `BinanceAdapter(config)` on mainnet        |

For non-standard exchange names (not in `EXCHANGE_CONFIG`), calls `_load_custom_adapter()` for DEX auto-discovery.
