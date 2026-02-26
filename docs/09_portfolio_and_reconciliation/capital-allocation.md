# Capital Allocation

> How capital is managed across multiple symbols and positions.

---

## Shared Capital Pool

All symbols trade from the same exchange balance. There is no per-symbol capital allocation or segregation.

```
Total Balance: $10,000
├── BTC/USDT position: using $2,000 margin
├── ETH/USDT position: using $1,500 margin
└── Available: $6,500
```

---

## Position Sizing

### Risk-Based (Default)

```
risk_capital = initial_capital (if use_initial_capital_for_risk) else current_balance
risk_amount = risk_capital × risk_per_trade_pct          # e.g., $10,000 × 0.02 = $200
sl_distance_pct = |entry - sl| / entry                   # e.g., 2%
position_notional = risk_amount / sl_distance_pct         # e.g., $200 / 0.02 = $10,000
position_size = position_notional / entry_price           # e.g., $10,000 / $50,000 = 0.2 BTC
```

### Max Position Cap

```
max_notional = balance × max_position_size_pct × leverage  # e.g., $10,000 × 0.99 × 10 = $99,000
max_amount = max_notional / entry_price
final_size = min(risk_based_size, max_amount)
```

### `use_initial_capital_for_risk`

| Setting | Behavior |
|---------|----------|
| `True` (default) | Risk calculated on starting capital — consistent sizing regardless of P&L |
| `False` | Risk calculated on current balance — position sizes grow/shrink with performance |

---

## Multi-Symbol Considerations

### Concurrent Positions
- Multiple symbols can have open positions simultaneously
- Each position is sized independently based on its own SL distance
- No check for total exposure across all positions

### Capital Availability
- Position sizing uses `exchange.fetch_balance()` to get available margin
- If previous positions consumed margin, less is available for new entries
- The `max_position_size_pct` cap applies per-trade, not portfolio-wide

---

## Configuration Reference

```yaml
risk:
  risk_per_trade_pct: 0.02        # Risk 2% per trade
  max_position_size_pct: 0.99     # Max 99% of balance as margin per trade
  leverage: 10                    # 10x leverage
  use_risk_based_sizing: true     # Use risk-based (vs. fixed fraction)
  use_initial_capital_for_risk: true  # Risk on initial capital
  min_sl_distance_pct: 0.003      # Skip trades with SL closer than 0.3%
  tp1_close_pct: 0.33             # Close 33% at TP1
  tp2_close_pct: 0.50             # Close 50% of remaining at TP2
```
