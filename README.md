# RSI Bot

A cryptocurrency trading bot for Binance futures (USDT-M) with a professional backtesting UI.

## Features

- **Live Trading** — WebSocket-driven signal detection with automated order execution
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

| Resource | Description |
|----------|-------------|
| [Getting Started](wiki/getting-started.md) | Installation, setup, and first run |
| [Architecture Overview](wiki/architecture-overview.md) | System design and key concepts |
| [Backtest Guide](wiki/backtest-guide.md) | Using the UI, parameter tuning, optimization |
| [Strategy Reference](docs/strategy-reference.md) | Strategy parameters and trading rules |

## Project Structure

```
rsi_bot/
├── main.py              # Live bot entry point
├── config.yaml          # Bot configuration
├── app/                 # Python backend
│   ├── core/            # Interfaces, config, portfolio, runner
│   ├── strategies/      # Trading strategies
│   ├── services/        # Exchange adapters, market data, notifications
│   ├── backtest/        # Backtest engine
│   ├── api/             # FastAPI backend (backtest UI)
│   └── repository/      # SQLAlchemy ORM models
├── ui/                  # React frontend (backtest UI)
├── tests/               # Test suite
├── docs/                # Technical specifications
└── wiki/                # User-facing documentation
```

## License

Private repository.
