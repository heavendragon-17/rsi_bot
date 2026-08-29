# Data Formats

> DataFrame schemas, CSV formats, and data normalization rules used throughout the system.

---

## OHLCV DataFrame Schema (MarketDataStore)

The canonical DataFrame structure used by strategies and indicators. Created by `MarketDataStore` and enriched by `Indicators.compute()`.

### Base Columns (from MarketDataStore)

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | datetime (index) | Candle open time, used as DataFrame index |
| `open` | float64 | Open price (for pandas math/indicators) |
| `high` | float64 | High price |
| `low` | float64 | Low price |
| `close` | float64 | Close price |
| `volume` | float64 | Volume |
| `closed` | bool | Whether candle is finalized (True for historical, toggles for live streaming) |
| `open_dec` | Decimal | Precision-safe open (for financial calculations) |
| `high_dec` | Decimal | Precision-safe high |
| `low_dec` | Decimal | Precision-safe low |
| `close_dec` | Decimal | Precision-safe close |

### Computed Indicator Columns (from Indicators.compute())

Added by `Indicators.compute(df)` — called once for full backtest data, or per-update for live data.

| Column | Type | Description |
|--------|------|-------------|
| `rsi` | float64 | RSI(period) — default period 21 |
| `rsi_ema9` | float64 | EMA(RSI, 9) — smoothed RSI |
| `rsi_wma45` | float64 | WMA(RSI, 45) — trend-following RSI |
| `ema21` | float64 | EMA(close, 21) — fast price EMA |
| `ema200` | float64 | EMA(close, 200) — slow trend filter |

Additional columns may be present depending on strategy configuration. The Indicators class uses `pandas_ta` for computation with manual fallbacks.

### Memory Constraints

- `MAX_CANDLES_IN_RAM = 6000` per symbol
- When DataFrame exceeds this, `.tail(6000)` is applied on append
- Backtest loads entire CSV into memory (no cap — CSV size is the limit)

---

## OHLCV CSV Format

Output of `app/backtest/data/download.py`. Input to `BacktestEngine`.

```csv
timestamp,open,high,low,close,volume
2024-01-01 07:00:00,42150.0,42180.5,42130.0,42165.3,125.4
2024-01-01 07:05:00,42165.3,42200.0,42160.0,42195.7,98.2
```

| Column | Type | Notes |
|--------|------|-------|
| `timestamp` | datetime string | `YYYY-MM-DD HH:MM:SS` (UTC+7) |
| `open` | float | |
| `high` | float | |
| `low` | float | |
| `close` | float | |
| `volume` | float | |

**File naming**: `{SYMBOL_NO_SLASH}_{timeframe}.csv` (e.g., `BTCUSDT_5m.csv`)

---

## Tick Data CSV Format (aggTrades)

Output of `download_tick_data.py`. Input to tick-level paper backtest.

Raw Binance Vision aggTrade CSV columns:

| Column | Description |
|--------|-------------|
| `agg_trade_id` | Aggregate trade ID |
| `price` | Trade price |
| `quantity` | Trade quantity |
| `first_trade_id` | First trade ID in aggregate |
| `last_trade_id` | Last trade ID in aggregate |
| `transact_time` | Transaction timestamp (milliseconds) |
| `is_buyer_maker` | True if buyer is maker (i.e., sell aggressor) |

**File naming**: `{SYM}_ticks_{year}_{month:02d}.csv` (e.g., `BTCUSDT_ticks_2024_01.csv`)

---

## Candle Normalization (WebSocket → DataFrame)

### Live Streaming (BinanceStreamManager)

WebSocket kline messages are parsed into `Candle` objects:

```python
@dataclass
class Candle:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    closed: bool        # True when candle finalizes
```

**Update behavior in MarketDataStore**:
- If last row timestamp matches incoming candle timestamp → **in-place update** (streaming price update)
- If timestamps differ → **append new row** (new candle opened)
- `closed=False` for streaming updates, `closed=True` when candle finalizes

### Backtest (BacktestEngine)

- CSV loaded directly into DataFrame
- All candles set to `closed=True` (historical data is always finalized)
- `ts` column added: epoch milliseconds (for MockExchange order matching)
- Indicators computed once for the full dataset during `_prepare_dataframe()`

---

## CSV File Location

Downloaded data normally lives in `app/backtest/data/` and is gitignored. The
four canonical BTC Signal Review Lab inputs are intentional versioned
exceptions: `BTCUSDT_5m.csv`, `BTCUSDT_15m.csv`, `BTCUSDT_1h.csv`, and
`BTCUSDT_4h.csv`. The API layer checks this directory via `/api/data/status`.

```
app/backtest/data/
├── BTCUSDT_5m.csv              # OHLCV candles
├── BTCUSDT_15m.csv             # Different timeframe
├── BTCUSDT_1h.csv              # BTC Signal Review Lab context
├── BTCUSDT_4h.csv              # BTC Signal Review Lab context
├── ETHUSDT_5m.csv              # Different symbol
├── BTCUSDT_ticks_2024_01.csv   # Monthly tick data
├── BTCUSDT_ticks_2024_02.csv
└── BTCUSDT_ticks_202401_to_202403.csv  # Merged tick data
```
