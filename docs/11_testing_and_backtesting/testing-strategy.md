# Testing Strategy

> Testing philosophy, conventions, fixture patterns, and coverage goals.

---

## Philosophy

- Tests verify behavior, not implementation details
- Each layer is tested against its interface contract
- Strategy tests use `ContextSnapshot` and `PositionSnapshot` — never mutate strategy state
- Patch `Indicators.last` explicitly to avoid global state pollution across test runs
- Run `python -m pytest tests/ -v` before marking any task complete

---

## Test Conventions

### Fixture Patterns

```python
# Always patch Indicators.last to control indicator values
@patch.object(Indicators, 'last', return_value={
    'rsi': 55.0, 'rsi_ema9': 52.0, 'rsi_wma45': 48.0,
    'ema21': 42000.0, 'close': 42100.0
})
def test_entry_signal(mock_indicators):
    strategy = RsiNoRetestStrategy(config)
    result = strategy.analyze(
        symbol="BTC/USDT",
        df=sample_df,
        position=PositionSnapshot(has_position=False),
        context=ContextSnapshot(state="CONFIRMING")
    )
    assert isinstance(result.actions[0], OpenPosition)
```

### Key Rules

1. **Pass context explicitly**: `context=ContextSnapshot(state="CONFIRMING")` — don't use `strategy.context.transition()`
2. **Patch indicators**: Always mock `Indicators.last` to control test conditions
3. **Use PositionSnapshot**: Read-only position data, not mutable Position objects
4. **Check action types**: Assert on `isinstance(action, OpenPosition)` not string matching

### Test Organization

```
tests/
├── test_rsi_no_retest.py       # Strategy entry/exit logic
├── test_partial_tp_sl.py        # TP/SL management, partial closes
├── test_portfolio.py            # PortfolioManager position sizing, order flow
├── test_binance_adapter.py      # Exchange adapter (needs real API keys)
├── test_soft_sl.py              # Soft SL mechanism (known issues)
├── test_soft_sl_noretest.py     # Soft SL for rsi_no_retest (known issues)
└── ...
```

---

## What to Test

### Strategy Layer
- Entry conditions: reclaim detection, pullback filter, RSI spread
- Exit conditions: TP hits, SL hits, candle-close SL
- State transitions: SCANNING ↔ CONFIRMING
- Edge cases: insufficient data, last candle not closed

### Execution Layer
- Position sizing: risk-based calculation, max cap
- Order placement: correct types, reduceOnly flags
- Partial close: amount calculations, SL moves
- Error handling: exchange exceptions mapped correctly

### Backtest Engine
- Complete run produces valid metrics
- Round-trip construction (multiple partial fills grouped)
- Edge cases: no trades, single trade, all wins, all losses

---

## Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Single file
python -m pytest tests/test_partial_tp_sl.py -v

# Single test
python -m pytest tests/test_binance_adapter.py::test_name -v

# Skip integration tests (need API keys)
python -m pytest tests/ -v --ignore=tests/test_binance_adapter.py
```

---

## CI Expectations

- All tests should pass before merging (except known issues listed in [known-test-issues.md](known-test-issues.md))
- No `print()` statements in test files — use `structlog` or assertions
- Test files should be self-contained — no dependency on external state or running services
