# BTC RSI Cross Alert — Implementation Specification

> **Status:** Proposed and implementation-ready
> **Date:** 2026-08-24
> **Feature name:** `btc_rsi_cross_alert`
> **Runtime:** Existing signal-bot mode
> **Execution boundary:** Telegram advisory only; never place or manage orders

## 1. Agent execution instruction

Implement this specification completely in the existing `rsi_bot` repository.
Do not stop after producing a plan or additional documentation. Preserve
unrelated working-tree changes and use the existing Conda `rsi` environment.
Read `docs/agent-workflow.md` and `docs/workflows/add-strategy.md` before
editing code. The add-strategy workflow is required reading for repository
conventions only; this specification supersedes its loader, backtest seed, and
UI-registration steps because this component deliberately does not implement
the single-frame `IStrategy` contract.

The implementation is complete only after focused tests, the full test suite,
Ruff, compilation, configuration validation, and documentation checks pass.
Record exact verification results in `tasks/todo.md`.

## 2. Source request

The requested behavior, normalized from the product conversation, is:

1. Track only BTC.
2. Evaluate both M5 and M15.
3. On either trigger timeframe, alert when EMA9 of RSI crosses upward through
   WMA45 of RSI.
4. Alert only while H4 is bullish.
5. H4 is bullish exactly when `RSI21 > EMA9(RSI21) > WMA45(RSI21)`.
6. Send the alert to Telegram.

This document resolves all unspecified v1 behavior so implementation does not
depend on follow-up interpretation.

## 3. Architecture decision

Build this feature as an extension of the existing `SignalRunner` subsystem,
not as a new repository or a second independent bot.

Implement the pure models/evaluator under
`app/trading/strategy/btc_rsi_cross_alert/` and the runtime/configuration
adapter under `app/signal/btc_rsi_cross_alert/`. Expose the component through
the existing `strategies:` configuration list using the name
`btc_rsi_cross_alert`, but do not register it with the single-frame trading
strategy loader.

Do **not** force this component through the current single-frame
`IStrategy.analyze()` contract. That contract supplies one DataFrame, while
this feature requires point-in-time access to M5, M15, and H4 simultaneously.
Use a dedicated pure evaluator and a dedicated worker, both orchestrated by
`SignalRunner` and backed by the existing `TimeframeMultiplexer`,
`BinanceStreamManager`, and `NotificationService`.

Do not modify the behavior or locked contracts of:

- `app/trading/strategy/rsi_alert/`;
- `app/trading/strategy/core_v2_1/`;
- `app/signal/core_v2_1/`; or
- existing single-timeframe signal strategies.

The existing `rsi_alert` is an RSI14 oversold/intrabar alert and is not a
suitable implementation base. Core V2.1 has a separate locked strategy and
runtime contract.

## 4. Goals

- Subscribe to native Binance USD-M BTC candles for `5m`, `15m`, and `4h`.
- Evaluate only fully closed M5 and M15 candles.
- Detect one fresh bullish EMA9/WMA45 crossover on the selected RSI21 series.
- Gate every M5/M15 signal using the latest fully closed H4 candle available at
  the trigger candle's close time.
- Deliver a clear Telegram message to one configured topic.
- Suppress all alerts while initial REST history is loading.
- Deduplicate repeated callbacks for the same trigger candle.
- Remain backward compatible with every existing SignalRunner strategy.
- Fail closed when indicator, timing, continuity, or H4 context is invalid.

## 5. Non-goals

- Automated order placement, cancellation, or position management.
- Entry, stop-loss, take-profit, leverage, sizing, PnL, or win-rate logic.
- Virtual positions or mechanical exit monitoring.
- Monitoring any symbol other than `BTC/USDT` in v1.
- Short/bearish crossover alerts.
- Intrabar alerts or alerts based on forming candles.
- Historical alerts during startup.
- A backtest UI strategy entry or database strategy seed.
- Changes to Core V2.1 indicator, anchor, evaluator, state, or runtime behavior.
- Durable/exactly-once Telegram delivery in v1.

## 6. Locked configuration

Add the following disabled component entry to `config.yaml`. Topic `1007` is the
current proposed value because it does not collide with the checked-in active
topic or debug topic; startup validation remains authoritative.

```yaml
strategies:
  - name: btc_rsi_cross_alert
    active: false
    telegram_topic_id: 1007
    symbol: "BTC/USDT"
    trigger_timeframes: ["5m", "15m"]
    trend_timeframe: "4h"
    rsi_period: 21
    rsi_ema_period: 9
    rsi_wma_period: 45
    context_settle_seconds: 5
```

Validation must reject startup with `ValueError` when any condition below is
violated:

- `symbol` is anything other than the canonical `BTC/USDT`;
- `trigger_timeframes` is missing, contains duplicates, or is not exactly the
  set `{5m, 15m}`;
- `trend_timeframe != "4h"`;
- indicator periods are not exactly `21`, `9`, and `45`;
- `context_settle_seconds` is not an integer in the inclusive range `0..30`;
- `telegram_topic_id` is missing, is not integer-coercible, collides with the
  debug topic, or collides with another active strategy topic; or
- more than one active `btc_rsi_cross_alert` entry exists.

These values are explicit in configuration for auditability, but they are
locked for v1. Do not silently accept other values.

The checked-in default must remain `active: false` until the operator verifies
that Telegram topic `1007` exists in the configured supergroup. Once enabled,
a configuration containing only this component and no ordinary strategies is
valid and must still start the signal runtime.

## 7. Market identity and candle semantics

| Property | Required value |
|---|---|
| Venue | Binance USD-M Futures |
| User-facing symbol | `BTC/USDT` |
| CCXT instrument | `BTC/USDT:USDT` |
| WebSocket stream symbol | `btcusdt` |
| Trigger timeframes | Native Binance `5m`, native Binance `15m` |
| Trend timeframe | Native Binance `4h` |
| Trigger policy | Closed candles only |

Do not resample M5 or M15 into H4. Subscribe to Binance's native H4 stream and
load native H4 REST history.

The current multiplexer indexes candles by their open timestamp. Normalize an
index value with this exact algorithm before any point-in-time comparison:

1. Parse it as a pandas/Python datetime.
2. If it is timezone-naive, interpret it as fixed UTC+07:00 because that is the
   current `DataNormalizer` storage convention.
3. If it is already timezone-aware, preserve its represented instant.
4. Convert the open timestamp to UTC.
5. Add the exact timeframe duration to obtain an aware UTC close timestamp.

Keep this conversion inside one tested helper. Never compare a naive stored
timestamp directly with an aware UTC timestamp, and never add or subtract
seven hours twice.

For a trigger candle closing at time `T`:

- only trigger rows with close time `<= T` may be used;
- the current trigger row must close exactly at `T`;
- the previous trigger row must close exactly one trigger interval before `T`;
- only H4 rows with close time `<= T` may be used;
- the selected H4 row must have the latest expected native UTC four-hour close
  at or before `T`; and
- an H4 candle closing exactly at `T` is available at `T`.

If the exact expected H4 row has not arrived yet at a shared timeframe
boundary, wait `context_settle_seconds` and retry the evaluation once. If it
is still absent or marked forming, record a structured warning and emit no
Telegram alert.

## 8. Indicator contract

All three timeframes use the same RSI bundle:

- Wilder RSI with period 21;
- recursive EMA with period 9 applied to RSI21; and
- linearly weighted moving average with period 45 applied to RSI21, using
  weights `1..45` with the newest observation carrying weight 45.

Reuse the already tested pure primitives exported by
`app.trading.strategy.core_v2_1.indicators`:

```python
rsi21 = rsi_wilder(frame["close"], period=21)
rsi_ema9 = ema(rsi21, period=9)
rsi_wma45 = wma(rsi21, period=45)
```

Import and call those primitives without altering their implementation or
Core V2.1 constants. Give columns in the new component the unambiguous names
`rsi21`, `rsi_ema9`, and `rsi_wma45`.

Readiness requirements:

- H4 needs at least 66 contiguous closed candles and a finite current RSI
  bundle.
- Each trigger timeframe needs at least 67 contiguous closed candles so the
  previous and current RSI bundles are both finite.
- Every close value used for an indicator must be numeric and finite.
- Any duplicate, backward, or gapped candle in the required contiguous tail
  makes that evaluation not ready.

Lock the recursive-indicator input window as follows for each timeframe:

1. Point-in-time filter to closed rows whose computed close time is no later
   than the requested as-of time.
2. Preserve input order; do not sort, deduplicate, or resolve conflicting rows
   silently. Duplicate or non-increasing timestamps make preparation not
   ready.
3. Find the most recent cadence gap and select the complete maximal contiguous
   suffix after that gap, ending at the expected current row.
4. Compute RSI21, EMA9, and WMA45 over that entire contiguous suffix, not only
   its last 66/67 rows.
5. Require at least 67 rows in the selected trigger suffix or 66 rows in the
   selected H4 suffix.

A gap older than the selected suffix is allowed because it explicitly starts
a new seed segment. A gap inside the selected suffix is impossible by
construction; if the suffix after the latest gap is too short, preparation is
not ready. This rule makes the rolling REST bootstrap behavior deterministic
without introducing Core V2.1's permanent anchor.

Do not use `pandas_ta`, `app.data.indicators.Indicators`, or its misleading
`rsi_14` output column for this feature. The result must not depend on whether
an optional indicator library happens to be installed.

## 9. Signal algorithm

Evaluate only when a new closed candle arrives on `5m` or `15m`. An H4 close
updates context but never directly emits an alert.

Given the previous and current trigger indicator points:

```text
fresh_bullish_cross =
    previous.rsi_ema9 <= previous.rsi_wma45
    AND
    current.rsi_ema9 > current.rsi_wma45
```

Given the latest eligible H4 indicator point:

```text
h4_bullish =
    h4.rsi21 > h4.rsi_ema9
    AND
    h4.rsi_ema9 > h4.rsi_wma45
```

Emit an alert if and only if:

```text
fresh_bullish_cross AND h4_bullish
```

Decision precedence is locked:

1. Preparation/readiness is evaluated first. A not-ready result never calls
   the decision evaluator.
2. For ready inputs, evaluate the fresh cross first. If it is false, return
   `NO_FRESH_BULLISH_CROSS` without using H4 alignment to choose the reason.
3. Only after a fresh cross passes, evaluate H4. If it is not strictly bullish,
   return `H4_NOT_BULLISH`.
4. Otherwise return `ALERT_FRESH_BULLISH_CROSS_H4_BULLISH`.

Important boundary rules:

- Equality on the previous trigger candle counts as being below for crossover
  detection: `previous EMA9 <= previous WMA45`.
- Equality on the current trigger candle is not a cross.
- Every H4 comparison is strict; equality anywhere fails the H4 gate.
- Do not require trigger-timeframe `RSI21 > EMA9` or `RSI21 > WMA45`; the
  product request requires only the trigger crossover plus the H4 gate.
- M5 and M15 are independent. If both cross on their respective candles, both
  alerts are valid, even if their close timestamps are equal.
- A fresh cross observed while H4 is not bullish is consumed. Do not alert
  later merely because H4 becomes bullish while EMA9 remains above WMA45; a
  new qualifying fresh cross is required.
- No cooldown is applied. Deduplication is by event identity, not elapsed
  wall-clock time.

## 10. Pure models and evaluator

Create the following frozen typed models under
`app/trading/strategy/btc_rsi_cross_alert/`:

```python
@dataclass(frozen=True)
class RsiBundlePoint:
    rsi21: float
    rsi_ema9: float
    rsi_wma45: float


@dataclass(frozen=True)
class BtcRsiCrossInput:
    symbol: str
    trigger_timeframe: str
    trigger_close_time: datetime
    trigger_close_price: Decimal
    previous_trigger: RsiBundlePoint
    current_trigger: RsiBundlePoint
    h4: RsiBundlePoint
    h4_close_time: datetime


@dataclass(frozen=True)
class BtcRsiCrossDecision:
    should_alert: bool
    event_id: str
    reason: str


@dataclass(frozen=True)
class BtcRsiCrossPreparation:
    input: BtcRsiCrossInput | None
    reason: str
```

Implement two separate pure functions. The preparation function is named
`prepare_btc_rsi_cross_input` and returns `BtcRsiCrossPreparation`. It accepts
the trigger and H4 DataFrames plus keyword-only `symbol`,
`trigger_timeframe`, `trigger_open_time`, `history_ready_at`, and an immutable
set of `observed_live_h4_closes`. The decision function is named
`evaluate_btc_rsi_cross`, accepts one `BtcRsiCrossInput`, and returns one
`BtcRsiCrossDecision`.

`prepare_btc_rsi_cross_input()` owns timestamp normalization, point-in-time
slicing, bootstrap eligibility, continuity, finite-value checks, recursive
indicator preparation, exact current-trigger selection, and exact H4 context
selection. `evaluate_btc_rsi_cross()` owns only the fresh-cross and H4 Boolean
decision.

Both functions must be pure: identical inputs produce identical outputs, with
no clock, network, filesystem, database, logging, Telegram, sleep, thread, or
mutable-global access. The worker obtains the current/history-ready times and
the live H4 confirmation set, then passes immutable values into preparation.

Use these exact preparation reasons:

- `READY`;
- `TRIGGER_UNSUPPORTED_TIMEFRAME`;
- `TRIGGER_CURRENT_ROW_MISSING`;
- `TRIGGER_INSUFFICIENT_CONTIGUOUS_HISTORY`;
- `TRIGGER_DUPLICATE_OR_NON_INCREASING_TIME`;
- `TRIGGER_NON_FINITE_DATA`;
- `H4_EXPECTED_CLOSE_MISSING`;
- `H4_LIVE_CLOSE_UNCONFIRMED`;
- `H4_INSUFFICIENT_CONTIGUOUS_HISTORY`;
- `H4_DUPLICATE_OR_NON_INCREASING_TIME`; and
- `H4_NON_FINITE_DATA`.

`input` is non-`None` if and only if `reason == "READY"`.

Use these exact decision reasons:

- `ALERT_FRESH_BULLISH_CROSS_H4_BULLISH`;
- `NO_FRESH_BULLISH_CROSS`; and
- `H4_NOT_BULLISH`.

Build the deterministic event ID from:

```text
btc-rsi-cross-v1 | BTC/USDT | trigger timeframe | UTC trigger close time
```

The stored ID may be a SHA-256 digest or an equally deterministic normalized
string. Telegram must display a short recognizable suffix derived from it.

## 11. Runtime and worker behavior

Create a dedicated queue-backed worker so indicator computation and Telegram
formatting never block multiplexer callbacks.

The worker must:

1. Accept closed `BTC/USDT` callbacks for `5m`, `15m`, and `4h`.
   M5/M15 callbacks are evaluation triggers; H4 callbacks only confirm that a
   native H4 candle has closed and never emit an alert by themselves.
2. Ignore all callbacks until initial history loading is declared complete.
3. At history completion, record an aware UTC history-ready time and a
   per-trigger bootstrap watermark equal to the newest eligible REST candle
   close for M5 and M15. Any later WebSocket callback whose close is at or
   before its timeframe's bootstrap watermark **or** at or before the
   history-ready time is historical for public-notification purposes and must
   be ignored.
4. Historical H4 rows closing at or before the history-ready instant may be
   trusted as closed; a later H4 row is eligible only after its closed H4
   WebSocket callback has been observed.
5. Read trigger and H4 DataFrames from `TimeframeMultiplexer` using defensive
   copies supplied by `get_dataframe()`.
6. Slice every DataFrame point-in-time to the trigger close before calculating
   indicators.
7. Retry once after `context_settle_seconds` only when exact H4 context for a
   shared boundary is not yet available.
8. Evaluate using the pure evaluator.
9. Send one message through
   `NotificationService.send_message(formatted_message,
   topic_id=config.telegram_topic_id)` when `should_alert` is true.
10. Remember the last evaluated trigger close and emitted event IDs separately
   for M5 and M15.
11. Ignore and structured-log duplicate, backward, or already-evaluated trigger
   callbacks.
12. Catch per-event failures, use the existing consecutive-failure budget, and
    report terminal worker failures to the debug Telegram topic.
13. Support bounded, idempotent shutdown through `request_stop()` and thread
    join, following the existing `StrategyWorker` lifecycle.

H4 boundary coordination must not depend on an H4 item being processed by the
same queue that is waiting for it. The multiplexer callback handles a live
closed H4 event synchronously: under a thread-safe `Condition`, add its aware
UTC close to the observed-H4 set and notify waiters; do not enqueue H4 for
normal worker processing. When a trigger needs an unconfirmed H4 close, the
worker waits on that condition for at most `context_settle_seconds`, which
releases the condition lock. It then prepares/evaluates exactly once more.
`request_stop()` must notify the condition so shutdown does not wait for the
full settle timeout.

Terminal-state precedence for each trigger event is locked:

- Do not advance `last_evaluated` while waiting for the one allowed H4 retry.
- After a ready decision—alert, no cross, or H4 rejection—advance
  `last_evaluated` for that trigger timeframe.
- After retry exhaustion or any other deterministic not-ready result, advance
  `last_evaluated`; a duplicate callback must not retry a terminally rejected
  candle.
- On an unexpected exception, do not advance `last_evaluated` until the event
  succeeds or its bounded failure budget is exhausted. Requeue that same event
  ahead of newer events while attempts remain. On reaching the configured
  `signal_runner.max_consecutive_failures`, advance the cursor, notify the
  debug topic once, and terminate this alert worker thread, matching the
  existing `StrategyWorker` terminal policy.
- Format first, call the notifier once, and add the event ID to the emitted-ID
  set immediately after `send_message()` returns. If formatting or the call
  raises, do not add it. Because delivery is best-effort, no delivered-message
  acknowledgement exists in v1.

The component must never open a `VirtualPosition`, call exchange order APIs,
or invoke the mechanical exit monitor.

### Startup bootstrap suppression

`BinanceStreamManager.fetch_initial_data()` currently forwards REST history
through the multiplexer, which fires close callbacks. Historical crosses must
not generate messages.

Add a backward-compatible optional history-complete hook to
`BinanceStreamManager`:

```python
history_complete_callback: Callable[[], None] | None = None
```

Required order inside `start()`:

1. load REST history for every target;
2. invoke `history_complete_callback` exactly once after all target fetch
   attempts return;
3. start the WebSocket loop.

The BTC alert worker's callback must synchronously discard events while its
history-ready event is unset. `history_complete_callback` records the UTC
history-ready time, computes the M5/M15 bootstrap watermarks from hydrated
frames, and sets that event.
Do not evaluate or alert immediately when history becomes ready; the first
eligible evaluation is a live closed M5 or M15 callback whose close is strictly
later than both the history-ready time and that timeframe's bootstrap
watermark. This remains true when a delayed WebSocket close duplicates the
last REST candle after readiness or closes in the narrow interval while REST
hydration is still running.

Existing SignalRunner workers must retain their current startup behavior.
The new stream-manager argument must be optional so every existing caller
continues to work unchanged.

### Restart and delivery semantics

V1 state is intentionally in memory:

- restart silently bootstraps history again;
- historical candles are not replayed as public alerts;
- only subsequent live trigger closes are eligible;
- repeated callbacks within one process are deduplicated; and
- Telegram remains the existing signal runtime's asynchronous best-effort
  delivery, not Core V2.1's durable outbox.

Document this limitation. Do not introduce SQLite or reuse the Core V2.1
state store/outbox in this implementation.

## 12. SignalRunner integration

Extend the signal configuration resolver and runner without changing ordinary
strategy behavior.

Add this explicit aggregate boundary in `app/signal/strategy_config.py`:

```python
@dataclass(frozen=True)
class ResolvedSignalRuntimeConfig:
    strategies: tuple[StrategyInstanceConfig, ...]
    btc_rsi_cross_alert: BtcRsiCrossAlertConfig | None
    debug_topic_id: int
```

`resolve_signal_runtime_config(raw)` validates the entire active component set
and returns this aggregate. Keep the existing `resolve_strategy_configs(raw)`
API backward compatible and returning only ordinary
`StrategyInstanceConfig` values for its existing callers/tests; internally it
may delegate to the aggregate resolver. It must not expose the BTC component
as a fake single-frame `StrategyInstanceConfig`.

Required integration behavior:

- `btc_rsi_cross_alert` is accepted in the existing `strategies:` list even
  though it is not registered in the trading/backtest `STRATEGY_MAP`.
- The resolver creates a typed BTC alert config and includes its three targets
  in the union passed to `TimeframeMultiplexer` and `BinanceStreamManager`.
- `SignalRunner` creates one BTC alert worker and one thread for the active
  entry.
- The runner passes a history-complete callback that enables all active BTC
  alert workers after REST hydration.
- Ordinary entries continue to resolve and instantiate through
  `STRATEGY_MAP` and `StrategyWorker` exactly as before.
- Topic uniqueness validation covers ordinary strategies, the BTC alert, and
  the debug topic together.
- A config with zero ordinary strategies and one active BTC alert still starts
  the multiplexer, stream, worker, notifier, health/status lifecycle, and
  graceful shutdown.
- A config with no active ordinary strategy and no active BTC alert retains
  the existing clean no-op startup behavior.
- Shutdown sends no virtual-position summary for the BTC alert because it owns
  no positions.
- `/test_signal` behavior for existing strategies remains unchanged; extending
  it to this alert is a non-goal. Keep `SignalRunner.strategies` limited to
  ordinary `StrategyInstanceConfig` entries so `/test_signal` never creates a
  fake virtual-position card for this alert. An alert-only configuration may
  therefore omit the `/test_signal` command.
- Add `SignalRunner.alert_components`, returning a defensive tuple containing
  the active typed BTC config when enabled. Keep ordinary workers in
  `_workers`, alert workers in `_alert_workers`, and join both thread groups on
  shutdown. Virtual-position/status and shutdown-broadcast code continues to
  inspect ordinary workers/strategies only.
- `_build_signal_startup_message()` must identify this component as
  `BTC/USDT · 5m,15m · H4 filter`; it must not display the global symbol count
  or global single timeframe for this entry.

Prefer a small explicit resolver/factory for signal-only component types over
adding `btc_rsi_cross_alert` to the trading/backtest strategy loader. It must
not appear in the backtest UI because no trade lifecycle exists.

## 13. Telegram message contract

Use deterministic HTML-safe formatting. A valid M5 example is:

```text
🟢 BTC RSI BULLISH CROSS

Timeframe: 5m
Candle close: 2026-08-24 09:35:00 UTC
BTC close: 64,321.50

M5 RSI21: 53.42
M5 EMA9(RSI): 48.76
M5 WMA45(RSI): 48.55

H4 trend: BULLISH ✅
H4 RSI21 / EMA9 / WMA45: 61.20 / 57.40 / 54.80
Event: a1b2c3d4
```

For an M15 trigger, labels must say `15m` and `M15`. Requirements:

- show the UTC trigger close time;
- show the trigger candle BTC close price;
- show trigger RSI21, EMA9, and WMA45 to two decimals;
- show H4 RSI21, EMA9, and WMA45 to two decimals;
- include the short event ID;
- escape all dynamic text before HTML delivery; and
- do not display entry, SL, TP, leverage, position, or expected-profit fields.

No Telegram message is sent for not-ready data, no-cross decisions, a bearish
or neutral H4 gate, bootstrap history, duplicate callbacks, or internal retry.

## 14. Structured logging

Use `structlog`; do not add `print()` calls. At minimum emit these events with
the shown core fields:

| Event | Required fields |
|---|---|
| `btc_rsi_cross_worker_started` | topic, targets |
| `btc_rsi_cross_history_ready` | target count |
| `btc_rsi_cross_not_ready` | timeframe, trigger close, reason |
| `btc_rsi_cross_h4_retry` | timeframe, trigger close, expected H4 close |
| `btc_rsi_cross_decision` | timeframe, trigger close, decision reason, event ID |
| `btc_rsi_cross_alert_enqueued` | timeframe, trigger close, event ID, topic |
| `btc_rsi_cross_duplicate_ignored` | timeframe, trigger close, event ID |
| `btc_rsi_cross_worker_error` | timeframe, trigger close, attempt |
| `btc_rsi_cross_worker_stopped` | last evaluated M5/M15 closes |

Normal no-cross decisions should use debug level. Readiness failures and
duplicates should not flood Telegram.

## 15. File-level implementation map

### New files

| File | Responsibility |
|---|---|
| `app/trading/strategy/btc_rsi_cross_alert/__init__.py` | Public pure-domain exports; no loader registration |
| `app/trading/strategy/btc_rsi_cross_alert/models.py` | Frozen input, point, decision, and event models |
| `app/trading/strategy/btc_rsi_cross_alert/evaluator.py` | Pure indicator preparation and signal decision |
| `app/trading/strategy/core_v2_1/model_validation.py` | Shared validation primitives for immutable Core V2.1 models |
| `app/trading/strategy/core_v2_1/input_models.py` | Core V2.1 point-in-time snapshot and evaluator-input models |
| `app/trading/strategy/core_v2_1/decision_models.py` | Core V2.1 state, event, decision, and result models |
| `app/trading/strategy/core_v2_1/models.py` | Compatibility exports for the split Core V2.1 model modules |
| `app/signal/btc_rsi_cross_alert/__init__.py` | Runtime/configuration exports |
| `app/signal/btc_rsi_cross_alert/config.py` | Frozen config and strict resolver/validation |
| `app/signal/btc_rsi_cross_alert/formatter.py` | Deterministic HTML-safe Telegram card |
| `app/signal/btc_rsi_cross_alert/worker.py` | Queue, bootstrap gate, point-in-time adapter, retry, dedupe, lifecycle |
| `app/signal/btc_rsi_cross_alert/worker_support.py` | Multiplexer preparation and failure-budget helpers used by the worker |

### Existing files expected to change

| File | Required change |
|---|---|
| `app/data/stream_manager.py` | Add optional history-complete hook and tests |
| `app/signal/strategy_config.py` | Resolve special signal component and enforce cross-component topic uniqueness |
| `app/signal/runner.py` | Union targets, build/start/stop BTC alert worker, support alert-only config |
| `main.py` | Render accurate startup text and keep trade-like `/test_signal` scoped to ordinary strategies |
| `config.yaml` | Add the locked component entry, checked in disabled until topic verification |
| `docs/02_architecture/system-overview.md` | Show the BTC multi-timeframe alert branch |
| `docs/03_setup_and_installation/configuration.md` | Document configuration and validation |
| `docs/05_data_pipeline/live-data-flow.md` | Document three-stream data flow and bootstrap gate |
| `docs/07_trading_strategies/signal-bot.md` | Document runner integration and non-goals |
| `docs/07_trading_strategies/strategy-reference.md` | Add alert semantics and parameters |
| `docs/08_execution_and_oms/notifications.md` | Add Telegram routing/message semantics |
| `docs/11_testing_and_backtesting/testing-strategy.md` | Add focused verification command/matrix |
| `docs/INDEX.md` | Link this specification from the task routing table |
| `tasks/todo.md` | Implementation checklist and exact verification evidence |

Do not add this component to `app/trading/strategy/loader.py`, the backtest
database seed, or the UI strategy list.

## 16. Required tests

Create focused test modules with deterministic synthetic candles and no real
network or Telegram calls.

### `tests/test_btc_rsi_cross_alert_config.py`

- accepts the exact locked config;
- canonical target set is `{(BTC/USDT, 5m), (BTC/USDT, 15m),
  (BTC/USDT, 4h)}`;
- rejects wrong symbol, missing/duplicate/wrong trigger timeframes, wrong H4,
  wrong periods, invalid settle delay, duplicate component, and topic
  collisions;
- accepts alert-only runtime with zero ordinary strategies; and
- ignores a disabled component without reserving its topic.

### `tests/test_btc_rsi_cross_alert_preparation.py`

- naive stored candle opens are interpreted as fixed UTC+07:00, converted to
  UTC, and advanced by the timeframe exactly once;
- already-aware timestamps represent the same instant without a second
  timezone shift;
- current trigger and expected H4 rows are selected exactly as of `T`;
- a future/forming H4 candle is never used;
- post-bootstrap H4 closes require membership in the observed-live set;
- 67 trigger rows and 66 H4 rows are the exact readiness boundaries;
- duplicate/non-increasing timestamps and non-finite data return their exact
  preparation reasons;
- the maximal contiguous suffix after the latest cadence gap is used in full;
- an old gap is allowed when the suffix remains long enough;
- a recent gap that leaves a short suffix is not ready;
- widening the same contiguous input suffix produces the expected deterministic
  primitive result; and
- `input` is non-`None` exactly when the reason is `READY`.

### `tests/test_btc_rsi_cross_alert_evaluator.py`

- exact bullish cross alerts when H4 is strictly bullish;
- previous equality then current greater counts as a cross;
- remaining above without a new cross does not alert;
- current equality does not alert;
- downward cross does not alert;
- strict H4 `RSI21 > EMA9 > WMA45` passes;
- equality at either H4 boundary fails;
- bearish/neutral H4 suppresses an otherwise valid cross;
- a cross rejected by H4 is not emitted later when only H4 turns bullish;
- M5 and M15 create different deterministic event IDs at the same close;
- identical input reproduces the identical decision and event ID;
- trigger RSI position relative to its EMA/WMA adds no undocumented filter;
- no-cross reason takes precedence over H4 alignment; and
- the point-only evaluator has no readiness, DataFrame, clock, or I/O behavior.

Use golden indicator vectors or compare the new adapter directly with the
existing Core V2.1 primitive outputs. Never patch the evaluator into returning
the condition being tested.

### `tests/test_btc_rsi_cross_alert_formatter.py`

- M5 and M15 labels are correct;
- all required values and event suffix appear;
- timestamp is UTC;
- numeric formatting is stable; and
- dynamic HTML is escaped.

### `tests/test_btc_rsi_cross_alert_worker.py`

- bootstrap callbacks are silently discarded;
- history-ready transition itself sends no alert;
- a delayed WebSocket duplicate at or before each M5/M15 bootstrap watermark
  remains silent after history-ready is set;
- a candle closing after the REST watermark but at or before history-ready is
  also suppressed;
- closed M5/M15 callbacks evaluate;
- open candles never trigger alerts, and H4 callbacks only mark context closed;
- a post-bootstrap H4 row cannot be used until its live closed callback is
  observed;
- exact H4 is selected as of the trigger close;
- boundary race retries once and succeeds when H4 arrives;
- H4 confirmation is recorded synchronously and wakes a waiting trigger
  without requiring the H4 event to pass through the worker queue;
- retry exhaustion fails closed without Telegram;
- duplicate and backward callbacks are ignored;
- `last_evaluated` advances under every terminal precedence rule and remains
  unchanged during an allowed retry or retryable exception;
- one event is retried ahead of newer events and terminal failure kills only
  the alert worker after the configured budget;
- simultaneous valid M5/M15 closes produce two alerts;
- Telegram uses the configured topic;
- no virtual position is opened;
- per-event exception budget and debug notification work; and
- stop is bounded and idempotent.

### Existing integration tests to extend

- `tests/test_stream_manager_multi_tf.py`: history callback order and exactly
  once behavior, including one failed target fetch.
- `tests/test_signal_runner.py`: mixed ordinary/BTC workers, union targets,
  alert-only startup, no-active no-op, topic collision, shutdown.
- `tests/test_signal_runner_integration.py`: real multiplexer and BTC worker
  with mocked stream/notifier; one qualifying candle reaches the correct
  Telegram topic and never creates a virtual position.
- `tests/test_main_signal_mode.py`: startup text reports BTC plus M5/M15/H4
  accurately, and alert-only mode does not build a fake virtual-position test
  callback.
- Run all existing signal, stream, multiplexer, notification, and Core V2.1
  tests to prove backward compatibility.

## 17. Verification commands

Run with the existing Conda environment. First record its interpreter version:

```powershell
conda run -n rsi python --version
```

Focused feature verification:

```powershell
conda run -n rsi python -m pytest `
  tests/test_btc_rsi_cross_alert_config.py `
  tests/test_btc_rsi_cross_alert_preparation.py `
  tests/test_btc_rsi_cross_alert_evaluator.py `
  tests/test_btc_rsi_cross_alert_formatter.py `
  tests/test_btc_rsi_cross_alert_worker.py `
  tests/test_stream_manager_multi_tf.py `
  tests/test_signal_runner.py `
  tests/test_signal_runner_integration.py `
  tests/test_main_signal_mode.py -q
```

Regression verification:

```powershell
conda run -n rsi python -m pytest tests -q
conda run -n rsi python -m ruff check app tests
conda run -n rsi python -m compileall -q app tests
conda run -n rsi python -c "from app.signal.btc_rsi_cross_alert.config import resolve_btc_rsi_cross_alert_config; print('btc_rsi_cross_alert import OK')"
git diff --check
Test-Path docs\07_trading_strategies\btc-rsi-cross-alert-spec.md
Select-String -Path docs\INDEX.md -Pattern "btc-rsi-cross-alert-spec.md"
```

Configuration smoke verification must instantiate `SignalRunner` with a
mocked stream/notifier for:

1. one ordinary strategy plus the BTC alert;
2. only the BTC alert; and
3. all components disabled.

Documentation validation also requires a manual diff review proving that every
documentation file in section 15 was updated for each delivered code path and
that its examples match the accepted config schema. Do not perform a live
Telegram send as part of automated verification. `/test_signal` does not cover
this component. If the operator separately authorizes a live smoke, use a
purpose-built BTC alert test card marked `[FAKE TEST]`; otherwise stop at the
mocked notifier integration test.

## 18. Acceptance criteria

The feature is accepted only when all statements are true:

- The checked-in runtime remains `bot.mode: "signal"` and existing strategies
  still start normally.
- When the component is active, native BTC M5, M15, and H4 streams are present
  in the stream target union.
- No alert is possible from a forming or historical bootstrap candle, including
  a delayed WebSocket duplicate at or before a bootstrap watermark and any
  trigger that closed no later than the history-ready instant.
- A fresh M5 or M15 bullish crossover enqueues exactly one Telegram message
  when the exact eligible H4 context is strictly bullish.
- The same crossover enqueues no message when H4 is neutral, bearish, missing,
  forming, stale, unconfirmed at a live boundary, or not indicator-ready.
- M5 and M15 operate independently and can both alert at one timestamp.
- Duplicate callbacks cannot duplicate an alert within one process.
- No code path can place an order or create a virtual position for this
  component.
- No existing Core V2.1 file or behavior changes.
- Existing single-timeframe strategy configuration remains backward
  compatible.
- The checked-in BTC component remains disabled until the Telegram topic is
  operator-verified.
- Focused tests, the full suite, Ruff, compilation, and config smoke checks all
  pass with exact results recorded.
- All documentation listed in the implementation map reflects the delivered
  behavior.

## 19. Rollout and rollback

### Rollout

1. Deploy with `active: false` and verify the existing signal bot is unchanged.
2. Confirm that topic `1007` exists, then enable the component.
3. Verify the target-union log contains BTC M5, M15, and H4.
4. Confirm history readiness without any historical alert burst.
5. Run an offline synthetic integration smoke test.
6. Observe the first live M5 and M15 closes and verify decision logs.
7. Keep order execution modes unchanged.

### Rollback

Set the component entry to `active: false` and redeploy. Because v1 owns no
orders, positions, or persistent schema, rollback requires no trade cleanup or
database migration. Existing SignalRunner strategies continue independently.

## 20. Explicit v1 limitations

- Indicator history is seeded from the current REST bootstrap window rather
  than a permanent anchor. With 300 candles this is adequate for the requested
  alert, but it is not the audit-grade anchored reproducibility of Core V2.1.
- Alert deduplication is in memory. Restart bootstrap suppression prevents a
  normal historical resend, but the design does not promise exactly-once
  delivery across crash boundaries.
- Telegram uses the existing asynchronous notification queue and does not have
  a durable retry outbox.
- Only Binance BTC/USDT and the fixed M5/M15/H4 rules are supported.

Any request to remove these limitations is a separate versioned scope and
must not silently expand this v1 implementation.
