# Runbook: Position Drift

## Severity: P1-Critical

## Symptoms
- Bot tries to manage a position that doesn't exist on exchange
- Bot misses a position that exists on exchange
- structlog shows `OrderRejectedError` with "reduceOnly order failed" (no position to reduce)
- Unexpected `InsufficientFundsError` despite having balance

## Diagnostic Steps
1. Check bot's internal state: look for `position_opened` / `position_closed` in logs
2. Check exchange state: log into Binance, check Positions tab
3. Compare: does the bot think it has a position? Does the exchange?
4. Check for missed fills: look for order IDs in logs, verify on exchange

## Resolution
1. **Restart the bot**: `sync_from_exchange()` runs on startup and reconciles state
2. **If orphan position on exchange**: Manually close it via Binance web interface
3. **If bot has stale position**: Restart clears positions not found on exchange
4. **If orders are orphaned**: Check `fetch_open_orders()` and cancel stale orders manually

## Prevention
- Avoid manual intervention on exchange while bot is running
- Future improvement: implement periodic reconciliation loop (every 60s)
- Future improvement: subscribe to order/position WebSocket streams

## Escalation
- If position is large and actively losing money
- If manual exchange intervention is needed to close a position
