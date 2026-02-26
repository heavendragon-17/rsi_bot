# Runbook: WebSocket Disconnect

## Severity: P2-High

## Symptoms
- No new candles appearing in MarketDataStore
- Strategy not triggering any actions
- No Telegram notifications for extended period
- structlog shows `stream_disconnected` or WebSocket error messages

## Diagnostic Steps
1. Check structlog output for WebSocket errors: `grep "websocket\|stream\|disconnect" bot.log`
2. Check Binance status: https://www.binance.com/en/support/announcement
3. Check server network: `ping api.binance.com`
4. Check MarketDataStore last update time in logs

## Resolution
1. **Auto-reconnect** (built-in): `BinanceStreamManager` has automatic reconnection with backoff. Wait 30-60 seconds for auto-recovery.
2. **If stuck**: Restart the bot — `Ctrl+C` then `python main.py`
3. **After restart**: Check for orphan positions (bot does this automatically on startup)
4. **If Binance is down**: Wait for service restoration. Bot will reconnect automatically.

## Prevention
- Monitor candle freshness (last candle age > 2× timeframe = warning)
- Set up external health check that alerts if no Telegram messages for >1 hour
- Consider running on a VPS close to Binance servers for better connectivity

## Escalation
- If disconnect persists > 10 minutes and auto-reconnect fails
- If orphan positions exist on exchange after restart
