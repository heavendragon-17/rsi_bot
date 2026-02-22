# Getting Started

## Prerequisites

- **Python 3.10+** with pip
- **Node.js 18+** with npm (for the backtest UI)
- **Git** for version control

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/heavendragon-17/rsi_bot.git
cd rsi_bot
```

### 2. Set up Python environment

```bash
# Option A: Using conda
conda create -n rsi python=3.13
conda activate rsi

# Option B: Using venv
python -m venv venv
source venv/Scripts/activate  # Windows
# source venv/bin/activate    # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### 3. Set up environment variables

```bash
cp .env.example .env
```

Edit `.env` with your API keys:

```env
BINANCE_API_KEY=your_api_key_here
BINANCE_SECRET_KEY=your_secret_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 4. Configure the bot

Edit `config.yaml`:

```yaml
bot:
  active: true
  mode: paper       # paper = testnet, sim = local simulation, live = real money
  debug: true
  telegram_enabled: true

exchange:
  name: binanceusdm
  leverage: 10
  margin_type: ISOLATED

symbols:
  - BTC/USDT
  - ETH/USDT

strategy: rsi_no_retest
timeframe: 5m

risk:
  risk_per_trade_pct: 0.02
  max_position_size_pct: 0.99
  leverage: 10
  use_risk_based_sizing: true
```

## Running the Live Bot

```bash
python main.py
```

The bot will:
1. Load configuration and validate
2. Connect to Binance WebSocket for market data
3. Start monitoring symbols for trading signals
4. Send notifications via Telegram

## Running the Backtest UI

### Start the backend

```bash
cd rsi_bot
python -m uvicorn app.api.main:app --reload --port 8000
```

### Start the frontend

```bash
cd ui
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

## Running Backtests (CLI)

### 1. Download historical data

```bash
python app/backtest/download_data.py --symbol BTC/USDT --timeframe 5m --limit 5000
```

### 2. Run backtest

```bash
python app/backtest/backtest.py --data app/backtest/data/BTCUSDT_5m.csv --balance 10000
```

### Download options

| Argument | Default | Description |
|----------|---------|-------------|
| `--symbol` | BTC/USDT | Trading pair |
| `--timeframe` | 5m | Candle interval (1m, 5m, 15m, 1h, 4h, 1d) |
| `--limit` | 1000 | Number of candles |
| `--output` | data | Output directory |

## Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Single file
pytest tests/test_partial_tp_sl.py -v

# Single test
pytest tests/test_binance_adapter.py::test_name
```

## Exchange Modes

| Mode | Description | Use For |
|------|-------------|---------|
| `mock` | In-memory simulation, no network | Backtesting |
| `sim` | Local order sim against live data | Paper trading with tick-level accuracy |
| `paper` | Binance testnet (real exchange, fake money) | Integration testing |
| `live` | Binance mainnet (real money) | Production trading |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `0 trades executed` | RSI thresholds too extreme. Try wider spread settings |
| `Insufficient funds` | Increase `--balance` or reduce `risk_per_trade_pct` |
| `No data received` | Check network, symbol format (use `/` separator) |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| `451 Error` | Binance API may be blocked in your region. Use VPN |
