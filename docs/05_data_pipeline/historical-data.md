# Historical Data Downloads

> How OHLCV candles and aggTrade tick data are downloaded and stored for backtesting.

---

## OHLCV Candle Download (`app/backtest/data/download.py`)

Downloads historical candles from Binance USDT-M Futures via CCXT with automatic pagination.

### CLI Usage

```bash
python app/backtest/data/download.py --symbol BTC/USDT --timeframe 5m --limit 5000
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
- **Location**: `app/backtest/data/` (gitignored)
- **Columns**: `timestamp, open, high, low, close, volume`
- **Sort order**: oldest-first
- **Timestamps**: Milliseconds converted to datetime with UTC+7 offset

---

## Tick Data Download (`app/backtest/download_tick_data.py`)

Downloads aggregated trade (aggTrade) data from Binance Vision public data repository. Used for tick-level paper backtesting.

### CLI Usage

```bash
# Single month
python app/backtest/download_tick_data.py --symbol BTCUSDT --year 2024 --month 1

# Multiple months with merge
python app/backtest/download_tick_data.py --symbol BTCUSDT --year 2024 --month 1 --months 3 --merge

# Recent N months (auto-merges, uses daily files for current month)
python app/backtest/download_tick_data.py --symbol BTCUSDT --recent 2
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

- **Location**: `app/backtest/data/` (gitignored)
- **Format**: CSV
- **Size**: OHLCV CSVs are small (MBs). Tick CSVs can be large (hundreds of MBs per month for BTC)
- **Backtest UI data management**: The API (`/api/data/status`) checks if CSV files exist and returns metadata. The download endpoint (`/api/data/download`) triggers `download_data()` in a background thread

---

## Incremental Downloads

The OHLCV download always fetches fresh data (no incremental update). To extend an existing dataset, re-download with a larger `--limit`. The tick download downloads complete monthly/daily archives — no partial downloads.
