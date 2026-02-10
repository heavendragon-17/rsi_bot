# Backtest Engine Reference

> **For AI Agents** | How the existing backtest engine works and how to use it programmatically

---

## 📌 Overview

The backtest engine runs a trading strategy against historical OHLCV data and produces trade results, metrics, and reports. You MUST understand this to build the analysis features (grid search, walk-forward, sensitivity).

**Key files:**

| File | Purpose |
|------|---------|
| `app/backtest/engine.py` | `BacktestEngine` - runs strategy on data |
| `app/backtest/mock_exchange.py` | `MockExchange` - simulates exchange with leverage |
| `app/backtest/reporting.py` | `BacktestReporter` - calculates metrics from results |
| `app/backtest/backtest.py` | CLI runner (uses argparse to run from terminal) |
| `app/backtest/run_batch_analysis.py` | Batch runner (runs multiple symbols in parallel) |
| `app/strategies/loader.py` | `load_strategy()`, `get_available_strategies()` |
| `app/strategies/base.py` | `BaseStrategy` - abstract class all strategies inherit |
| `config.yaml` | Global config (symbols, risk, backtest settings) |

---

## 🔧 How to Run a Single Backtest Programmatically

This is the **core pattern** you must follow for ALL analysis features:

```python
import copy
import yaml
import os
import pandas as pd
from decimal import Decimal
from app.backtest.engine import BacktestEngine
from app.backtest.reporting import BacktestReporter
from app.strategies.loader import load_strategy, get_available_strategies

# 1. Load base config
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.yaml")
with open(CONFIG_PATH, "r") as f:
    base_config = yaml.safe_load(f)

# 2. Prepare run-specific config
config = copy.deepcopy(base_config)
config["symbols"] = ["BTC/USDT"]
config["strategy"] = "rsi_no_retest"   # Must match STRATEGY_MAP key
config["backtest"] = {"initial_balance": 10000}

# 3. Optionally override strategy parameters
# These get merged into the strategy's DEFAULT_CONFIG
config["strategy_params"] = {
    "rsi_period": 14,
    "take_profit_pct": 0.02,
}

# 4. Get strategy class
strategy_class = load_strategy(config)

# 5. Create and run engine
data_path = "app/backtest/data/BTCUSDT_15m.csv"
engine = BacktestEngine(
    data_path=data_path,
    strategy_class=strategy_class,
    config=config
)
engine.run()

# 6. Extract results
reporter = BacktestReporter(
    engine.exchange,
    config,
    initial_balance=10000,
    symbol="BTC/USDT",
    timeframe="15m",
    strategy_name="rsi_no_retest"
)

# Build trade data
trades_df = pd.DataFrame(engine.exchange.trade_history)
round_trips = reporter._build_round_trips(trades_df)
metrics = reporter._calculate_metrics(round_trips)
drawdown = reporter._calculate_drawdown(round_trips)
risk_metrics = reporter._calculate_risk_metrics(round_trips, drawdown)

# Get final balance
final_bal = engine.exchange.fetch_balance().get("total", {}).get("USDT", 0)
profit = float(round_trips['pnl'].sum()) if not round_trips.empty else 0.0
```

---

## 📊 What BacktestEngine Produces

After `engine.run()`, the results live on `engine.exchange`:

### engine.exchange.trade_history

A list of dicts, each trade order:

```python
{
    "id": "mock_order_1",
    "status": "closed",
    "type": "market",
    "side": "BUY",        # or "SELL"
    "symbol": "BTC/USDT",
    "price": 42000.5,      # execution price
    "amount": 0.1,         # quantity
    "filled": 0.1,
    "cost": 4200.05,       # notional value
    "fee": {"currency": "USDT", "cost": 0.0, "rate": 0.0},
    "info": {"exit_reason": "TP1"},  # or "STOP_LOSS", "TP2", "TP3", "EOD"
    "time": Timestamp,
    "notional": 4200.05,
    "margin": 420.005,     # cost / leverage
    "leverage": 10.0,
    "balance_after": 10083.95,
    "entry_price": 42000.5,
    "pnl": 83.95,          # only on SELL orders
    "pnl_pct": 2.0,
    "hold_duration_seconds": 14400,
}
```

### engine.exchange.fetch_balance()

```python
{
    "free": {"USDT": Decimal("10083.95")},
    "used": {"USDT": Decimal("0")},
    "total": {"USDT": Decimal("10083.95")},
}
```

---

## 📈 What BacktestReporter Produces

### reporter._calculate_metrics(round_trips)

```python
{
    "total_trades": 42,
    "win_count": 25,
    "loss_count": 17,
    "win_rate": 59.5,          # percentage
    "total_pnl": 1234.56,
    "avg_pnl": 29.39,
    "avg_win": 85.32,
    "avg_loss": -52.11,
    "largest_win": 250.00,
    "largest_loss": -120.00,
    "profit_factor": 2.1,
    "risk_reward": 1.64,
    "expectancy": 29.39,
    "avg_hold_hours": 6.5,
    "tp1_count": 15,
    "tp2_count": 8,
    "tp3_count": 2,
    "sl_count": 17,
    "exit_reason_counts": {"TP1": 15, "TP2": 8, "TP3": 2, "STOP_LOSS": 17},
    "max_consec_wins": 5,
    "max_consec_losses": 3,
    "gross_profit": 2133.0,
    "gross_loss": 885.87,
}
```

### reporter._calculate_drawdown(round_trips)

```python
{
    "max_drawdown_pct": -12.5,
    "max_drawdown_amount": -1250.0,
    "avg_drawdown_pct": -3.2,
    "drawdown_duration_hours": 48.0,
    "equity_curve": [...],     # list of equity values over time
    "drawdown_curve": [...],   # list of drawdown % over time
}
```

### reporter._calculate_risk_metrics(round_trips, drawdown)

```python
{
    "sharpe_ratio": 1.5,
    "sortino_ratio": 2.1,
    "calmar_ratio": 0.8,
    # ... other risk metrics
}
```

---

## 🗂️ Strategy System

### Available Strategies

Defined in `app/strategies/loader.py`:

```python
STRATEGY_MAP = {
    "rsi_wma_retest": RsiWmaRetestStrategy,
    "rsi_no_retest": RsiNoRetestStrategy,
}
```

### Strategy Config (DEFAULT_CONFIG)

Each strategy has a `DEFAULT_CONFIG` dict with its parameters. For example in `rsi_no_retest.py`:

```python
DEFAULT_CONFIG = {
    "rsi_period": 14,
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    # ... more params
}
```

### How Config Overrides Work

1. Strategy loads `DEFAULT_CONFIG` from its .py file
2. `config.yaml` can have `strategy_params:` to override
3. JSON override files in `config/strategy_overrides/{name}.json` can further override
4. Merge order: DEFAULT_CONFIG < config.yaml < JSON override

---

## 📂 Data Files

CSV files are in `app/backtest/data/`:
- Naming: `{SYMBOL}{QUOTE}_{TIMEFRAME}.csv` (e.g., `BTCUSDT_15m.csv`)
- Columns: `timestamp, open, high, low, close, volume`
- Timestamp format: ISO datetime string

---

## ⚠️ Critical Notes

1. **Always `copy.deepcopy(base_config)`** before modifying config. The engine mutates config internally.
2. **Strategy class, not instance**: `BacktestEngine.__init__` takes a strategy CLASS, not an instance. It instantiates it.
3. **exchange.trade_history** contains ALL orders (BUY and SELL). Use `reporter._build_round_trips()` to get paired trades.
4. **Decimal precision**: The exchange uses Decimal internally. Convert to float for JSON serialization.
5. **warmup_period**: The engine skips the first 220 candles for indicator warmup. This is hardcoded.
6. **Existing `run_single_backtest()`** in `run_batch_analysis.py` is a reference implementation. Study it.
