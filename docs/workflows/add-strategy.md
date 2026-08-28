# Add a Trading Strategy

> Add a new `IStrategy` implementation following the stateless analyze pattern.
> Reference implementations: `app/trading/strategy/rsi_no_retest/` (LONG),
> `app/trading/strategy/rsi_momentum/` (SHORT)

## Prerequisites

- Read `docs/07_trading_strategies/strategy-reference.md` — understand the
  entry/exit/SL/TP model
- Read `docs/07_trading_strategies/strategy-pattern.md` — understand the
  stateless `analyze()` pattern and context state machine
- Read `app/core/actions.py` — all available Action types
- Read `app/core/snapshots.py` — `PositionSnapshot` and `ContextSnapshot` fields
- Read `app/core/analysis_result.py` — `AnalysisResult` structure

## Steps

### 1. Create the strategy file

Directory: `app/trading/strategy/{your_strategy_name}/`

Model on `app/trading/strategy/rsi_no_retest/`. Keep public orchestration in
`strategy.py` and split entry/exit logic before the file-size limit is reached.
Required structure:

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

**Strategy class**: Inherits from `BaseStrategy` (`app/trading/strategy/base.py`).

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

**Shared utilities**: If your strategy needs logic that already exists in another strategy, check `app/trading/strategy/utils/` first. Common helpers for config merging, signal detection, SL/TP building, and trade state serialization live there. Add new shared logic to `utils/` rather than duplicating across strategies.

### 2. Register in the strategy loader

File: `app/trading/strategy/loader.py`

Add import and entry to `STRATEGY_MAP`:
```python
from .your_strategy import YourStrategy

STRATEGY_MAP = {
    "rsi_wma_retest": RsiWmaRetestStrategy,
    "rsi_no_retest": RsiNoRetestStrategy,
    "your_strategy": YourStrategy,    # add this
}
```

This is the **single registration point**. The backtest service (`app/backtest/service.py`) and database seed (`app/repository/backtest/seed.py`) both import `STRATEGY_MAP` from this loader, so your strategy will automatically be available in:
- The live bot (via `loader.py`)
- The backtest API (via `app/backtest/service.py`)
- The backtest UI dropdown (via `app/repository/backtest/seed.py`)

### 3. Seed the database

File: `app/repository/backtest/seed.py`

The seed function iterates over `STRATEGY_MAP` and auto-creates DB records. If your strategy class has a `DEFAULT_CONFIG` class attribute, it will be used as the default config in the UI:

```python
class YourStrategy(BaseStrategy):
    DEFAULT_CONFIG = {
        "param_a": 21,
        "param_b": 0.5,
    }
```

The seed runs on every server startup (`app/api/main.py` → `lifespan` → `seed_strategies`). It is idempotent — the `filter_by(name=...).first() is None` check prevents duplicates.

### 4. Update `config.yaml` (for live bot)

```yaml
strategy: your_strategy   # must match key in STRATEGY_MAP
strategy_params:
  param_a: 21
  param_b: 0.5
```

## SHORT Strategy Considerations

If your strategy opens SHORT positions (selling to enter, buying to exit):

1. **Entry side**: Use `side="SELL"` in `OpenPosition`. The engine maps this to `signal_type="SELL"` in `SignalEvent`.
2. **SL placement**: SL goes **above** entry for SHORT (price going up = loss). Use `stop_market BUY` with `reduceOnly=True`.
3. **TP placement**: TP goes **below** entry for SHORT (price going down = profit). Use `limit BUY` with `reduceOnly=True`.
4. **SLTPCalculator**: Use `app/trading/sl_tp_calculator.py` for direction-aware SL/TP/sizing. All methods accept a `side` parameter.
5. **Indicators**: All indicator computation (including RSI crossover indicators) is provided by the `Indicators` class in `app/data/indicators.py`.
6. **Position amounts**: PortfolioManager stores SHORT positions with **negative** amounts. PnL formula `amount × (exit - entry)` handles both directions.

See `app/trading/strategy/rsi_momentum/` and its test files for a complete
SHORT strategy example.

## Testing

Write `tests/test_{your_strategy_name}.py` modeled on `tests/test_stateless_strategy.py` (LONG) or `tests/test_rsi_momentum.py` (SHORT).

**Key invariants to verify:**
1. `analyze()` never returns `None`
2. `analyze()` never mutates `self` attributes between calls
3. Same `(df, position, context)` inputs → same outputs (pure function)
4. With `context=None` → returns a valid `AnalysisResult` with `state="SCANNING"`
5. With `position=None` → entry state machine runs
6. With `position.has_position=True` → position management runs
7. `new_context` is always a frozen `ContextSnapshot`

**Verify registration:**
```bash
# Strategy loader (single registration point)
python -c "from app.trading.strategy.loader import STRATEGY_MAP; assert 'your_strategy' in STRATEGY_MAP"

# DB seed (start the server, then check)
python -m uvicorn app.api.main:app --port 8100 &
curl http://localhost:8100/api/strategies | python -m json.tool
# Verify your_strategy appears in the response
```

Run `pytest tests/ -v` — all existing tests must pass.

## Documentation Impact

Consult `docs/INDEX.md` → "Code Path → Documentation File" table:

- `app/trading/strategy/` modified → update
  **`docs/07_trading_strategies/strategy-reference.md`** with the parameter,
  entry, exit, SL/TP, and context contracts
- `app/repository/backtest/seed.py` modified → run
  **`python scripts/gen_db_docs.py`** to regenerate
  `docs/14_api_reference/database.md`
- If `app/core/interfaces.py` or `app/core/actions.py` changed → also update
  **`docs/02_architecture/`**
