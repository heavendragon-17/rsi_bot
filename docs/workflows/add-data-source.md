# Add a Data Source / Stream Manager

> Add a new market data stream (live) or historical data source (backtest).
> Reference implementations:
>   - Live stream: `app/services/market_data/stream_manager.py` (BinanceStreamManager)
>   - Event source bridge: `app/services/market_data/live_event_source.py` (LiveEventSource)
>   - Backtest data: `app/backtest/backtest_event_source.py` (BacktestEventSource)
>   - Event source interface: `app/core/event_source.py`

## Prerequisites

- Read `docs/live-bot.md` — Data Ingestion section
- Read `docs/backtest-engine.md` — data management section
- Read `app/core/event_source.py` — `IEventSource` interface
- Identify which path you're modifying: live stream, sim tick feed, or historical CSV

---

## Path A: Live Stream (Real-Time Data)

### A1. Create a stream manager

File: `app/services/market_data/{name}_stream_manager.py`

Model on `app/services/market_data/stream_manager.py` (BinanceStreamManager). Required:

- **`start(store)`** method: begin streaming, populate `MarketDataStore` via `store.update_candle(candle)`
- **`stop()`** method: graceful shutdown (close WebSocket, join threads)
- **Callbacks**: Set `on_kline_close: Callable[[Candle], None]` and `on_tick: Callable[[Candle], None]` (optional, used by `LiveEventSource`)
- **Normalization**: Convert exchange-specific data format to `Candle` objects from `app/core/events.py`
- **Thread safety**: Stream runs in a daemon thread; `MarketDataStore` is already thread-safe
- **Reconnection**: Handle disconnects with exponential backoff

### A2. Create an event source bridge

File: `app/services/market_data/{name}_live_event_source.py`

Model on `app/services/market_data/live_event_source.py`. Implement `IEventSource`:

- `events()` → `Iterator[EngineEvent]`: yields `CandleCloseEvent` on each closed candle
- `stop()`: signals the stream to stop and unblocks the `events()` generator
- Bridge between the stream manager's callback-based API and the Engine's iterator-based API

### A3. Inject into the runner

File: `app/core/runner.py` (MultiSymbolRunner) or wherever `_start_stream()` is called.

Currently hardcoded to `BinanceStreamManager`. Add routing based on `config['exchange']['name']` or a new `config['data_source']` key. The unified `Engine` accepts any `IEventSource`, so swapping is straightforward at the event source level.

---

## Path B: Historical Data (Backtest)

### B1. Create a download script

File: `app/backtest/download_{name}.py`

Fetch OHLCV data and write CSV to `app/backtest/data/{SYMBOL}_{timeframe}.csv`.

Required CSV columns (matching existing format):
```
timestamp,open,high,low,close,volume
```

Where `timestamp` is Unix milliseconds. The backtest engine reads from this path via `BacktestEventSource`.

Model on `app/backtest/download_data.py` for CLI argument parsing.

### B2. Add a data API endpoint (optional)

File: `app/api/routes/data.py`

Add a download-trigger endpoint that runs the download script. Model on the existing `/api/data/download` endpoint. This allows the UI to trigger downloads from new data sources.

---

## Path C: Sim Tick Feed

For `PaperExchange` (sim mode), the tick feed comes from `app/paper/stream_manager.py`. If your new exchange needs sim mode support, create a similar tick-level stream that feeds `PaperExchange.on_tick()`.

## Testing

**Live stream (Path A):**
1. Unit test: mock WebSocket, verify `Candle` objects have correct fields
2. Unit test: verify `on_kline_close` callback fires only on closed candles (not partial updates)
3. Unit test: verify reconnection logic on disconnect
4. Integration test: run against testnet or mock server

**Historical data (Path B):**
1. Test that the download script produces valid CSV with correct columns
2. Test that `BacktestEventSource` can iterate over the generated CSV
3. Verify event count matches row count minus warmup period

Run `pytest tests/ -v` — all existing tests must pass.

## Documentation Impact

Consult `docs/INDEX.md` → "Code Path → Documentation File" table:

- `app/services/market_data/` modified → update **`docs/live-bot.md`**: Data Ingestion section — add the new stream manager, its WebSocket URL or API, symbol normalization rules, and startup sequence
- `app/backtest/` modified → update **`docs/backtest-engine.md`**: data management section — add the new data source and its CSV format
- If `app/core/event_source.py` modified → also update **`docs/architecture.md`**
