# Live Data Flow

> Real-time market data ingestion from Binance Futures WebSocket through to strategy consumption. Covers BinanceStreamManager, DataNormalizer, MarketDataStore, and LiveEventSource.

---

## Overview

The live data pipeline streams kline (candlestick) data from Binance USDT-M Futures via WebSocket, normalizes it into `Candle` objects with `Decimal` precision, and stores it in a thread-safe in-memory `MarketDataStore`. The unified Engine consumes closed-candle events through a `LiveEventSource` adapter.

```
Binance fstream WebSocket
        |
        v
BinanceStreamManager.on_message()
        |
        v
DataNormalizer.normalize_binance(raw_data) -> MarketEvent(Candle)
        |
        v
MarketDataStore.update_candle(candle)
        |
        v  (on kline close)
LiveEventSource._on_kline_close(candle)
        |
        v
Engine event loop (CandleCloseEvent with DataFrame)
        |
        v
Strategy.analyze(symbol, df, position, context)
```

---

## BinanceStreamManager

**Source**: `app/data/stream_manager.py`

### WebSocket Connection

| Property | Value |
|----------|-------|
| Base URL | `wss://fstream.binance.com/stream?streams=` |
| Stream format | `{symbol}@kline_{timeframe}` per symbol |
| Transport | `websocket-client` (`WebSocketApp`) |
| Ping interval | 60 seconds |
| Ping timeout | 10 seconds |
| Thread model | Daemon thread with blocking `run_forever()` |

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbols` | `List[str]` | required | Trading pairs (e.g. `["BTC/USDT", "ETH/USDT"]`) |
| `timeframe` | `str` | required | Candle interval (e.g. `"5m"`, `"1h"`) |
| `store` | `MarketDataStore` | required | Destination for candle data |
| `history_limit` | `int` | `300` | Number of historical candles to fetch on startup |
| `enable_history` | `bool` | `True` | Whether to fetch history before streaming |

### Symbol Normalization

The stream manager handles multiple symbol formats internally:

| Input | Stream symbol (WebSocket) | CCXT symbol (history fetch) |
|-------|---------------------------|----------------------------|
| `BTC/USDT` | `btcusdt` | `BTC/USDT:USDT` |
| `BTCUSDT` | `btcusdt` | `BTC/USDT:USDT` |
| `BTC/USDT:USDT` | `btcusdt` | `BTC/USDT:USDT` (passthrough) |

- `_to_stream_symbol()`: Strips `/`, lowercases. Used for WebSocket stream subscription.
- `_to_ccxt_symbol()`: Appends `:USDT` suffix for CCXT Futures market. Used for `fetch_ohlcv()`.

### Startup Sequence

1. `start()` is called.
2. `fetch_initial_data()` runs synchronously:
   - Creates a `ccxt.binanceusdm()` client with rate limiting enabled.
   - For each symbol, calls `exchange.fetch_ohlcv(ccxt_symbol, timeframe, limit=history_limit)`.
   - Each OHLCV row is normalized via `DataNormalizer.normalize_ccxt()` and stored via `store.update_candle()`.
3. A daemon thread is spawned running the WebSocket reconnection loop.

### Reconnection Logic

The WebSocket runs inside a `while self.keep_running` loop:

```python
while self.keep_running:
    ws = WebSocketApp(url, on_open=..., on_message=..., on_error=..., on_close=...)
    ws.run_forever(ping_interval=60, ping_timeout=10)
    # If we reach here, the connection dropped
    if self.keep_running:
        time.sleep(2)  # 2-second delay before reconnect
```

- On disconnect: logs warning, waits 2 seconds, reconnects.
- On error: logs error, connection closes, reconnection loop handles retry.
- `stop()` sets `keep_running = False` and calls `ws.close()`.

### Callbacks

The stream manager exposes two optional callbacks for `LiveEventSource` integration:

| Callback | Fires when | Payload |
|----------|-----------|---------|
| `on_kline_close` | A candle's `closed` field is `True` | `Candle` object |
| `on_tick` | Every kline update (open or closed) | `Candle` object |

---

## DataNormalizer

**Source**: `app/data/normalizer.py`

Stateless class with static methods that convert raw exchange data into typed `Candle` / `MarketEvent` objects.

### normalize_binance(raw_data) -> MarketEvent

Converts a Binance WebSocket kline message:

```python
# Input (raw WebSocket JSON after parsing):
{
    "e": "kline",
    "s": "BTCUSDT",
    "k": {
        "t": 1708905600000,   # kline open time (ms)
        "o": "51234.50",      # open
        "h": "51300.00",      # high
        "l": "51200.00",      # low
        "c": "51280.00",      # close
        "v": "123.456",       # volume
        "x": false            # is closed
    }
}

# Output:
MarketEvent(
    type=EventType.TICK_UPDATE,  # or KLINE_CLOSE if x=True
    exchange="binance",
    payload=Candle(
        symbol="BTC",                                    # normalized to base asset
        timestamp=Timestamp('2024-02-26 06:00:00+07:00'),# UTC+7
        open=Decimal('51234.50'),
        high=Decimal('51300.00'),
        low=Decimal('51200.00'),
        close=Decimal('51280.00'),
        volume=Decimal('123.456'),
        closed=False
    )
)
```

Key behaviors:
- **Symbol normalization**: `_normalize_symbol()` strips quote asset (`USDT`, `USDC`, `BUSD`, `USD`) leaving only the base (e.g. `BTCUSDT` -> `BTC`).
- **Timestamp**: Converted from milliseconds to pandas `Timestamp` with **+7 hours UTC offset** (Bangkok time).
- **Decimal precision**: All price and volume fields use `Decimal(str(value))` to avoid float rounding.
- **Event type**: `KLINE_CLOSE` when `kline['x']` is `True`, otherwise `TICK_UPDATE`.

### normalize_ccxt(symbol, ohlcv) -> Candle

Converts a CCXT OHLCV list (used for historical backfill):

```python
# Input:
symbol = "BTC/USDT"
ohlcv = [1708905600000, 51234.5, 51300.0, 51200.0, 51280.0, 123.456]

# Output:
Candle(symbol="BTC", timestamp=..., open=Decimal('51234.5'), ..., closed=True)
```

- Historical candles always have `closed=True`.
- Same UTC+7 timestamp offset as live data.

---

## MarketDataStore

**Source**: `app/data/store.py`

### Purpose

Thread-safe in-memory storage for candle data. Each symbol maintains its own `pandas.DataFrame` indexed by timestamp. Stores both `float` columns (for pandas operations) and `Decimal` columns (for financial precision).

### Memory Cap

```python
MAX_CANDLES_IN_RAM = 6000
```

When a symbol's DataFrame exceeds 6000 rows, it is trimmed to the last 6000 using `df.tail(6000)`. This happens after every append operation.

### Thread Safety

Two-level locking:

| Lock | Scope | Purpose |
|------|-------|---------|
| `global_lock` | `threading.Lock()` | Protects creation of per-symbol locks |
| `locks[symbol]` | `threading.Lock()` per symbol | Protects read/write of `data[symbol]` DataFrame |

`_get_lock(symbol)` acquires `global_lock` to lazily create per-symbol locks on first access.

### update_candle(candle) Logic

```
Is candle.timestamp == last row timestamp?
    YES -> Update existing row in-place (intra-candle tick update)
    NO  -> Append new row (new candle opened)

If len(df) > 6000:
    df = df.tail(6000)
```

Each candle is stored as a row with these columns:

| Column | Type | Source |
|--------|------|--------|
| `timestamp` (index) | `datetime` | `candle.timestamp` |
| `open` | `float` | `float(candle.open)` |
| `high` | `float` | `float(candle.high)` |
| `low` | `float` | `float(candle.low)` |
| `close` | `float` | `float(candle.close)` |
| `volume` | `float` | `float(candle.volume)` |
| `closed` | `bool` | `candle.closed` |
| `open_dec` | `Decimal` | `candle.open` |
| `high_dec` | `Decimal` | `candle.high` |
| `low_dec` | `Decimal` | `candle.low` |
| `close_dec` | `Decimal` | `candle.close` |

### get_dataframe(symbol) -> Optional[DataFrame]

Returns a **copy** of the symbol's DataFrame (thread-safe). Returns `None` if no data exists for the symbol.

### get_last_candle(symbol) -> Optional[Dict]

Returns the last candle as a dictionary with `Decimal` values for precise price calculations. Falls back to `Decimal(str(float_value))` if `_dec` columns are missing.

---

## LiveEventSource

**Source**: `app/data/live_event_source.py`

Bridges the callback-based `BinanceStreamManager` to the pull-based `IEventSource` interface used by the unified Engine.

### How It Works

1. `events()` is called by the Engine.
2. It registers `_on_kline_close` as the stream manager's `on_kline_close` callback.
3. When a candle closes, the callback:
   - Fetches the full DataFrame from `store.get_dataframe(symbol)`.
   - Creates a `CandleCloseEvent(candle=candle, df=df)`.
   - Pushes it onto a bounded `queue.Queue` (default max size: 500).
4. The `events()` generator blocks on `queue.get(timeout=1.0)`, yielding events as they arrive.
5. If the queue is full, the event is dropped with a `live_event_queue_full` warning log.

### Stop Mechanism

`stop()` sets a `threading.Event` flag and pushes an `EngineStopEvent` onto the queue to unblock the generator.

---

## Strategy Consumption

The Engine receives `CandleCloseEvent` objects and passes the DataFrame to the strategy:

```python
# Inside Engine event loop:
for event in event_source.events():
    if isinstance(event, CandleCloseEvent):
        df = indicators.compute(event.df, symbol=symbol, timeframe=timeframe)
        result = strategy.analyze(symbol, df, position=snapshot, context=ctx)
        # Handle result actions (OpenPosition, ClosePosition, etc.)
```

The DataFrame passed to `analyze()` has indicator columns already computed by the `Indicators` class (see `data-formats.md` for column schema).

---

## Signal-Bot Branch (multi-TF)

When `bot.mode: "signal"` is set, `main.py` routes to `SignalRunner`
(`app/signal/runner.py`) which replaces `MarketDataStore` + `LiveEventSource`
with `TimeframeMultiplexer` + per-strategy worker queues. The live bot is
**not** affected by this path — it continues to use `MarketDataStore`.

```
Binance fstream WebSocket (URL: btcusdt@kline_1m/btcusdt@kline_15m/...)
        |
        v
BinanceStreamManager(targets, multiplexer).on_message()
        |
        v
DataNormalizer.normalize_binance(raw)  -- populates Candle.timeframe from k.i
        |
        v
TimeframeMultiplexer.on_kline_event(symbol, timeframe, candle)
        |  (per-(sym,tf) frame + per-TF RAM cap)
        v  (on candle.closed: fan out to registered callbacks)
StrategyWorker.enqueue(symbol, timeframe, candle)  -- per-strategy bounded queue
        |
        v
StrategyWorker.run():
    1. exit_monitor.check(vp, candle)   -> SLHit / TPHit / Expired
    2. strategy.analyze(symbol, df, position, context)
    3. dispatch OpenPosition | ClosePosition | MoveSL | PartialClose | DoNothing
        |
        v
NotificationService.send_message(msg, topic_id=...)
        |
        v
Telegram topic (per strategy) or debug_topic_id (infra messages)
```

### BinanceStreamManager in multi-TF mode

Same class as the live bot, invoked via the keyword-only form:

```python
BinanceStreamManager(
    targets={("BTC/USDT", "1m"), ("BTC/USDT", "15m"), ("ETH/USDT", "15m")},
    multiplexer=mux,
    history_limit=300,
)
```

The WS URL concatenates one `@kline_{tf}` sub-stream per `(pair, tf)`. The
legacy `(symbols, timeframe, store)` ctor form is unchanged — the two modes
are mutually exclusive and validated at construction.

### TimeframeMultiplexer

**Source**: `app/data/multiplexer.py`. Thread-safe storage keyed on
`(symbol, timeframe)` tuples. One DataFrame per pair — the RAM cap comes from
`data.max_candles_per_timeframe` in YAML (default `MAX_CANDLES_IN_RAM_PER_TF`).
Close callbacks fire outside the per-pair lock so a slow subscriber cannot
block ingest for other pairs; callback exceptions are isolated and logged.

Shared helpers in `app/data/_candle_row.py` (`candle_to_row`,
`last_row_to_decimal_dict`) ensure the row schema matches `MarketDataStore`
exactly — row building and last-row Decimal extraction are single-source.

### Per-strategy worker queue

Each `StrategyWorker` owns a bounded `queue.Queue`
(size `SIGNAL_WORKER_QUEUE_SIZE = 500`). `SignalRunner` registers a filtered
callback on the multiplexer that routes only the worker's own `(sym, tf)`
targets into the queue — other events are dropped at callback time, not
after queue ingest. On overflow, the enqueue side drops with a
`strategy_worker_queue_full` warn-log so WebSocket ingest never stalls.

### BTC RSI cross alert branch (5m + 15m + native 4h)

The `btc_rsi_cross_alert` component extends the same multi-TF pipeline with a
**three-stream** target union: native Binance `btcusdt@kline_5m`,
`btcusdt@kline_15m` and `btcusdt@kline_4h` (H4 is subscribed natively — M5/M15
are never resampled into H4).

```
BinanceStreamManager(targets ∪ {(BTC/USDT,5m),(BTC/USDT,15m),(BTC/USDT,4h)})
        |
        v  fetch_initial_data(): REST history per target → multiplexer
        |  (close callbacks fire for historical rows too — see gate below)
        v
history_complete_callback()  -- exactly once, after all fetch attempts,
        |                      before the WebSocket loop starts
        v
BtcRsiCrossAlertWorker.on_history_complete():
    records UTC history-ready instant + per-timeframe REST watermark
    (newest closed candle close hydrated per 5m/15m)
        |
        v  multiplexer close callbacks:
        ├─ 5m/15m closed candle → worker queue (evaluation trigger)
        ├─ 4h closed candle   → synchronous Condition confirmation
        |                       (observed-live set; NEVER queued)
        └─ open candles       → ignored entirely
        |
        v  worker thread, per event:
    1. bootstrap gate: discard while history-ready unset; ignore closes
       <= timeframe watermark OR <= history-ready instant (covers delayed
       WS duplicates and candles that closed during hydration)
    2. dedupe: per-timeframe cursor + deterministic event id; after an M5
       alert, suppress qualifying M5 closes at +5m/+10m and allow +15m;
       M15 has no cooldown
    3. point-in-time preparation over defensive get_dataframe() copies:
       naive stored opens = fixed UTC+07:00 → UTC close = open + tf duration;
       maximal contiguous cadence suffix ending at the exact expected row;
       >=67 trigger rows / >=21 H4 rows; finite values only; post-bootstrap
       H4 closes require live observation; one settle/retry at shared H4
       boundaries (context_settle_seconds), then fail closed
    4. timeframe decision:
       M5 = current RSI21 > EMA9 > WMA45 alignment
       M15 = fresh EMA9(RSI21)↑WMA45(RSI21) cross
       both require H4 close > EMA21(price)
    5. both triggers require their own close > EMA21(price); M5 additionally
       requires RSI EMA/WMA spread > 2 and RSI WMA45 > 45
        |
        v  on ALERT only:
NotificationService.send_message(html-escaped card, topic_id=btc topic)
```

The bootstrap gate makes historical REST replay silent by construction: no
alert can originate from the hydration window regardless of how many crosses
it contains. See
[docs/07_trading_strategies/btc-rsi-cross-alert-spec.md](../07_trading_strategies/btc-rsi-cross-alert-spec.md)
§7/§11 for the locked semantics.
