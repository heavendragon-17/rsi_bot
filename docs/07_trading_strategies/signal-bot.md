# Signal Bot — Multi-Strategy Runner Spec (v1)

> Design reference for `SignalRunner`, the multi-strategy signal-only runtime.
> Use this doc as the source of truth for implementation. Read
> [strategy-pattern.md](strategy-pattern.md) first for the `analyze()` contract.

---

## Implementation Status (v1 shipped)

The v1 runtime is implemented under `app/signal/` and wired into `main.py`
via `bot.mode: "signal"`. The file-by-file list in §13 is complete; the
rollout slices in §14 were merged as separate commits.

**v1 deviations from the spec below** — all intentional, locked in by tests:

| Area | Spec | v1 | Reason |
|------|------|-----|--------|
| VP store keying | `close(signal_id)` / `update_sl(signal_id)` | `close(strategy_name, symbol)` / `update_sl(strategy_name, symbol, new_sl)` | Callers never hold `signal_id`; they have `(strategy, symbol)`. `signal_id` stays on the VP for formatting. |
| `VirtualPosition.tp_hits` | `set[int]` | `frozenset[int]` | Frozen dataclass immutability; state transitions produce new VPs via `dataclasses.replace`. |
| `VirtualPosition.side` | `Literal["LONG","SHORT"]` | plain `str` with the same values | Matches the codebase's `SIDE_BUY`/`SIDE_SELL` convention. |
| Signal-id prefix | "3–4 chars" | first 4 chars of `strategy_name.replace("_", "").upper()` | Makes `rsi_no_retest`/`rsi_wma_retest`/`rsi_momentum` unambiguous (`RSIN`/`RSIW`/`RSIM`). Explicit `id_prefix` config deferred per §15. |
| `as_legacy_dict()` | shim for existing strategies | Implemented; mirrors `AppConfig.to_legacy_dict()` for the subset of keys strategies read. | No ctor changes needed in v1 strategies. |

**Known behavioral defaults:**

* Signal-bot messages are plain text (no HTML / parse_mode). The formatter
  lives in `app/signal/signal_formatter.py`.
* Worker threads are `daemon=True`; shutdown waits up to
  `SIGNAL_SHUTDOWN_JOIN_SECONDS = 10` per worker before force-aborting via
  process exit.
* `VirtualPositionStore` has a **single-writer-per-strategy** concurrency
  contract enforced by the thread-per-strategy model (spec §16). No CAS
  primitive — if that invariant ever breaks, add an `apply(key, fn)` method
  under the existing lock.

Cross-references for implementation details:

* Config schema: [docs/03_setup_and_installation/configuration.md](../03_setup_and_installation/configuration.md#signal-mode-schema)
* Multi-TF data flow: [docs/05_data_pipeline/live-data-flow.md](../05_data_pipeline/live-data-flow.md#signal-bot-branch-multi-tf)
* Telegram topic routing: [docs/08_execution_and_oms/notifications.md](../08_execution_and_oms/notifications.md#telegram-topic-routing-signal-mode)
* Architecture diagram: [docs/02_architecture/system-overview.md](../02_architecture/system-overview.md#signal-bot-data-flow-simplified)

---

## 1. Goals & Non-Goals

### Goals (v1)
- Run N strategies concurrently as a **signal bot** (no order execution).
- Each strategy emits entry signals to its **own Telegram topic** in a single group.
- Each strategy tracks **in-memory "virtual positions"** for its own signals, firing candle-close SL and TP exit advisories.
- Per-strategy config overrides for `symbols`, `timeframe`, `risk`.
- Per-strategy `active: true/false` gate.
- Graceful-shutdown broadcast listing open virtual positions per strategy.
- Live-trading `MultiSymbolRunner` is **untouched**; `SignalRunner` is additive.

### Non-Goals (v1)
- Multi-strategy backtest (deferred).
- Multiple instances of the same strategy class with different params.
- Persisted virtual positions, DB-backed state, restart recovery.
- Confluence / cross-strategy aggregation.
- Taken/Skipped UX (`/skip` commands, inline buttons).
- Capital allocation / position sizing in messages.
- Tick-level SL/TP checks (candle-close only).
- Scale-in (one VP per `(strategy, symbol)` — see §6).

---

## 2. Architecture Overview

### New package: `app/signal/`

```
app/signal/
    __init__.py
    runner.py               # SignalRunner (SIGTERM handling, lifecycle)
    strategy_worker.py      # per-strategy thread: candle loop + analyze + VP check
    virtual_position.py     # VirtualPosition dataclass + VirtualPositionStore
    exit_monitor.py         # mechanical SL/TP candle-close check
    signal_formatter.py     # Telegram message templates
    strategy_config.py      # StrategyInstanceConfig resolver (globals + overrides)
```

### New data-layer class: `app/data/multiplexer.py`

`TimeframeMultiplexer` — owns per-`(symbol, timeframe)` dataframes. Replaces `MarketDataStore` for the signal-bot path only. Live bot continues to use `MarketDataStore`.

### Runtime switch

`main.py` branches on `config.bot.mode`:
- `mode: "signal"` → start `SignalRunner`
- any other mode → existing `MultiSymbolRunner` (unchanged)

Signal mode also starts `StatusWriter` (so the deploy health check sees the new version), enables Telegram command polling, and posts a start-up / shutdown notice to the debug topic.

### Telegram commands (signal mode)

| Command | Behavior |
|---|---|
| `/bot_version` | Deployed tag, SHA, uptime, open VP count |
| `/force_deploy` | Writes the force-deploy flag file |
| `/deploy_status` | Reads the deploy state file |
| `/cancel_deploy` | Cancels a pending (waiting) deploy |
| `/help` | Lists commands |
| `/topics` | Lists configured strategy topic names and IDs, including inactive entries and the debug topic |
| `/status`, `/history`, `/report`, `/winrate`, `/reset` | Reply "Not available in signal mode" (require a live exchange) |

### Data flow (signal mode)

```
BinanceStreamManager (native WS per (sym, tf))
        ↓ normalize_binance
TimeframeMultiplexer.on_kline_event(sym, tf, candle)
        ↓ fires close callbacks on candle.closed==True
StrategyWorker.on_candle_close(sym, tf, candle)   [registered by SignalRunner]
        ↓
Worker runs exit_monitor + strategy.analyze()
        ↓
NotificationService.send(msg, topic_id=...)       [fire-and-forget queue]
        ↓
Telegram topic (per strategy / debug)
```

### Alert-only branch: `btc_rsi_cross_alert`

A dedicated branch of the same pipeline exists for the BTC RSI cross alert.
It shares the stream manager, multiplexer, resolver and notifier but never
touches virtual positions or strategies:

```
BinanceStreamManager ── history_complete_callback ──→ BtcRsiCrossAlertWorker.on_history_complete()
        │                                              (arms bootstrap watermarks; no evaluation)
        ↓
TimeframeMultiplexer close callbacks
        ├─ 5m closed candle → worker queue → m5_checker alignment + filters
        ├─ 15m closed candle → worker queue → m15_checker cross + price filter
        │            ↑ point-in-time H4 context read from the same multiplexer
        └─ 4h closed candle  → synchronous Condition confirmation (never queued)
        ↓
NotificationService.send(card, topic_id=M5/M15 route topic) [only on ALERT decisions]
```

Key properties (full contract:
[docs/07_trading_strategies/btc-rsi-cross-alert-spec.md](btc-rsi-cross-alert-spec.md)):

* **Not an `IStrategy`** — it is not registered in the trading/backtest
  `STRATEGY_MAP`, produces no backtest UI entry, and `/test_signal` never
  fabricates a card for it. `SignalRunner.strategies` stays limited to
  ordinary configs; active alerts are exposed via
  `SignalRunner.alert_components`.
* **Alert-only startup** — a config with zero ordinary strategies and one
  active BTC alert still starts multiplexer, stream, worker, notifier,
  health/status lifecycle and graceful shutdown. With everything disabled the
  runner keeps its clean no-op startup.
* **Bootstrap suppression** — `BinanceStreamManager` accepts an optional
  `history_complete_callback`; it fires exactly once after all REST fetch
  attempts return and before the WebSocket loop starts. The worker discards
  every callback until then and permanently ignores trigger closes at/before
  the per-timeframe REST watermark or the history-ready instant.
* **H4 boundary coordination** — live H4 closes are confirmed synchronously
  under a `threading.Condition`; when a trigger needs an unconfirmed H4
  context the worker waits at most `context_settle_seconds` once, then
  re-prepares exactly once more. Retry exhaustion fails closed silently.
* **Deduplication, M5 cooldown & failure budget** — per-timeframe cursor + deterministic
  event identity (SHA-256 of
  `btc-rsi-cross-v1|BTC/USDT|tf|UTC close`). After an M5 alert, qualifying M5
  closes before +15 minutes are suppressed using candle-close time; M15 has no
  cooldown.
  Unexpected exceptions requeue the same event ahead of newer ones within the
  existing `signal_runner.max_consecutive_failures` budget; exhaustion
  advances the cursor, notifies the debug topic once and terminates only this
  alert worker thread.
* **Timeframe-specific Telegram routing** — M5 alerts use topic `1147` and M15
  alerts use topic `1003` in the checked-in configuration. The M5 and M15
  checker modules remain separate because their signal rules differ.
* **Non-goals** — no orders, no virtual positions, no SL/TP, no PnL claims;
  M5/M15/H4 are native Binance streams (no resampling); v1 state is in
  memory, so restart bootstraps again and delivery remains best-effort
  asynchronous Telegram (not the Core V2.1 durable outbox).

---

## 3. Config Schema

```yaml
bot:
  active: true
  mode: "signal"                 # new mode; existing modes untouched
  debug: true

exchange:
  name: "binanceusdm"            # market data only; no orders placed

timeframe: "15m"                 # global default
symbols:                         # global default
  - "PYTH/USDT"
  - "BTC/USDT"

telegram:
  group_id: -1001234567890       # supergroup with topics enabled
  debug_topic_id: 99             # receives expiry alerts, failures, warnings

strategies:
  - name: rsi_no_retest
    active: true
    telegram_topic_id: 42
  - name: rsi_wma_retest
    active: true
    telegram_topic_id: 43
    timeframe: "1h"
    symbols: ["BTC/USDT"]
    risk:
      tp1_close_pct: 0.5
  - name: rsi_momentum
    active: false
    telegram_topic_id: 44

virtual_positions:
  max_age_candles: 50            # auto-expire after N candles with no SL/TP hit
  check_on: "candle_close"

signal_runner:
  max_consecutive_failures: 3    # per symbol; hitting this kills the worker thread

data:
  max_candles_per_timeframe:
    "1m":  6000
    "5m":  6000
    "15m": 6000
    "1h":  3000
    "4h":  1500
    "1d":  500

risk:                            # global defaults (used for SL/TP computation)
  risk_per_trade_pct: 0.002
  leverage: 10
  tp1_close_pct: 1
  tp2_close_pct: 0
  min_sl_distance_pct: 0.003
```

### Startup validation
- `mode == "signal"` requires `telegram.group_id`, `telegram.debug_topic_id`.
- Every active strategy must declare a `telegram_topic_id`.
- `telegram_topic_id` must be **unique** across strategies and differ from `debug_topic_id`.
- The `btc_rsi_cross_alert` component must declare separate M5
  `telegram_topic_id` and M15 `m15_telegram_topic_id` values; both must be
  unique and differ from `debug_topic_id`.
- Strategy `name` must exist in `STRATEGY_MAP` (see `app/trading/strategy/loader.py`).
- If no active strategies, log warning and exit cleanly.

### Telegram chat target
- In signal mode, `telegram.group_id` from `config.yaml` is wired straight into
  `TelegramNotifier` as the chat target — every entry/exit notification is
  posted to that supergroup with the strategy's `telegram_topic_id`.
- The `TELEGRAM_CHAT_ID` env var is **not** consulted in signal mode. Only
  `TELEGRAM_BOT_TOKEN` is required from the environment.
- Live/sim/paper modes are unchanged: they still read `TELEGRAM_CHAT_ID` from
  the env.

### Smoke-testing the notifier
- `/test_signal` (sent in the supergroup) posts a `[FAKE TEST]` entry message
  to every active strategy's topic plus the debug topic. Useful for verifying
  end-to-end routing without waiting for a real signal.
- The script `scripts/test_signal_notification.py` does the same thing from
  the command line and supports `--all` to also fire SL / TP / shutdown
  messages.

---

## 4. `StrategyInstanceConfig` (resolver)

Frozen dataclass built once per active strategy at startup from global defaults + per-strategy overrides:

```python
@dataclass(frozen=True)
class StrategyInstanceConfig:
    name: str                    # maps to class via STRATEGY_MAP
    telegram_topic_id: int
    symbols: tuple[str, ...]     # global ∪ override, minus exclude
    timeframe: str               # override or global
    risk: RiskConfig             # deep-merge of global risk + per-strategy risk
```

**Migration shim:** existing strategies read from top-level `config` dict. Add `instance_config.as_legacy_dict()` so current strategy code runs unchanged in v1.

---

## 5. Multi-Timeframe Stream (`TimeframeMultiplexer`)

### Approach: native per-TF WS subscriptions (no resample-from-1m)

Binance's kline stream delivers a canonical candle per interval. One WS subscription per `(symbol, timeframe)` pair. Benefits:
- Canonical closes matching every market participant.
- No warmup/drift edge cases.
- Trivial bandwidth (~1 msg/sec per stream).

If intra-candle SL/TP is ever needed, `@aggTrade` can be added **in addition**, not in place.

### Class surface

```python
class TimeframeMultiplexer:
    def __init__(self, targets: set[tuple[str, str]]): ...
    def on_kline_event(self, symbol: str, timeframe: str, candle: Candle) -> None:
        """Route the event to (symbol, tf) frame; fire callbacks if candle.closed."""
    def register_close_callback(
        self, cb: Callable[[str, str, Candle], None]
    ) -> None: ...
    def get_dataframe(self, symbol: str, timeframe: str) -> pd.DataFrame | None: ...
```

Thread-safe via per-`(symbol, tf)` locks.

### Changes to `BinanceStreamManager`
- Accept `targets: set[tuple[str, str]]` in addition to the legacy `(symbols, timeframe)` ctor.
- Build WS URL: `/`.join(`f"{stream_symbol}@kline_{tf}"` for each pair).
- Route `on_message` to `multiplexer.on_kline_event(symbol, tf, candle)` instead of `store.update_candle`.
- Legacy ctor path remains for `MultiSymbolRunner` back-compat.

### Changes to `DataNormalizer`
- Ensure `timeframe` is present on the `Candle` (extract from kline `k.i`).

### Per-timeframe RAM cap
- `MAX_CANDLES_IN_RAM_PER_TF: dict[str, int]` in `app/core/constants.py`. Config override via `data.max_candles_per_timeframe`.

---

## 6. Virtual Positions

### Data model

```python
@dataclass(frozen=True)
class VirtualPosition:
    signal_id: str              # e.g. "RSI#042"
    strategy_name: str
    symbol: str
    side: Literal["LONG", "SHORT"]
    entry_price: Decimal
    sl_price: Decimal
    tp_levels: list[Decimal]
    tp_close_pcts: list[float]
    opened_at_candle_ts: int    # unix ms of the candle the entry signal fired on
    timeframe: str
    tp_hits: set[int] = field(default_factory=set)
```

### Store

```python
class VirtualPositionStore:
    """Thread-safe in-memory VP store; owned by SignalRunner, scoped per strategy."""
    def open(self, vp: VirtualPosition) -> None: ...
    def close(self, signal_id: str, reason: str) -> None: ...
    def update_sl(self, signal_id: str, new_sl: Decimal) -> None: ...
    def mark_tp_hit(self, signal_id: str, tp_index: int) -> None: ...
    def get_for_symbol(self, strategy_name: str, symbol: str) -> VirtualPosition | None: ...
    def all_open(self, strategy_name: str) -> list[VirtualPosition]: ...
```

### Invariant (v1): **one VP per `(strategy, symbol)`**

Simpler, matches current strategy code (no strategy scales in). Scale-in may be added later by extending the store to hold a list.

### Signal IDs

Human-readable, in-memory monotonic counter **per strategy**:
```
RSI#001, RSI#002, ...
WMA#001, WMA#002, ...
```
Prefix derived from strategy name (first 3–4 capitalized chars). Resets on restart. Used in entry, exit, and shutdown messages.

---

## 7. Exit Monitor (mechanical)

Runs **first** on each closed candle for any open VP on that `(strategy, symbol, tf)`.

### SL check (candle close)
- `LONG`: if `candle.close < vp.sl_price` → fire 🛑, close VP, return early.
- `SHORT`: if `candle.close > vp.sl_price` → fire 🛑, close VP, return early.

### TP check (wick touch)
- `LONG`: for each TP not in `tp_hits`, if `candle.high >= tp` → fire 🎯, mark hit.
- `SHORT`: for each TP not in `tp_hits`, if `candle.low <= tp` → fire 🎯, mark hit.
- If the last TP fires, close the VP.

### Age expiry
- If `current_candle_ts - vp.opened_at_candle_ts > max_age_candles * timeframe_ms` → close with reason `expired`, send `⏰ expired` alert to **debug topic**.

### Rule: if both SL and TP would fire on the same candle, SL wins (close takes precedence over wick).

---

## 8. `StrategyWorker` (per-strategy thread)

One thread per active strategy. Handles all of its `(symbol, timeframe)` pairs.

### Loop (pseudocode)

```python
def run(self) -> None:
    failure_counts: dict[str, int] = defaultdict(int)
    while self.running.is_set():
        sym, tf, candle = self.event_queue.get()   # populated by multiplexer callback
        if (sym, tf) not in self.instance_cfg.targets:
            continue

        try:
            df = self.multiplexer.get_dataframe(sym, tf)
            vp = self.vp_store.get_for_symbol(self.strategy.name, sym)

            # 1. Mechanical exit monitor first
            if vp is not None:
                if self.exit_monitor.check(vp, candle):   # fires messages + closes VP if hit
                    failure_counts[sym] = 0
                    continue

            # 2. Strategy analyze
            snapshot = build_position_snapshot(vp) if vp else None
            result = self.strategy.analyze(sym, df, position=snapshot, context=...)

            # 3. Handle actions
            self._handle_action(result.action, vp, sym, candle)
            failure_counts[sym] = 0

        except Exception as e:
            failure_counts[sym] += 1
            logger.exception(
                "strategy_worker_error",
                strategy=self.strategy.name, symbol=sym, attempt=failure_counts[sym],
            )
            if failure_counts[sym] >= self.max_failures:
                self._notify_strategy_dead(sym, e)
                return   # thread exits → strategy dead
```

### Action dispatch

| Action         | No open VP                              | With open VP                                      |
|----------------|-----------------------------------------|---------------------------------------------------|
| `OpenPosition` | Build VP, fire 🟢 entry message         | Log warning to debug topic + ignore (no scale-in) |
| `ClosePosition`| Log warning to debug topic + ignore     | Fire 🔚 strategy-exit message, close VP           |
| `MoveSL`       | Log warning to debug topic + ignore     | Update `vp.sl_price`, fire 📉 SL-moved message    |
| `PartialClose` | Log warning to debug topic + ignore     | Fire ⚖️ partial-close message, VP stays open      |
| `DoNothing`    | No-op                                   | No-op                                             |

### Exception-safety boundaries

- Every `analyze()` call is inside try/except with the retry counter.
- Every exit-monitor check is inside try/except — a VP-check bug skips that VP, doesn't break the loop.
- **No direct `telegram.send()` calls** from worker threads — always through `NotificationService.send()` (queue-based; Telegram HTTP errors live in the worker, not the caller).
- Result: the only way a worker thread dies is if its own `analyze()` fails `max_consecutive_failures` times in a row on a single symbol.

---

## 9. `SignalRunner`

### Responsibilities

1. Parse config; build `StrategyInstanceConfig` per active strategy.
2. Compute union of `(symbol, timeframe)` pairs across all active strategies.
3. Instantiate `TimeframeMultiplexer(targets=union)`.
4. Instantiate `BinanceStreamManager(targets=union, multiplexer=...)`; fetch history for each `(sym, tf)`.
5. Instantiate shared `VirtualPositionStore` and `NotificationService`.
6. For each active strategy, spawn a `StrategyWorker` thread and register its queue as a close callback on the multiplexer (filtered to its targets).
7. Block on SIGINT/SIGTERM; on signal, run `stop()`.

### `stop()` flow

1. Clear `running` event → all workers exit their loops after current iteration.
2. For each strategy with open VPs, send shutdown broadcast to that strategy's topic:
   ```
   ⚠ Signal bot shutting down.
   You have 3 open virtual positions:
   • RSI#041 LONG BTC @ 62,340 (SL 61,800)
   • RSI#043 SHORT ETH @ 3,120 (SL 3,175)
   • RSI#044 LONG SOL @ 178.2 (SL 174.1)
   Manage these manually.
   ```
3. Drain notification queue (await queue.join with timeout).
4. Stop stream manager, join worker threads.

---

## 10. `NotificationService` — topic support

- Add `topic_id: int | None = None` parameter to `send()`.
- When set, passes `message_thread_id=topic_id` to Telegram's `sendMessage` API.
- Existing callers (live runner) default to `None` → send to main chat, unchanged.

### Topic routing (signal mode)

| Event                                  | Topic                         |
|----------------------------------------|-------------------------------|
| Entry signal                           | strategy's `telegram_topic_id`|
| Mechanical SL hit                      | strategy's `telegram_topic_id`|
| Mechanical TP hit                      | strategy's `telegram_topic_id`|
| Strategy-emitted exit / move / partial | strategy's `telegram_topic_id`|
| Shutdown broadcast                     | strategy's `telegram_topic_id`|
| VP expiry (`⏰`)                        | `debug_topic_id`              |
| Strategy failed N times on a symbol    | `debug_topic_id`              |
| Strategy thread dead                   | `debug_topic_id`              |
| Internal warnings (invalid action, etc)| `debug_topic_id`              |
| BTC M5 bullish alignment                 | component's `telegram_topic_id` |
| BTC M15 bullish cross                    | component's `m15_telegram_topic_id` |

---

## 11. Message Templates

```
[rsi_no_retest] 🟢 LONG BTC/USDT  (RSI#042)
Entry: 62,340
SL:    61,800  (candle-close)
TP1:   62,960
TP2:   63,500
```

```
[rsi_no_retest] 🛑 EXIT advice — LONG BTC/USDT  (RSI#042)
15m candle closed at 61,720 (below SL 61,800)
If still in this trade, consider closing.
```

```
[rsi_no_retest] 🎯 TP1 hit — LONG BTC/USDT  (RSI#042)
Price reached 62,960 (high 62,985)
Consider closing 1/3 per strategy plan.
```

```
[rsi_no_retest] 🔚 STRATEGY EXIT — LONG BTC/USDT (RSI#042)
Reason: strategy signaled close
Price at signal: 62,450
```

```
[rsi_no_retest] 📉 SL MOVED — LONG BTC/USDT (RSI#042)
Old SL: 61,800 → New SL: 62,100
```

```
[rsi_no_retest] ⚖️ PARTIAL CLOSE — LONG BTC/USDT (RSI#042)
Close 33% at 62,960
```

```
[debug] ⏰ RSI#042 expired after 50 candles (no SL/TP hit)
[debug] ⚠ rsi_no_retest disabled on SOL/USDT after 3 failures. Last error: ValueError: ...
```

---

## 12. Failure & Edge Cases

| Case                                              | Handling                                                   |
|---------------------------------------------------|------------------------------------------------------------|
| `analyze()` throws once                           | Log, skip this candle, increment counter                   |
| `analyze()` throws N times on same symbol         | Debug-topic notice, thread exits (strategy dead on that sym)|
| Exit monitor throws on one VP                     | Log, skip that VP, continue                                |
| Telegram send fails                               | Absorbed by `NotificationService` worker, logged           |
| SL + TP both touched same candle                  | SL wins                                                    |
| Strategy emits `OpenPosition` while VP exists     | Debug-topic warning, ignore                                |
| Strategy emits exit action while no VP            | Debug-topic warning, ignore                                |
| SIGKILL / OOM                                     | No warning fires (acceptable)                              |
| Duplicate `telegram_topic_id`                     | Startup validation error                                   |
| No `active: true` strategies                      | Warn and exit cleanly                                      |
| WS disconnect                                     | Stream manager auto-reconnects (existing behavior)         |

---

## 13. File-by-file Change List

### New files
- `app/data/multiplexer.py` (~180 LoC) — `TimeframeMultiplexer`
- `app/signal/__init__.py`
- `app/signal/runner.py` (~250 LoC)
- `app/signal/strategy_worker.py` (~200 LoC)
- `app/signal/virtual_position.py` (~130 LoC)
- `app/signal/exit_monitor.py` (~120 LoC)
- `app/signal/signal_formatter.py` (~150 LoC)
- `app/signal/strategy_config.py` (~100 LoC)

### Modified files
- `main.py` — branch on `config.bot.mode == "signal"`
- `app/core/config.py` — accept new schema (`strategies:` list, `telegram.group_id`, `telegram.debug_topic_id`, `signal_runner.*`, `virtual_positions.*`, `data.max_candles_per_timeframe`)
- `app/core/constants.py` — add `SIGNAL_MAX_CONSECUTIVE_FAILURES = 3`, `SIGNAL_MAX_VP_AGE_CANDLES = 50`, `MAX_CANDLES_IN_RAM_PER_TF` dict
- `app/data/stream_manager.py` — accept `targets: set[tuple[str, str]]`; multi-TF URL; callback to multiplexer. Keep legacy ctor path for live bot.
- `app/data/normalizer.py` — ensure `timeframe` present on `Candle`
- `app/notification/notification_service.py` — route `topic_id` through
  `send()`
- `config.yaml` — schema migration (retain `strategy: ...` support for live mode back-compat)

### Docs (mandatory per CLAUDE.md)
- `docs/03_setup_and_installation/configuration.md` — new config keys, `signal` mode
- `docs/05_data_pipeline/live-data-flow.md` — `TimeframeMultiplexer` and multi-TF streams
- `docs/08_execution_and_oms/notifications.md` — topic routing
- `docs/02_architecture/system-overview.md` — add `SignalRunner` branch to the diagram
- `docs/07_trading_strategies/signal-bot.md` — **this file**

### Tests
- `tests/test_timeframe_multiplexer.py` — routing, callbacks, locks, per-TF caps
- `tests/test_virtual_position_store.py` — open/close/query thread-safety, one-VP invariant
- `tests/test_exit_monitor.py` — SL-before-TP, TP wick-touch, multi-TP, age expiry
- `tests/test_strategy_config_resolver.py` — global + override + exclude merging
- `tests/test_strategy_worker_failure.py` — retry counter, thread-dies-after-N
- `tests/test_signal_runner.py` — startup, shutdown, and worker coordination
- `tests/test_signal_formatter.py` — message templates
- `tests/test_notification_service_topic.py` — topic_id forwarded correctly

---

## 14. Rollout Order

Each slice is independently shippable/testable.

1. **`TimeframeMultiplexer`** + per-TF cap constants + tests.
2. **`BinanceStreamManager` multi-TF** (keep legacy ctor wrapper) + tests.
3. **`NotificationService` topic support** + tests.
4. **`StrategyInstanceConfig` resolver** + tests.
5. **`VirtualPositionStore` + `exit_monitor`** + tests.
6. **`StrategyWorker`** (all 5 action types + failure policy) + tests.
7. **`SignalRunner`** (SIGTERM broadcast) + integration test.
8. **`main.py` mode branch** — end-to-end smoke on one strategy.
9. **Scale to N strategies** — verify topic routing, debug topic, per-TF frames.
10. **Docs** and `config.yaml` migration.

---

## 15. Deferred / Follow-ups

- Scale-in (multiple VPs per `(strategy, symbol)`).
- Persisted VPs for restart recovery.
- Intra-candle SL/TP via `@aggTrade`.
- Multi-strategy backtest mode (reuse `StrategyInstanceConfig` + exit monitor).
- Explicit `id_prefix` field in strategy config (currently derived from name).
- Taken/Skipped UX + inline buttons.

---

## 16. Open Questions Settled in Planning

- Concurrency model: **thread per strategy** (not thread per symbol, not single loop).
- Failure policy: **hybrid** — `max_consecutive_failures` retries per symbol, then thread exits.
- Multi-timeframe: **native per-TF WS subscriptions** (not resample-from-1m).
- Strategy-emitted exits: **respected** — all five action types handled in signal mode.
- VP cardinality: **one VP per (strategy, symbol)** — no scale-in in v1.
- Expiry / failure alerts: routed to a dedicated **debug topic**.
- RAM cap: **per-timeframe** dict, configurable.
