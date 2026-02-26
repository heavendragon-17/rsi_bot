# Deployment Checklist

> Step-by-step progression from development to production trading.

---

## Recommended Progression

```
mock → sim → paper → live
```

### Step 1: Mock (Backtesting)
- [ ] Run backtest with historical data
- [ ] Verify strategy produces expected metrics (Sharpe > 1.0, drawdown < 20%)
- [ ] Run grid search to check parameter sensitivity
- [ ] Run walk-forward to validate out-of-sample performance
- [ ] Verdict should be "Robust" or "Marginal"

### Step 2: Sim (Live Ticks, Simulated Fills)
- [ ] Set `bot.mode: sim` in `config.yaml`
- [ ] Run for at least 1 week to observe behavior with live data
- [ ] Check Telegram notifications are accurate
- [ ] Verify entry/exit logic matches expectations from backtest

### Step 3: Paper (Testnet)
- [ ] Set `bot.mode: paper` in `config.yaml`
- [ ] Configure `BINANCE_TESTNET_API_KEY` and `BINANCE_TESTNET_SECRET_KEY` in `.env`
- [ ] Run for at least 2-4 weeks
- [ ] Verify orders are placed and filled correctly on testnet
- [ ] Monitor for position drift or missed fills
- [ ] Test manual stop/restart — verify orphan position cleanup works

### Step 4: Live (Production)
- [ ] Set `bot.mode: live` in `config.yaml`
- [ ] Configure `BINANCE_API_KEY` and `BINANCE_SECRET_KEY` in `.env`
- [ ] **Double-check**: correct API keys, conservative position sizing
- [ ] Set `risk.max_position_size_pct` conservatively (start with 0.1-0.3)
- [ ] Set `risk.risk_per_trade_pct` conservatively (start with 0.01)
- [ ] IP-whitelist API keys on Binance
- [ ] Disable withdrawal permissions on API keys
- [ ] Start with a single symbol
- [ ] Monitor closely for first 48 hours
- [ ] Gradually increase position sizes after confirming stability
