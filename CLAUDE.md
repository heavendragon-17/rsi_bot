# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RSI trading bot for Binance futures (USDT-M) with backtesting UI. Two subsystems:

1. **Live Bot** (`main.py` → `app/`) — WebSocket streaming, signal detection, order execution
2. **Backtest UI** (`ui/` + `app/api/` + `app/engine/`) — React frontend, FastAPI backend, SQLite DB (under active development)

## Commands

```bash
# Run live bot (signal-only mode)
python main.py

# Run backtest
python app/backtest/download_data.py --symbol BTC/USDT --timeframe 5m --limit 5000
python app/backtest/backtest.py --data app/backtest/data/BTCUSDT_5m.csv --balance 10000

# Tests
pytest tests/                                    # all tests
pytest tests/test_partial_tp_sl.py -v            # single file
pytest tests/test_binance_adapter.py::test_name  # single test

# Setup
python -m venv venv && source venv/Scripts/activate && pip install -r requirements.txt
```

## Architecture

### Clean 3-Layer Architecture (`app/core/interfaces.py`)

```
Layer 1: Data Ingestion    IDataProvider, IDataStore
Layer 2: Core Logic        IStrategy, IIndicators
Layer 3: Execution         IExchange, IFuturesExchange, IPortfolio
```

Each layer only depends on the layer above it. All interfaces are abstract classes in `interfaces.py`.

### Live Bot Data Flow

```
WebSocket (BinanceStreamManager) → MarketDataStore → Strategy.analyze() → SignalEvent → PortfolioManager → Exchange → Telegram
```

- `MultiSymbolRunner` (`app/core/runner.py`) spawns one thread per symbol, shares Exchange and MarketDataStore (thread-safe)
- `StrategyContext` (`app/core/context.py`) is a state machine: SCANNING → RETESTING → CONFIRMING
- All prices use `Decimal` for financial precision

### Backtest UI Architecture (in development)

```
React/Zustand stores → FastAPI REST + SSE → Python executors (ProcessPoolExecutor) → SQLite
```

- DB at `data/backtest.db`, schema in `docs/DATABASE.md`
- Money stored as TEXT in SQLite, parsed with Python `Decimal`
- SSE for progress streaming: `asyncio.Queue` per run_id, `publish_from_thread()` bridges thread→async
- `engineStore.ts` is the reference pattern for all Zustand stores (session as param, SSE in `await new Promise`, `onerror` handler)

### Exchange Adapters

Factory pattern in `app/services/execution/exchange_factory.py`:

- `BinanceAdapter` (CEX, CCXT wrapper) — primary
- `HyperliquidAdapter` (DEX) — implemented
- `LighterAdapter` (DEX) — implemented
- `MockExchange` (`app/backtest/mock_exchange.py`) — backtesting

### Strategy System

Two strategies in `app/strategies/`, loaded dynamically by `loader.py`:

- `rsi_no_retest` — primary (entry on EMA21 reclaim + RSI momentum spread)
- `rsi_wma_retest` — legacy (requires RSI retest of WMA45)

Both produce `SignalEvent` with: entry price, hard SL, soft SL, TP1/TP2/TP3, lock-profit price.

### Position Management (`app/core/portfolio.py`)

Risk-based sizing: `position = (capital × risk_pct) / sl_distance / price`, capped by leverage and max position pct. Partial TP closes at TP1 (33%), TP2 (50% remaining). Lock-profit moves SL to breakeven at +0.5R.

## Key Configuration

- `config.yaml` — bot mode, exchange, symbols, strategy, risk params
- `.env` — API keys (BINANCE_API_KEY, TELEGRAM_BOT_TOKEN, etc.)
- `docs/DATABASE.md` — full SQLite schema for backtest UI

## Conventions

- Python backend, TypeScript/React frontend
- `SignalEvent` is the universal message type between strategy and execution layers
- `MarketDataStore` caps at 6,000 candles per symbol in memory
- Main branch: `mua-tren-the-nang`
