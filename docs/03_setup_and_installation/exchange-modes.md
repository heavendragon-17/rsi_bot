# Exchange Modes

> Defines the four exchange modes (mock, sim, paper, live), how the factory selects the correct adapter, and the behavioral differences between each. An AI agent should consult this before modifying exchange adapters, the factory, or any mode-dependent logic.

---

## Mode Overview

| Mode | Adapter Class | Network | Credentials | Use Case |
|---|---|---|---|---|
| `mock` | `MockExchange` | None | None | Backtesting with historical data (in-memory simulation) |
| `sim` | `PaperExchange` | Live Binance WebSocket (read-only) | None | Local order simulation against live aggTrade tick data |
| `paper` | `BinanceAdapter` (testnet) | Binance Testnet API | `BINANCE_TESTNET_*` | Integration testing with real exchange API, fake money |
| `live` | `BinanceAdapter` (mainnet) | Binance Mainnet API | `BINANCE_*` | Production trading with real money |

### Switching Modes

Change `bot.mode` in `config.yaml`:

```yaml
bot:
    mode: 'paper'   # mock | sim | paper | live
```

No other code changes are needed. The factory pattern handles adapter selection automatically.

---

## Factory Pattern

**File:** `app/trading/exchange/factory.py`

**Entry point:** `create_exchange(config: Dict) -> IExchange`

The factory reads `bot.mode` and `exchange.name` from the config dict and returns the appropriate adapter. All adapters implement `IExchange` so the rest of the system (PortfolioManager, strategies, etc.) is exchange-agnostic.

### Selection Logic

```
bot.mode == "mock"
    → MockExchange(initial_balance, leverage)

bot.mode == "sim"
    → PaperExchange(config)

bot.mode in ("paper", "live") AND exchange.name in ("binanceusdm", "binance")
    → BinanceAdapter(config)

bot.mode in ("paper", "live") AND exchange.name not in EXCHANGE_CONFIG
    → _load_custom_adapter(exchange_name, config)  # DEX auto-discovery
```

### CCXT Exchange Registry

The factory maintains `EXCHANGE_CONFIG` mapping config names to CCXT class names:

```python
EXCHANGE_CONFIG = {
    'binanceusdm': {'ccxt_class': 'binanceusdm', 'env_prefix': 'BINANCE'},
    'binance':     {'ccxt_class': 'binanceusdm', 'env_prefix': 'BINANCE'},
}
```

Both `binanceusdm` and `binance` resolve to the same CCXT class (`binanceusdm`) and credential prefix (`BINANCE`).

---

## DEX Auto-Discovery

For exchanges not in the CCXT registry (e.g., Lighter, Hyperliquid), the factory uses dynamic module loading via `importlib`.

**Convention:**
- Module path: `app/trading/exchange/{name}_adapter.py`
- Class name: `{Name}Adapter` (first letter capitalized)

**Examples:**
- `lighter` resolves to `app.trading.exchange.lighter_adapter.LighterAdapter`
- `hyperliquid` resolves to `app.trading.exchange.hyperliquid_adapter.HyperliquidAdapter`

**To add a new DEX:**

1. Create `app/trading/exchange/{name}_adapter.py`.
2. Define class `{Name}Adapter` implementing `IExchange`.
3. Set `exchange.name: '{name}'` in `config.yaml`.
4. No changes to `factory.py` are needed.

The factory calls `_load_custom_adapter(exchange_name, config)` which will:
- `importlib.import_module(f"app.trading.exchange.{exchange_name}_adapter")`
- `getattr(module, f"{exchange_name.capitalize()}Adapter")`
- Instantiate with `adapter_class(config)`

Raises `ValueError` if the module or class cannot be found.

---

## FillSimulator

**File:** `app/trading/exchange/fill_simulator.py`

**Purpose:** Unified fill simulation logic shared across MockExchange and PaperExchange. Uses the `FillMode` ABC pattern to support different fill strategies.

### Fill Modes

| Mode | Class | Used By | Description |
|------|-------|---------|-------------|
| Wick fill | `WickFillMode` | `MockExchange` (backtest) | Checks pending orders against candle high/low wicks |
| Tick fill | `TickFillMode` | `PaperExchange` (sim) | Checks pending orders against individual tick prices |

The `FillSimulator` accepts a `FillMode` instance at construction, decoupling the trigger logic from the order management logic. Both modes share the same order execution and state update code.

---

## MockExchange (mock mode)

**File:** `app/backtest/mock_exchange.py`

**Purpose:** In-memory futures exchange simulator for backtesting. No network calls, no credentials.

### Key Characteristics

- **Instant market fills:** Market orders fill immediately at the signal price (or current price if no price specified).
- **Pending order types:** Supports `limit`, `stop_market`, `stop_limit`, and `trailing_stop` as pending orders checked on each candle update.
- **Candle-based trigger:** `update_candle(symbol, open, high, low, close, timestamp)` checks all pending orders against the candle's high/low wicks.
- **Trigger logic:**
  - `limit` SELL (TP): triggers when `high >= price`
  - `stop_market` SELL (SL): triggers when `low <= stopPrice`
  - `limit` BUY: triggers when `low <= price`
  - `stop_market` BUY: triggers when `high >= stopPrice`
  - `trailing_stop`: tracks peak price, triggers when price drops by `callbackRate%` from peak
- **Leverage support:** Margin-based position sizing. `margin = notional / leverage`.
- **Fee support:** Configurable `maker_fee` and `taker_fee` rates (default: 0.0 for backtesting; the backtest engine sets these explicitly).
- **reduceOnly enforcement:** Sell orders with `reduceOnly=True` are capped at current position size; skipped if no position exists.
- **Thread-safe:** All state access is protected by `threading.RLock()`.
- **CCXT-compliant output:** Order and position dicts follow CCXT structure for compatibility.

### Construction

```python
MockExchange(initial_balance=1000.0, leverage=1, maker_fee=0.0, taker_fee=0.0)
```

Created by the factory as:

```python
MockExchange(
    initial_balance=config["backtest"]["initial_balance"],
    leverage=config["risk"]["leverage"]
)
```

---

## PaperExchange (sim mode)

**File:** `app/trading/exchange/sim/paper_exchange.py`

**Purpose:** Local order simulation against live Binance aggTrade WebSocket data. Behaves identically to BinanceAdapter from PortfolioManager's perspective.

### Key Characteristics

- **Live tick data:** Subscribes to Binance aggTrade streams (read-only, no API keys needed).
- **Tick-by-tick SL/TP checking:** Unlike MockExchange which checks on candle close, PaperExchange evaluates pending orders on every tick for higher fidelity.
- **Entry fill on kline open:** Market entry orders get `status=pending_open` and fill at the next kline open price via `on_kline_open()`.
- **Realistic fees:** Applies `TAKER_FEE = 0.05%` and `MAKER_FEE = 0.02%`.
- **State management:** Uses `PaperTradeState` (defined in `app/trading/exchange/sim/state.py`) with typed dataclasses (`PaperOrder`, `PaperPosition`, `ClosedTrade`).
- **Notifications:** Initializes `PaperTelegramNotifier` and a `NotificationWorker` for real-time trade alerts. Can be silenced via `silence_notifications()` for replay mode.
- **Thread-safe:** Protected via `PaperTradeState.lock`.

### Order Lifecycle

```
Entry (market, no reduceOnly):
    create_order() -> status=pending_open
    on_kline_open(symbol, open_price) -> _execute_fill(order, open_price)

SL (stop_market, reduceOnly=True):
    create_order() -> status=pending
    on_tick(price <= stop_price) -> _execute_fill(order, stop_price)

TP (limit, reduceOnly=True):
    create_order() -> status=pending
    on_tick(price >= limit_price) -> _execute_fill(order, limit_price)

Soft SL (market, reduceOnly=True):
    create_order() -> fills immediately at current tick price
```

### Construction

```python
PaperExchange(config)  # receives the full config dict
```

Reads `paper_sim.initial_balance` from config. Telegram override credentials (`PAPER_TELEGRAM_BOT_TOKEN`, `PAPER_TELEGRAM_CHAT_ID`) are read from `.env` by `PaperTelegramNotifier`.

### Configurable Parameters

| Parameter | YAML Path | Default | Purpose |
|---|---|---|---|
| `initial_balance` | `paper_sim.initial_balance` | `10000` | Starting USDT balance |
| `tick_sample_interval_ms` | `paper_sim.tick_sample_interval_ms` | `500` | aggTrade sampling rate (ms) |

---

## BinanceAdapter (paper and live modes)

**File:** `app/trading/exchange/binance_adapter.py`

**Purpose:** Production exchange adapter wrapping CCXT `binanceusdm`. Used for both paper (testnet) and live (mainnet) trading.

### Key Characteristics

- **CCXT wrapper:** Instantiates `ccxt.binanceusdm` with API credentials and rate limiting enabled.
- **Paper mode:** Calls `self._exchange.set_sandbox_mode(True)` to route all API calls to Binance Testnet.
- **Live mode:** Connects to Binance Mainnet. Logs a prominent warning: `WARNING: RUNNING IN LIVE TRADING MODE - REAL MONEY AT RISK`.
- **Normalized order types:** Translates the internal order vocabulary (`market`, `limit`, `stop_market`, `stop_limit`, `trailing_stop`) to Binance-native API parameters (e.g., `stop_market` becomes `STOP_MARKET` with `stopPrice` param).
- **Symbol normalization:** Converts `BTC/USDT` to CCXT futures format `BTC/USDT:USDT` via `_to_external_symbol()`.
- **Credential loading:** Reads from `.env` based on mode:
  - Paper: `BINANCE_TESTNET_API_KEY`, `BINANCE_TESTNET_SECRET_KEY`
  - Live: `BINANCE_API_KEY`, `BINANCE_SECRET_KEY`
- **Thread-safe:** Protected by `threading.Lock()`.
- **Market loading:** Calls `self._exchange.load_markets()` at construction to fetch symbol metadata (precision, limits, etc.).

### Construction

```python
BinanceAdapter(config)  # receives the full config dict
```

The factory creates it identically for both paper and live modes. The mode is read from `config["bot"]["mode"]` internally.

---

## Recommended Progression Path

When developing or validating a new strategy, follow this progression:

```
mock -> sim -> paper -> live
```

1. **mock** -- Run backtests against historical CSV data. Fast iteration, deterministic results. No network dependencies.
2. **sim** -- Run against live tick data locally. Validates that the strategy works with real-time price feeds and realistic fill simulation. No API keys needed.
3. **paper** -- Execute real orders on Binance Testnet. Tests the full order lifecycle including exchange API interactions, rate limits, and order book behavior. Uses testnet (fake) funds.
4. **live** -- Production deployment with real money. Only after thorough validation in all prior modes.

---

## Common Pitfalls

### Using mainnet keys in paper mode

Paper mode explicitly reads `BINANCE_TESTNET_*` environment variables. If these are not set, it raises `RuntimeError`. It will never accidentally use mainnet keys. Conversely, live mode reads `BINANCE_*` variables and raises if they are missing.

### Missing testnet credentials

Paper mode requires both `BINANCE_TESTNET_API_KEY` and `BINANCE_TESTNET_SECRET_KEY` in `.env`. Obtain these from the Binance Testnet portal (testnet.binancefuture.com). The error message is explicit:

```
RuntimeError: Paper mode requires BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_SECRET_KEY in .env
```

### Mode "testnet" vs "paper"

The `ExchangeConfig` validation accepts both `testnet` and `paper` as valid modes. In the factory, only `paper` is explicitly handled for CCXT exchanges. If using `testnet`, verify the factory code path handles it correctly (currently it would fall through to the CCXT/DEX branch since it is not `mock` or `sim`).

### Leverage duplication

`leverage` appears in both `ExchangeConfig` and `RiskConfig`. Both are populated from `risk.leverage` in YAML. When modifying leverage handling, update both references.

### DEX adapter class naming

The auto-discovery convention requires exact naming: module `{name}_adapter.py` with class `{Name}Adapter` where `Name` has only the first letter capitalized (via `str.capitalize()`). For example, `hyperliquid` becomes `HyperliquidAdapter`, not `HyperLiquidAdapter`.
