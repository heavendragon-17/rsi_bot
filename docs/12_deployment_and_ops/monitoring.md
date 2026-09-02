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

### Telegram delivery and strategy liveness

Signal mode records forum topic IDs and names observed in incoming Telegram
updates. `/topics` reports those observed topics separately when they have no
configured strategy route. It cannot prove that an unobserved topic does not
exist because bots cannot request Telegram's complete historical forum-topic
list.

Telegram send failures, notification queue drops, and notification-worker
exceptions emit structured logs. With `telegram.debug_topic_id` configured,
the bot also attempts a rate-limited developer alert directly, using the main
chat as a fallback if the debug topic is unavailable. Search for:

```text
telegram_delivery_failure_alert_sent
telegram_delivery_failure_alert_failed
notification_queue_full
notification_failed
notification_delivery_failed
strategy_worker_error
strategy_worker_queue_full
signal_runner_worker_not_alive
```

An alert is not generated for an intentional no-signal decision: warm-up or
missing candles, rejected higher-timeframe context, cooldown/duplicate
suppression, an inactive strategy, or a valid `DoNothing` result. Those are
normal strategy decisions. An unexpected data/stream failure, strategy
exception, dead worker, queue overflow, invalid topic, or Telegram API/network
failure is operational and should produce a log plus a developer alert when a
route remains available.

If the whole process is killed or runs out of memory, it cannot send its own
Telegram alert. The VPS service supervisor must restart it and an external
uptime/process monitor should alert when the service or status file stops
changing.

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

## Bot Status File

`StatusWriter` (`app/trading/status_writer.py`) writes bot health data to `/tmp/rsi_bot_status.json` on a periodic basis. It runs in both live and signal modes; live mode reports real positions from the portfolio, signal mode reports open virtual positions from the VP store. This file is used by the deploy system to check for open positions before deploying (and to confirm the new `version` string during the health check), and is useful for quick health checks:

```bash
cat /tmp/rsi_bot_status.json | python3 -m json.tool
```

## Health Check (Backtest API)

```bash
curl http://localhost:8100/health
# {"status": "ok"}
```

## What to Monitor

| Metric | Warning Threshold | Action |
|--------|------------------|--------|
| Last candle age | > 2× timeframe | Check WebSocket connection |
| Consecutive errors | > 3 | Check exchange status, API keys |
| Position count | > expected symbols | Check for orphan positions |
| Balance change | Unexpected large drop | Check for runaway SL or liquidation |
