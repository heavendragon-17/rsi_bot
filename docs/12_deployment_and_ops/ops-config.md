# Production Configuration

> Recommended config values for production deployment.

---

## Conservative Starting Config

```yaml
bot:
  active: true
  mode: 'live'
  debug: false
  telegram_enabled: true

exchange:
  name: 'binanceusdm'
  margin_type: 'ISOLATED'

timeframe: '15m'
warmup_candles: 220

symbols:
  - 'BTC/USDT'       # Start with 1 symbol

strategy: 'rsi_no_retest'

risk:
  max_position_size_pct: 0.20    # Conservative: 20% of balance per trade
  risk_per_trade_pct: 0.01       # Conservative: 1% risk per trade
  use_risk_based_sizing: true
  use_initial_capital_for_risk: true
  min_sl_distance_pct: 0.003
  leverage: 5                    # Conservative: 5x (not max)
  tp1_close_pct: 0.50
  tp2_close_pct: 0.50
```

## Scaling Up

After confirming stability (2+ weeks):
1. Increase `risk_per_trade_pct` gradually (0.01 → 0.02 → 0.03)
2. Increase `max_position_size_pct` (0.20 → 0.50)
3. Add more symbols
4. Increase leverage only if strategy shows consistent edge

## Process Management

For production, run the bot under a process supervisor:

```bash
# systemd (Linux)
# Create /etc/systemd/system/rsi-bot.service

# pm2 (cross-platform)
pm2 start "python main.py" --name rsi-bot

# Screen/tmux (simple)
screen -S rsi-bot python main.py
```

Ensure the supervisor restarts the bot on crash. The bot handles orphan position cleanup on startup.
