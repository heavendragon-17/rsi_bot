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
├── test_executor.py              # Executor job-key and worker-argument forwarding
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

### Telegram command layer
- `tests/test_command_handlers.py` verifies `/topics` renders active,
  inactive, and debug topic IDs and escapes configured labels for Telegram's
  HTML parse mode.
- `tests/test_main_signal_mode.py` verifies `/topics` is registered for
  signal mode, including alert-only configurations where `/test_signal` is
  intentionally unavailable.

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

## BTC RSI Cross Alert — focused verification matrix

The `btc_rsi_cross_alert` component (see
[docs/07_trading_strategies/btc-rsi-cross-alert-spec.md](../07_trading_strategies/btc-rsi-cross-alert-spec.md)
§16/§17) ships with deterministic, synthetic-data tests — no network, no real
Telegram, no sleeps beyond bounded shutdown waits.

| Module | Covers |
|---|---|
| `tests/test_btc_rsi_cross_alert_config.py` | Locked config acceptance/rejection, canonical M5/M15/H1/H4 target set, topic collisions (debug / ordinary / duplicate component), disabled entries reserve nothing, alert-only aggregate |
| `tests/test_btc_rsi_cross_alert_preparation.py` | UTC+7 naive-index interpretation (advanced exactly once), aware passthrough, exact current/H1/H4 row selection as-of T, forming/future exclusion, live H1/H4 confirmation sets, 21-H1/21-H4/67-trigger-row readiness boundaries, duplicate/backward/non-finite reasons, maximal-contiguous-suffix rules (old gap allowed, recent gap not ready), full-window indicator determinism |
| `tests/test_btc_rsi_cross_alert_evaluator.py` | Fresh-cross truth table (equality boundaries both sides), strict H1/H4 close>EMA21(price) gates, decision precedence, no undocumented trigger filters, deterministic SHA-256 event identity per (symbol, tf, close), frozen models |
| `tests/test_btc_rsi_cross_alert_timeframe_checkers.py` | M5 current RSI21>EMA9>WMA45 alignment without a fresh cross, strict M5 RSI21<60 ceiling, M15 fresh-cross parity plus strict close>EMA21(price), strict shared H1/H4 gates, wrong-timeframe rejection, worker dispatch, inclusive M5 spread>=2 plus strict WMA45>45 / close>EMA21(price) boundaries, and M15 isolation from M5-only RSI filters |
| `tests/test_btc_rsi_cross_alert_formatter.py` | M5/M15 labels, all required values + event suffix, UTC timestamp, stable numeric formatting, HTML escaping, no trade-lifecycle fields |
| `tests/test_btc_rsi_cross_alert_worker.py` | Bootstrap suppression (pre-ready discard, watermark duplicates, during-hydration closes), closed-candle evaluation to the configured topic, strict one-hour M5/M15 cooldown boundaries (+5m through +55m M5 suppressed, +15m through +45m M15 suppressed, +60m allowed), independent timeframe cooldown state, open candles ignored, H1/H4 sync confirmation waking a waiting trigger without queue transit, boundary race retry-once, retry exhaustion failing closed, duplicate/backward/consumed-cross dedupe, cursor precedence per terminal state, failure budget with requeue-ahead + debug notification + worker-only death, simultaneous M5+M15 alerts, no-virtual-position surface, bounded idempotent stop |
| `tests/test_signal_replay.py` | Historical CSV validation, naive/aware/mixed UTC+7 normalization, full-card combined and split Markdown output, timeframe-isolated M5/M15 files, native H1/H4 context gates, indicator warmup and initial warmup skipping, point-in-time future-row isolation, exact cached-preparation parity with existing checkers, conservative candidate-scan coverage and WMA tolerance, rejected-candle allocation avoidance, independent one-hour M5/M15 cooldown boundaries, duplicate suppression, manual-review fields, and repeatable rendering |
| `tests/test_signal_review_lab.py` | Trigger-close forward return/MFE/MAE calculations and preindexed-source parity, one-time metric-source preparation/progress, canonical common-range availability, bounded/default run creation, orphan reconciliation, immutable card and structured-snapshot persistence, M5 filtering, review reload, independent quality/outcome labels, staged future-candle access, the 2,000-candle unlocked window, and replay-source chart warnings |
| `tests/test_executor.py` | Executor bookkeeping IDs remain independent from worker keyword arguments such as `run_id` |
| `tests/test_stream_manager_multi_tf.py` | `history_complete_callback` order (all fetches → once → WS thread), exactly-once despite a failed fetch, exception isolation, default-None backward compatibility |
| `tests/test_signal_runner.py` | Mixed ordinary/BTC worker groups, union stream targets, alert-only startup, disabled no-op, topic collisions, alert-thread join on stop, no BTC shutdown broadcast |
| `tests/test_signal_runner_integration.py` | Real multiplexer + real worker + mocked stream/notifier: qualifying candle reaches the BTC topic, virtual positions stay empty, duplicates silent |
| `tests/test_main_signal_mode.py` | Startup text renders `BTC/USDT · 5m,15m · H1/H4 filter`, alert-only mode registers no `/test_signal` fake card |

Shared deterministic fixtures live in `tests/btc_alert_fixtures.py`
(synthetic candle shapes engineered so the trigger condition and H4
close-above-price-EMA21 gate land at known rows via the real primitives).

The Signal Review Lab tests use the same fixtures plus isolated in-memory
SQLite databases. They do not require a running API server or live market
data. The chart gate is tested at both states: `UNREVIEWED` clamps the chart
to the trigger close, while any explicit quality label unlocks future candles.
Availability and start-run tests replace canonical paths or executor submission
with local deterministic doubles; they do not download market data.

Focused command:

```bash
python -m pytest \
  tests/test_btc_rsi_cross_alert_config.py \
  tests/test_btc_rsi_cross_alert_preparation.py \
  tests/test_btc_rsi_cross_alert_evaluator.py \
  tests/test_btc_rsi_cross_alert_timeframe_checkers.py \
  tests/test_btc_rsi_cross_alert_formatter.py \
  tests/test_btc_rsi_cross_alert_worker.py \
  tests/test_stream_manager_multi_tf.py \
  tests/test_signal_runner.py \
  tests/test_signal_runner_integration.py \
  tests/test_main_signal_mode.py -q
```

---

## CI Expectations

- All tests should pass before merging (except known issues listed in [known-test-issues.md](known-test-issues.md))
- No `print()` statements in test files — use `structlog` or assertions
- Test files should be self-contained — no dependency on external state or running services
