# PnL Calculation

> How profit and loss is tracked across live trading and backtesting.

---

## Live Trading PnL

### Realized PnL
Calculated implicitly when positions close:
- Exit market order fills at market price
- Exchange deducts fees from balance
- PnL = (exit_price - entry_price) × amount × side_multiplier - fees

**Not explicitly tracked by PortfolioManager**. The exchange balance before and after a trade cycle reflects the realized PnL.

### Unrealized PnL
- Fetched from exchange via `PositionSnapshot.unrealized_pnl`
- Represents mark-to-market PnL of the open position
- Updated by exchange in real-time

### Funding Fees
**Not currently tracked.** Binance perpetual futures charge/pay funding every 8 hours. These affect the balance but are not recorded by the bot. See [known-gaps.md](known-gaps.md).

### Trading Fees
- Deducted by the exchange on each order fill
- Reflected in the balance change but not separately tracked
- Fee rates depend on VIP level (taker ~0.04%, maker ~0.02%)

---

## Backtest PnL

### MockExchange Balance Tracking
MockExchange maintains `self.balance` and adjusts it on every fill:
- Entry: `balance -= margin` (margin = notional / leverage)
- Exit: `balance += margin + pnl - fees`
- Fees: taker 0.05%, maker 0.02% (hardcoded)

### BacktestEngine Metrics
`compute_results()` produces comprehensive PnL analysis:

| Metric | Calculation |
|--------|-------------|
| `net_profit` | `final_balance - initial_balance` |
| `net_profit_pct` | `net_profit / initial_balance × 100` |
| `total_pnl` | Sum of all round-trip PnLs |
| `avg_pnl` | `total_pnl / total_trades` |
| `avg_win` | Average PnL of winning trades |
| `avg_loss` | Average PnL of losing trades |
| `largest_win` | Max single-trade profit |
| `largest_loss` | Max single-trade loss |
| `gross_profit` | Sum of winning trade PnLs |
| `gross_loss` | Sum of losing trade PnLs |
| `profit_factor` | `gross_profit / |gross_loss|` |
| `expectancy` | `(win_rate × avg_win) + ((1 - win_rate) × avg_loss)` |

### Round-Trip Construction
Multiple partial fills (TP1, TP2, TP3, SL) within one trade are grouped into a single round-trip:
- `avg_exit_price` = weighted average of all exit fills
- `exit_reason` priority: SL > TP3 > TP2 > TP1 (if SL + TP both hit, annotated as e.g., `"TP2+SL"`)

### Risk Metrics
| Metric | Description |
|--------|-------------|
| `sharpe_ratio` | Annualized Sharpe (risk-free = 0) |
| `sortino_ratio` | Like Sharpe but only penalizes downside volatility |
| `calmar_ratio` | Annualized return / max drawdown |
| `volatility` | Annualized standard deviation of returns |
| `var_95` | Value at Risk at 95% confidence |

### Drawdown Metrics
| Metric | Description |
|--------|-------------|
| `max_drawdown_pct` | Largest peak-to-trough decline as percentage |
| `max_drawdown_value` | Largest peak-to-trough decline in absolute terms |
| `max_dd_duration` | Longest drawdown period (candles) |
| `avg_drawdown_pct` | Average drawdown across all drawdown periods |
