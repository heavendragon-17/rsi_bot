# System Architecture

> High-level overview of the RSI bot system. Read this first before diving into domain-specific specs.

---

## System Overview

Two subsystems sharing a common core:

```
┌─────────────────────────────────────────────────────────────────┐
│                        RSI Bot System                           │
├──────────────────────────┬──────────────────────────────────────┤
│     Live Bot             │     Backtest UI                      │
│     (main.py)            │     (ui/ + app/api/)                 │
│                          │                                      │
│  WebSocket → Strategy    │  React → FastAPI → Engine            │
│  → Portfolio → Exchange  │  → SQLite → SSE → Results            │
│                          │                                      │
│  Runs on: local/VPS      │  Runs on: local machine              │
└──────────────────────────┴──────────────────────────────────────┘
```

## Tech Stack

| Layer | Live Bot | Backtest UI |
|-------|----------|-------------|
| Frontend | — | React 18 + TypeScript, Zustand, Tailwind CSS, shadcn/ui |
| Backend | Python 3.13 | FastAPI + SQLAlchemy ORM, structlog |
| Database | — | SQLite (`data/backtest.db`) |
| Streaming | Binance WebSocket | Server-Sent Events (SSE) |
| Charts | — | TradingView Lightweight Charts v5, Recharts |
| Exchange | CCXT (Binance Futures) | MockExchange (in-memory simulation) |
| Build | — | Vite (frontend), ProcessPoolExecutor (backend parallelism) |

## Clean 3-Layer Architecture

All interfaces defined in `app/core/interfaces.py`. Each layer only depends on the layer above it.

```
Layer 1: Data Ingestion
├── IDataProvider    — subscribe/unsubscribe to market data streams
└── IDataStore       — update_candle(), get_dataframe()

Layer 2: Core Logic
├── IIndicators      — compute(), get_mode(), calculate_price_at_rsi()
└── IStrategy        — analyze(symbol, df, position, context) → AnalysisResult

Layer 3: Execution
├── IExchange        — create_order(), fetch_order(), cancel_order()
├── IFuturesExchange — extends IExchange: set_leverage(), fetch_positions()
└── IPortfolio       — on_signal(), has_position(), close_position()
```

## Key Data Types

### PositionSnapshot (read-only, passed to strategy)

```python
has_position: bool
symbol: str
side: str
entry_price: Decimal
current_sl: Decimal
tp1_hit, tp2_hit, tp3_hit: bool
lock_profit_triggered: bool
unrealized_pnl: Optional[Decimal]
```

### ContextSnapshot (state machine, passed to/from strategy)

```python
state: str  # "SCANNING" or "CONFIRMING"
soft_sl_price: Optional[Decimal]
meta: Dict[str, Any]  # Strategy-owned metadata (entry prices, flags, etc.)
```

### AnalysisResult (returned by strategy)

```python
actions: List[Action]  # OpenPosition | ClosePosition | MoveSL | PartialClose | DoNothing
new_context: ContextSnapshot
```

### SignalEvent (internal, Portfolio ↔ Exchange)

```python
symbol, signal_type, price, timestamp, reason
tp1/2/3_price, sl_price, soft_sl_price
lock_profit_price, tp_allocations, signal_class
```

## Order Vocabulary

Normalized across all exchange adapters:

| Order Type | Usage | Exchange Mapping |
|------------|-------|-----------------|
| `market` | Entry orders, emergency exits | CCXT `market` |
| `limit` | TP orders (with `reduceOnly=True`) | CCXT `limit` |
| `stop_market` | Hard SL (with `reduceOnly=True`) | CCXT `stop` with stopPrice |
| `stop_limit` | Reserved | CCXT `stop_limit` |
| `trailing_stop` | Reserved | CCXT `trailing` with callbackRate |

All exit orders use `reduceOnly=True` in params.

## Configuration System

### Typed Config (`app/core/config.py`)

```
AppConfig (root)
├── ExchangeConfig     — name, mode, leverage, margin_type
├── RiskConfig         — risk_per_trade_pct, leverage, max_position_size_pct
├── NotificationConfig — telegram_enabled
├── BacktestConfig     — initial_balance
├── PaperSimConfig     — initial_balance, tick_sample_interval_ms
├── symbols: List[str]
├── strategy_name: str
├── strategy_params: Dict[str, Any]
├── timeframe: str
└── debug: bool
```

**Loading**: `AppConfig.from_yaml("config.yaml")` with `__post_init__` validation.

### Exchange Modes

| Mode | Adapter | Description |
|------|---------|-------------|
| `mock` | `MockExchange` | In-memory simulation (backtesting) |
| `sim` | `PaperExchange` | Local order sim against live aggTrade data |
| `paper` | `BinanceAdapter` (testnet) | Real exchange testnet |
| `live` | `BinanceAdapter` (mainnet) | Real exchange, real money |

Factory: `app/services/execution/exchange_factory.py`

## Threading Model

```
Main Thread
├── BinanceStreamManager (1 daemon thread)
│   └── WebSocket → MarketDataStore (thread-safe, per-symbol locks)
│
└── Per-Symbol Threads (N daemon threads)
    ├── Strategy instance (not shared)
    ├── PortfolioManager instance (not shared)
    └── ContextSnapshot storage (owned by runner)
```

**Thread-safe components**: MarketDataStore (per-symbol locks + global lock), BinanceAdapter (single `threading.Lock`).

**Not shared** (by design): Strategy instances, PortfolioManager instances, ContextSnapshots.

## Custom Exception Hierarchy (`app/core/exceptions.py`)

```python
ExchangeError              # Base for all exchange errors
├── InsufficientFundsError
├── OrderRejectedError
├── OrderNotFoundError
├── ConnectionError
└── RateLimitError
PositionError              # Position management errors
```

Each exchange adapter catches its own library errors and re-raises as these.

## Structured Logging

All modules use `structlog` (`app/core/logging.py`). Zero `print()` statements in production code.

```python
import structlog
logger = structlog.get_logger()
logger.info("order_placed", symbol="BTC/USDT", order_id="123")
```

## Financial Precision

- All prices use `Decimal` in live trading for financial precision
- BacktestEngine can use `float64` for performance (15-16 significant digits, sufficient for simulation)
- Database stores money as `TEXT`, parsed with Python `Decimal`
