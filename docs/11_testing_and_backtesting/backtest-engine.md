# Backtest Engine

> Single backtest flow, portfolio mode, batch mode, tick-level paper replay, engine internals, and performance optimizations.

---

## Module Structure

The backtest module is organized into sub-packages under `app/backtest/`:

```
app/backtest/
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

---

## Core V2.1 point-in-time replay

Core V2.1 has a separate deterministic event replay in
`app/backtest/core_v2_1/`. It calls the same pure evaluator as the live
signal-only runtime; it does not run `MockExchange`, synthesize fills, or
calculate portfolio metrics.

```bash
# Reviewer stepping stone: ETH, SOL, BNB, XRP, LINK, HYPE + BTC context
python -m app.backtest.core_v2_1 \
  --universe-mode six \
  --data-dir app/backtest/data \
  --output-dir artifacts/core_v2_1/replay

# Locked 25-candidate mixed-venue universe + BTC benchmark
python -m app.backtest.core_v2_1 \
  --universe-mode full \
  --data-dir app/backtest/data \
  --output-dir artifacts/core_v2_1/full_replay
```

`--universe-mode available` replays all valid discovered candidates;
`--symbols` chooses an explicit approved subset. `--start` and `--end` require
timezone-aware boundaries. The default/common-window mode uses the
intersection shared by the selected candidates and BTC; `--full-available`
retains every trigger close and records unavailable contexts as explicit
`NOT_READY` ledger rows.

### Data and point-in-time rules

1. Load the venue-specific M15 CSV for every selected candidate and Binance
   BTC benchmark. PUMP resolves only to
   `HYPERLIQUID__PUMP_USDC_PERP_15m.csv`.
2. Normalize the stored timezone-naive UTC+7 candle-open timestamp to aware
   UTC close time.
3. Strictly validate schema, OHLCV, duplicates, cadence, forming candles,
   locked anchor, source identity, and coverage.
4. Derive H1/H4 on UTC epoch boundaries from complete M15 buckets. Partial
   buckets are discarded.
5. At each candidate M15 close, require the exact latest expected Alt H1, BTC
   H1, and BTC H4 close. No future row and no one-bucket-stale fallback is
   allowed.
6. Process each candidate's state chronologically from the locked feature
   anchor and write every decision, including silent/rejected/not-ready rows.

### Audit outputs

Each run writes:

- `core_v2_1_replay.jsonl` for one complete structured record per trigger;
- `core_v2_1_replay.csv` for spreadsheet/filter workflows; and
- `core_v2_1_replay.metadata.json` for hashes, inputs, coverage, anchor,
  timestamp/seed conventions, counts, and requested/actual window.

The checked full-universe artifact under `artifacts/core_v2_1/full_replay/`
covers all 25 candidates plus BTC from `2026-06-29T11:30:00Z` through
`2026-08-20T13:15:00Z`: 125,000 ledger records, 98,550 evaluated rows,
26,450 `NOT_READY` rows, and 477 public events (`63 A_PLUS_LONG`,
`207 WAIT_FOR_PULLBACK`, `19 PULLBACK_LONG`, `72 WAIT_CANCELLED`, and
`116 WAIT_EXPIRED`). See the adjacent
[`artifacts/core_v2_1/README.md`](../../artifacts/core_v2_1/README.md) for
reproduction and artifact hashes.

These counts audit signal/state-machine behavior only. They make no claim
about orders, fills, fees, slippage, PnL, win rate, or strategy performance.
A future execution simulator must implement those separately under the
reviewed execution contract.

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
    1. Validate request + check CSV exists
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
