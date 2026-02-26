# Recommended Research Stack

> Libraries and tools for quantitative signal research in Jupyter notebooks.

---

## Core (Already in Project)

| Library | Purpose | Notes |
|---------|---------|-------|
| `pandas` | Data manipulation | Already used throughout the bot |
| `numpy` | Numerical computation | Already a dependency |
| `pandas_ta` | Technical indicators | Same library the bot uses — ensures research indicators match production |

## Visualization

| Library | Purpose | Install |
|---------|---------|---------|
| `matplotlib` | Static charts, publication-quality plots | `pip install matplotlib` |
| `plotly` | Interactive charts, zoom/pan/hover | `pip install plotly` |
| `mplfinance` | Candlestick charts | `pip install mplfinance` |

**Recommendation**: Use `plotly` for EDA (interactive exploration), `matplotlib` for final report charts.

## Quantitative Evaluation

| Library | Purpose | Install |
|---------|---------|---------|
| `vectorbt` | Vectorized backtesting in notebooks | `pip install vectorbt` |
| `quantstats` | Performance tearsheets, metrics | `pip install quantstats` |

**vectorbt** is ideal for rapid signal iteration — test hundreds of parameter combinations in seconds using vectorized NumPy operations. Use it during research; the bot's `BacktestEngine` is the production-grade simulation.

**quantstats** generates comprehensive tearsheets: Sharpe, Sortino, Calmar, drawdown analysis, monthly returns heatmap, rolling statistics.

## Statistical Analysis

| Library | Purpose | Install |
|---------|---------|---------|
| `scipy.stats` | Distribution analysis, statistical tests | Already a dependency of pandas |
| `statsmodels` | Stationarity tests (ADF), autocorrelation | `pip install statsmodels` |

Useful for: testing if returns are normally distributed, checking for serial correlation in signals, regime detection.

---

## Jupyter Setup

### Use the Project's Conda Environment

```bash
source C:/ProgramData/miniconda3/Scripts/activate rsi
pip install jupyterlab
jupyter lab
```

This ensures your notebook uses the same Python version and `pandas_ta` version as the bot.

### Recommended Notebook Directory

```
research/
├── 2026-02-25_rsi-divergence-study.ipynb
├── 2026-03-01_ema-crossover-filter.ipynb
├── data/                  # Symlink or copy from app/backtest/data/
└── utils/                 # Shared helper functions
```

Add `research/` to `.gitignore` or keep in a separate repository to avoid polluting the bot repo with large notebook files.
