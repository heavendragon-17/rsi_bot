# Add an Indicator Set

> Add new technical indicator columns computed on the OHLCV DataFrame.
> Reference implementation: `app/utils/indicators.py`
> Interface: `app/core/interfaces.py` → `IIndicators`

## Prerequisites

- Read `docs/strategy-reference.md` — understand which indicators existing strategies use
- Read `app/core/interfaces.py` — `IIndicators` interface (4 abstract methods)
- Read `app/utils/indicators.py` — the concrete `Indicators` class
- Understand which strategy will consume the new indicators

## Steps

### 1. Decide: extend existing or create new class

**Extend existing `Indicators` class** (preferred when adding indicators in the same family — e.g., a new RSI variant, new EMA period):
- Add parameters to `Indicators.__init__()` and new columns in `Indicators.compute()`

**Create a new class** (preferred for entirely different indicator families — e.g., MACD-based, Bollinger-based, volume profile):
- Create `app/utils/{name}_indicators.py` implementing `IIndicators` from `app/core/interfaces.py`
- Must implement all 4 abstract methods: `compute()`, `get_mode()`, `check_wma_retest()`, `calculate_price_at_rsi()`

### 2. Add parameters to the constructor

File: `app/utils/indicators.py` (if extending existing)

Add new parameters with defaults consistent with the consuming strategy's `DEFAULT_CONFIG`:

```python
def __init__(
    self,
    rsi_length: int = 21,
    ...
    new_period: int = 14,    # add
):
    ...
    self.new_period = int(new_period)
```

### 3. Add computation in `compute()`

File: `app/utils/indicators.py`, in the `compute()` method.

The existing pattern uses `pandas_ta` with a manual fallback:

```python
try:
    import pandas_ta as ta
    out["new_indicator"] = ta.sma(out["close"], length=self.new_period)
except Exception:
    # manual fallback if pandas_ta is not installed
    out["new_indicator"] = out["close"].rolling(self.new_period).mean()
```

**Cache consideration**: The existing cache key is `(symbol, timeframe, last_timestamp, df_length)`. It does NOT include parameter values. If you add indicator parameters that can vary between strategy instances running simultaneously, the cache may return stale results. Consider whether to add a parameter hash to the cache key.

### 4. Add helper methods if needed

The `Indicators` class already has these helpers — add new ones following the same pattern:
- `get_mode(df)` → `"BULLISH"` or `"NEUTRAL"`
- `check_wma_retest(df, distance)` → `bool`
- `calculate_price_at_rsi(df, target_rsi)` → `Decimal`
- `last(df)` → dict of last row values (staticmethod, used by strategies to read indicators)

### 5. Update the consuming strategy

File: `app/strategies/{your_strategy}.py`

Pass the new parameter when instantiating `Indicators`:
```python
self.indicators = Indicators(
    rsi_length=...,
    new_period=cfg.get("new_period", 14),
)
```

Access the new column in `analyze()` via `Indicators.last(df)`:
```python
last = Indicators.last(df)
new_val = last.get("new_indicator")
```

## Testing

1. Write `tests/test_{name}_indicators.py`
2. Create a minimal synthetic DataFrame (220+ rows — indicators need warmup period)
3. Test that `compute()` returns a DataFrame with the new column populated (no NaN in the tail rows after warmup)
4. Test the fallback path: mock `pandas_ta` import to raise `ImportError`
5. Test the cache: calling `compute()` twice with same inputs returns the cached object
6. Test edge cases: empty DataFrame, DataFrame shorter than the indicator period
7. Run `pytest tests/ -v`

## Documentation Impact

Consult `docs/INDEX.md` → "Code Path → Documentation File" table:

- `app/utils/indicators.py` supports strategies → update **`docs/strategy-reference.md`**: add the new computed columns to the Indicator Settings parameter table of the affected strategy
- If `app/core/interfaces.py` (`IIndicators`) was modified → update **`docs/architecture.md`**, Layer 2 section
