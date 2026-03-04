# RSI Bot

A cryptocurrency trading bot for Binance futures (USDT-M) with a professional backtesting UI.

## Features

- **Live Trading** — WebSocket-driven signal detection with automated order execution
- **Paper Trading (Sim)** — Full strategy execution against live Binance aggTrade ticks via `PaperExchange`
- **Tick-Level Backtest** — Replay 40M+ historical aggTrades through `PaperExchange` for precise SL/TP fill simulation
- **Backtesting UI** — React frontend + FastAPI backend with SQLite storage
- **Multi-Symbol** — Trade multiple pairs simultaneously with shared capital pool
- **Grid Search** — Parameter optimization with heatmap visualization
- **Walk-Forward** — Out-of-sample validation to detect overfitting
- **Sensitivity Analysis** — Identify fragile parameters

## Quick Start

```bash
# Clone and install
git clone https://github.com/heavendragon-17/rsi_bot.git
cd rsi_bot
pip install -r requirements.txt

# Configure
cp .env.example .env  # Add your API keys
# Edit config.yaml    # Set mode, symbols, strategy

# Run live bot
python main.py

# Or run backtest UI
python -m uvicorn app.api.main:app --reload --port 8000  # backend
cd ui && npm install && npm run dev                        # frontend
```

## Documentation

**Human Guides (wiki/):**

| Resource | Description |
|----------|-------------|
| [Getting Started](wiki/getting-started.md) | Installation, setup, and first run |
| [Architecture Overview](wiki/architecture-overview.md) | System design and key concepts |
| [Backtest Guide](wiki/backtest-guide.md) | Using the UI, parameter tuning, optimization |
| [Paper Backtest](wiki/paper-backtest.md) | Tick-level paper backtest guide |

**AI Agent Specs (docs/):**

| Resource | Description |
|----------|-------------|
| [Documentation Index](docs/INDEX.md) | Smart routing table — start here |
| [Architecture](docs/02_architecture/) | System overview, data types, threading model |
| [Strategy Reference](docs/07_trading_strategies/) | Strategy parameters and trading rules |
| [API Reference](docs/14_api_reference/) | REST + SSE endpoint reference |

**Other:**

| Resource | Description |
|----------|-------------|
| [CHANGELOG](CHANGELOG.md) | Version history and release notes |
| [Security Policy](SECURITY.md) | Secrets management and vulnerability reporting |

## Project Structure

```
rsi_bot/
├── main.py              # Live bot entry point
├── config.yaml          # Bot configuration
├── app/                 # Python backend
│   ├── core/            # Interfaces, config, portfolio, runner
│   ├── strategies/      # Trading strategies
│   ├── services/        # Exchange adapters, market data, notifications
│   ├── backtest/        # Backtest engine & CLI scripts
│   │   ├── backtest.py             # OHLC backtest CLI (MockExchange)
│   │   ├── run_paper_tick_replay.py # Tick-level paper backtest CLI (PaperExchange)
│   │   ├── download_data.py        # Download OHLC candles from Binance
│   │   ├── download_tick_data.py   # Download aggTrades ticks from Binance Vision
│   │   └── data/                   # CSV storage (gitignored)
│   ├── paper/           # PaperExchange sim engine
│   ├── api/             # FastAPI backend (backtest UI)
│   └── repository/      # SQLAlchemy ORM models
├── ui/                  # React frontend (backtest UI)
├── tests/               # Test suite
├── docs/                # Technical specifications
└── wiki/                # User-facing documentation
```

## Tick-Level Paper Backtest (CLI)

Test `PaperExchange` with real historical aggTrades for precise SL/TP simulation:

```bash
# 1. Download monthly tick data from Binance Vision (~40M rows)
python app/backtest/download_tick_data.py --symbol BTCUSDT --year 2024 --month 1

# 2. Download matching OHLC candles
python app/backtest/download_data.py --symbol BTC/USDT --timeframe 5m --limit 9000

# 3. Run tick-level paper backtest
python app/backtest/run_paper_tick_replay.py \
    --ohlc  app/backtest/data/BTCUSDT_5m.csv \
    --ticks app/backtest/data/BTCUSDT_ticks_2024_01.csv \
    --symbol BTC/USDT --timeframe 5m --balance 10000 --strategy rsi_no_retest
```

## License

Private repository.
