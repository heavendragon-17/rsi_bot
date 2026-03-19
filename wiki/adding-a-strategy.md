# How to Add a Strategy

This guide explains how to add a completely new Python trading strategy to the application and ensure it shows up in the UI.

The UI (`/api/strategies`) fetches available strategies from the SQLite database. Therefore, simply dropping a `.py` file into `app/strategies/` is **not enough**—you must also register the strategy and insert its default configuration into the database.

## 3 Simple Steps

### 1. Create the Strategy File

Create your new strategy class inside the `app/strategies/` folder. It must inherit from `BaseStrategy`.

```python
# app/strategies/my_new_strategy.py
from app.strategies.base import BaseStrategy

class MyNewStrategy(BaseStrategy):
    DEFAULT_CONFIG = {
        "rsi_period": 14,
        "some_param": 100
    }

    def analyze(self, symbol: str, df):
        # Your trading logic here...
        pass
```

### 2. Register in the Loaders

Register the strategy so the execution engine knows how to initialize it. There are **two independent loaders** you must update.

**First**: Open `app/strategies/loader.py` and add it to the `STRATEGY_MAP` dictionary.

```python
# app/strategies/loader.py
from .my_new_strategy import MyNewStrategy  # <--- Import it

STRATEGY_MAP = {
    "rsi_wma_retest": RsiWmaRetestStrategy,
    "rsi_no_retest": RsiNoRetestStrategy,
    "my_new_strategy": MyNewStrategy,       # <--- Add it here
}
```

**Second**: Open `app/api/routes/backtest.py` and add it to the `_load_strategies()` function (around line 54).

```python
# app/api/routes/backtest.py
def _load_strategies():
    global STRATEGY_MAP
    if not STRATEGY_MAP:
        from app.strategies.rsi_no_retest import RsiNoRetestStrategy
        from app.strategies.my_new_strategy import MyNewStrategy   # <--- Import here

        STRATEGY_MAP = {
            "rsi_no_retest": RsiNoRetestStrategy,
            "my_new_strategy": MyNewStrategy,                      # <--- Add here
        }
    return STRATEGY_MAP
```

### 3. Seed the Database

To make the UI aware of the strategy, it must exist in the database.
Open `app/repository/backtest/seed.py` and add the default configuration and database insertion logic.

```python
# app/repository/backtest/seed.py
from app.repository.backtest.models import Strategy

MY_NEW_STRATEGY_CONFIG = {
    "rsi_period": 14,
    "some_param": 100
}

def seed_strategies(session) -> None:
    # Existing strategies...

    # Add your new one here:
    if session.query(Strategy).filter_by(name="my_new_strategy").first() is None:
        session.add(
            Strategy(
                name="my_new_strategy",
                description="Short description for the UI",
                default_config=MY_NEW_STRATEGY_CONFIG,
            )
        )
        session.commit()
```

### SHORT Strategy Note

For SHORT strategies, use `side="SELL"` in `OpenPosition`. SL goes above entry (`stop_market BUY`), TP goes below entry (`limit BUY`). See `app/strategies/rsi_momentum.py` for a complete example. Use `SLTPCalculator` (`app/core/sl_tp_calculator.py`) for direction-aware SL/TP calculations.

### That's it!

When you restart your Python bot server, the `init_db()` function will automatically run `seed.py`. Your new strategy will be inserted into the database, and the UI will dynamically list it in the Strategy dropdown menus!
