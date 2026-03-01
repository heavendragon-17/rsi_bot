# Backtest Engine

> Single backtest flow, batch mode, tick-level paper replay, engine internals, and performance optimizations.

---

## System Architecture

```
React Frontend (Zustand stores)
    │ HTTP / SSE
FastAPI Backend
    ├── Routes: /backtest, /history, /data, /strategies
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

**Class**: `BacktestEngine(Engine)` in `app/backtest/engine.py`

### Initialization

1. Read CSV, parse timestamps
2. Create `MockExchange(initial_balance, leverage, taker_fee=0.05%, maker_fee=0.02%)`
3. Create strategy instance and `PortfolioManager`
4. `_prepare_dataframe()`: set index, mark all `closed=True`, add `ts` column, run `Indicators.compute()` once for full dataset

### WARMUP = 220 candles

First 220 candles are skipped (indicators need warmup). Events start from candle 221.

### Candle Processing (`_handle_candle_close()`)

1. `exchange.update_candle(symbol, o, h, l, c, ts)` — MockExchange checks wicks against pending SL/TP orders
2. If SELL orders executed and symbol not in exchange.positions → position fully closed → clean up local state, reset context to SCANNING
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

A true chronological portfolio simulation via `app/backtest/run_portfolio_backtest.py`.

- **Event Multiplexing**: `PortfolioEventSource` loads pre-computed CSVs for all configured symbols and uses a priority queue to yield `CandleCloseEvent`s sorted strictly by time.
- **Global Liquidation**: `MockExchange.check_liquidation()` continuously monitors total portfolio equity (balance + margin + unrealized PnL). If it drops below zero, all positions are force-closed with an additional 0.5% liquidation fee penalty.
- **Sizing**: Trades use the exact same strategy config, but position sizing calculates risk based on a fixed initial portfolio capital percentage (if `use_initial_capital_for_risk` is set).
- **Auto Data Fetching**: On startup, it checks for missing historical data across all requested tickers and seamlessly attempts to download the data before processing to execution.

---

## Tick-Level Paper Backtest

Tick-by-tick replay through `PaperExchange` for high-fidelity SL/TP fill simulation.

**Entry**: `app/backtest/run_paper_tick_replay.py`

```bash
python app/backtest/run_paper_tick_replay.py \
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
