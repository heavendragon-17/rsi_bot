# Paper Backtest (Tick-Level Replay)

A higher-fidelity backtesting mode that replays real aggTrades tick data through `  SimExchange` instead of using the wick-approximation `MockExchange`. This measures precise SL/TP fill prices, FIFO ordering, and gap scenarios that OHLC-based backtests cannot capture.

---

## When to Use

- **Final validation** before deploying a strategy to live/paper trading
- **Verifying fill assumptions** — check whether SL/TP levels are hit in a different order than the standard wick-based engine assumes
- Comparing metrics against the standard backtest to find **overfitting** to OHLC shapes

---

## Prerequisites

You need **two data files** that cover the **same time window**:

### 1. OHLC Candle CSV

If you don't already have OHLC data for the symbol and timeframe, download it:

```bash
python app/backtest/download_data.py --symbol ZILUSDT --timeframe 5m --limit 8700
```

This saves to `app/backtest/data/ZILUSDT_5m.csv`.

### 2. Tick (aggTrades) CSV

**Option A — Exact N months from today (recommended):**

This automatically uses monthly archives for completed months and daily archives for the current (incomplete) month:

```bash
python app/backtest/download_tick_data.py --symbol ZILUSDT --recent 3
```

**Option B — Specific month:**

```bash
python app/backtest/download_tick_data.py --symbol ZILUSDT --year 2026 --month 1
```

**Option C — Multiple months (completed months only):**

```bash
python app/backtest/download_tick_data.py --symbol ZILUSDT --year 2026 --month 1 --months 3 --merge
```

> **Important:** The OHLC and tick files **must cover the same time window**. If only a partial overlap exists, the replay script will only simulate candles that fall within the tick file's range.

---

## Running the Paper Backtest

```bash
python app/backtest/run_paper_tick_replay.py \
    --ohlc   app/backtest/data/ZILUSDT_5m.csv \
    --ticks  app/backtest/data/ZILUSDT_ticks_2026_01.csv \
    --symbol ZIL/USDT \
    --timeframe 5m \
    --balance 10000 \
    --strategy rsi_no_retest
```

### CLI Arguments

| Argument      | Required | Default         | Description                                         |
| ------------- | -------- | --------------- | --------------------------------------------------- |
| `--ohlc`      | Yes      | —               | Path to the OHLC candle CSV                         |
| `--ticks`     | Yes      | —               | Path to the aggTrades tick CSV                      |
| `--symbol`    | No       | `BTC/USDT`      | Trading pair (must match the data files)            |
| `--timeframe` | No       | `5m`            | Candle timeframe                                    |
| `--balance`   | No       | `10000`         | Initial USDT balance                                |
| `--strategy`  | No       | `rsi_no_retest` | Strategy to use (`rsi_no_retest`, `rsi_wma_retest`) |

---

## How It Works

```
OHLC CSV
    │
    ▼
strategy.indicators.compute()   ← pre-compute all indicators once (WARMUP=220)
    │
    ▼
Candle loop (per closed candle):
  ├── PaperExchange.on_kline_open(open_price)  ← fill pending entry orders
  ├── Tick sub-loop:
  │     for each aggTrade tick in candle window:
  │         PaperExchange.on_tick(symbol, price, ts)  ← check SL/TP fills
  └── strategy.analyze() → actions → PortfolioManager.on_signal() / close / move SL
    │
    ▼
BacktestEngine.compute_results()  ← same P&L / Sharpe / drawdown metrics
```

1. **Indicators are pre-computed** from the full OHLC CSV (same path as the standard engine).
2. **Each candle** is processed in order. At the open of a new candle, pending entry orders are filled.
3. **Within each candle**, the real aggTrade ticks are replayed one-by-one through `PaperExchange.on_tick()`, which checks for SL/TP fills at the exact tick price.
4. **After all ticks** for a candle, the strategy runs `analyze()` to generate new signals.
5. **Metrics** are computed using the same helpers as `BacktestEngine`, so results are directly comparable.

---

## Key Design Decisions

| Concern       | Decision                                                                        |
| ------------- | ------------------------------------------------------------------------------- |
| Memory        | Tick CSV is streamed line-by-line (`csv.DictReader`), never fully loaded        |
| Exchange      | `PaperExchange` (not `MockExchange`) — real SL/TP FIFO, gap fills, fees         |
| Strategy      | Identical path to `BacktestEngine` — same `ContextSnapshot`, `PortfolioManager` |
| Metrics       | Uses `BacktestEngine` static helpers — identical metric definitions             |
| Notifications | Telegram silenced with mock notifier (replay mode)                              |

---

## Comparison with Standard Backtest

| Feature            | Standard (`BacktestEngine`) | Tick Replay (`run_paper_tick_replay.py`) |
| ------------------ | --------------------------- | ---------------------------------------- |
| Fill simulation    | Wick-based (MockExchange)   | Tick-by-tick (PaperExchange)             |
| SL/TP FIFO         | Not modeled                 | Exact, per-tick FIFO                     |
| Gap scenario fills | At wick extremes            | At stop/limit price exactly              |
| Speed              | ~1-2s per 9k candles        | Minutes for 40M ticks                    |
| Best for           | Strategy parameter search   | Final validation / paper testing         |

---

## Understanding the Output

The script prints a summary report to the console including:

- **Net Profit**, **Win Rate**, **Max Drawdown**, **Sharpe Ratio**
- **Total Trades**, **Average Win**, **Average Loss**
- **Profit Factor**, **Expectancy**

Compare these numbers against a standard backtest on the same data range to assess how much the wick-based simulation diverges from tick-level reality.
