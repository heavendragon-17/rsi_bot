# Runbook: Order Failure

## Severity: P2-High

## Symptoms
- structlog shows `InsufficientFundsError`, `OrderRejectedError`, or `RateLimitError`
- Position opened but SL/TP not placed
- Entry signal detected but no position opened

## Diagnostic Steps

### InsufficientFundsError
1. Check exchange balance: is there enough free margin?
2. Check if other positions are consuming margin
3. Check leverage setting: is it applied correctly?
4. Check `max_position_size_pct`: is position size too large for available balance?

### OrderRejectedError
1. Check `reduceOnly` flag: is there a position to reduce? (SL/TP on non-existent position)
2. Check order price validity: is TP above entry (long) or below entry (short)?
3. Check minimum order size: does the amount meet exchange minimums?
4. Check symbol availability: is the pair available for trading?

### RateLimitError
1. Check CCXT `enableRateLimit=True` (should be enabled by default)
2. Reduce `max_workers` in grid search if running backtests
3. Wait and retry (CCXT has built-in rate limit handling)

## Resolution
- **InsufficientFunds**: Reduce `max_position_size_pct` or `risk_per_trade_pct`. Ensure leverage is set.
- **OrderRejected with reduceOnly**: Position was likely already closed (hard SL fired). Bot's `_handle_soft_sl_exit()` checks for this.
- **RateLimit**: Transient — bot retries automatically. If persistent, reduce API call frequency.

## Prevention
- Conservative position sizing (`max_position_size_pct < 0.5`)
- Verify leverage is set before entry (`set_leverage()` called in entry flow)
- Monitor free margin relative to position sizes
