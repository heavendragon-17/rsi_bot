# Notebook Conventions

> Standards for research notebooks to ensure reproducibility and organization.

---

## Directory Structure

```
research/
├── YYYY-MM-DD_description.ipynb    # Date-prefixed for chronological ordering
├── data/                            # Symlink or copy from app/backtest/data/
└── utils/                           # Shared helper functions (optional)
```

Keep `research/` in `.gitignore` or a separate repository to avoid bloating the bot repo.

## File Naming

```
YYYY-MM-DD_description.ipynb
```

Examples:
- `2026-02-25_rsi-divergence-ema21-reclaim.ipynb`
- `2026-03-01_volume-spike-entry-filter.ipynb`
- `2026-03-10_btc-eth-correlation-study.ipynb`

## Notebook Structure

Every research notebook should follow this structure:

```
1. Title & Hypothesis
   - What market behavior are we testing?
   - What is the expected edge?

2. Data Loading
   - Source (Binance Vision, CCXT download)
   - Symbol, timeframe, date range
   - Data quality checks (gaps, duplicates)

3. Exploratory Data Analysis
   - Price/volume visualization
   - Indicator behavior
   - Pattern identification

4. Signal Logic
   - Entry conditions (code + explanation)
   - Exit conditions (SL, TP, time-based)
   - Filter conditions

5. Backtest Results
   - Key metrics table (Sharpe, drawdown, profit factor, etc.)
   - Equity curve plot
   - Trade list / sample trades

6. Conclusion
   - Is the signal worth pursuing? (Yes/No/Needs more work)
   - Next steps
   - Parameters for strategy implementation
```

## Reproducibility Rules

1. **Pin random seeds**: `np.random.seed(42)` at the top of every notebook
2. **Document data source**: exact CLI command used to download data
3. **Document date range**: start and end dates of the test period
4. **Save parameters**: write final parameter set to a cell or file for easy transfer to strategy code
5. **Version tag**: note the git commit hash of the bot codebase used (indicator behavior may change)

## Data Access

Use the bot's download scripts to get data:

```python
# In notebook — run once to download
!python app/backtest/download_data.py --symbol BTC/USDT --timeframe 5m --limit 50000

# Load the data
import pandas as pd
df = pd.read_csv("app/backtest/data/BTCUSDT_5m.csv", parse_dates=["timestamp"], index_col="timestamp")
```

Use `pandas_ta` for indicators to match the bot's production computation:

```python
import pandas_ta as ta
df["rsi"] = ta.rsi(df["close"], length=21)
df["ema21"] = ta.ema(df["close"], length=21)
```
