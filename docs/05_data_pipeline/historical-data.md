# Historical Data Downloads

> How OHLCV candles and aggTrade tick data are downloaded and stored for backtesting.

---

## OHLCV Candle Download (`app/backtest/data/download.py`)

Downloads historical candles from Binance USDT-M Futures via CCXT with automatic pagination.

### CLI Usage

```bash
python app/backtest/data/download.py --symbol BTC/USDT --timeframe 5m --limit 5000
```

For the BTC signal replay, download the required native H1 context as well as
the trigger and trend timeframes:

```bash
python app/backtest/data/download.py --symbol BTC/USDT --timeframe 1h --days 732 --output app/backtest/data
```

### Arguments

| Arg | Default | Description |
|-----|---------|-------------|
| `--symbol` | `BTC/USDT` | Trading pair (CCXT slash format) |
| `--timeframe` | `5m` | Candle interval (`1m`, `5m`, `15m`, `1h`, `4h`, `1d`) |
| `--limit` | `1000` | Total candles to fetch (can exceed Binance's 1000 per-request limit) |
| `--output` | `app/backtest/data/` | Output directory |

### Pagination Logic

1. First request fetches `min(remaining, 1000)` most recent candles
2. Subsequent requests walk backward using `endTime = oldest_timestamp - 1`
3. Continues until `remaining == 0` or no more data from API
4. Deduplicates on timestamp (keeps last occurrence)
5. 0.5s sleep between requests for rate limiting

### Output

- **File**: `{SYMBOL_NO_SLASH}_{timeframe}.csv` (e.g., `BTCUSDT_5m.csv`)
- **Location**: `app/backtest/data/` (downloaded files are normally gitignored;
  the four canonical BTC Signal Review Lab CSVs are versioned exceptions)
- **Columns**: `timestamp, open, high, low, close, volume`
- **Sort order**: oldest-first
- **Timestamps**: Milliseconds converted to datetime with UTC+7 offset

---

## Tick Data Download (`app/backtest/data/download_tick.py`)

Downloads aggregated trade (aggTrade) data from Binance Vision public data repository. Used for tick-level paper backtesting.

### CLI Usage

```bash
# Single month
python app/backtest/data/download_tick.py --symbol BTCUSDT --year 2024 --month 1

# Multiple months with merge
python app/backtest/data/download_tick.py --symbol BTCUSDT --year 2024 --month 1 --months 3 --merge

# Recent N months (auto-merges, uses daily files for current month)
python app/backtest/data/download_tick.py --symbol BTCUSDT --recent 2
```

### Arguments

| Arg | Default | Description |
|-----|---------|-------------|
| `--symbol` | `BTCUSDT` | Trading pair (no-slash format) |
| `--year` | last completed month's year | Year to download |
| `--month` | last completed month | Starting month |
| `--months` | `1` | Consecutive months to download |
| `--recent N` | — | Last N months from today (hybrid: monthly archives + daily for current month) |
| `--merge` | `false` | Merge downloaded files into one CSV |
| `--output` | `app/backtest/data/` | Output directory |

### Download Sources

- **Monthly archives**: `https://data.binance.vision/data/futures/um/monthly/aggTrades/{SYM}/`
- **Daily archives**: `https://data.binance.vision/data/futures/um/daily/aggTrades/{SYM}/`
- Files are `.zip` containing `.csv`

### Output File Naming

| Mode | Pattern | Example |
|------|---------|---------|
| Single month | `{SYM}_ticks_{year}_{month:02d}.csv` | `BTCUSDT_ticks_2024_01.csv` |
| Single day | `{SYM}_ticks_day_{date}.csv` | `BTCUSDT_ticks_day_2024-01-15.csv` |
| Classic merge | `{SYM}_ticks_{start}_to_{end}.csv` | `BTCUSDT_ticks_202401_to_202403.csv` |
| Recent merge | `{SYM}_ticks_{start}_to_{end}.csv` | `BTCUSDT_ticks_20240101_to_20240225.csv` |

### `--recent` Mode Behavior

1. Computes download plan: completed months use monthly archives, current (incomplete) month uses daily archives from 1st to yesterday
2. Downloads all files
3. Automatically merges into single output
4. Individual files deleted after merge

---

## Data Storage

- **Location**: `app/backtest/data/`; downloaded files are normally gitignored,
  except for the four versioned BTC Signal Review Lab inputs
- **Format**: CSV
- **Size**: OHLCV CSVs are small (MBs). Tick CSVs can be large (hundreds of MBs per month for BTC)
- **Backtest UI data management**: The API (`/api/data/status`) checks if CSV files exist and returns metadata. The download endpoint (`/api/data/download`) triggers `download_data()` in a background thread

---

## Incremental Downloads

The OHLCV download always fetches fresh data (no incremental update). To extend an existing dataset, re-download with a larger `--limit`. The tick download downloads complete monthly/daily archives — no partial downloads.

The statement above applies to the legacy generic downloader. Core V2.1 uses
the stricter anchored reconcilers below.

---

## Core V2.1 anchored M15 acquisition

Core V2.1 has dedicated public-data acquisition under
`app/backtest/core_v2_1/` and `app/signal/core_v2_1/`. It covers the locked 24
Binance USD-M candidates, Binance BTC benchmark, and Hyperliquid PUMP
candidate. Exchange credentials and a Hyperliquid wallet are not required.

```bash
# 24 Binance candidates + BTC benchmark
python -m app.backtest.core_v2_1.binance_data \
  --data-dir app/backtest/data \
  --candle-count 5000 \
  --manifest artifacts/core_v2_1/binance_refresh.json

# Hyperliquid PUMP/USDC perpetual
python -m app.signal.core_v2_1.hyperliquid_export \
  --data-dir app/backtest/data \
  --candle-count 5000 \
  --manifest artifacts/core_v2_1/hyperliquid_refresh.json
```

`--symbols` may restrict the Binance command to an approved subset. PUMP has
the structural filename
`HYPERLIQUID__PUMP_USDC_PERP_15m.csv`; a Binance-style `PUMPUSDT_15m.csv`
cannot satisfy that identity.

### Shared storage and validation contract

- Stored columns remain `timestamp,open,high,low,close,volume`, oldest first.
- `timestamp` is the timezone-naive UTC+7 candle open used by the repository.
  Consumers normalize it to aware UTC close time.
- OHLCV values must be finite; prices must be positive; volume must be
  non-negative; and the series must have exact 15-minute cadence.
- Only fully finalized candles are written. Each command obtains an
  authoritative venue/server clock and uses a shared finalization boundary;
  failure to obtain that clock fails closed instead of falling back to the
  host clock.
- A fresh Binance file is paged from the locked feature anchor. An existing
  anchored prefix is preserved while gaps and the missing tail are reconciled;
  the requested recent Binance window is re-fetched authoritatively so venue
  revisions in that window replace local values. The full candidate file is
  strictly round-tripped before an atomic replacement.
- Duplicate API timestamps, interior gaps, or a missing anchor reject the
  Binance refresh rather than using first/last-wins deduplication. In an
  existing local Binance prefix, value-identical duplicate rows may be
  coalesced, but a conflicting duplicate anywhere in the preserved anchor
  history rejects the refresh before network acquisition. The PUMP exporter
  treats an identical inclusive overlap as idempotent and rejects a
  conflicting immutable-overlap value.
- JSON manifests record source identity, clock/boundary, row count, feature
  anchor, and SHA-256 so an acquisition can be audited independently.

### Hyperliquid retention rule

Hyperliquid's public candle API retains a rolling tail and accepts at most
5,000 candles for this exporter. The first canonical PUMP CSV must therefore
begin at the locked anchor. Later runs fetch an inclusive overlap with the
existing last close, verify that the overlap is unchanged, append only the
new tail, validate the whole anchored file, and replace it atomically.

If a fresh API request can no longer reach the locked anchor, or an existing
file is more than the retained tail behind, acquisition fails with an explicit
migration/recovery error. It must not create a new moving indicator seed. The
canonical validated PUMP CSV is also the cold-start source used to seed an
empty Core V2.1 runtime SQLite database before the latest public API tail is
reconciled.
