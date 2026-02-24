# Add a Trading Strategy

> Add a new `IStrategy` implementation following the stateless analyze pattern.
> Reference implementation: `app/strategies/rsi_no_retest.py`

## Prerequisites

- Read `docs/strategy-reference.md` — understand entry/exit/SL/TP model
- Read `docs/live-bot.md` — understand the stateless analyze pattern and context state machine
- Read `app/core/actions.py` — all available Action types
- Read `app/core/snapshots.py` — `PositionSnapshot` and `ContextSnapshot` fields
- Read `app/core/analysis_result.py` — `AnalysisResult` structure

## Steps

### 1. Create the strategy file

File: `app/strategies/{your_strategy_name}.py`

Model on `app/strategies/rsi_no_retest.py`. Required structure:

**Config dataclass**: A frozen `@dataclass` with typed fields and a `from_dict()` classmethod that filters unknown keys. This allows the backtest UI to pass arbitrary JSON params without crashing:

```python
@dataclass(frozen=True)
class YourStrategyConfig:
    param_a: int = 21
    param_b: float = 0.5

    @classmethod
    def from_dict(cls, d: dict) -> "YourStrategyConfig":
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in valid})
```

**Strategy class**: Inherits from `BaseStrategy` (`app/strategies/base.py`).

**`__init__(self, config: dict)`**: Extract `strategy_params` sub-dict. Instantiate `Indicators` with your indicator settings. Set parameter attributes.

**`analyze(self, symbol, df, position, context) -> AnalysisResult`**:
- **Always** returns `AnalysisResult(actions=[...], new_context=ContextSnapshot(...))`
- **Never** returns `None` — use `DoNothing()` as the no-op action
- **Never** mutates `self` — the function must be pure
- Start with `if context is None: context = ContextSnapshot(state="SCANNING")`
- Define a `_noop = AnalysisResult(actions=[DoNothing()], new_context=context)` for early returns
- Access `context.state`, `context.soft_sl_price`, `context.meta` — never mutate them
- Return a **new** `ContextSnapshot` (frozen dataclass) in `new_context`

**Available Actions** (from `app/core/actions.py`):
- `OpenPosition(symbol, side, entry_price, sl_price, soft_sl_price, tp_prices, tp_allocations, lock_profit_price, signal_class, reason)`
- `ClosePosition(symbol, reason, price=None)` — `price=None` means market order
- `MoveSL(symbol, new_sl_price, reason)`
- `PartialClose(symbol, tp_level, price, reason, new_sl_price=None)`
- `DoNothing()`

**TP allocations format**:
```python
tp_allocations = {"TP1": 0.5, "TP2": 0.5, "TP3": 1.0}
# Keys: "TP1"/"TP2"/"TP3". Values: fraction of remaining position to close.
```

### 2. Register in the live bot strategy loader

File: `app/strategies/loader.py`

Add import and entry to `STRATEGY_MAP`:
```python
from .your_strategy import YourStrategy

STRATEGY_MAP = {
    "rsi_wma_retest": RsiWmaRetestStrategy,
    "rsi_no_retest": RsiNoRetestStrategy,
    "your_strategy": YourStrategy,    # add this
}
```

### 3. Register in the backtest API route

File: `app/api/routes/backtest.py`

In the `_load_strategies()` function (line ~54):
```python
def _load_strategies():
    global STRATEGY_MAP
    if not STRATEGY_MAP:
        from app.strategies.rsi_no_retest import RsiNoRetestStrategy
        from app.strategies.rsi_wma_retest import RsiWmaRetestStrategy
        from app.strategies.your_strategy import YourStrategy    # add

        STRATEGY_MAP = {
            "rsi_no_retest": RsiNoRetestStrategy,
            "rsi_wma_retest": RsiWmaRetestStrategy,
            "your_strategy": YourStrategy,                       # add
        }
    return STRATEGY_MAP
```

**Why two maps?** The live bot loader (`loader.py`) and the backtest API (`backtest.py`) load strategies independently. Both must know about the strategy, or it will be available in one mode but not the other.

### 4. Seed the database

File: `app/repository/backtest/seed.py`

Add a default config dict and seed call. This is required for the strategy to appear in the backtest UI dropdown (`GET /api/strategies`):

```python
YOUR_STRATEGY_CONFIG = {
    "param_a": 21,
    "param_b": 0.5,
    # all strategy_params keys with their defaults
}

def seed_strategies(session) -> None:
    # ... existing seeds ...
    if session.query(Strategy).filter_by(name="your_strategy").first() is None:
        session.add(Strategy(
            name="your_strategy",
            description="Brief description of your strategy",
            default_config=YOUR_STRATEGY_CONFIG,
        ))
        session.commit()
```

The seed runs on every server startup (`app/api/main.py` → `lifespan` → `seed_strategies`). It is idempotent — the `filter_by(name=...).first() is None` check prevents duplicates.

### 5. Update `config.yaml` (for live bot)

```yaml
strategy: your_strategy   # must match key in STRATEGY_MAP
strategy_params:
  param_a: 21
  param_b: 0.5
```

## Testing

Write `tests/test_{your_strategy_name}.py` modeled on `tests/test_stateless_strategy.py`.

**Key invariants to verify:**
1. `analyze()` never returns `None`
2. `analyze()` never mutates `self` attributes between calls
3. Same `(df, position, context)` inputs → same outputs (pure function)
4. With `context=None` → returns a valid `AnalysisResult` with `state="SCANNING"`
5. With `position=None` → entry state machine runs
6. With `position.has_position=True` → position management runs
7. `new_context` is always a frozen `ContextSnapshot`

**Verify the 3 registration points:**
```bash
# Live bot loader
python -c "from app.strategies.loader import STRATEGY_MAP; assert 'your_strategy' in STRATEGY_MAP"

# Backtest API route
python -c "from app.api.routes.backtest import _load_strategies; assert 'your_strategy' in _load_strategies()"

# DB seed (start the server, then check)
python -m uvicorn app.api.main:app --port 8000 &
curl http://localhost:8000/api/strategies | python -m json.tool
# Verify your_strategy appears in the response
```

Run `pytest tests/ -v` — all existing tests must pass.

## Documentation Impact

Consult `docs/INDEX.md` → "Code Path → Documentation File" table:

- `app/strategies/` modified → update **`docs/strategy-reference.md`**: add a new section for the strategy with its parameter table, entry logic, SL/TP logic, and context state machine description
- `app/repository/backtest/seed.py` modified → run **`python scripts/gen_db_docs.py`** to regenerate `docs/database.md`
- If `app/core/interfaces.py` or `app/core/actions.py` modified → also update **`docs/architecture.md`**
