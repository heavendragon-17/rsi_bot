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

## Core V2.1 verification matrix

Core V2.1 has dedicated tests because the pure strategy, point-in-time replay,
mixed-venue acquisition, restart behavior, and outbox are one deterministic
contract.

```bash
python -m pytest \
  tests/test_core_v2_1_config_models.py \
  tests/test_core_v2_1_indicators.py \
  tests/test_core_v2_1_evaluator.py \
  tests/test_core_v2_1_replay_data.py \
  tests/test_core_v2_1_signal_runtime.py \
  tests/test_core_v2_1_bootstrap_performance.py \
  tests/test_core_v2_1_runtime_adapter.py -q
```

Required coverage includes:

- exact locked universe/venue routing, with PUMP structurally Hyperliquid and
  BTC reference-only;
- indicator golden vectors, warm-up, locked feature anchor, and direct vs
  native/resampled feature parity;
- every fresh-cross/filter/A+/WAIT/pullback/cancel/expire/consume/re-arm
  boundary, including cancellation-before-confirmation priority;
- timezone-naive UTC+7 open to aware UTC close normalization, complete UTC
  resampling, exact as-of joins, gap/duplicate/forming/stale rejection, and
  deterministic ledger export;
- authoritative server-clock failure, exact finalized-tail readiness,
  canonical PUMP cold seeding, incremental overlap reconciliation, and
  conflicting duplicate rejection for both venues and in preserved local
  anchor prefixes;
- silent new-install bootstrap, deliverable restart catch-up, uninterrupted vs
  restart state/event parity, atomic state/event/outbox commits, deterministic
  event dedupe, and immutable raw-candle conflicts; and
- outbox retry/reclaim behavior, including proof that stale claim tokens
  cannot mark a reclaimed row `sent` or `retry`, high-attempt backoff cannot
  overflow, cached venue time cannot lead its authoritative sample, and timed-
  out poller/outbox shutdown cannot report a false restart.

### Bootstrap performance acceptance

Bootstrap optimization is accepted only with **semantic parity first**:

1. Run the same anchored candle graph through the optimized bootstrap and a
   simple chronological reference path.
2. Assert identical transition kinds/payloads and final typed state for every
   candidate close.
3. Assert identical public events, deterministic event IDs, suppression
   decisions, and resulting outbox rows.
4. Repeat with a stop/restart boundary and assert the recovered result matches
   one uninterrupted run.

Use operation counts as the stable performance gate. Instrument
`_prepare_market` (or the injected feature builder) and assert initial
`prepare_history` calls it exactly `len(market_plan.all_keys)` times—52 for the
full locked graph: 25 candidate M15, 25 candidate H1, and shared BTC H1/H4.
Evaluating every historical M15 close through `evaluate_prepared` must not add
feature-build calls; shared BTC H1/H4 remain one build each. Thus calls scale
with unique series/candle rows—`O(N)` for the fixed graph—not with every
growing prefix of every M15 trigger (`O(N²)`). A generous wall-clock smoke
bound for a 25 × 5,000-candle fixture may supplement this check, but timing
alone is not a reliable acceptance gate.

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
