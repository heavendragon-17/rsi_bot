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
3. On M15, alert when EMA9 of RSI crosses upward through WMA45 of RSI.
4. On M5, do not require a new cross; require the current closed candle to
   satisfy `RSI21 > EMA9(RSI21) > WMA45(RSI21)`.
5. Alert only when the selected fully closed H4 candle closes strictly above
   EMA21 of H4 close price.
6. Do not calculate or evaluate EMA9(RSI21) or WMA45(RSI21) for the H4 gate.
7. Send the alert to Telegram.
8. For M5 only, also require an RSI smoothing-line spread greater than 2 and
   WMA45(RSI21) greater than 45. On both trigger timeframes, require the trigger
   candle close to be strictly above EMA21(price) of that same timeframe.
9. After an M5 alert is emitted, suppress further qualifying M5 alerts for 15
   minutes measured by candle close time. M15 has no cooldown.

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
- Detect a fresh bullish EMA9/WMA45 crossover on M15, or a strict bullish
  RSI21/EMA9/WMA45 alignment on M5.
- Gate every M5/M15 signal using the latest fully closed H4 candle available at
  the trigger candle's close time.
- Deliver M5 and M15 alerts to separate configured Telegram topics.
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

Add the following component entry to `config.yaml`. The M5 and M15 topic IDs
are intentionally separate because their checker logic is different. The
ordinary `rsi_no_retest` entry remains disabled, so topic `1003` is available
for M15 BTC alerts.

```yaml
strategies:
  - name: btc_rsi_cross_alert
    active: true
    telegram_topic_id: 1147          # M5 checker
    m15_telegram_topic_id: 1003      # M15 checker
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
- `telegram_topic_id` (M5) or `m15_telegram_topic_id` (M15) is missing, is not
  integer-coercible, collides with the debug topic, collides with another
  active strategy topic, or the two topic IDs are equal; or
- more than one active `btc_rsi_cross_alert` entry exists.

These values are explicit in configuration for auditability, but they are
locked for v1. Do not silently accept other values.

The checked-in configuration uses the operator-verified topics `1147` and
`1003`. A configuration containing only this component and no ordinary
strategies is valid and must still start the signal runtime.

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

Trigger preparation also computes EMA(21) directly over the trigger
timeframe's close-price series and stores the current value as
`trigger_price_ema21`. Both M5 and M15 require their trigger close price to be
strictly above this value.
H4 preparation computes EMA(21) directly over the selected contiguous H4
close-price suffix and stores both the selected H4 close and H4 price EMA21.

Readiness requirements:

- H4 needs at least 21 contiguous closed candles and a finite current price
  EMA21.
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
4. For trigger data, compute RSI21, EMA9, and WMA45 over the entire contiguous
   suffix, not only its last 67 rows. For H4, compute price EMA21 over its
   entire contiguous suffix.
5. Require at least 67 rows in the selected trigger suffix or 21 rows in the
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

For M15, given the previous and current trigger indicator points:

```text
fresh_bullish_cross =
    previous.rsi_ema9 <= previous.rsi_wma45
    AND
    current.rsi_ema9 > current.rsi_wma45
```

Given the latest eligible fully closed H4 candle and its price EMA21:

```text
h4_bullish =
    h4_close_price > h4_price_ema21
```

M15 emits an alert if and only if:

```text
fresh_bullish_cross
AND h4_bullish
AND trigger_close_price > trigger_price_ema21
```

M5 uses only the current trigger indicator point:

```text
m5_bullish_alignment =
    current.rsi21 > current.rsi_ema9
    AND
    current.rsi_ema9 > current.rsi_wma45
```

M5 emits an alert if and only if `m5_bullish_alignment`, `h4_bullish`, and all
three additional conditions below are true:

```text
current.rsi_ema9 - current.rsi_wma45 > 2
current.rsi_wma45 > 45
trigger_close_price > trigger_price_ema21
```

All comparisons are strict. Equality with spread `2`, WMA45 value `45`, or
price EMA21 fails. The spread and WMA45-level conditions do not apply to M15;
the trigger close/EMA21(price) condition applies independently to both M5 and
M15.

M15 decision precedence remains:

1. Preparation/readiness is evaluated first. A not-ready result never calls
   the decision evaluator.
2. For ready inputs, evaluate the fresh cross first. If it is false, return
   `NO_FRESH_BULLISH_CROSS` without using the H4 price gate to choose the reason.
3. Only after a fresh cross passes, evaluate H4. If H4 close is not strictly
   above H4 EMA21(price), return `H4_CLOSE_NOT_ABOVE_EMA21`.
4. Only after the cross and H4 gate pass, require M15 close > M15
   EMA21(price); otherwise return `M15_CLOSE_NOT_ABOVE_EMA21`.
5. Otherwise return `ALERT_FRESH_BULLISH_CROSS_H4_BULLISH`.

M5 decision precedence is:

1. Require strict `RSI21 > EMA9 > WMA45`; otherwise return
   `M5_RSI21_EMA9_WMA45_ALIGNMENT_NOT_BULLISH`.
2. Require H4 close > H4 EMA21(price); otherwise return
   `H4_CLOSE_NOT_ABOVE_EMA21`.
3. Evaluate spread, WMA45 level, then close-versus-price-EMA21 in that order.
   Return the matching M5 rejection reason on the first failure.
4. Otherwise return `ALERT_M5_BULLISH_ALIGNMENT_H4_BULLISH`.

Important boundary rules:

- Equality on the previous trigger candle counts as being below for crossover
  detection: `previous EMA9 <= previous WMA45`.
- Equality on the current trigger candle is not a cross.
- The two crossover boundary rules above apply to M15 only. M5 does not inspect
  the previous trigger point when deciding whether to alert.
- The H4 close/EMA21(price) comparison is strict; equality fails the H4 gate.
- H4 RSI21, EMA9(RSI21), and WMA45(RSI21) are not calculated or evaluated by
  this feature.
- M5 alone requires EMA9(RSI21) − WMA45(RSI21) > 2 and WMA45(RSI21) > 45.
- Both M5 and M15 require their trigger close > EMA21(price) on the same
  trigger timeframe. Equality fails.
- M5 requires strict current-candle `RSI21 > EMA9 > WMA45`; M15 does not add
  an RSI21-position filter to its fresh-cross rule.
- M5 and M15 are independent. If M5 has a qualifying bullish alignment while
  M15 has a fresh cross, both alerts are valid at the same timestamp.
- An M15 fresh cross observed while H4 is not bullish is consumed. Do not alert
  later merely because H4 price moves above EMA21; M15
  requires a new qualifying fresh cross. M5 evaluates each new closed candle's
  current alignment independently.
- After an M5 alert at close time `T`, qualifying M5 candles with close times
  before `T + 15 minutes` are suppressed. Therefore `T+5m` and `T+10m` fail
  the cooldown, while `T+15m` is eligible. Only a successfully emitted M5
  alert resets the cooldown. M15 is independent and has no cooldown.
- Deduplication remains based on candle event identity and per-timeframe cursor;
  the cooldown uses candle close time, never the process wall clock.

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
    trigger_price_ema21: Decimal
    previous_trigger: RsiBundlePoint
    current_trigger: RsiBundlePoint
    h4_close_price: Decimal
    h4_price_ema21: Decimal
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

Implement two shared pure functions. The preparation function is named
`prepare_btc_rsi_cross_input` and returns `BtcRsiCrossPreparation`. It accepts
the trigger and H4 DataFrames plus keyword-only `symbol`,
`trigger_timeframe`, `trigger_open_time`, `history_ready_at`, and an immutable
set of `observed_live_h4_closes`. The decision function is named
`evaluate_btc_rsi_cross`, accepts one `BtcRsiCrossInput`, and returns one
`BtcRsiCrossDecision`.

`prepare_btc_rsi_cross_input()` owns timestamp normalization, point-in-time
slicing, bootstrap eligibility, continuity, finite-value checks, recursive
indicator preparation, exact current-trigger selection, and exact H4 context
selection. `evaluate_btc_rsi_cross()` owns the M15 fresh-cross and shared H4
price-gate decision. `evaluate_m15_cross()` adds the M15 price-EMA21 filter.
`evaluate_m5_cross()` owns the M5 alignment, H4, and M5-only filter decision.

Expose timeframe-specific entry points in two separate modules:

- `m5_checker.py` fixes `trigger_timeframe="5m"` for preparation, accepts only
  prepared M5 inputs, and enforces the three mandatory M5-only filters;
- `m15_checker.py` fixes `trigger_timeframe="15m"` for preparation and accepts
  only prepared M15 inputs for evaluation.

The worker must dispatch through these entry points. Both delegate shared
indicator preparation to `evaluator.py`. M15 delegates fresh-cross/H4 decision
math to the shared evaluator and then applies its price-EMA21 filter; M5
deliberately replaces fresh-cross with its own current-candle alignment and
additional filters.

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
- `ALERT_M5_BULLISH_ALIGNMENT_H4_BULLISH`;
- `NO_FRESH_BULLISH_CROSS`;
- `H4_CLOSE_NOT_ABOVE_EMA21`;
- `M5_RSI21_EMA9_WMA45_ALIGNMENT_NOT_BULLISH`;
- `M5_EMA9_WMA45_SPREAD_NOT_ABOVE_2`;
- `M5_WMA45_NOT_ABOVE_45`; and
- `M5_CLOSE_NOT_ABOVE_EMA21`; and
- `M15_CLOSE_NOT_ABOVE_EMA21`.

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
9. For a qualifying M5 decision, apply the 15-minute candle-close cooldown.
   A suppressed candle remains terminally evaluated but is not added to the
   emitted-event-ID set and does not move the last-M5-alert timestamp.
10. Send one message through
    `NotificationService.send_message(formatted_message,
    topic_id=config.topic_id_for(trigger_timeframe))` when `should_alert` is
    true. M5 therefore routes to topic `1147` and M15 to topic `1003` in the
    checked-in configuration.
11. Remember the last evaluated trigger close and emitted event IDs separately
   for M5 and M15.
12. Remember the last successfully emitted M5 trigger close separately from
    `last_evaluated`.
13. Ignore and structured-log duplicate, backward, or already-evaluated trigger
   callbacks.
14. Catch per-event failures, use the existing consecutive-failure budget, and
    report terminal worker failures to the debug Telegram topic.
15. Support bounded, idempotent shutdown through `request_stop()` and thread
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
- A qualifying M5 decision suppressed by cooldown also advances
  `last_evaluated`, but neither changes `last_m5_alert_close` nor enters the
  emitted-event-ID set.
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
🟢 BTC RSI BULLISH ALIGNMENT

Timeframe: 5m
Candle close: 2026-08-24 16:35:00 UTC+7
BTC close: 64,321.50
M5 EMA21(price): 64,000.00
M5 close > EMA21(price): 64,321.50 > 64,000.00 ✅

Current M5 RSI21: 53.42
Current M5 EMA9(RSI21): 50.80
Current M5 WMA45(RSI21): 48.55

M5 RSI alignment: 53.42 > 50.80 > 48.55 ✅
M5 EMA9(RSI21) - WMA45(RSI21): 2.25 > 2.00 ✅
M5 WMA45(RSI21) > 45.00: 48.55 > 45.00 ✅

H4 close: 65,012.34
H4 EMA21(price): 64,001.23
H4 close > EMA21(price): 65,012.34 > 64,001.23 ✅

Duplicate check: NEW event ✅
Event: a1b2c3d4
```

For an M15 trigger, the title remains `BTC RSI BULLISH CROSS` and labels must
say `15m` and `M15`. Requirements:

- show the chart timeframe and UTC+7 trigger candle close time;
- show the trigger candle BTC close price;
- show trigger-timeframe price EMA21 and the strict close > EMA21 comparison;
- show current trigger RSI21, EMA9(RSI21), and WMA45(RSI21) to two decimals;
- show previous and current EMA9/WMA45 values to verify the fresh bullish cross;
- show H4 close and H4 EMA21(price) to two decimals;
- show each signal condition with the values compared and a pass/fail marker;
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
| `btc_rsi_cross_m5_cooldown_suppressed` | trigger close, last alert close, next eligible close, event ID |
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
| `app/trading/strategy/btc_rsi_cross_alert/m5_checker.py` | M5-only preparation and decision entry point |
| `app/trading/strategy/btc_rsi_cross_alert/m15_checker.py` | M15-only preparation and decision entry point |
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
- 67 trigger rows and 21 H4 rows are the exact readiness boundaries;
- duplicate/non-increasing timestamps and non-finite data return their exact
  preparation reasons;
- the maximal contiguous suffix after the latest cadence gap is used in full;
- an old gap is allowed when the suffix remains long enough;
- a recent gap that leaves a short suffix is not ready;
- widening the same contiguous input suffix produces the expected deterministic
  primitive result; and
- `input` is non-`None` exactly when the reason is `READY`.

### `tests/test_btc_rsi_cross_alert_evaluator.py`

- exact bullish cross alerts when H4 close is strictly above H4 EMA21(price);
- previous equality then current greater counts as a cross;
- remaining above without a new cross does not alert;
- current equality does not alert;
- downward cross does not alert;
- strict H4 close > EMA21(price) passes;
- equality between H4 close and EMA21(price) fails;
- H4 close at or below EMA21(price) suppresses an otherwise valid cross;
- a cross rejected by H4 is not emitted later when only H4 turns bullish;
- M5 and M15 create different deterministic event IDs at the same close;
- identical input reproduces the identical decision and event ID;
- trigger RSI position relative to its EMA/WMA adds no undocumented filter;
- no-cross reason takes precedence over the H4 price gate; and
- the point-only evaluator has no readiness, DataFrame, clock, or I/O behavior.

Use golden indicator vectors or compare the new adapter directly with the
existing Core V2.1 primitive outputs. Never patch the evaluator into returning
the condition being tested.

### `tests/test_btc_rsi_cross_alert_timeframe_checkers.py`

- M15 matches the shared fresh-cross/H4 decision when its price filter passes;
- M5 alerts on strict current `RSI21 > EMA9 > WMA45` even when the previous
  candle was already aligned and there is no new cross;
- M5 rejects equality or bearish ordering at either alignment boundary;
- each checker rejects a prepared input belonging to the other timeframe;
- each preparation entry point locks its own timeframe;
- worker preparation dispatch selects exactly the matching checker;
- M5 rejects spread equal to or below 2, WMA45 equal to or below 45, and BTC
  close equal to or below EMA21(price);
- M5 alerts when all three additional filters pass;
- M15 rejects its close equal to or below M15 EMA21(price); and
- M15 remains unaffected by the M5-only spread and WMA45-level filters.

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
- M5 alerts at +5m and +10m are cooldown-suppressed while +15m is allowed;
- the M5 cooldown does not suppress a simultaneous valid M15 alert;
- M5 Telegram alerts use the configured M5 topic and M15 alerts use the
  configured M15 topic;
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
  tests/test_btc_rsi_cross_alert_timeframe_checkers.py `
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
- A qualifying M5 bullish alignment or fresh M15 bullish crossover enqueues
  exactly one Telegram message when the exact eligible H4 context has
  close > EMA21(price), provided M5 also passes its three extra filters.
- The same crossover enqueues no message when H4 close is less than or equal
  to EMA21(price), or when H4 context is missing, forming, stale, unconfirmed
  at a live boundary, or not price-EMA-ready.
- An M5 alignment enqueues no message when its RSI spread is <= 2, its RSI
  WMA45 is <= 45, or its BTC close is <= EMA21(price).
- M5 and M15 operate independently and can both alert at one timestamp.
- After a qualifying M5 alert, qualifying closes at +5m and +10m enqueue no
  message; a qualifying close at +15m may enqueue the next M5 message.
- Duplicate callbacks for one candle remain suppressed by event identity.
- M15 behavior remains independent of the M5 spread and WMA45-level filters,
  but independently requires M15 close > M15 EMA21(price).
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

1. Keep the ordinary `rsi_no_retest` strategy disabled and enable the BTC
   component with M5 topic `1147` and M15 topic `1003`.
2. Verify that topics `1147` and `1003` exist in the configured supergroup.
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
