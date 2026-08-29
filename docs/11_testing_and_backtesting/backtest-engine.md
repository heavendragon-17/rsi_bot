# Backtest Engine

> Single backtest flow, portfolio mode, batch mode, tick-level paper replay, engine internals, and performance optimizations.

---

## Module Structure

The backtest module is organized into sub-packages under `app/backtest/`:

```
app/backtest/
├── signal_replay.py       # Offline BTC alert replay and Markdown audit log
├── signal_replay_cli.py   # Replay command-line argument parsing
├── signal_replay_data.py  # Vectorized CSV normalization and event loading
├── signal_replay_models.py # Typed replay result models
├── signal_replay_preparation.py # Cached point-in-time indicator preparation
├── engine/          # Core engines and event sources
│   ├── backtest_engine.py      # Single-symbol BacktestEngine
│   ├── portfolio_engine.py     # Multi-symbol PortfolioEngine
│   ├── event_source.py         # Candle event source for single backtest
│   ├── portfolio_event_source.py  # Time-sorted event multiplexer
│   ├── metrics.py              # Metrics computation
│   └── curves.py               # Equity/drawdown curve generation
├── exchange/        # Mock/simulated exchange adapters
│   ├── executor.py             # Order execution logic
│   └── mock_exchange.py        # MockExchange for backtesting
├── data/            # Data loading and downloading
│   ├── manager.py              # Data manager
│   ├── download.py             # OHLCV data download (CLI)
│   ├── inline_download.py      # API missing/stale CSV download, serialized per path
│   └── download_tick.py        # Tick data download
├── runners/         # Runner scripts for each backtest mode
│   ├── batch_runner.py         # Batch (multi-config) runner
│   ├── portfolio_runner.py     # Portfolio backtest runner
│   ├── tick_replay.py          # Tick-level paper replay
│   └── progress.py             # Progress reporting utilities
├── reporting/       # Report generation and export
│   ├── reporter.py             # Main report generator
│   ├── html.py                 # HTML report output
│   ├── export.py               # CSV/JSON export
│   ├── batch_report.py         # Batch run reports
│   └── styles.py               # Report styling
├── statistics/      # Statistical analysis and visualization
│   ├── analyzer.py             # Statistical analysis
│   ├── metrics.py              # Statistical metrics
│   └── visualize.py            # Chart/plot generation
├── optimization/    # (placeholder for future optimization tools)
├── service.py       # BacktestService — orchestrates runs
├── persistence.py   # DB persistence for backtest results
├── enrichment.py    # Result enrichment
├── config_builder.py # Config construction helpers
└── backtest.py      # CLI entry point
```

---

## Backtest Modes

The system supports 4 backtest modes via the `BacktestMode` enum:

| Mode | Runner | Description |
|------|--------|-------------|
| `single` | `BacktestEngine` | Single-symbol backtest against a local CSV |
| `portfolio` | `app/backtest/runners/portfolio_runner.py` | Multi-symbol chronological portfolio simulation |
| `batch` | `app/backtest/runners/batch_runner.py` | Batch runs across multiple configs/symbols |
| `tick_replay` | `app/backtest/runners/tick_replay.py` | Tick-by-tick replay through PaperExchange |

The repository also provides `app.backtest.signal_replay`, an offline
multi-timeframe replay for the Telegram-only `btc_rsi_cross_alert`. It is not
an order simulation and is intentionally separate from `BacktestEngine`.

## Historical BTC Alert Replay

Run the replay with native BTC M5, M15, H1, and H4 OHLCV CSVs:

```bash
python -m app.backtest.signal_replay \
    --m5 app/backtest/data/BTCUSDT_5m.csv \
    --m15 app/backtest/data/BTCUSDT_15m.csv \
    --h1 app/backtest/data/BTCUSDT_1h.csv \
    --h4 app/backtest/data/BTCUSDT_4h.csv \
    --start 2026-08-01 \
    --end 2026-08-28
```

By default this writes two independent manual-review files:
`app/backtest/report/signal_replay_2026-08-01_2026-08-28_m5.md` and
`app/backtest/report/signal_replay_2026-08-01_2026-08-28_m15.md`. Each file
contains only its own timeframe's confirmed cards, with the full Telegram
card fields and blank manual-review fields. To choose the paths explicitly,
use both `--output-m5 <path>` and `--output-m15 <path>`. The legacy combined
file remains available with `--output <path>`.

The public Python entry point is:

```python
run_btc_alert_replay(
    m5_path,
    m15_path,
    h4_path,
    start_utc7=None,
    end_utc7=None,
    output_path=None,
    *,
    h1_path=None,
    output_m5_path=None,
    output_m15_path=None,
)
```

When `output_path` is omitted, the API writes the default M5 and M15 files.
When `output_path` is provided, it writes one combined report for backward
compatibility. Explicit split paths must be supplied together, and cannot be
combined with `output_path`.

Each input CSV must contain `timestamp, open, high, low, close, volume`.
Naive source timestamps use the repository's fixed UTC+07:00 storage
convention and are converted to UTC exactly once before evaluation. CLI dates
and naive Python datetimes are interpreted as UTC+7; date-only `--end` values
include the entire local day.

The runner keeps the full frames available for indicator warmup, skips initial
M5/M15 candles until the trigger and both H1/H4 contiguous-history minimums are
available, and reports those skipped warmup candles separately from later
not-ready data. It precomputes the locked indicators once per contiguous
segment, then evaluates M5 and M15 trigger candles chronologically with
constant-time point-in-time lookups. This avoids recalculating the complete
historical prefix for every candle. Homogeneous CSV timestamps are parsed in
one vectorized operation, and each event retains its source-array position so
the hot loop does not repeat datetime normalization or dictionary lookup.

The replay first runs an allocation-light NumPy candidate scan. Its vectorized
WMA45 is used only to produce a conservative candidate superset with a numeric
safety margin. Every possible signal then rebuilds the exact locked WMA values
and passes through the existing M5/M15 evaluator before cooldown, deduplication,
or logging. Rejected candles therefore avoid unnecessary `Decimal`, domain
model, SHA-256 event-ID, and Telegram-card allocation without changing signal
semantics. It selects only point-in-time H1/H4 data, applies the live one-hour
per-timeframe M5/M15 cooldowns and event deduplication, and writes only confirmed alerts. Every
written alert reuses the exact Telegram card formatter, including its indicator
snapshot and UTC+7 candle-close time.

This replay path is CPU-only. An Intel Arc or other GPU does not accelerate
pandas/NumPy automatically and is not required for a two-year BTC replay. On
the development machine, the 280,510-candle 2024-08-28 through 2026-08-28
replay improved from 12.43 seconds to 3.87 seconds; this is a local benchmark,
not a runtime guarantee.

Each Markdown report includes a confirmed-signal count and blank `WIN`,
`LOSS`, and `SKIP` review fields. It does not calculate win rate, PnL, SL/TP,
orders, or any automated outcome because the alert card has no trade-lifecycle
levels; outcomes remain manual chart-review decisions.

### BTC Signal Review Lab

The backtest UI's **Signal Review** workspace runs the same deterministic BTC
alert replay, but persists a research dataset instead of `RunResult` or
`Trade` rows. Each run is immutable and records the replay definition, Git
revision, requested UTC+7 window, source CSV facts, counters, and status.
Each emitted alert becomes an immutable `SignalReplaySignal` with the exact
Telegram card plus a versioned structured snapshot. A unique
`(replay_run_id, event_id)` constraint prevents duplicate alerts within a run;
rerunning a window creates a new run and never overwrites prior data.

The review layer keeps two labels independent:

- `quality`: `UNREVIEWED`, `GOOD`, `BAD`, or `UNCERTAIN`;
- `human_outcome`: `UNSET`, `WIN`, `LOSS`, or `SKIP`.

The initial chart exposes candles at or before the trigger close only. Saving
any explicit quality label unlocks forward candles and the human outcome
controls. The chart uses the trigger candle close as its reference and shows
1h, 4h, 12h, and 24h close-return, maximum favorable excursion, and maximum
adverse excursion observations. These are market observations, not simulated
trade PnL: there are no fills, TP/SL levels, sizing, fees, leverage, or
execution assumptions.

The availability endpoint validates the current M5, M15, H1, and H4 CSVs and
returns their common candle-close range. Omitted replay boundaries default to
that full intersection; supplied boundaries are rejected before job creation
when they fall outside it. Only one signal replay may run at a time, and a
`running` database row without an in-memory executor job is reconciled to a
clear interrupted/failed state after an API restart.

The worker uses the existing ThreadPoolExecutor/SSE infrastructure and loads
the four current CSVs. Forward observations prepare one timestamp index and
one set of NumPy OHLC arrays per trigger timeframe, then use binary searches
and bounded slices for every signal/horizon. This avoids rescanning an entire
source frame for every signal. SSE phases continue after signal detection as
`metrics` and `saving`, so the UI no longer appears frozen while rows are
prepared and committed. Signals, latest reviews, and forward metrics are
persisted in one transaction before the run is marked complete.

CSV candles remain outside SQLite; chart responses report missing historical
data, shortened future data, and incomplete horizons explicitly. Markdown
replay reports remain available through the existing CLI as an optional
audit/export format.

---

## System Architecture

```
React Frontend (Zustand stores)
    │ HTTP / SSE
FastAPI Backend
    ├── Routes: backtest_run.py, backtest_results.py, backtest_stream.py
    ├── BacktestService (app/backtest/service.py)
    ├── Executor (ThreadPoolExecutor, SSE queues)
    ├── BacktestEngine (MockExchange, Strategy, PortfolioManager)
    └── SQLite DB (runs, configs, results, trades)
```

---

## Single Backtest Flow

```
User clicks "Run Backtest"
    │
    ▼
POST /api/backtest/run
    1. Validate request; download a missing or stale CSV when required
    2. Create Run row (status="running") + RunConfig row
    3. Create asyncio.Queue for SSE progress
    4. Submit BacktestEngine.run() to ThreadPoolExecutor
    5. Return { run_id, status: "running" }
    │
Frontend opens SSE: GET /api/backtest/{run_id}/progress
    ├── "progress" events → update progress bar (0-100%)
    ├── "complete" event → fetch results
    └── "error" event → show toast + mark failed
    │
On complete:
    1. getRunDetail(run_id)  → metrics + trades
    2. getTimeseries(run_id) → equity/drawdown curves (zlib decompressed)
    3. Render ResultsDashboard
```

Inline downloads use one `threading.Lock` per CSV path. API jobs share a
single-process thread pool, so this prevents concurrent writes to the same
dataset without platform-specific file locking.

---

## BacktestEngine Internals

**Class**: `BacktestEngine(Engine)` in `app/backtest/engine/backtest_engine.py`

### Initialization

1. Read CSV, parse timestamps
2. Create `MockExchange(initial_balance, leverage, taker_fee=0.05%, maker_fee=0.02%)` (in `app/backtest/exchange/mock_exchange.py`)
3. Create strategy instance and `PortfolioManager`
4. `_prepare_dataframe()`: set index, mark all `closed=True`, add `ts` column, run `strategy.indicators.compute()` once for the full dataset (O(n) pre-computation instead of per-candle O(n²)). Works with any `IIndicators` implementation (the unified `Indicators` class supports all strategies).

### WARMUP = 220 candles

First 220 candles are skipped (indicators need warmup). Events start from candle 221.

### Candle Processing (`_handle_candle_close()`)

1. `exchange.update_candle(symbol, o, h, l, c, ts)` — MockExchange checks wicks against pending SL/TP orders. Supports both LONG and SHORT positions:
   - LONG: SELL limit (TP) triggers when `low <= price`; SELL stop_market (SL) triggers when `low <= stopPrice`
   - SHORT: BUY limit (TP) triggers when `low <= price`; BUY stop_market (SL) triggers when `high >= stopPrice`
2. If exit orders executed and symbol no longer in exchange.positions → position fully closed → clean up local state, reset context to SCANNING. Position amounts are **signed** (positive=LONG, negative=SHORT). PnL: `amount × (exit - entry)` works for both directions.
3. `portfolio.sync_from_exchange()`
4. `strategy.analyze(symbol, df_slice, position, context)` → dispatch actions
5. Report progress every 2%

### End of Run

1. Close any open positions at final CSV price (`exit_reason="EOD"`)
2. Fire `on_progress({"pct": 100})`
3. Return `compute_results()`

---

## Results Structure

`compute_results()` returns:

| Key                                                     | Contents                                                                                                                             |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `metrics`                                               | total_trades, win/loss counts, win_rate, pnl stats, profit_factor, expectancy, avg_hold_hours, exit_reason_counts, consecutive stats |
| `risk_metrics`                                          | sharpe_ratio, sortino_ratio, calmar_ratio, volatility, var_95                                                                        |
| `drawdown`                                              | max_drawdown_pct/value, max_dd_duration, avg_drawdown_pct                                                                            |
| `monthly_returns`                                       | Per-month: pnl, pnl_pct, trade count                                                                                                 |
| `equity_curve`                                          | [{date, balance}, ...]                                                                                                               |
| `drawdown_curve`                                        | [{date, drawdown}, ...]                                                                                                              |
| `round_trips`                                           | Complete trade cycles with avg_exit_price, exit_reason                                                                               |
| `initial/final_balance`, `net_profit`, `net_profit_pct` | Summary                                                                                                                              |

### Round-Trip Construction

Multiple partial fills (TP1, TP2, SL) grouped under one round-trip. `avg_exit_price` = weighted average. Exit reason priority: SL > TP3 > TP2 > TP1.

---

## Batch Mode (Multi-Symbol)

Single engine instance simulating portfolio across all symbols simultaneously (NOT N independent backtests).

- **Capital**: Shared pool, risk-based sizing per trade
- **Exposure cap**: Total open value cannot exceed `equity × max_position_pct`; new trades rejected if exceeded
- **Data sync**: Intersection-only date range; small gaps (<5 candles) forward-filled, large gaps rejected
- **Results**: Portfolio aggregate + per-symbol breakdown + correlation matrix

---

## Unified Portfolio Mode

A true chronological portfolio simulation via `app/backtest/runners/portfolio_runner.py`.

- **Event Multiplexing**: `PortfolioEventSource` (in `app/backtest/engine/portfolio_event_source.py`) loads pre-computed CSVs for all configured symbols and uses a priority queue to yield `CandleCloseEvent`s sorted strictly by time.
- **Global Liquidation**: `MockExchange.check_liquidation()` continuously monitors total portfolio equity (balance + margin + unrealized PnL). If it drops below zero, all positions are force-closed with an additional 0.5% liquidation fee penalty.
- **Sizing**: Trades use the exact same strategy config, but position sizing calculates risk based on a fixed initial portfolio capital percentage (if `use_initial_capital_for_risk` is set).
- **Auto Data Fetching**: On startup, it checks for missing historical data across all requested tickers and seamlessly attempts to download the data before processing to execution.

---

## Tick-Level Paper Backtest

Tick-by-tick replay through `PaperExchange` for high-fidelity SL/TP fill simulation.

**Entry**: `app/backtest/runners/tick_replay.py`

```bash
python -m app.backtest.runners.tick_replay \
    --ohlc app/backtest/data/BTCUSDT_5m.csv \
    --ticks app/backtest/data/BTCUSDT_ticks_2024_01.csv \
    --symbol BTC/USDT --timeframe 5m --balance 10000
```

- Exchange: `PaperExchange` — real FIFO SL/TP, gap fills, fees
- Tick CSV streamed line-by-line (low memory)
- OHLC and tick files must overlap in time range
- Runtime: 1-5 minutes per month of tick data

---

## Performance Optimizations

| Optimization            | Speedup             | Mechanism                        |
| ----------------------- | ------------------- | -------------------------------- |
| ProcessPoolExecutor     | 8-12× (grid search) | Bypasses GIL, parallel processes |
| float64 in MockExchange | 20-40% per run      | Replaces Decimal arithmetic      |
| Fixed-size tail window  | 10-25% per run      | O(1) DataFrame slicing vs O(n)   |

**Combined impact**: Grid search (200 params, 8 cores): ~600s → ~30-60s

---

## SSE Thread-to-Async Bridge

```python
# Worker thread → asyncio.Queue → SSE endpoint
mp_queue.put({"event": "progress", "pct": 42})
# Main thread polls mp_queue:
loop.call_soon_threadsafe(async_queue.put_nowait, msg)
# SSE endpoint:
event = await asyncio.wait_for(async_queue.get(), timeout=300)
```

### Crash Recovery

On server startup: query `runs` where `status='running'`, mark as `status='failed'` with note "Server restart — run interrupted".
