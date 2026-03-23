# Backtest Guide

## Using the Backtest UI

### Starting the Application

1. Start the backend: `python -m uvicorn app.api.main:app --reload --port 8000`
2. Start the frontend: `cd ui && npm run dev`
3. Open `http://localhost:5173`

### Running a Single Backtest

1. **Select symbol** (e.g., BTC/USDT) in the sidebar
2. **Choose timeframe** (5m, 15m, 1h, 4h, 1d)
3. **Set date range** using the calendar picker or quick presets (7d, 30d, 90d, 1y)
4. **Configure capital**: Initial capital, leverage, risk per trade %
5. **Adjust strategy parameters** if needed (RSI period, TP ratios, etc.)
6. Click **Run**

If data is missing, a download modal will appear to fetch it from Binance.

### Understanding Results

After a backtest completes, you'll see:

**Hero Stats** (top row):

- Net Profit — total P&L in USDT
- Win Rate — percentage of winning trades
- Max Drawdown — largest peak-to-trough decline
- Sharpe Ratio — risk-adjusted return

**Metrics Grid**:

- Sortino, Calmar, Volatility, Profit Factor, Expectancy
- Average Win/Loss, Largest Win/Loss, Consecutive W/L

**Charts**:

- Equity Curve — your balance over time
- Exit Reasons — pie chart of why trades closed (TP1, TP2, SL, etc.)

**Trades Table**:

- Every trade with entry/exit times, prices, P&L
- Click a row to see the trade on a candlestick chart

### Comparing Runs

1. Go to the **History** tab
2. Select 2 runs using checkboxes
3. Click **Compare**
4. See overlaid equity curves and metrics diff table

### Batch Mode (Multi-Symbol)

Run backtests across multiple symbols with shared capital:

1. Switch to the **Batch** tab
2. Select multiple symbols
3. Set max exposure % (prevents over-allocation)
4. Run — the engine simulates portfolio management across all symbols simultaneously

## CLI Backtesting

For quick testing without the UI:

```bash
# Download data
python app/backtest/download_data.py --symbol BTC/USDT --timeframe 5m --limit 5000

# Run backtest
python app/backtest/backtest.py --data app/backtest/data/BTCUSDT_5m.csv --balance 10000
```

### Batch Analysis (CLI)

1. Edit `app/backtest/symbols.txt` — one symbol per line
2. Run: `python -m app.backtest.runners.batch_runner`
3. View results: `app/backtest/report/batch_report.html`

### Unified Portfolio Backtest (CLI)

A true **chronological multi-symbol simulation** where all tickers share a single capital pool and trades are simulated in real time order.

```bash
# Run with strategy from config.yaml
python -m app.backtest.runners.portfolio_runner

# Or specify a strategy directly
python -m app.backtest.runners.portfolio_runner --strategy rsi_no_retest
```

**Key behaviours:**

| Feature             | How it works                                                                                                                                                 |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Symbols**         | Reads `symbols` list from `config.yaml`                                                                                                                      |
| **Missing data**    | Automatically detects and downloads missing CSVs on startup. Aborts with a clear error if download fails.                                                    |
| **Position sizing** | Sizes trades as a fixed % of the _initial_ capital (not floating equity) — controlled by `risk_per_trade_pct` in `config.yaml`                               |
| **Leverage & fees** | Uses `leverage`, `taker_fee`, and `maker_fee` from `config.yaml`                                                                                             |
| **Liquidation**     | If total portfolio equity (balance + margin + unrealized PnL) drops ≤ 0, all positions are force-closed at a 0.5% liquidation fee penalty — simulation halts |
| **Output**          | Summary printed to console + full HTML report at `app/backtest/report/portfolio_backtest_report.html`                                                        |

**Key config knobs (in `config.yaml`):**

```yaml
risk:
  leverage: 10 # 10x futures leverage
  risk_per_trade_pct: 0.02 # Risk 2% of initial capital per trade
  use_initial_capital_for_risk: true # Use fixed initial balance for sizing

backtest:
  initial_balance: 10000 # Starting portfolio capital (USDT)
```

## Strategy Parameter Tuning

### Key Parameters to Experiment With

| Parameter           | Effect of Increasing           | Effect of Decreasing         |
| ------------------- | ------------------------------ | ---------------------------- |
| `rsi_period`        | Smoother signals, fewer trades | More responsive, more trades |
| `nr_lookback`       | Stricter pullback requirement  | More entries allowed         |
| `nr_rsi_spread_min` | Stronger momentum required     | More entries on weaker moves |
| `nr_tp1_rr`         | Higher first target            | Earlier profit taking        |
| `tp1_close_pct`     | More locked in at TP1          | More riding for TP2/TP3      |
| `nr_lock_profit_rr` | Wider SL after lock-profit     | Tighter protection           |

### Testing vs Production Settings

| Mode         | `nr_rsi_spread_min` | `nr_max_above_ema21` | Description                       |
| ------------ | ------------------- | -------------------- | --------------------------------- |
| Testing      | 1.5                 | 3                    | More signals for validating logic |
| Conservative | 2.5                 | 1                    | Fewer, higher-quality signals     |
| Aggressive   | 1.0                 | 5                    | Maximum signal frequency          |

## Advanced: Optimization Features

### Grid Search

Sweep two parameters simultaneously to find optimal combinations:

1. Go to **Grid Search** tab
2. Set X-axis parameter (e.g., `rsi_period`, range 10-30, step 2)
3. Set Y-axis parameter (e.g., `price_ema_fast`, range 10-30, step 2)
4. Choose metric to optimize (Sharpe, Net Profit, Win Rate)
5. Run — results shown as a heatmap

### Walk-Forward Optimization

Test parameter stability over time:

1. Go to **Walk-Forward** tab
2. Set in-sample (IS) and out-of-sample (OOS) window sizes
3. Choose parameter to optimize
4. Run — system optimizes on IS, validates on OOS, reports robustness verdict

### Sensitivity Analysis

Identify which parameters are fragile:

1. Go to **Sensitivity** tab
2. Set variation % (e.g., 20%)
3. Run — each parameter varied up and down, impact measured
4. Tornado chart shows which parameters most affect results
