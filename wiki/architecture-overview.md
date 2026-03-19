# Architecture Overview

## System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        RSI Bot System                           │
├──────────────────────────┬──────────────────────────────────────┤
│     Live Bot             │     Backtest UI                      │
│                          │                                      │
│  ┌──────────────────┐    │    ┌──────────────────┐              │
│  │ BinanceStream    │    │    │ React Frontend    │              │
│  │ (WebSocket)      │    │    │ (Zustand stores)  │              │
│  └────────┬─────────┘    │    └────────┬──────────┘              │
│           │              │             │ REST + SSE              │
│  ┌────────▼─────────┐    │    ┌────────▼──────────┐              │
│  │ MarketDataStore   │    │    │ FastAPI Backend    │              │
│  │ (Thread-safe)     │    │    │ (ProcessPool)      │              │
│  └────────┬─────────┘    │    └────────┬──────────┘              │
│           │              │             │                         │
│  ┌────────▼─────────┐    │    ┌────────▼──────────┐              │
│  │ Strategy.analyze()│    │    │ BacktestEngine     │              │
│  │ (per symbol)      │    │    │ (MockExchange)     │              │
│  └────────┬─────────┘    │    └────────┬──────────┘              │
│           │              │             │                         │
│  ┌────────▼─────────┐    │    ┌────────▼──────────┐              │
│  │ PortfolioManager  │    │    │ SQLite Database    │              │
│  │ → BinanceAdapter  │    │    │ (runs, results,    │              │
│  │ → Binance Futures │    │    │  trades, timeseries)│             │
│  └──────────────────┘    │    └───────────────────┘              │
└──────────────────────────┴──────────────────────────────────────┘
```

## Key Concepts

### Clean 3-Layer Architecture

The bot uses a clean architecture with abstract interfaces (`app/core/interfaces.py`):

1. **Data Ingestion** — How market data gets in (WebSocket live, CSV backtest)
2. **Core Logic** — Strategy and indicators (pure computation, no side effects)
3. **Execution** — How orders get placed (real exchange, mock, paper)

Each layer only depends on the layer above it. This means the same strategy code runs identically in live trading and backtesting.

### Stateless Strategy Pattern

Strategies are pure functions:

```
analyze(symbol, candle_data, position_snapshot, context_snapshot)
  → actions to take + new context
```

The strategy never mutates its own state. Instead, it receives read-only snapshots and returns what should happen next. This makes testing trivial and prevents state bugs.

### Signal Flow

```
Market Data → Strategy → Actions → Portfolio → Exchange Orders
                                                      │
                                                      ▼
                                               TP Fill Sync
                                               (polling exchange)
```

### Exchange Adapter Pattern

All exchanges implement the same interface (`IExchange`). The factory (`exchange_factory.py`) creates the right adapter based on configuration:

- **mock** → MockExchange (backtest)
- **sim** → PaperExchange (local simulation)
- **paper** → BinanceAdapter (testnet)
- **live** → BinanceAdapter (mainnet)

### Multi-Symbol Threading

The live bot runs one thread per trading symbol. All threads share:
- A single exchange connection (thread-safe via locks)
- A single market data store (thread-safe via per-symbol locks)

Each thread has its own:
- Strategy instance
- Portfolio manager
- Context state machine

## Project Structure

```
rsi_bot/
├── main.py                          # Live bot entry point
├── config.yaml                      # Bot configuration
├── app/
│   ├── core/                        # Interfaces, config, portfolio, runner
│   │   ├── interfaces.py            # Abstract base classes
│   │   ├── config.py                # Typed config (dataclasses)
│   │   ├── runner.py                # MultiSymbolRunner
│   │   ├── portfolio.py             # Position sizing, order management
│   │   ├── context.py               # ContextSnapshot state machine
│   │   ├── actions.py               # Typed action classes
│   │   ├── snapshots.py             # PositionSnapshot, ContextSnapshot
│   │   ├── events.py                # SignalEvent, TickEvent, etc.
│   │   ├── engine.py                # Unified Engine (live + backtest)
│   │   ├── event_source.py          # IEventSource interface
│   │   ├── exceptions.py            # Custom exception hierarchy
│   │   └── logging.py               # structlog setup
│   ├── strategies/                   # Trading strategies
│   │   ├── loader.py                # Dynamic strategy loading
│   │   ├── rsi_no_retest.py         # Primary long strategy
│   │   ├── rsi_momentum.py          # Short strategy (RSI crossover + divergence)
│   │   └── rsi_wma_retest.py        # Legacy strategy
│   ├── services/
│   │   ├── market_data/             # WebSocket, data store
│   │   ├── execution/               # Exchange adapters (Binance, DEX)
│   │   └── notification/            # Telegram bot
│   ├── backtest/                    # Backtest engine, mock exchange
│   ├── api/                         # FastAPI backend for backtest UI
│   ├── repository/backtest/         # SQLAlchemy ORM models
│   └── utils/                       # Indicators, helpers
├── ui/                              # React frontend (backtest UI)
│   └── src/
│       ├── components/              # UI components
│       ├── stores/                  # Zustand state management
│       ├── api/                     # API client layer
│       └── types/                   # TypeScript types
├── tests/                           # pytest test suite
├── docs/                            # AI agent specs (implementation details)
├── wiki/                            # Human-readable guides (you are here)
└── scripts/                         # Utility scripts
```

## Strategies

Three strategies are available, selected via `config.yaml`:

| Strategy | Side | Key Difference |
|----------|------|---------------|
| `rsi_no_retest` | LONG | Entry on EMA21 reclaim + RSI momentum spread. Primary long strategy. |
| `rsi_wma_retest` | LONG | Requires RSI to retest WMA45 before entry. Legacy, more conservative. |
| `rsi_momentum` | SHORT | RSI crossover + bearish divergence. Uses `CrossoverIndicators` and `SLTPCalculator`. |

All strategies share the same position management system: partial TP at 3 levels, dual SL (soft + hard), lock-profit mechanism. SHORT positions use signed amounts (negative) and `opposite_side()` for exit orders.

## Database

The backtest UI uses SQLite (`data/backtest.db`) with 7 tables:
- **strategies** — Available strategies and their default configs
- **runs** — Individual backtest runs with status tracking
- **run_configs** — Configuration used for each run
- **run_results** — Scalar performance metrics (fast loading)
- **run_timeseries** — Heavy time-series data (lazy loading, zlib compressed)
- **trades** — Individual trade records
- **tags** — Labels for organizing runs
