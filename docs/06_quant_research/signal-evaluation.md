# Signal Evaluation Criteria

> How to determine if a trading signal is worth coding into a production strategy.

---

## Key Metrics

| Metric | Target | Red Flag |
|--------|--------|----------|
| Sharpe Ratio | > 1.5 | > 3.0 (likely overfit) |
| Max Drawdown | < 20% | > 30% |
| Profit Factor | > 1.5 | < 1.2 |
| Win Rate | Depends on R:R | < 30% with R:R < 2 |
| Total Trades | > 50 in sample | < 30 (not statistically significant) |
| Avg Hold Time | Consistent with timeframe | Extreme outliers suggest data issues |
| Risk:Reward | > 1.5 | < 1.0 (negative expectancy likely) |

### Sharpe Ratio Guidelines
- `< 0.5` — Not worth pursuing
- `0.5 – 1.0` — Weak, needs significant improvement
- `1.0 – 1.5` — Acceptable for further development
- `1.5 – 2.5` — Strong signal, proceed with validation
- `> 3.0` — Suspiciously good, check for overfitting or look-ahead bias

---

## Robustness Checks

### 1. Parameter Sensitivity
Sweep each parameter ±20-50% from the chosen value. Performance should degrade gradually, not cliff:

```
param value:    8    10    12    14    16
Sharpe:        1.4   1.6   1.7   1.5   1.3   ← Gradual = robust
Sharpe:        0.3   0.4   1.8   0.2   0.1   ← Cliff = fragile, overfit
```

Use the bot's grid search or sensitivity analysis for this.

### 2. Walk-Forward Validation
Split data into in-sample (IS) and out-of-sample (OOS) windows:
- IS: optimize parameters
- OOS: test with fixed parameters
- Repeat across multiple windows

**Verdict criteria** (from the bot's walk-forward):
- **Robust**: OOS Sharpe ≥ 50% of IS Sharpe across majority of windows
- **Marginal**: Mixed results, some windows good, some bad
- **Overfit**: OOS consistently worse than IS

### 3. Market Regime Testing
Test the signal across different market conditions:
- **Strong uptrend** (e.g., BTC Q4 2023)
- **Strong downtrend** (e.g., BTC Q2 2022)
- **Range-bound / choppy** (e.g., BTC Q3 2023)
- **High volatility event** (e.g., around major news)

A robust signal should perform consistently, or at least not catastrophically fail in any regime.

### 4. Statistical Significance
- Minimum 50 trades for any meaningful statistical conclusion
- Check p-value of returns vs. zero (are profits statistically different from random?)
- Check for serial correlation in trade outcomes (clustered wins/losses suggest regime dependency)

---

## Common Overfitting Red Flags

1. **Too many parameters** — More than 5-7 tunable parameters increases overfitting risk
2. **Extreme parameter values** — Optimal values at the edge of tested range
3. **Perfect performance on specific period** — Falls apart outside that window
4. **High Sharpe + low trade count** — A few lucky trades, not a real edge
5. **Look-ahead bias** — Using future data in signal computation (e.g., using the current candle's close to decide entry on the same candle)
6. **Survivorship bias** — Only testing on assets that still exist/are popular

---

## Using the Bot's Validation Tools

After initial notebook evaluation, run the signal through the bot's optimization suite:

1. **Grid Search** (`POST /api/backtest/optimization/grid`): Sweep 2-3 key parameters, visualize as heatmap
2. **Walk-Forward** (`POST /api/backtest/optimization/walk-forward`): Automated IS/OOS window testing
3. **Sensitivity Analysis** (`POST /api/backtest/optimization/sensitivity`): Per-parameter impact assessment

The bot runs each configuration as a full backtest with realistic execution simulation (MockExchange with fees).
