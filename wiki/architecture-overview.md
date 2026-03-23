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
│   ├── core/                        # Interfaces, config, constants, events, snapshots
│   │   ├── interfaces.py            # Abstract base classes
│   │   ├── config.py                # Typed config (dataclasses)
│   │   ├── constants.py             # Centralized constants (WARMUP, fees, etc.)
│   │   ├── actions.py               # Typed action classes
│   │   ├── snapshots.py             # PositionSnapshot, ContextSnapshot
│   │   ├── events.py                # SignalEvent, TickEvent, etc.
│   │   ├── exceptions.py            # Custom exception hierarchy
│   │   └── logging.py               # structlog setup
│   ├── trading/                      # All live trading logic
│   │   ├── engine.py                # Unified Engine (live + backtest)
│   │   ├── runner.py                # MultiSymbolRunner
│   │   ├── sl_tp_calculator.py      # Direction-aware SL/TP/sizing
│   │   ├── strategy/               # Trading strategies
│   │   │   ├── loader.py            # Dynamic strategy loading
│   │   │   ├── rsi_no_retest.py     # Primary long strategy
│   │   │   ├── rsi_momentum.py      # Short strategy (RSI crossover + divergence)
│   │   │   ├── rsi_wma_retest.py    # Legacy strategy
│   │   │   └── utils/              # Shared strategy utilities
│   │   ├── portfolio/              # Position management (decomposed)
│   │   │   ├── manager.py           # Slim facade (orchestrator)
│   │   │   ├── trade_executor.py    # Entry/exit orchestration
│   │   │   ├── position_sizer.py    # Risk-based sizing
│   │   │   ├── sl_tp_manager.py     # SL/TP placement & moves
│   │   │   └── notification_dispatch.py  # Telegram dispatch
│   │   └── exchange/               # Exchange adapters
│   │       ├── factory.py           # Exchange factory (auto-discovery)
│   │       ├── binance_adapter.py   # Binance USD-M futures (CCXT)
│   │       ├── fill_simulator.py    # Pluggable fill logic
│   │       └── sim/                # Simulation exchanges
│   │           ├── sim_exchange.py  # PaperExchange
│   │           └── sim_stream.py   # AggTrade WebSocket for sim
│   ├── data/                        # Data ingestion & indicators
│   │   ├── store.py                 # MarketDataStore (thread-safe)
│   │   ├── stream_manager.py        # BinanceStreamManager (WebSocket)
│   │   ├── indicators.py            # Consolidated indicators (RSI, EMA, WMA, crossover)
│   │   ├── normalizer.py            # Data normalization
│   │   └── resampler.py             # Candle resampling
│   ├── backtest/                    # Backtest engine, mock exchange
│   │   ├── engine.py                # BacktestEngine
│   │   ├── service.py               # BacktestService (extracted from routes)
│   │   ├── mock_exchange.py         # MockExchange (in-memory sim)
│   │   └── runners/                # CLI runners (batch, portfolio, tick replay)
│   ├── api/                         # FastAPI backend for backtest UI
│   │   └── routes/                 # REST endpoints (split by concern)
│   ├── notification/                # Telegram notifications
│   └── repository/                  # SQLAlchemy ORM models
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

All strategies share the same position management system: partial TP at 3 levels, dual SL (soft + hard), lock-profit mechanism. SHORT positions use signed amounts (negative) and `opposite_side()` for exit orders. Shared strategy logic lives in `app/trading/strategy/utils/`. SHORT strategies use `CrossoverIndicators` from `app/data/indicators.py` and `SLTPCalculator` from `app/trading/sl_tp_calculator.py`.

## Database

The backtest UI uses SQLite (`data/backtest.db`) with 7 tables:
- **strategies** — Available strategies and their default configs
- **runs** — Individual backtest runs with status tracking
- **run_configs** — Configuration used for each run
- **run_results** — Scalar performance metrics (fast loading)
- **run_timeseries** — Heavy time-series data (lazy loading, zlib compressed)
- **trades** — Individual trade records
- **tags** — Labels for organizing runs
