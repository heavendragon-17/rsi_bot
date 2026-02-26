# Monitoring

> How to monitor the live bot and detect issues.

---

## Telegram Notifications

The bot sends Telegram messages for key events:
- **Entry**: Symbol, side, entry price, SL/TP levels, position size
- **TP hit**: Which TP level, partial close amount, new SL
- **Exit**: Exit price, PnL, exit reason (SL, TP3, candle SL, etc.)
- **Errors**: Exchange errors, connection issues

### Health Indicators
- **Regular messages** = bot is running and processing signals
- **No messages for extended period** = either no signals or bot may be stuck
- **Error messages** = investigate immediately

## structlog Inspection

All bot output uses structured logging. Key patterns to monitor:

```bash
# Watch live bot output
python main.py 2>&1 | tee bot.log

# Search for errors
grep "level=error" bot.log

# Track specific symbol
grep "symbol=BTC/USDT" bot.log

# Watch order flow
grep "order_placed\|order_filled\|order_cancelled" bot.log
```

### Key Log Events

| Event | Level | Meaning |
|-------|-------|---------|
| `stream_connected` | info | WebSocket connected |
| `candle_update` | debug | New candle data received |
| `strategy_action` | info | Strategy emitted an action |
| `order_placed` | info | Order sent to exchange |
| `order_error` | error | Order failed |
| `position_opened` | info | New position created |
| `position_closed` | info | Position fully exited |

## Health Check (Backtest API)

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

## What to Monitor

| Metric | Warning Threshold | Action |
|--------|------------------|--------|
| Last candle age | > 2× timeframe | Check WebSocket connection |
| Consecutive errors | > 3 | Check exchange status, API keys |
| Position count | > expected symbols | Check for orphan positions |
| Balance change | Unexpected large drop | Check for runaway SL or liquidation |
