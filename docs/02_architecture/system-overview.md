# System Overview

> Comprehensive architecture specification for the RSI bot system. Read this first before diving into domain-specific specs. This document covers the two subsystems, the clean 3-layer interface architecture, exchange modes, order vocabulary, exception hierarchy, logging, financial precision, and configuration.

---

## Table of Contents

- [Two-Subsystem Architecture](#two-subsystem-architecture)
- [Tech Stack](#tech-stack)
- [Clean 3-Layer Architecture](#clean-3-layer-architecture)
- [Exchange Modes](#exchange-modes)
- [Exchange Factory Pattern](#exchange-factory-pattern)
- [Order Vocabulary](#order-vocabulary)
- [Custom Exception Hierarchy](#custom-exception-hierarchy)
- [Structured Logging](#structured-logging)
- [Financial Precision Rules](#financial-precision-rules)
- [Configuration System](#configuration-system)

---

## Two-Subsystem Architecture

The RSI bot is composed of two independent subsystems that share a common core library (`app/core/`). They never run simultaneously in the same process.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                             RSI Bot System                                   │
│                                                                              │
│   Shared Core: app/core/ (interfaces, events, snapshots, actions, config)    │
│                                                                              │
├──────────────────────────────────┬───────────────────────────────────────────┤
│         LIVE BOT                 │         BACKTEST UI                       │
│         (main.py)                │         (ui/ + app/api/)                  │
│                                  │                                           │
│  ┌────────────────────────┐      │  ┌─────────────────────────────────┐      │
│  │ BinanceStreamManager   │      │  │ React 18 + TypeScript Frontend │      │
│  │ (WebSocket daemon)     │      │  │ (Zustand, Tailwind, shadcn/ui) │      │
│  └──────────┬─────────────┘      │  └──────────────┬──────────────────┘      │
│             │ Candle events      │                  │ HTTP REST + SSE        │
│             v                    │                  v                        │
│  ┌────────────────────────┐      │  ┌─────────────────────────────────┐      │
│  │ MarketDataStore        │      │  │ FastAPI Backend                 │      │
│  │ (thread-safe, in-mem)  │      │  │ (app/api/main.py)              │      │
│  └──────────┬─────────────┘      │  └──────────────┬──────────────────┘      │
│             │ DataFrame          │                  │ submit_backtest()      │
│             v                    │                  v                        │
│  ┌────────────────────────┐      │  ┌─────────────────────────────────┐      │
│  │ Strategy.analyze()     │      │  │ ThreadPoolExecutor              │      │
│  │ (per-symbol thread)    │      │  │ (max_workers=2)                 │      │
│  └──────────┬─────────────┘      │  └──────────────┬──────────────────┘      │
│             │ Actions            │                  │ BacktestEngine.run()   │
│             v                    │                  v                        │
│  ┌────────────────────────┐      │  ┌─────────────────────────────────┐      │
│  │ PortfolioManager       │      │  │ MockExchange (in-memory sim)    │      │
│  │ -> BinanceAdapter      │      │  │ -> SQLite results storage       │      │
│  │ -> Telegram alerts     │      │  │ -> SSE progress streaming       │      │
│  └────────────────────────┘      │  └─────────────────────────────────┘      │
│                                  │                                           │
│  Runs on: local machine / VPS   │  Runs on: local machine (dev only)        │
│  Entry: python main.py          │  Entry: uvicorn + npm run dev             │
└──────────────────────────────────┴───────────────────────────────────────────┘
```

### Live Bot Data Flow (simplified)

```
WebSocket (fstream.binance.com)
  -> BinanceStreamManager.on_message()
    -> DataNormalizer.normalize_binance() -> MarketEvent(Candle)
      -> MarketDataStore.update_candle()
        -> Per-symbol thread reads DataFrame
          -> Strategy.analyze(symbol, df, position, context) -> AnalysisResult
            -> Runner dispatches Actions:
               OpenPosition  -> portfolio.on_signal(_action_to_signal(action))
               ClosePosition -> portfolio.close_position(symbol, reason, price)
               MoveSL        -> portfolio.move_stop_loss(symbol, new_sl_price)
               PartialClose  -> portfolio.execute_partial_close(symbol, tp_level)
               DoNothing     -> (no-op)
```

### Backtest UI Data Flow (simplified)

```
React UI (Zustand store)
  -> POST /api/backtest/run (FastAPI)
    -> submit_backtest(run_id, fn) -> ThreadPoolExecutor
      -> BacktestEngine.run(on_progress=callback)
        -> MockExchange (in-memory order matching)
        -> on_progress(data) -> asyncio.Queue via loop.call_soon_threadsafe
          -> SSE generator yields events to frontend
            -> Frontend updates progress bar + results display
```

---

## Tech Stack

| Layer | Live Bot | Backtest UI |
|-------|----------|-------------|
| **Language** | Python 3.13 | Python 3.13 (backend), TypeScript (frontend) |
| **Frontend** | -- | React 18, Zustand (state), Tailwind CSS, shadcn/ui |
| **Backend Framework** | -- | FastAPI, SQLAlchemy ORM |
| **Database** | -- | SQLite (`data/backtest.db`) |
| **Real-time Streaming** | Binance WebSocket (`fstream.binance.com`) | Server-Sent Events (SSE) |
| **Charts** | -- | TradingView Lightweight Charts v5, Recharts |
| **Exchange Library** | CCXT (`binanceusdm`) | MockExchange (in-memory simulation) |
| **Concurrency** | `threading` (1 stream daemon + N symbol daemons) | `ThreadPoolExecutor` (max_workers=2) |
| **Build** | -- | Vite (frontend), pip/conda (backend) |
| **Logging** | structlog (JSON or console) | structlog (JSON or console) |
| **Config** | `config.yaml` -> `AppConfig` dataclass | `config.yaml` -> `AppConfig` dataclass |
| **Notifications** | Telegram Bot API | -- |
| **Testing** | pytest | pytest |

---

## Clean 3-Layer Architecture

All interfaces are defined in `app/core/interfaces.py`. Each layer only depends on the layer above it. Implementations are injected via constructors (no global singletons).

```
┌──────────────────────────────────────────────────────────────────┐
│ Layer 1: Data Ingestion                                          │
│                                                                  │
│  IDataProvider                    IDataStore                     │
│  ├─ subscribe(symbols)           ├─ update_candle(candle)       │
│  └─ unsubscribe(symbols)        └─ get_dataframe(symbol) -> df │
│                                                                  │
│  Implementations:                 Implementations:               │
│  - BinanceStreamManager          - MarketDataStore               │
├──────────────────────────────────────────────────────────────────┤
│ Layer 2: Core Logic                                              │
│                                                                  │
│  IIndicators                      IStrategy                      │
│  ├─ compute(df) -> df            └─ analyze(symbol, df,         │
│  ├─ get_mode(df) -> str              position, context)         │
│  ├─ check_wma_retest(df,dist)        -> AnalysisResult          │
│  └─ calculate_price_at_rsi(                                     │
│         df, target_rsi)                                          │
│      -> Decimal                                                  │
│                                                                  │
│  Implementations:                 Implementations:               │
│  - Indicators                    - RsiNoRetestStrategy           │
├──────────────────────────────────────────────────────────────────┤
│ Layer 3: Execution                                               │
│                                                                  │
│  IExchange                        IPortfolio                     │
│  ├─ fetch_ohlcv(sym,tf,limit)    ├─ on_signal(signal)          │
│  ├─ create_order(sym,type,       ├─ has_position(symbol)        │
│  │   side,amount,price,params)   └─ close_position(sym,pct)    │
│  ├─ fetch_order(id,sym)                                         │
│  └─ cancel_order(id,sym)         Implementations:               │
│                                   - PortfolioManager             │
│  IFuturesExchange (extends                                       │
│    IExchange)                                                    │
│  ├─ set_leverage(lev,sym)                                       │
│  ├─ fetch_positions(symbols?)                                   │
│  ├─ fetch_balance(params?)                                      │
│  ├─ fetch_open_orders(sym?)                                     │
│  └─ cancel_all_orders(sym)                                      │
│                                                                  │
│  Implementations:                                                │
│  - BinanceAdapter (paper/live)                                   │
│  - MockExchange (backtest)                                       │
│  - PaperExchange (sim)                                           │
│  - Custom DEX adapters (auto-discovered)                         │
└──────────────────────────────────────────────────────────────────┘
```

### Interface Method Reference

#### IDataProvider (`app/core/interfaces.py`)

| Method | Signature | Description |
|--------|-----------|-------------|
| `subscribe` | `(symbols: List[str]) -> None` | Subscribe to market data streams for given symbols |
| `unsubscribe` | `(symbols: List[str]) -> None` | Unsubscribe from market data streams |

#### IDataStore (`app/core/interfaces.py`)

| Method | Signature | Description |
|--------|-----------|-------------|
| `update_candle` | `(candle: Candle) -> None` | Update existing candle or append new one |
| `get_dataframe` | `(symbol: str) -> Optional[pd.DataFrame]` | Get candle data as DataFrame (returns copy) |

#### IIndicators (`app/core/interfaces.py`)

| Method | Signature | Description |
|--------|-----------|-------------|
| `compute` | `(df: pd.DataFrame, **kwargs) -> pd.DataFrame` | Compute all indicators, return DataFrame with new columns |
| `get_mode` | `(df: pd.DataFrame) -> str` | Get current market mode (`"BULLISH"`, `"NEUTRAL"`) |
| `check_wma_retest` | `(df: pd.DataFrame, distance: float) -> bool` | Check if RSI is retesting WMA45 within distance threshold |
| `calculate_price_at_rsi` | `(df: pd.DataFrame, target_rsi: float) -> Decimal` | Calculate the price level that would produce a target RSI value |

#### IStrategy (`app/core/interfaces.py`)

| Method | Signature | Description |
|--------|-----------|-------------|
| `analyze` | `(symbol: str, df: pd.DataFrame, position: Optional[PositionSnapshot], context: Optional[ContextSnapshot]) -> AnalysisResult` | Pure analysis function. Returns typed actions and new context to store. Strategy never mutates state directly. |

#### IExchange (`app/core/interfaces.py`)

| Method | Signature | Description |
|--------|-----------|-------------|
| `fetch_ohlcv` | `(symbol: str, timeframe: str, limit: int) -> Sequence[Sequence[Any]]` | Fetch historical OHLCV candles. Returns `[[ts_ms, o, h, l, c, v], ...]` |
| `create_order` | `(symbol, order_type, side, amount, price?, params?) -> Optional[Dict]` | Create order using normalized types. Adapter translates to exchange-native format |
| `fetch_order` | `(order_id: str, symbol: str) -> Dict[str, Any]` | Fetch order status by ID |
| `cancel_order` | `(order_id: str, symbol: str) -> bool` | Cancel an open order |

#### IFuturesExchange (extends IExchange) (`app/core/interfaces.py`)

| Method | Signature | Description |
|--------|-----------|-------------|
| `set_leverage` | `(leverage: int, symbol: str) -> bool` | Set leverage for a symbol |
| `fetch_positions` | `(symbols: Optional[List[str]]) -> List[Dict]` | Fetch open positions (filters zero-size) |
| `fetch_balance` | `(params: Optional[Dict]) -> Dict` | Fetch balance in CCXT format |
| `fetch_open_orders` | `(symbol: Optional[str]) -> List[Dict[str, Any]]` | Fetch all open/pending orders for a symbol |
| `cancel_all_orders` | `(symbol: str) -> int` | Cancel all open orders for a symbol. Returns count cancelled |

#### IPortfolio (`app/core/interfaces.py`)

| Method | Signature | Description |
|--------|-----------|-------------|
| `on_signal` | `(signal: SignalEvent) -> None` | Process a trading signal (entry) |
| `has_position` | `(symbol: str) -> bool` | Check if there is an open position for symbol |
| `close_position` | `(symbol: str, percentage: Decimal) -> None` | Close percentage of position (0.0 - 1.0) |

---

## Exchange Modes

Four distinct modes control which adapter is instantiated and which network it connects to.

| Mode | Adapter Class | Network | Credentials (env vars) | Real Money? | Use Case |
|------|---------------|---------|------------------------|-------------|----------|
| `mock` | `MockExchange` | None (in-memory) | None required | No | Backtesting. No network calls. Historical data only. |
| `sim` | `PaperExchange` | Binance mainnet (read-only aggTrade stream) | None required (public data) | No | Local order simulation against live market data. Fills orders at realistic prices using aggTrade ticks. |
| `paper` | `BinanceAdapter` (testnet) | Binance Futures Testnet | `BINANCE_TESTNET_API_KEY`, `BINANCE_TESTNET_SECRET_KEY` | No | Integration testing against real exchange testnet. Real order book, test funds. |
| `live` | `BinanceAdapter` (mainnet) | Binance Futures Mainnet | `BINANCE_API_KEY`, `BINANCE_SECRET_KEY` | **YES** | Production trading with real money. Factory logs prominent warning. |

### Mode Selection

Mode is set in `config.yaml` under `bot.mode`:

```yaml
bot:
  mode: paper  # mock | sim | paper | live
```

The factory reads `config["bot"]["mode"]` and instantiates the appropriate adapter.

---

## Exchange Factory Pattern

**File**: `app/services/execution/exchange_factory.py`

The factory function `create_exchange(config) -> IFuturesExchange` selects the adapter based on mode and exchange name.

### Resolution Order

```
1. mode == "sim"?    -> PaperExchange(config)
2. mode == "mock"?   -> MockExchange(initial_balance, leverage)
3. exchange_name in EXCHANGE_CONFIG (binanceusdm, binance)?
   -> BinanceAdapter(config)  [paper or live based on mode]
4. Otherwise -> _load_custom_adapter(exchange_name, config)
   Auto-discovers DEX adapter via importlib
```

### Custom DEX Auto-Discovery

To add a new DEX exchange (e.g., Hyperliquid, Lighter):

1. Create `app/services/execution/dex/{name}_adapter.py`
2. Define class `{Name}Adapter` (first letter capitalized)
3. The factory calls `importlib.import_module(f"app.services.execution.dex.{name}_adapter")` and instantiates `{Name}Adapter(config)`

No code changes to the factory are required. The naming convention is:

| Exchange Name (in config) | Module Path | Class Name |
|---------------------------|-------------|------------|
| `lighter` | `app.services.execution.dex.lighter_adapter` | `LighterAdapter` |
| `hyperliquid` | `app.services.execution.dex.hyperliquid_adapter` | `HyperliquidAdapter` |

### CCXT Exchange Mapping

```python
EXCHANGE_CONFIG = {
    'binanceusdm': {'ccxt_class': 'binanceusdm', 'env_prefix': 'BINANCE'},
    'binance':     {'ccxt_class': 'binanceusdm', 'env_prefix': 'BINANCE'},
}
```

Both `binanceusdm` and `binance` map to the same CCXT class (`binanceusdm` for USDT-M perpetual futures).

---

## Order Vocabulary

All order types are normalized across every exchange adapter. The adapter translates these to exchange-native formats.

| Normalized Type | CCXT/Binance Translation | Usage | `params` Required | `reduceOnly` |
|-----------------|--------------------------|-------|-------------------|--------------|
| `market` | `MARKET` | Entry orders, emergency exits | -- | No for entry, Yes for exit |
| `limit` | `LIMIT` (+ `timeInForce=GTC`) | Take-profit orders | -- | Yes (`reduceOnly=True`) |
| `stop_market` | `STOP_MARKET` (+ `stopPrice`) | Hard/disaster stop loss | `{"stopPrice": <price>, "reduceOnly": True}` | Yes |
| `stop_limit` | `STOP` (+ `stopPrice`) | Reserved for future use | `{"stopPrice": <price>}` | Depends |
| `trailing_stop` | `TRAILING_STOP_MARKET` (+ `callbackRate`) | Reserved for future use | `{"callbackRate": <pct>}` | Depends |

### Order Type Translation Examples

**Entry (market buy)**:
```python
exchange.create_order(
    symbol="BTC/USDT",
    order_type="market",
    side="BUY",
    amount=Decimal("0.001"),
)
```

**Take-profit (limit sell with reduceOnly)**:
```python
exchange.create_order(
    symbol="BTC/USDT",
    order_type="limit",
    side="SELL",
    amount=Decimal("0.001"),
    price=Decimal("105000"),
    params={"reduceOnly": True},
)
```

**Stop loss (stop_market with reduceOnly)**:
```python
exchange.create_order(
    symbol="BTC/USDT",
    order_type="stop_market",
    side="SELL",
    amount=Decimal("0.001"),
    params={"stopPrice": Decimal("95000"), "reduceOnly": True},
)
```

### Key Rules

- **All exit orders MUST use `reduceOnly=True`** in params. This prevents accidental position reversal.
- SL orders are always `stop_market`, never `limit`. A limit SL can be skipped in fast markets.
- TP orders are always `limit` with `reduceOnly=True`.
- Entry orders are always `market` (immediate fill at best available price).

---

## Custom Exception Hierarchy

**File**: `app/core/exceptions.py`

Each exchange adapter catches its library-specific errors (e.g., CCXT exceptions) and re-raises them as these application-level exceptions. This ensures the portfolio layer never needs to know which exchange library is in use.

```
Exception
└── ExchangeError                    # Base for all exchange errors
    │   Attributes: message (str), original (Exception | None)
    │
    ├── InsufficientFundsError       # Not enough balance/margin
    ├── OrderRejectedError           # Invalid params, symbol not found, etc.
    ├── OrderNotFoundError           # Order ID does not exist
    ├── ConnectionError              # Network/connection failure
    ├── RateLimitError               # Exchange rate limit exceeded
    └── PositionError                # Leverage, margin mode errors
```

### CCXT Exception Mapping (BinanceAdapter)

| CCXT Exception | Application Exception |
|----------------|----------------------|
| `ccxt.InsufficientFunds` | `InsufficientFundsError` |
| `ccxt.InvalidOrder` | `OrderRejectedError` |
| `ccxt.OrderNotFound` | `OrderNotFoundError` |
| `ccxt.RateLimitExceeded` | `RateLimitError` |
| `ccxt.NetworkError` | `ConnectionError` |
| `ccxt.BaseError` (catch-all) | `ExchangeError` |

All exceptions carry the `original` attribute containing the underlying library exception for debugging.

---

## Structured Logging

**File**: `app/core/logging.py`

All modules use `structlog`. Zero `print()` statements in production code.

### Setup

`setup_logging()` is called once at startup in `main.py`. It configures both structlog and stdlib `logging`.

```python
from app.core.logging import setup_logging
setup_logging(level="INFO", json_output=False)  # dev mode (colored console)
setup_logging(level="INFO", json_output=True)   # production (JSON lines)
```

### Output Destinations

- **Console** (`StreamHandler`): Always active.
- **File** (`FileHandler`): Always writes to `rsi_bot.log`.

### Processors Pipeline

```
1. merge_contextvars          — merge bound context (symbol, trade_id)
2. add_log_level              — inject "info", "warning", etc.
3. TimeStamper(fmt="iso")     — ISO 8601 timestamp
4. _add_thread_name           — current thread name (custom processor)
5. StackInfoRenderer          — stack info if present
6. format_exc_info            — format exception tracebacks
7. Renderer                   — ConsoleRenderer (dev) or JSONRenderer (prod)
```

### Usage Pattern

```python
import structlog
logger = structlog.get_logger()

# Simple event
logger.info("order_placed", symbol="BTC/USDT", order_id="123", side="BUY")

# Bind context for a trade session
from app.core.logging import bind_trade_context, clear_trade_context
bind_trade_context(symbol="BTC/USDT", trade_id="trade_001")
# ... all subsequent logs in this context include symbol and trade_id ...
clear_trade_context()
```

### Example Output (dev mode)

```
2026-02-25T10:30:45Z [info     ] order_placed    symbol=BTC/USDT order_id=123 side=BUY thread=Symbol-BTC/USDT
```

---

## Financial Precision Rules

| Context | Type | Rationale |
|---------|------|-----------|
| Live trading (all prices, amounts, balances) | `Decimal` | Financial precision required. No floating-point rounding errors. |
| Backtest engine (simulation prices) | `float64` | Performance. 15-16 significant digits is sufficient for simulation. |
| Database storage (money columns) | `TEXT` | Stored as string, parsed with `Decimal` on read. No float rounding in storage. |
| MarketDataStore (pandas columns) | `float64` (main) + `Decimal` (separate `_dec` columns) | Pandas requires float for vectorized operations. Decimal columns preserved for precise calculations. |
| Config values (risk percentages, balances) | `Decimal` | Validated on construction. Used in position sizing calculations. |

### Conversion Rules

- **Decimal to float**: Only at the exchange API boundary (`float(amount)` in `create_order`).
- **float to Decimal**: Use `Decimal(str(value))`, never `Decimal(value)` directly (avoids float representation issues).
- **DataFrame columns**: Main OHLCV columns (`open`, `high`, `low`, `close`, `volume`) are `float64`. Companion columns (`open_dec`, `high_dec`, `low_dec`, `close_dec`) hold original `Decimal` values.

---

## Configuration System

**File**: `app/core/config.py`

### AppConfig Tree

All config classes are frozen dataclasses (`@dataclass(frozen=True)`) -- immutable after construction. Loaded once at startup, passed to constructors (not a global singleton).

```
AppConfig (root)
├── exchange: ExchangeConfig
│   ├── name: str = "binanceusdm"        # binanceusdm | binance | hyperliquid | lighter
│   ├── mode: str = "mock"               # mock | sim | paper | testnet | live
│   ├── leverage: int = 10               # 1-125
│   └── margin_type: str = "ISOLATED"    # ISOLATED | CROSSED
│
├── risk: RiskConfig
│   ├── risk_per_trade_pct: Decimal = 0.02       # 0 < x <= 0.1 (max 10%)
│   ├── max_position_size_pct: Decimal = 0.99    # max % of balance per position
│   ├── leverage: int = 10                        # 1-125
│   ├── use_initial_capital_for_risk: bool = False
│   ├── use_risk_based_sizing: bool = True
│   ├── tp1_close_pct: Decimal = 0.33            # close 33% at TP1
│   ├── tp2_close_pct: Decimal = 0.50            # close 50% at TP2
│   └── min_sl_distance_pct: Decimal = 0.003     # minimum SL distance (0.3%)
│
├── notification: NotificationConfig
│   └── telegram_enabled: bool = True
│
├── backtest: BacktestConfig
│   └── initial_balance: Decimal = 10000
│
├── paper_sim: PaperSimConfig
│   ├── initial_balance: Decimal = 10000
│   └── tick_sample_interval_ms: int = 500
│
├── symbols: List[str] = ["BTC/USDT"]
├── strategy_name: str = "rsi_no_retest"
├── strategy_params: Dict[str, Any] = {}
├── timeframe: str = "5m"
├── warmup_candles: int = 200
└── debug: bool = False
```

### Loading from YAML

```python
from app.core.config import AppConfig
config = AppConfig.from_yaml("config.yaml")
```

`from_yaml` reads the YAML file, maps sections to sub-config constructors, and returns a fully-validated `AppConfig`. Each sub-config's `__post_init__` validates its fields immediately on construction.

### YAML Structure Mapping

```yaml
# config.yaml
bot:
  mode: paper                    # -> exchange.mode
  debug: false                   # -> debug
  telegram_enabled: true         # -> notification.telegram_enabled

exchange:
  name: binanceusdm              # -> exchange.name
  margin_type: ISOLATED          # -> exchange.margin_type

risk:
  risk_per_trade_pct: 0.02       # -> risk.risk_per_trade_pct
  leverage: 10                   # -> exchange.leverage AND risk.leverage
  max_position_size_pct: 0.99    # -> risk.max_position_size_pct
  use_risk_based_sizing: true    # -> risk.use_risk_based_sizing
  tp1_close_pct: 0.33           # -> risk.tp1_close_pct
  tp2_close_pct: 0.50           # -> risk.tp2_close_pct
  min_sl_distance_pct: 0.003    # -> risk.min_sl_distance_pct

symbols:                         # -> symbols
  - BTC/USDT
  - ETH/USDT

strategy: rsi_no_retest          # -> strategy_name
strategy_params: {}              # -> strategy_params
timeframe: 5m                    # -> timeframe
warmup_candles: 200              # -> warmup_candles

backtest:
  initial_balance: 10000         # -> backtest.initial_balance

paper_sim:
  initial_balance: 10000         # -> paper_sim.initial_balance
  tick_sample_interval_ms: 500   # -> paper_sim.tick_sample_interval_ms
```

### Validation Rules

| Config | Validation | Error on Violation |
|--------|------------|-------------------|
| `ExchangeConfig.mode` | Must be one of `{mock, sim, paper, testnet, live}` | `ValueError` |
| `ExchangeConfig.name` | Must be one of `{binanceusdm, binance, hyperliquid, lighter}` | `ValueError` |
| `RiskConfig.risk_per_trade_pct` | `0 < value <= 0.1` (max 10%) | `ValueError` |
| `RiskConfig.leverage` | `1 <= value <= 125` | `ValueError` |

### Legacy Compatibility

`config.to_legacy_dict()` converts the typed `AppConfig` back to a raw dict for constructors not yet migrated to accept `AppConfig` directly. This allows incremental migration -- new code reads `AppConfig` fields directly, old code receives the dict.

---

## Key Source Files

| File | Role |
|------|------|
| `app/core/interfaces.py` | All interface definitions (ABC classes) |
| `app/core/config.py` | Typed config with dataclasses, YAML loading, validation |
| `app/core/events.py` | Core event types (Candle, SignalEvent, MarketEvent, engine events) |
| `app/core/snapshots.py` | PositionSnapshot, ContextSnapshot (frozen dataclasses) |
| `app/core/actions.py` | Typed action objects (OpenPosition, ClosePosition, etc.) |
| `app/core/analysis_result.py` | AnalysisResult (returned by analyze()) |
| `app/core/exceptions.py` | Custom exception hierarchy |
| `app/core/logging.py` | structlog setup and context binding |
| `app/core/runner.py` | MultiSymbolRunner (threading orchestration) |
| `app/services/execution/exchange_factory.py` | Exchange factory with auto-discovery |
| `app/services/execution/cex/binance_adapter.py` | BinanceAdapter (CCXT wrapper) |
| `app/services/market_data/store.py` | MarketDataStore (thread-safe candle storage) |
| `app/services/market_data/stream_manager.py` | BinanceStreamManager (WebSocket daemon) |
| `main.py` | Live bot entry point |
| `app/api/main.py` | FastAPI entry point for backtest UI |
