# Core V2.1 on the shared backtest engine — integration + findings (2026-09-20)

Packet: `research/results/core_v2_1_engine_backtest_v1/` (protocol `core-v2.1-engine-backtest-v1`,
frozen sha `4320063133edb459…`). Reference simulator (`research/core_v2_1_reference_sim.py` and
`research/results/core_v2_1_reference_sim_v1/`) preserved untouched as prior evidence; its P&L is
not an oracle.

## 1. Compatibility table (requirement → existing component → verdict → smallest change)

| # | Core V2.1 requirement | Existing component | Verdict | Smallest change (done) |
|---|---|---|---|---|
| 1 | Point-in-time MTF signals + persistent setup state | Locked `CoreV21` evaluator + `build_replay_frames` / `build_point_in_time_context` (audit replay) | Supported | None — adapter reuses verbatim |
| 2 | Indicators / anchor / state machine | `app/trading/strategy/core_v2_1/` (locked) | Supported | None — no logic copied |
| 3 | Next-candle-open entry, explicit open/close timestamps | `PortfolioEngine` + `MockExchange` market slippage | Supported | Adapter defers signal one candle; entry action carries next open |
| 4 | Partial take-profits (3 levels) | `PortfolioEngine` TP1/TP2/TP3 limit orders + `WickFillMode` | Supported | None (allocation 1/3, 1/2 of rest, remainder = assumption, labeled) |
| 5 | Stop on completed M15 close < EMA21 (strict, wicks ignored) | Engine SL is price-touch; Core stop is close-based | Gap | Adapter owns trigger detection; exits via `ClosePosition` at next open |
| 6 | No TP1→breakeven move (no approved rule) | Engine hard-codes `move_stop_loss` after TP1 | Gap | `DISABLE_TP1_BREAKEVEN_MOVE` opt-out, default `False` (existing behavior unchanged) |
| 7 | One position per symbol, extras explicit | Engine `max_positions_per_symbol` silently skips | Supported | Adapter records `overlap_skipped` / `no_fill_candle` in ledger |
| 8 | Sizing / fees / valuation / accounting | Shared `PositionSizer`, `MockExchange` executor, engine metrics | Supported | None — sizing basis is actual next-open price (labeled, see §4) |
| 9 | Funding excluded | Engine has no funding leg in backtest path | Supported | `EXCLUDED_BY_DESIGN`, asserted in protocol |
| 10 | `IStrategy` single-timeframe interface | `Engine.analyze()` per candle | Supported via adapter | `CoreV21EngineStrategy` feeds locked evaluator output through; no interface change |

## 2. Integration diagram

```
locked replay frames (M15/H1/H4/alt)
  → CoreV21EngineStrategy.analyze() [app/backtest/core_v2_1/engine_adapter.py, backtest-only]
      → locked CoreV21 evaluator (signals) + adapter-owned close-based stop trigger
  → PortfolioEngine (unchanged except opt-out flag, default off)
      → MockExchange (market/limit fills, fees) + PortfolioManager/PositionSizer
  → ledger_* + trades.json + results.json + manifest.json
  → check_parity() vs research/results/core_v2_1_audit_replay/core_v2_1_replay.csv
```

## 3. Verification (actual results)

- `tests/test_core_v2_1_engine_integration.py`: **9 passed** — flat prices create no equity;
  partial exits conserve quantity, fees charged once; fill timestamps are candle-open, not
  signal-close; TP fills survive a later close-based stop; reference/fill/sizing/R kept
  distinct and consistent; overlap/missing/unresolved explicit; interleaved-symbol ledger
  reconstruction covered.
- Regression: **131 passed** (`partial_tp_sl`, `candle_close_sl`, `engine_events/metrics/results`,
  `backtest_short_integration`, `dynamic_tp`, `exit_monitor`, `core_v2_1_evaluator`,
  `core_v2_1_reference_sim`).
- Parity vs audited replay: **82/82 entry events, multiset match, per-venue chronological,
  Decimal reference levels match**. (Audit CSV is grouped per symbol, not globally
  chronological — documented in the parity output, not a mismatch.)
- Run commands:
  `python -m app.backtest.core_v2_1.engine_backtest --freeze-protocol`
  `python -m app.backtest.core_v2_1.engine_backtest --run-dir research/results/core_v2_1_engine_backtest_v1 --audit-dir research/results/core_v2_1_audit_replay --data-dir app/backtest/data`

## 4. Results + explained differences from the parallel simulator (not forced to match)

| Venue | Positions | Net PnL (quote) | Net R | Engine final |
|---|---|---|---|---|
| BINANCE_FUTURES (24 sym) | 76 (3 overlap-skipped) | −20568.38 | −102.84 | 79431.62 |
| HYPERLIQUID_PERP (1 sym) | 3 | +146.68 | +0.73 | 100146.68 |

Reference sim (same data, `fee 1.0/slip 0.0005` leg): gross ≈ −9414.77 / net ≈ −15339.57.
Same negative-expectancy direction; magnitudes differ for documented reasons, not tuned away:

1. **Entry basis**: reference fills at signal reference close; engine fills at next M15 open
   × (1 ± 0.001 slippage) — execution decision 3.
2. **Same-candle TP**: reference ignores TP levels in the trigger/exit candle; engine keeps
   standing limit fills via wick-fill semantics.
3. **Sizing basis**: reference sizes off reference close; engine sizes off the actual
   next-open order price through shared `PositionSizer`.
4. Venues reported separately, no pooling; fees per shared executor (taker market / maker limit).

## 5. Limitations / remaining gaps

- TP allocation (1/3, 1/2 of rest, remainder) and TP activation on wick-touch are
  `ASSUMPTION_NOT_A_DECISION`; strategy stop exit fill at next open likewise.
- No disaster stop placed (reference stop is sizing-only) and no max-holding force-close
  (`GENUINELY_UNRESOLVED`) — positions ride to TP3/stop/EOD.
- 24,216 + 1,009 NOT_READY warm-up evaluations are counted per symbol, never simulated.
- Engine float serialization in `trade_history` leaves ≤1e-9-relative dust on close;
  recorded explicitly as `close_dust_qty`, never blended.
- Shared-engine change is one default-off flag (`DISABLE_TP1_BREAKEVEN_MOVE`); no trading
  logic, sizing, risk, or live config touched. No tuning, no live promotion.
