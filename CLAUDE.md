# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Documentation

For detailed specs, read `docs/INDEX.md` first — it has a **task-based routing table** that tells you exactly which folder and files to read for your task.

- **First time?** Read `docs/00_onboarding/onboarding.md` — agent bootstrap, conventions, do/don't rules
- **Agent workflow**: `docs/agent-workflow.md` — **MUST READ before every task.** Covers planning, verification, task management, and code quality standards.
- **AI agent specs**: `docs/` — numbered folders (02_architecture through 15_debugging) covering every system domain
- **Extension guides**: `docs/workflows/` — step-by-step guides for adding strategies, exchanges, endpoints, etc.
- **Human guides**: `wiki/` (getting started, architecture overview, backtest guide)
- **Database schema**: `docs/14_api_reference/database.md` — auto-generated from ORM. Run `python scripts/gen_db_docs.py` to regenerate.

## Commands

```bash
# Run live bot
python main.py

# Run backtest (CLI)
python app/backtest/download_data.py --symbol BTC/USDT --timeframe 5m --limit 5000
python app/backtest/backtest.py --data app/backtest/data/BTCUSDT_5m.csv --balance 10000

# Run backtest UI
python -m uvicorn app.api.main:app --reload --port 8000  # backend
cd ui && npm run dev                                       # frontend

# Tests
pytest tests/                                    # all tests
pytest tests/test_partial_tp_sl.py -v            # single file
pytest tests/test_binance_adapter.py::test_name  # single test

# Regenerate database docs
python scripts/gen_db_docs.py
```

## Architecture (Quick Reference)

### Clean 3-Layer Architecture (`app/core/interfaces.py`)

```
Layer 1: Data Ingestion    IDataProvider, IDataStore
Layer 2: Core Logic        IStrategy, IIndicators
Layer 3: Execution         IExchange, IPortfolio
```

### Live Bot Data Flow

```
WebSocket (BinanceStreamManager) → MarketDataStore → Strategy.analyze() → Actions → PortfolioManager → Exchange → Telegram
```

### Backtest UI Data Flow

```
React/Zustand → FastAPI REST + SSE → ProcessPoolExecutor → BacktestEngine → SQLite
```

### Exchange Modes

| Mode | Adapter | Use |
|------|---------|-----|
| `mock` | MockExchange | Backtesting |
| `sim` | PaperExchange | Local sim against live data |
| `paper` | BinanceAdapter (testnet) | Integration testing |
| `live` | BinanceAdapter (mainnet) | Production |

### Stateless Strategy Pattern

```python
analyze(symbol, df, position=PositionSnapshot, context=ContextSnapshot) -> AnalysisResult
```

Actions: `OpenPosition` (side="BUY" for long, "SELL" for short), `ClosePosition`, `MoveSL`, `PartialClose`, `DoNothing`

### Key Utilities

- `SLTPCalculator` (`app/trading/sl_tp_calculator.py`) — Direction-aware SL/TP/sizing (static methods, accepts `side` param)
- `CrossoverIndicators` (`app/data/indicators.py`) — RSI14 + EMA9/WMA45 of RSI for crossover strategies (consolidated indicators module)
- `opposite_side()` (`app/core/actions.py`) — BUY↔SELL, used for exit orders
- Position amounts are **signed**: positive=LONG, negative=SHORT

### Order Vocabulary

- `market` — entry orders, emergency exits
- `limit` — TP orders (with `reduceOnly=True`)
- `stop_market` — hard SL (with `reduceOnly=True`)
- All exit orders use `reduceOnly=True` in params

## Key Configuration

- `config.yaml` — bot mode, exchange, symbols, strategy, risk params
- `.env` — API keys (BINANCE_API_KEY, TELEGRAM_BOT_TOKEN, etc.)

## Conventions

- Python backend, TypeScript/React frontend
- All prices use `Decimal` for financial precision (live); `float64` acceptable in backtest
- `SignalEvent` is the universal message between strategy and execution layers
- `MarketDataStore` caps at 6,000 candles per symbol in memory
- Main branch: `mua-tren-the-nang`
- structlog for all logging (zero print statements)

## IMPORTANT: Architectural Rules (MUST FOLLOW)

These rules are **mandatory** for every code change. Violating them creates tech debt.

### Directory Boundaries — Do NOT put files in the wrong place

```
app/core/         → ONLY interfaces, models, actions, config, constants, exceptions, events, snapshots
                    NO implementation logic. NO exchange/strategy/portfolio code.
app/trading/      → ALL live trading: strategy/, portfolio/, exchange/, engine, runner
app/data/         → ALL data ingestion: store, stream, normalizer, indicators, resampler
app/backtest/     → ALL backtest: engine, mock_exchange, service, reporting, download
app/api/          → ALL HTTP: FastAPI routes, schemas, executor. NO business logic in routes.
app/notification/ → ALL notifications: telegram, notification service/worker
app/repository/   → ALL database: ORM models, queries, connections
```

### File Size Limits

- **Max 400 lines per file.** If a file grows past 400 lines, decompose it.
- **Max 1 class with real logic per file.** Small dataclasses/enums can share a file.

### No Magic Numbers

- ALL constants go in `app/core/constants.py` — WARMUP, MAX_CANDLES_IN_RAM, fee defaults, etc.
- Strategy parameters go in the strategy's own frozen config dataclass — NOT in config.yaml, NOT hardcoded.
- If you add a constant, check constants.py first. Don't duplicate.

### Import Discipline

- `app/core/` may NOT import from `app/trading/`, `app/data/`, `app/backtest/`, `app/api/`, or `app/notification/`
- `app/trading/` may import from `app/core/` and `app/data/` only
- `app/backtest/` may import from `app/core/`, `app/data/`, and `app/trading/` (shared strategies/models)
- `app/api/` may import from anything (it's the outermost layer)
- **Never create circular imports.** Test with: `python -c "from app.core import interfaces"`

### No God Classes

- Classes should have **one responsibility**. If a class has 5+ unrelated methods, split it.
- Exchange adapters: delegate fill logic to `FillSimulator`, don't inline it.
- Portfolio: delegate to `PositionSizer`, `SLTPManager`, `TradeExecutor`, `NotificationDispatcher`.
- API routes: delegate business logic to service classes. Routes are thin HTTP handlers only.

### DRY — Don't Repeat Yourself

- Shared strategy logic lives in `app/trading/strategy/utils/` — do NOT copy-paste between strategies.
- Symbol normalization: use `app/core/utils.py` — do NOT write another `_base_asset()` helper.
- Fee constants: import from `app/core/constants.py` — do NOT hardcode `0.0005` anywhere.
- dotenv: loaded ONCE in `main.py` entry point — do NOT call `load_dotenv()` in individual modules.

### Before You Code, Check the Spec

If `SPEC_CLEANUP_*.md` files exist at repo root, read them. They document architectural decisions.

## IMPORTANT: Documentation Maintenance

After ANY code change, follow the documentation maintenance rules in `docs/INDEX.md` → "Documentation Maintenance" section. This is mandatory for all non-trivial changes.
