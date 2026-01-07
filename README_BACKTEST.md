# RSI Bot Backtesting Guide

A comprehensive backtesting system for the RSI WMA Retest strategy.

## Quick Start

```bash
# 1. Download historical data
python download_data.py --symbol BTC/USDT --timeframe 5m --limit 5000

# 2. Run backtest
python backtest.py --data data/BTCUSDT_5m.csv --balance 10000
```

---

## Prerequisites

```bash
pip install -r requirements.txt
```

Required packages: `ccxt`, `pandas`, `pandas_ta`, `pyyaml`

---

## Step 1: Download Historical Data

Use `download_data.py` to fetch OHLCV data from Binance.

### Basic Usage
```bash
python download_data.py --symbol BTC/USDT --limit 1000
```

### All Options
| Argument | Default | Description |
|----------|---------|-------------|
| `--symbol` | BTC/USDT | Trading pair (e.g., ETH/USDT, SOL/USDT) |
| `--timeframe` | 5m | Candle interval (1m, 5m, 15m, 1h, 4h, 1d) |
| `--limit` | 1000 | Number of candles (max ~1500 per request) |
| `--output` | data | Output directory |

### Examples
```bash
# Download 1 month of 5m BTC data (~8640 candles)
python download_data.py --symbol BTC/USDT --timeframe 5m --limit 8640

# Download daily ETH data
python download_data.py --symbol ETH/USDT --timeframe 1d --limit 365

# Download to custom folder
python download_data.py --symbol SOL/USDT --output ./historical
```

**Output**: `data/BTCUSDT_5m.csv` (CSV with columns: timestamp, open, high, low, close, volume)

---

## Step 2: Configure Strategy

Edit `config.yaml` to adjust strategy parameters:

```yaml
strategy:
  rsi_period: 14      # RSI calculation period
  rsi_buy: 30         # Buy when RSI < this value (oversold)
  rsi_sell: 80        # Sell when RSI > this value (overbought)
  rsi_ema_length: 9   # EMA of RSI
  rsi_wma_length: 45  # WMA of RSI (for retest detection)
  price_ema_fast: 21  # Fast EMA on price
  price_ema_slow: 200 # Slow EMA on price
```

### Testing vs Production Thresholds
| Mode | rsi_buy | rsi_sell | Description |
|------|---------|----------|-------------|
| Testing | 40 | 60 | More signals, good for validating logic |
| Conservative | 30 | 70 | Balanced approach |
| Aggressive | 25 | 75 | More extreme, fewer but stronger signals |

---

## Step 3: Run Backtest

### Basic Usage
```bash
python backtest.py --data data/BTCUSDT_5m.csv
```

### All Options
| Argument | Default | Description |
|----------|---------|-------------|
| `--data` | (required) | Path to CSV data file |
| `--balance` | 1000.0 | Initial balance (USDT) |

### Examples
```bash
# Standard backtest
python backtest.py --data data/BTCUSDT_5m.csv --balance 10000

# Test with different data
python backtest.py --data data/ETHUSDT_1h.csv --balance 5000
```

---

## Understanding Results

### Console Output
```
Starting backtest on BTC/USDT with 2000 candles...
Executed BUY for BTC/USDT @ 90930.11
Executed SELL for BTC/USDT @ 91250.00
...

=== Backtest Summary ===
Total Trades (Round Trip): 5
Win Rate: 60.00% (3W / 2L)
Final Balance: $10523.45
========================
```

### Output Files
- `backtest_logs.csv`: Detailed trade-by-trade log

---

## Common Use Cases

### 1. Compare Different Timeframes
```bash
python download_data.py --symbol BTC/USDT --timeframe 5m --limit 5000
python backtest.py --data data/BTCUSDT_5m.csv

python download_data.py --symbol BTC/USDT --timeframe 1h --limit 1000
python backtest.py --data data/BTCUSDT_1h.csv
```

### 2. Test Multiple Assets
```bash
for symbol in BTC/USDT ETH/USDT SOL/USDT; do
  python download_data.py --symbol $symbol --limit 3000
done
# Then run backtest on each
```

### 3. Optimize RSI Parameters
1. Edit `config.yaml` → change `rsi_buy` and `rsi_sell`
2. Run backtest
3. Compare results
4. Repeat

### 4. Walk-Forward Testing
```bash
# Download different date ranges (manually split your CSV)
# Test on first half, validate on second half
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `0 trades executed` | RSI thresholds too extreme. Try 40/60 for testing |
| `Insufficient funds` | Increase `--balance` or reduce position size in config |
| `No data received` | Check network, symbol format (use `/` separator) |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |

---

## Architecture

```
backtest.py              # Entry point
├── BacktestEngine       # Main loop, feeds candles to strategy
├── RsiWmaRetestStrategy # Generates BUY/SELL signals
├── PortfolioManager     # Position sizing, risk management
├── MockExchange         # Simulates order execution
└── BacktestReporter     # Calculates PnL, win rate
```

---

## Next Steps

1. **Add more indicators**: Edit `app/utils/indicators.py`
2. **Create new strategies**: Extend `BaseStrategy` in `app/strategies/`
3. **Add stop-loss/take-profit**: Modify `PortfolioManager`
4. **Visualize results**: Export to Excel/TradingView
