# Quant Research Workflow

> End-to-end process for discovering, evaluating, and deploying trading signals using this bot's infrastructure.

---

## Overview

```
Hypothesis → EDA → Signal Discovery → Signal Evaluation → Manual Handoff → Validation → Paper Trading → Live
```

The research phase happens in Jupyter notebooks. Once a signal is validated, it is manually coded into a strategy class and registered in the bot.

---

## Step 1: Hypothesis

Define a clear, testable hypothesis about market behavior:

- **Good**: "RSI divergence at EMA21 reclaim predicts a 1-2R move within 10 candles"
- **Bad**: "Find something that makes money"

Document in the notebook:
- Market regime assumption (trending, ranging, volatile)
- Asset class (BTC, ETH, altcoins — behavior differs)
- Timeframe (5m, 15m, 1h — different noise levels)
- Expected edge (why would this work? who is on the other side?)

## Step 2: Exploratory Data Analysis (EDA)

Download historical data using the bot's scripts:

```bash
python app/backtest/data/download.py --symbol BTC/USDT --timeframe 5m --limit 50000
```

In your notebook, explore:
- Price distribution, volatility regimes
- Indicator behavior (RSI, EMA crossovers, volume patterns)
- Correlation between signals and subsequent price moves
- Visual inspection of candidate setups on charts

## Step 3: Signal Discovery

Identify specific entry/exit conditions:
- Entry trigger (e.g., "RSI crosses above WMA while price reclaims EMA21")
- Exit conditions (TP levels, SL placement, time-based exits)
- Filter conditions (trend filter, volatility filter, time-of-day filter)

Code the signal logic in the notebook and apply it vectorized across the dataset.

## Step 4: Signal Evaluation

Run the signal through evaluation criteria (see [signal-evaluation.md](signal-evaluation.md)):
- Compute key metrics: Sharpe, drawdown, profit factor, win rate
- Check for overfitting red flags
- Test parameter sensitivity (small param changes shouldn't cliff performance)
- Validate across different time periods and market regimes

Use the bot's backtest engine for accurate simulation:
```bash
python app/backtest/backtest.py --data app/backtest/data/BTCUSDT_5m.csv --balance 10000
```

## Step 5: Manual Handoff

Code the signal as a strategy class following `docs/workflows/add-strategy.md`:
1. Create strategy file inheriting `BaseStrategy`
2. Implement `analyze()` method with stateless pattern
3. Define `DEFAULT_CONFIG` with all parameters
4. Register in loader, seed database

This is a manual process — the researcher translates notebook findings into production code.

## Step 6: Validation with Bot Tools

Use the bot's optimization suite:
1. **Grid search**: Sweep key parameters, check for sensitivity cliffs
2. **Walk-forward**: Out-of-sample validation to detect overfitting
3. **Sensitivity analysis**: Identify which parameters are fragile

Criteria for proceeding:
- Walk-forward verdict: "Robust" or "Marginal" (not "Overfit")
- Sensitivity: no parameter cliff within ±20% of chosen value
- Minimum trade count: 50+ trades in the test period

## Step 7: Paper Trading

Test with progressively more realistic execution:
1. `mock` mode — backtest on new, unseen data
2. `sim` mode — live ticks, simulated fills
3. `paper` mode — real exchange API, testnet funds

Monitor for at least 2-4 weeks in paper mode before considering live deployment.

## Step 8: Live Deployment

Switch to `live` mode with conservative position sizing. See `docs/12_deployment_and_ops/deployment-checklist.md`.
