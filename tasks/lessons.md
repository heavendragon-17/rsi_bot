# Lessons Learned

> Patterns captured from user corrections. Review at session start. Update after every correction.

<!-- Example:
## 2024-01-15: Always check for None before accessing .symbol
- **Mistake**: Assumed position was never None in backtest context
- **Rule**: Always guard `position` access with a None check — backtest engine passes None for flat positions
- **Files affected**: app/strategies/*.py
-->

## 2026-08-27: Keep timeframe gates tied to the requested market quantity

- **Correction**: The BTC RSI alert's H4 confirmation must use the closed H4 candle price above EMA21(price), not EMA9/WMA45 derived from RSI21.
- **Rule**: When a user changes an indicator gate from RSI-space to price-space, remove the obsolete RSI-derived input, readiness requirement, message field, and tests instead of retaining a hidden dependency.
- **Files affected**: `app/trading/strategy/btc_rsi_cross_alert/`, `app/signal/btc_rsi_cross_alert/`, related tests and strategy documentation.

## 2026-08-27: Cooldown must preserve timeframe independence

- **Correction**: M5 alignment alerts need a 15-minute cooldown, while M15 must remain unchanged.
- **Rule**: Store alert cooldown state separately from evaluation cursors and emitted-event dedupe; measure it from candle close time, update it only after a successful send, and test the equality boundary plus other-timeframe isolation.
- **Files affected**: `app/signal/btc_rsi_cross_alert/worker.py`, worker tests, and BTC RSI alert documentation.

## 2026-08-27: Separate shared gates from timeframe-specific price filters

- **Correction**: M15 must keep the shared H4 close-above-EMA21 gate and also require its own close above its own price EMA21.
- **Rule**: When adding a same-named indicator condition across timeframes, verify the source series and timeframe explicitly, reuse an existing shared gate once, and add a distinct rejection reason plus equality-boundary tests for the new timeframe-specific filter.
- **Files affected**: `app/trading/strategy/btc_rsi_cross_alert/m15_checker.py`, domain reasons, timeframe-checker tests, and BTC RSI alert documentation.
