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

---

## Core V2.1 signal-only rollout

Core V2.1's standalone process is an advisory service, not a stage in the
`mock → sim → paper → live` execution progression above.

- [ ] Activate the repository's Conda `rsi` environment and run the focused
  Core V2.1 tests plus the complete `python -m pytest tests -q` suite.
- [ ] Refresh/validate all 24 Binance candidate files plus BTC using an
  authoritative Binance clock and retain the acquisition manifest.
- [ ] Verify the canonical Hyperliquid PUMP CSV begins at the locked feature
  anchor, extends through the finalized tail, and has a matching manifest.
- [ ] Re-run the full 25-candidate point-in-time replay and compare metadata,
  event counts, input hashes, and determinism with the reviewed artifact.
- [ ] Configure only `TELEGRAM_BOT_TOKEN` and the target chat/topic. Do not
  provision exchange trading keys or a Hyperliquid wallet for this runtime.
- [ ] Start with a new dedicated SQLite path and confirm cold bootstrap is
  silent, the canonical PUMP CSV is accepted, every market reaches the exact
  finalized tail, and health reports coordinator/poller ready.
- [ ] Stop during a controlled catch-up, restart against the same SQLite file,
  and verify cursor/state parity and deliverable post-cursor outbox events.
- [ ] Exercise Telegram failure/retry and outbox lease reclamation. Accept the
  documented at-least-once duplicate window and verify deterministic event
  tags are visible.
- [ ] Stop and restart the standalone runtime. Treat any poller/outbox stop
  timeout as an incomplete shutdown; do not launch a replacement beside the
  still-live worker.
- [ ] Alert on poller death/not-ready/error, stale last success, and growing
  `pending`/`retry`/expired `inflight` outbox counts.
- [ ] Preserve the SQLite file and anchored CSVs across process restarts;
  changing the feature anchor requires an explicit versioned migration.

Do not describe this rollout as paper trading or live trading. The process has
no order adapter and cannot establish fills, PnL, win rate, or taken/skipped
status. See [Core V2.1 standalone runtime](../07_trading_strategies/signal-bot.md#core-v21-standalone-durable-runtime).
