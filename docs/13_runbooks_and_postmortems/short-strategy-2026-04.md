# Short-Strategy Review — April 2026

## Scope
Review of seven problematic SHORT trades executed by the `rsi_momentum`
strategy between December 2025 and March 2026. The user provided a report
(Vietnamese) flagging each case; this document records the findings, the
patterns across trades, and the code-level fixes applied.

## Problem cases

| # | Date | Symbol | Issue reported |
|---|------|--------|----------------|
| 1 | 2025-12-27 17:30 | ETH  | Concept OK, but entry was poor; need a time-based exit (close at BE if TP not hit within 5–7 candles). |
| 2 | 2026-01-19        | TON  | Entered *after* the move was already done. Late entry. |
| 3 | 2026-03-13        | BERA | Shorted during a larger-timeframe uptrend; price did not drop. Wants trend filter + time-based exit (7–10 candles). |
| 4 | 2026-02-08 08:15  | BERA | Suspicious entry — trade should have reached 0.5R, instead SL'd. |
| 5 | 2026-03-08        | TRX  | Same as #3: shorted during an uptrend. Wants only short when `close < EMA200`. |
| 6 | 2026-02-13        | TRX  | Trade ran nicely, but SL was moved to BE and then immediately swept. |
| 7 | —                 | AXS  | Trade was running well but was SL'd early after a small retrace. |

## Patterns identified

1. **No trend filter.** Cases #3 and #5 are textbook "short in an uptrend"
   — price was above the daily/larger-frame mean so any retracement was
   bought aggressively. The strategy had no macro-trend guardrail.
2. **Signal persistence too permissive.** Cases #2 and #4 point at entries
   taken on candles where the EMA9<WMA45 crossover had fired many bars
   earlier. Our `crossover_detected` flag had no expiry, so we could
   enter long after the momentum had decayed.
3. **No stale-trade exit.** Cases #1 and #3 describe trades that sat for
   far too many candles without making progress toward TP1 and ended up
   SL'ing. The user explicitly asked for a "cut at BE after N candles".
4. **BE lock was too aggressive.** Cases #6 and #7 got stopped out right
   after SL was moved to BE. The defaults were `move_sl_rr=0.5` (trigger
   at −0.5R) and `lock_profit_rr=0.2` (SL parked barely below entry),
   which left almost no room for normal noise.

## Fixes applied

All changes live on the `rsi_momentum` strategy. Each fix is individually
configurable so we can tune or revert without editing code.

### 1. EMA200 trend filter (S6)
- `RsiMomentumConfig.ema200_filter: bool = True`
- `RsiMomentumConfig.price_ema_slow: int = 200`
- Entry is rejected when `close >= ema200` on the current candle.
- The strategy's `Indicators` instance now has `include_price_emas=True`
  so `ema200` is always produced.
- Addresses cases #3, #5 (and tightens #2, #4 indirectly).

### 2. Crossover freshness cap (S1)
- `RsiMomentumConfig.max_candles_since_crossover: int = 3`
- `TradeState.candles_since_crossover` counter, incremented each candle
  while the signal is persisting without firing an entry. Once it exceeds
  the limit, the signal is dropped and a fresh crossover must occur.
- Addresses cases #2, #4.

### 3. Stale-trade exit
- `RsiMomentumConfig.stale_exit_candles: int = 8`
- `TradeState.candles_in_trade` counter, incremented in `manage_exit` on
  every call. When it reaches the limit and TP1 has not been hit, the
  strategy emits `ClosePosition(reason=EXIT_STALE_TRADE)`.
- Reuses the existing lock-profit mechanism — if the SL was already moved
  to the `lock_profit_price`, the position will close at (at worst) the
  locked-in profit level; otherwise it's cut at market.
- Addresses cases #1, #3.

### 4. Loosened BE-lock defaults
- `move_sl_rr: 0.5 → 1.0`
- `lock_profit_rr: 0.2 → 0.5`
- The SL now only moves after a 1R favourable excursion, and it's parked
  at 0.5R in profit, well clear of typical 15m retrace noise.
- Addresses cases #6, #7.

## Files touched

- `app/core/actions.py` — new `EXIT_STALE_TRADE` reason string.
- `app/trading/strategy/rsi_momentum.py` — config fields, warm-up
  bumped to 210 candles for EMA200, `strategy_params` now properly read.
- `app/trading/strategy/rsi_momentum_entry.py` — EMA200 filter (S6) and
  crossover freshness cap (S1).
- `app/trading/strategy/rsi_momentum_exit.py` — stale-trade exit (STEP 3);
  all return paths now persist the incremented `candles_in_trade` counter.
- `app/trading/strategy/utils/trade_state.py` — new counters.
- `app/trading/strategy/utils/param_metadata.py` — UI schema for the new
  knobs.
- `tests/test_rsi_momentum.py` — fixture opts existing tests out of the
  new filters so their original semantics still apply.
- `tests/test_rsi_momentum_fixes.py` — 12 new tests, one per behaviour.
- `tests/test_backtest_short_integration.py` — same opt-out pattern.
- `docs/07_trading_strategies/strategy-reference.md` — parameter table.
- `docs/07_trading_strategies/entry-exit-rules.md` — S6 entry rule, new
  STEP 4 exit rule, new `TradeState` keys.

## Verification

- `pytest tests/` — 821 passed, 12 skipped (environment-gated API/signal
  tests excluded on this review host).
- `pytest tests/test_rsi_momentum_fixes.py -v` — 12 / 12 passed.

## Open follow-ups

- Re-run the portfolio backtest against the same symbols over
  Dec 2025 – Mar 2026 to quantify the expected equity curve impact.
- Consider an M5 variant (`timeframe: "5m"`) for symbols where the 15m
  EMA200 filter rarely allows entries, per the user's BERA note.
- Add a Telegram diagnostic when `STALE_TRADE` fires so we can monitor
  how often the guardrail activates.
