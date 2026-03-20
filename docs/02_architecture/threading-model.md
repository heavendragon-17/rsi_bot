# Threading Model

> Deep-dive into concurrency and threading across both the live bot and backtest UI subsystems. Covers thread topology, synchronization primitives, thread-safe components, the SSE bridge pattern, and safety rules for agents modifying code.

---

## Table of Contents

- [Live Bot Threading Architecture](#live-bot-threading-architecture)
- [BinanceStreamManager (WebSocket Daemon)](#binancestreammanager-websocket-daemon)
- [MarketDataStore (Thread-Safe Storage)](#marketdatastore-thread-safe-storage)
- [Per-Symbol Threads](#per-symbol-threads)
- [BinanceAdapter (Exchange Lock)](#binanceadapter-exchange-lock)
- [Backtest Concurrency](#backtest-concurrency)
- [SSE Bridge (Thread-to-Async)](#sse-bridge-thread-to-async)
- [Sim Mode Additional Threads](#sim-mode-additional-threads)
- [Thread Safety Rules for Agents](#thread-safety-rules-for-agents)

---

## Live Bot Threading Architecture

The live bot uses a multi-threaded architecture with one coordinator (main thread), one WebSocket daemon, and N per-symbol trading daemons.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          LIVE BOT PROCESS                                   │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  MAIN THREAD                                                         │  │
│  │                                                                       │  │
│  │  1. Load AppConfig from config.yaml                                   │  │
│  │  2. Create exchange via factory                                       │  │
│  │  3. Create MultiSymbolRunner                                          │  │
│  │  4. runner.start():                                                   │  │
│  │     a. Set leverage for all symbols                                   │  │
│  │     b. Close orphan positions (_cleanup_on_startup)                   │  │
│  │     c. Start BinanceStreamManager (spawns daemon thread)              │  │
│  │     d. Sleep 2s (wait for initial data)                               │  │
│  │     e. Spawn N per-symbol daemon threads                              │  │
│  │  5. runner.wait() — blocks in loop, logs heartbeat every 60s          │  │
│  │  6. On SIGINT/SIGTERM → runner.stop() → clear running Event           │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌────────────────────────┐     ┌────────────────────────────────────────┐  │
│  │  STREAM THREAD         │     │  SYMBOL THREADS (N daemons)            │  │
│  │  (1 daemon)            │     │                                        │  │
│  │                        │     │  Thread: "Symbol-BTC/USDT"             │  │
│  │  BinanceStreamManager  │     │  ├── Strategy instance (own copy)      │  │
│  │  ├── WebSocketApp      │     │  ├── PortfolioManager (own copy)       │  │
│  │  │   .run_forever()    │     │  ├── ContextSnapshot (owned by runner) │  │
│  │  │                     │     │  └── Loop:                             │  │
│  │  ├── on_message():     │     │      1. store.get_dataframe(symbol)    │  │
│  │  │   normalize →       │     │      2. Check if candle is closed      │  │
│  │  │   store.update_     │     │      3. strategy.analyze(...)          │  │
│  │  │   candle()     ─────┼─────┼──>   4. Dispatch actions               │  │
│  │  │                     │     │      5. portfolio.sync_tp_fills()      │  │
│  │  └── Auto-reconnect    │     │      6. Sleep 0.1s                     │  │
│  │      on disconnect     │     │                                        │  │
│  │      (2s delay)        │     │  Thread: "Symbol-ETH/USDT"             │  │
│  │                        │     │  └── (same structure)                   │  │
│  └────────────────────────┘     │                                        │  │
│                                 │  Thread: "Symbol-SOL/USDT"             │  │
│                                 │  └── (same structure)                   │  │
│                                 └────────────────────────────────────────┘  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  SHARED RESOURCES (thread-safe)                                     │    │
│  │                                                                     │    │
│  │  MarketDataStore        BinanceAdapter        threading.Event       │    │
│  │  ├── global_lock        ├── self._lock        └── runner.running    │    │
│  │  ├── per-symbol locks   └── wraps all CCXT        (stop signal)     │    │
│  │  └── self.data dict         API calls                               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Thread Count Summary

| Thread | Type | Count | Lifetime |
|--------|------|-------|----------|
| Main thread | Main | 1 | Process lifetime |
| BinanceStreamManager | Daemon | 1 | Until `runner.stop()` |
| Per-symbol trading | Daemon | N (1 per symbol) | Until `runner.stop()` |
| **Total** | -- | **2 + N** | -- |

All non-main threads are **daemon threads** (`daemon=True`). If the main thread exits (e.g., unhandled exception), daemon threads are terminated automatically by Python.

### Shutdown Sequence

1. `SIGINT` or `SIGTERM` received by main thread
2. `runner._signal_handler()` calls `runner.stop()`
3. `runner.running.clear()` -- signals all per-symbol loops to exit
4. `stream.stop()` -- sets `keep_running = False`, closes WebSocket
5. `thread.join(timeout=5)` for each symbol thread
6. Log warnings for any threads that did not stop gracefully

---

## BinanceStreamManager (WebSocket Daemon)

**File**: `app/data/stream_manager.py`

A single daemon thread that maintains a persistent WebSocket connection to Binance Futures.

### WebSocket URL Construction

```python
STREAM_URL = "wss://fstream.binance.com/stream?streams="

# Symbols are converted: "BTC/USDT" -> "btcusdt"
# Stream names: "{symbol}@kline_{timeframe}"
# Combined URL example:
# wss://fstream.binance.com/stream?streams=btcusdt@kline_5m/ethusdt@kline_5m
```

### Symbol Normalization

The stream manager converts symbols at two boundaries:

| Direction | Method | Example |
|-----------|--------|---------|
| Config -> WebSocket | `_to_stream_symbol()` | `"BTC/USDT"` -> `"btcusdt"` |
| Config -> CCXT (history) | `_to_ccxt_symbol()` | `"BTC/USDT"` -> `"BTC/USDT:USDT"` |

### Lifecycle

```
start()
├── fetch_initial_data()                    # Synchronous, fetches history via CCXT REST
│   └── For each symbol:
│       └── exchange.fetch_ohlcv() -> DataNormalizer.normalize_ccxt() -> store.update_candle()
│
└── threading.Thread(target=run, daemon=True).start()
    └── run() loop:
        └── while keep_running:
            ├── Create WebSocketApp(url, callbacks)
            ├── ws.run_forever(ping_interval=60, ping_timeout=10)  # BLOCKS until disconnect
            └── if keep_running: sleep(2) then reconnect
```

### Reconnection Strategy

- On disconnect (network error, server close): wait 2 seconds, create new `WebSocketApp`, reconnect
- On exception in `run_forever`: log error, wait 2 seconds, retry
- The `keep_running` flag is set to `False` by `stop()` to break the reconnection loop
- `ping_interval=60`, `ping_timeout=10` -- sends WebSocket pings to detect dead connections

### Message Processing

```python
def on_message(self, ws, message):
    data = json.loads(message).get("data")
    event = DataNormalizer.normalize_binance(data)   # -> MarketEvent(Candle)
    self.store.update_candle(event.payload)           # Thread-safe write

    # Optional callbacks for LiveEventSource integration
    if self.on_tick is not None:
        self.on_tick(event.payload)
    if event.type.name == "KLINE_CLOSE" and self.on_kline_close is not None:
        self.on_kline_close(event.payload)
```

The `on_tick` and `on_kline_close` callbacks are optional hooks set by `LiveEventSource` for the unified engine event loop.

---

## MarketDataStore (Thread-Safe Storage)

**File**: `app/data/store.py`

Thread-safe in-memory storage for candle data. Uses a **two-level locking scheme**: a global lock for creating new per-symbol locks, and per-symbol locks for all data access.

### Locking Architecture

```
┌──────────────────────────────────────────────┐
│ MarketDataStore                               │
│                                               │
│  self.global_lock: threading.Lock             │
│  ├── Protects: self.locks dict                │
│  └── Held briefly: only during lock lookup    │
│                                               │
│  self.locks: Dict[str, threading.Lock]        │
│  ├── self.locks["BTC/USDT"]: Lock             │
│  │   └── Protects: self.data["BTC/USDT"]      │
│  ├── self.locks["ETH/USDT"]: Lock             │
│  │   └── Protects: self.data["ETH/USDT"]      │
│  └── ... (one lock per symbol)                │
│                                               │
│  self.data: Dict[str, pd.DataFrame]           │
│  └── Each DataFrame is accessed only under    │
│      its corresponding per-symbol lock        │
└──────────────────────────────────────────────┘
```

### Lock Acquisition Pattern

```python
def _get_lock(self, symbol: str) -> threading.Lock:
    with self.global_lock:                    # Brief hold
        if symbol not in self.locks:
            self.locks[symbol] = threading.Lock()
        return self.locks[symbol]

def update_candle(self, candle: Candle) -> None:
    symbol = candle.symbol
    with self._get_lock(symbol):              # Per-symbol hold
        # ... update or append candle data ...
```

### Thread-Safe Operations

| Method | Lock Used | Returns | Notes |
|--------|-----------|---------|-------|
| `update_candle(candle)` | Per-symbol lock | `None` | Updates last row or appends new row. Trims to `MAX_CANDLES_IN_RAM`. |
| `get_dataframe(symbol)` | Per-symbol lock | `Optional[pd.DataFrame]` | Returns a **copy** of the DataFrame. Caller gets an independent snapshot. |
| `get_last_candle(symbol)` | Per-symbol lock (via `get_dataframe`) | `Optional[Dict]` | Returns last candle as dict with Decimal values. |

### Memory Management

- **Maximum**: 6,000 candles per symbol (`MAX_CANDLES_IN_RAM = 6000`)
- **Enforcement**: After each `update_candle()`, if `len(df) > MAX_CANDLES_IN_RAM`, oldest rows are dropped via `df.tail(MAX_CANDLES_IN_RAM)`
- **Total memory**: Approximately `6000 candles * N symbols * ~10 columns * 8 bytes` = ~480KB per symbol

### Contention Profile

- **Writer**: BinanceStreamManager thread (one writer per symbol, writes on every WebSocket message)
- **Reader**: Per-symbol trading thread (reads via `get_dataframe()` on every loop iteration, ~0.1s intervals)
- **Contention**: Low. Each symbol has its own lock. Different symbols never contend with each other. Same-symbol contention is brief (DataFrame copy or row append).

---

## Per-Symbol Threads

**File**: `app/trading/runner.py` -- `MultiSymbolRunner._run_symbol_loop()`

Each symbol runs in its own daemon thread named `"Symbol-{symbol}"` (e.g., `"Symbol-BTC/USDT"`).

### Per-Thread Ownership

Each thread **owns** (not shared) the following instances:

| Component | Created By | Shared? | Why |
|-----------|------------|---------|-----|
| `Strategy` instance | `self.strategy_class(self.config)` | **No** -- each thread gets its own | Strategy may have internal state (indicators cache). Avoids any possibility of cross-symbol state contamination. |
| `PortfolioManager` instance | `PortfolioManager(self.exchange, self.config)` | **No** -- each thread gets its own | Each portfolio tracks positions for its own symbol. |
| `ContextSnapshot` | Stored in `runner.contexts[symbol]` | **No** -- accessed only by its own symbol thread | Context is the strategy state machine for one symbol. |

### Shared Resources (accessed across threads)

| Resource | Access Pattern | Thread Safety Mechanism |
|----------|----------------|------------------------|
| `MarketDataStore` | Read by symbol threads, written by stream thread | Per-symbol `threading.Lock` + global lock |
| `BinanceAdapter` (exchange) | Called by all symbol threads for order operations | Single `threading.Lock` wrapping all API calls |
| `runner.running` | Read by all threads, written by main thread on shutdown | `threading.Event` (inherently thread-safe) |
| `runner.contexts` | Written by each symbol thread (only its own key) | No lock needed -- each thread writes only its own key |

### Trading Loop

```python
def _run_symbol_loop(self, symbol: str) -> None:
    strategy = self.strategy_class(self.config)     # Thread-local
    portfolio = PortfolioManager(self.exchange, self.config)  # Thread-local
    last_processed_ts = None

    while self.running.is_set():                    # Check stop signal
        df = self.store.get_dataframe(symbol)       # Thread-safe read (returns copy)

        if df is None or df.empty:
            time.sleep(1)
            continue

        current_ts = df.index[-1]
        if current_ts == last_processed_ts:         # Skip duplicate processing
            time.sleep(0.5)
            continue

        if not last_row.get('closed', False):       # Only process closed candles
            time.sleep(0.5)
            continue

        # Build stateless inputs
        position = portfolio.get_position_snapshot(symbol)
        ctx = self.contexts.get(symbol, ContextSnapshot(state="SCANNING"))

        # Pure analysis (no side effects)
        result = strategy.analyze(symbol, df, position=position, context=ctx)

        # Store new context (thread writes only its own key)
        self.contexts[symbol] = result.new_context

        # Dispatch actions (exchange calls are lock-protected inside BinanceAdapter)
        for action in result.actions:
            # ... isinstance dispatch ...

        # Sync TP fills from exchange
        portfolio.sync_tp_fills(symbol)

        last_processed_ts = current_ts
        time.sleep(0.1)                             # Prevent CPU spinning
```

### Error Handling

If an exception occurs in the trading loop:
1. The error is logged with full traceback (`exc_info=True`)
2. The thread sleeps 5 seconds (back-off)
3. The loop continues -- the thread does not crash

This means a transient exchange error (network timeout, rate limit) does not kill the symbol thread.

---

## BinanceAdapter (Exchange Lock)

**File**: `app/trading/exchange/binance_adapter.py`

The adapter uses a single `threading.Lock` to serialize all CCXT API calls. This is necessary because the underlying CCXT library is not thread-safe.

### Lock Scope

```python
class BinanceAdapter(IExchange):
    def __init__(self, config):
        self._lock = threading.Lock()
        self._exchange = ccxt.binanceusdm({...})
        # ...

    def create_order(self, symbol, order_type, side, amount, price=None, params=None):
        # ... prepare params ...
        with self._lock:
            result = self._exchange.create_order(...)
            return result

    def fetch_order(self, order_id, symbol):
        with self._lock:
            return self._exchange.fetch_order(order_id, ext_symbol)

    def cancel_order(self, order_id, symbol):
        with self._lock:
            self._exchange.cancel_order(order_id, ext_symbol)
            return True

    def set_leverage(self, leverage, symbol):
        with self._lock:
            self._exchange.set_leverage(leverage, ext_symbol)
            return True

    def fetch_positions(self, symbols=None):
        with self._lock:
            positions = self._exchange.fetch_positions(ext_symbols)
            return [p for p in positions if abs(float(p.get("contracts", 0))) > 0]

    def fetch_balance(self, params=None):
        with self._lock:
            return self._exchange.fetch_balance(params)

    def fetch_ohlcv(self, symbol, timeframe, limit=500):
        with self._lock:
            return self._exchange.fetch_ohlcv(ext_symbol, timeframe, limit=limit)

    def cancel_all_orders(self, symbol):
        with self._lock:
            result = self._exchange.cancel_all_orders(ext_symbol)
            return len(result) if isinstance(result, list) else 0

    def fetch_open_orders(self, symbol=None):
        with self._lock:
            return self._exchange.fetch_open_orders(ext_symbol)
```

**Every public method** that touches `self._exchange` (the CCXT instance) acquires `self._lock`. This means:

- Only one thread can make an exchange API call at a time
- This is a potential bottleneck if many symbols try to place orders simultaneously
- In practice, order events are rare (minutes to hours apart), so contention is negligible
- The lock also provides sequential ordering of orders, which prevents race conditions (e.g., two symbols trying to use the same margin simultaneously)

---

## Backtest Concurrency

**File**: `app/api/executor.py`

The backtest UI uses a fundamentally different concurrency model than the live bot: **ThreadPoolExecutor** for running backtest jobs, with no shared mutable state between jobs.

### Architecture

```
┌───────────────────────────────────────────────────────────────┐
│  BACKTEST API PROCESS (uvicorn)                               │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  MAIN ASYNC EVENT LOOP (asyncio, managed by uvicorn)    │  │
│  │                                                         │  │
│  │  FastAPI routes handle HTTP requests:                    │  │
│  │  - POST /api/backtest/run → submit_backtest()           │  │
│  │  - GET  /api/backtest/{id}/stream → SSE generator       │  │
│  │  - DELETE /api/backtest/{id} → cancel_job()             │  │
│  └────────────────────────┬────────────────────────────────┘  │
│                           │                                   │
│                           │ submit to pool                    │
│                           v                                   │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  ThreadPoolExecutor (max_workers=2)                     │  │
│  │                                                         │  │
│  │  Worker Thread 1:                                       │  │
│  │  └── BacktestEngine.run(on_progress=callback)           │  │
│  │      ├── MockExchange (in-memory, not shared)           │  │
│  │      ├── Strategy instance (not shared)                 │  │
│  │      └── SQLite writes (via session, not shared)        │  │
│  │                                                         │  │
│  │  Worker Thread 2:                                       │  │
│  │  └── (another backtest run, completely independent)     │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                               │
│  Module-level registries:                                     │
│  _executor: ThreadPoolExecutor                                │
│  _jobs: Dict[int, Future]           (run_id -> Future)       │
│  _progress_queues: Dict[int, Queue] (run_id -> asyncio.Queue)│
└───────────────────────────────────────────────────────────────┘
```

### No Shared State Between Backtest Runs

Each backtest job runs with its own:
- `MockExchange` instance (in-memory order book and balance tracking)
- `Strategy` instance
- SQLAlchemy session for database writes
- DataFrame loaded from CSV

There is zero shared mutable state between concurrent backtest runs. This makes the system inherently thread-safe for backtest execution.

### Job Lifecycle

```
1. POST /api/backtest/run
   ├── Create DB run record (status="running")
   ├── create_progress_queue(run_id) -> asyncio.Queue
   ├── make_progress_callback(run_id, loop) -> callback function
   └── submit_backtest(run_id, engine.run, ..., on_progress=callback)
       └── Returns Future (non-blocking)

2. GET /api/backtest/{id}/stream (SSE endpoint)
   └── Async generator:
       while True:
           event = await queue.get()     # Blocks until progress event
           yield f"data: {json.dumps(event)}\n\n"
           if event["event"] in ("complete", "error"):
               break

3. Worker thread completes:
   ├── on_progress({"event": "progress", "pct": 100})
   ├── publish_event(run_id, loop, "complete", {results...})
   └── cleanup_job(run_id)  # Remove from _jobs and _progress_queues
```

### Cancellation

```python
def cancel_job(run_id: int) -> bool:
    future = _jobs.get(run_id)
    if future is None:
        return False
    cancelled = future.cancel()       # Only works if job hasn't started yet
    if cancelled:
        cleanup_job(run_id)
    return cancelled
```

`Future.cancel()` only succeeds if the job is still queued (not yet running). If the backtest is already in progress, cancellation is not supported -- the job runs to completion.

---

## SSE Bridge (Thread-to-Async)

**File**: `app/api/executor.py`

The SSE (Server-Sent Events) bridge solves a fundamental problem: backtest engine runs in a **worker thread** (synchronous), but SSE responses must be yielded from an **async generator** (asyncio). The bridge uses `loop.call_soon_threadsafe()` to safely cross the thread/async boundary.

### Bridge Pattern

```
Worker Thread                          Async Event Loop
─────────────                          ─────────────────
BacktestEngine.run()
  │
  ├── on_progress({"pct": 50})
  │     │
  │     └── callback(data):
  │           q = _progress_queues[run_id]
  │           loop.call_soon_threadsafe(     ──────>  q.put_nowait(event)
  │               q.put_nowait, event)                    │
  │                                                       v
  │                                          SSE generator:
  │                                            event = await q.get()
  │                                            yield f"data: {event}\n\n"
  │
  ├── on_progress({"pct": 100})    ──────>   yield progress event
  │
  └── publish_event("complete")    ──────>   yield complete event
                                             break (stream ends)
```

### Key Implementation Details

```python
def make_progress_callback(run_id: int, loop: asyncio.AbstractEventLoop) -> Callable:
    """
    Return a thread-safe callback that pushes progress events onto the
    asyncio.Queue so the async SSE generator can yield them.

    Called from a worker thread -- must NOT await or call async functions.
    """
    def callback(data: dict[str, Any]) -> None:
        q = _progress_queues.get(run_id)
        if q is not None:
            loop.call_soon_threadsafe(q.put_nowait, {"event": "progress", **data})
    return callback


def publish_event(run_id, loop, event, data):
    """Push a named event (e.g. 'complete', 'error') onto the queue from any thread."""
    q = _progress_queues.get(run_id)
    if q is not None:
        payload = {"event": event, **data}
        loop.call_soon_threadsafe(q.put_nowait, payload)
```

**Critical rules**:
- The callback runs in the **worker thread**, not the event loop
- It must **never** use `await` or call any coroutine
- `loop.call_soon_threadsafe()` is the only safe way to interact with the asyncio event loop from a non-async thread
- `asyncio.Queue` is used (not `queue.Queue`) because the consumer is an async generator

---

## Sim Mode Additional Threads

When `mode == "sim"`, the runner spawns two additional daemon threads beyond the standard live bot threads:

### PaperTradeStreamManager

**File**: `app/trading/exchange/sim/sim_stream.py`

Streams real-time aggTrade data from Binance mainnet to feed `PaperExchange` for order matching at realistic prices.

```
┌─────────────────────────────────┐
│  PaperTradeStreamManager        │
│  (1 daemon thread)              │
│                                 │
│  WebSocket: aggTrade stream     │
│  -> PaperExchange.on_tick()     │
│  -> Matches pending orders      │
│     at live market prices       │
└─────────────────────────────────┘
```

### PaperFundingScheduler

Simulates periodic funding rate payments for paper positions.

```
┌─────────────────────────────────┐
│  PaperFundingScheduler          │
│  (1 daemon thread)              │
│                                 │
│  Periodic timer                 │
│  -> Apply funding to positions  │
│  -> Notify via notifier         │
└─────────────────────────────────┘
```

### Sim Mode Thread Count

| Thread | Count | Purpose |
|--------|-------|---------|
| Main thread | 1 | Orchestration |
| BinanceStreamManager | 1 | Kline WebSocket (candle data) |
| PaperTradeStreamManager | 1 | AggTrade WebSocket (tick data for order matching) |
| PaperFundingScheduler | 1 | Funding rate simulation |
| Per-symbol trading | N | Strategy + Portfolio per symbol |
| **Total (sim mode)** | **4 + N** | -- |

---

## Thread Safety Rules for Agents

When modifying code in this repository, follow these rules to maintain thread safety.

### Safe to Modify (no locks needed)

| Component | Why Safe |
|-----------|----------|
| Strategy classes | Each symbol thread has its own instance. No sharing. |
| PortfolioManager methods | Each symbol thread has its own instance. No sharing. |
| ContextSnapshot | Frozen dataclass. Each symbol writes only its own key in `runner.contexts`. |
| PositionSnapshot | Frozen dataclass. Created fresh for each `analyze()` call. |
| AnalysisResult | Frozen dataclass. Created by strategy, consumed by runner, then discarded. |
| Action types | Frozen dataclasses. Created once, read once, never mutated. |
| BacktestEngine | Runs in isolated thread/process. No shared state. |
| MockExchange | One instance per backtest job. Not shared. |
| Config dataclasses | Frozen. Immutable after construction. |

### Requires Lock Protection

| Component | Current Lock | Rule |
|-----------|-------------|------|
| `MarketDataStore.data` | Per-symbol `threading.Lock` | Always access through `update_candle()` or `get_dataframe()`. Never access `self.data` directly from outside the class. |
| `MarketDataStore.locks` | `self.global_lock` | Only accessed via `_get_lock()`. Never modify the locks dict directly. |
| CCXT exchange instance (`self._exchange` in BinanceAdapter) | `self._lock` | Every method that calls CCXT must hold `self._lock`. When adding new methods to BinanceAdapter, wrap CCXT calls with `with self._lock:`. |
| `_progress_queues` / `_jobs` in executor.py | Thread-safe by design (dict writes are GIL-protected, queue is `asyncio.Queue`) | Use provided helper functions (`create_progress_queue`, `get_progress_queue`, `cleanup_job`). Do not manipulate dicts directly. |

### Never Do

| Anti-pattern | Why | Instead |
|--------------|-----|---------|
| Share a Strategy instance across symbol threads | State contamination between symbols | Create one instance per thread in `_run_symbol_loop` |
| Access `MarketDataStore.data[symbol]` without lock | Race condition: stream thread may be writing while symbol thread reads | Use `get_dataframe()` which acquires lock and returns a copy |
| Call CCXT methods on `BinanceAdapter._exchange` without `self._lock` | CCXT is not thread-safe; concurrent calls corrupt internal state | Always use `with self._lock:` |
| Use `await` in a progress callback | Callbacks run in worker threads, not the async event loop | Use `loop.call_soon_threadsafe()` |
| Share `MockExchange` between concurrent backtest runs | Corrupts balance/position tracking | Each backtest job creates its own `MockExchange` |
| Modify `runner.contexts[symbol]` from a thread other than `Symbol-{symbol}` | No lock protects cross-symbol context writes | Each thread writes only its own symbol key |

### Adding a New Shared Resource

If you need to add a new resource that multiple threads access:

1. **Prefer immutability**: Use frozen dataclasses or namedtuples.
2. **Prefer thread-local**: Give each thread its own copy (like Strategy/Portfolio).
3. **If sharing is required**: Add a `threading.Lock` and document which data it protects.
4. **For async/thread bridge**: Use `loop.call_soon_threadsafe()` and `asyncio.Queue`.
5. **Never rely on the GIL** for correctness -- it protects individual bytecode operations, not logical operations.

---

## Key Source Files

| File | Threading Role |
|------|---------------|
| `app/trading/runner.py` | `MultiSymbolRunner` -- spawns and manages all live bot threads |
| `app/data/stream_manager.py` | `BinanceStreamManager` -- WebSocket daemon thread |
| `app/data/store.py` | `MarketDataStore` -- thread-safe candle storage |
| `app/trading/exchange/binance_adapter.py` | `BinanceAdapter` -- single lock for all CCXT calls |
| `app/api/executor.py` | `ThreadPoolExecutor` + SSE bridge for backtest concurrency |
| `app/trading/exchange/sim/sim_stream.py` | `PaperTradeStreamManager` -- aggTrade WebSocket for sim mode |
| `main.py` | Entry point; main thread lifecycle |
