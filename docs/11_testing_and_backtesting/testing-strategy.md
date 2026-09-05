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

### Deployment helper tests

`tests/test_deploy_scripts.py` executes the embedded Python helpers from
`deploy/check_deploy.sh` and `deploy/deploy.sh` under production-like
`set -euo pipefail` semantics with sandboxed state files. It also runs
`bash -n` across every deployment script. On Windows, the harness resolves
the installed Git Bash executable and supplies a `python3` shim; on Linux CI,
it uses the normal `bash` executable. These tests complement shell syntax
checks by catching runtime errors such as missing imports in embedded Python.

### Research pipeline tests

`tests/test_btc_ai_pipeline.py` covers the bounded thinker/executor/checker/
reviewer contract, durable provider recovery, evidence integrity, invocation
budgets, and the crash boundary after a review decision commits. The recovery
regression verifies that STOP, REJECT, and REPAIR effects are restored without
new provider calls, results, decisions, or budget reservations.

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
| `tests/test_signal_review_lab.py` | Trigger-close forward return/MFE/MAE calculations and preindexed-source parity, native-candle TP/SL first-touch and same-candle ambiguity, one-time metric-source preparation/progress, canonical common-range availability, bounded/default run creation, orphan reconciliation, immutable card and structured-snapshot persistence, M5 filtering, review reload, independent quality/outcome labels, staged future-candle access, the 2,000-candle unlocked window, M5/M15/H1/H4 chart selection, latest-closed higher-timeframe anchoring, EMA21/EMA200 plus RSI21/EMA9/WMA45 payloads, and replay-source chart warnings |
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
data. The chart gate is tested at both states: `UNREVIEWED` clamps every chart
timeframe to its point-in-time anchor, while any explicit quality label unlocks
future candles. Higher-timeframe tests assert the anchor never exceeds the
signal timestamp and that the complete reviewer indicator set is returned.
Availability and start-run tests replace canonical paths or executor submission
with local deterministic doubles; they do not download market data.
TP/SL tests use the native signal timeframe, exclude the signal candle because
entry is its close, allow the configured levels to be staged while quality is
still unreviewed, and evaluate the saved plan only after quality unlocks the
future. They persist the levels and first-touch result, verify that the separate
manual outcome remains unchanged, and cover the ambiguous case where both
levels occur within one OHLC candle.

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
