# How to Add a Strategy

This guide explains how to add a completely new Python trading strategy to the application and ensure it shows up in the UI.

The UI (`/api/strategies`) fetches available strategies from the SQLite database. The seed function auto-discovers strategies from `STRATEGY_MAP`, so you only need to register in one place.

## 3 Simple Steps

### 1. Create the Strategy File

Create your new strategy class inside the `app/trading/strategy/` folder. It must inherit from `BaseStrategy`.

```python
# app/trading/strategy/my_new_strategy.py
from app.trading.strategy.base import BaseStrategy

class MyNewStrategy(BaseStrategy):
    DEFAULT_CONFIG = {
        "rsi_period": 14,
        "some_param": 100
    }

    def analyze(self, symbol: str, df):
        # Your trading logic here...
        pass
```

### 2. Register in the Strategy Loader

Open `app/trading/strategy/loader.py` and add it to the `STRATEGY_MAP` dictionary. This is the **single registration point** — the backtest service and database seed both import from here automatically.

```python
# app/trading/strategy/loader.py
from .my_new_strategy import MyNewStrategy  # <--- Import it

STRATEGY_MAP = {
    "rsi_wma_retest": RsiWmaRetestStrategy,
    "rsi_no_retest": RsiNoRetestStrategy,
    "my_new_strategy": MyNewStrategy,       # <--- Add it here
}
```

### 3. Seed the Database

The seed function in `app/repository/backtest/seed.py` iterates over `STRATEGY_MAP` automatically. If your strategy class has a `DEFAULT_CONFIG` class attribute, it will be used as the default config in the UI. No manual edit to `seed.py` is needed.

The seed runs on every server startup (`app/api/main.py` → `lifespan` → `seed_strategies`). It is idempotent.

### SHORT Strategy Note

For SHORT strategies, use `side="SELL"` in `OpenPosition`. SL goes above entry
(`stop_market BUY`), while TP goes below entry (`limit BUY`). See
`app/trading/strategy/rsi_momentum/` for a complete example. Use
`SLTPCalculator` (`app/trading/sl_tp_calculator.py`) for direction-aware SL/TP
calculations. RSI crossover indicators live in `app/data/indicators.py`.

### That's it!

When you restart your Python bot server, the `init_db()` function will automatically run `seed.py`. Your new strategy will be inserted into the database, and the UI will dynamically list it in the Strategy dropdown menus!
