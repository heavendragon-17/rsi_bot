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

Actions: `OpenPosition`, `ClosePosition`, `MoveSL`, `PartialClose`, `DoNothing`

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

## IMPORTANT: Documentation Maintenance

After ANY code change, follow the documentation maintenance rules in `docs/INDEX.md` → "Documentation Maintenance" section. This is mandatory for all non-trivial changes.
