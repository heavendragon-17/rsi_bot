# Core V2.1 short-mirror experiment (research-only, NOT a strategy decision)

Date: 2026-09-20. Branch: experimental (see commit). Live strategy/config untouched.

## Question

Long-only Core V2.1 loses ~everything over two years. Is the direction wrong?
Mirror test: same signals, same timing, same sizing, same costs — side flipped.

## Mirror definition (ASSUMPTION_NOT_A_DECISION)

- SELL at the next M15 open (side-aware adverse slippage applies automatically).
- Exec soft stop = fill + signal `risk_1r`; exec TPs = fill − signaled TP
  distances (1R/2R/3R preserved). Fail closed on non-positive risk.
- Stop trigger mirrored: M15 close **above** EMA21 (strict).
- Signal rows keep original long levels, so parity still validates the
  identical signal population.

## Shared-engine short gaps fixed (backtest-only, long path untouched)

- `portfolio_engine._sync_executed_orders_to_portfolio`: was SELL-only, so
  short (BUY) TP/full-close fills never synced. Now side-aware with
  sign-aware partial reduction.
- `portfolio_engine._close_all_positions`: never closed shorts at EOD. Fixed.
- `exchange/executor.execute_order`: partial short exits booked
  `(exit − entry) × full_open_position` — overstated winning partials ~3x and
  contaminated balances. Now `(entry − exit) × closed_amount`. Long branch
  (`current_signed >= 0`) byte-identical; long frozen packet still validates.
- `engine_backtest.build_positions/_finish_position`: `direction` param
  (default `"long"`); short P&L sign-flipped.
- Adapter `SHORT_MODE` flag (default `False`); runner `--direction`.
- New frozen protocol `core-v2.1-engine-history-binonly-short-v1`
  (`2546c43a…`), same window, exclusive run dir, same fail-closed gates.

## Result (2024-09-21 → 2026-09-20, 24 Binance symbols, $100k shared)

|                       | Long | Short mirror |
| --------------------- | ---- | ------------ |
| Positions             | 793  | 859 |
| Net                   | −$98,541 (−492.7R) | −$98,905 (−494.5R) |
| Final equity          | $1,459 | $1,095 |
| Full ladders (TP3)    | 206 (26%) | 65 (7.6%) |
| Stop exits            | 587 (74%) | 794 (92%) |
| Symbols net-positive  | 0/24 | 0/24 |

Signal population identical (parity multiset + levels True both runs;
admissions 1,271 both). Count gap is mechanical: shorts stop out faster,
freeing the one-position-per-symbol slot sooner (12 vs 21 overlap skips),
plus divergent shared-capital margin skips (400 vs 457).

## Reading

Direction is not the problem. Both sides bleed; shorts structurally worse
(92% stopped, 7.6% ladders). The entries mark chop that stops out either
way. Rules out: side flip, hope-based stop widening, sizing up. Next honest
step: per-entry-family MFE measurement on a reserved out-of-sample window
before any exit/entry change.

## Packets

- Long: `research/results/core_v2_1_history_binonly_2y_v1/`
- Short: `research/results/core_v2_1_history_binonly_short_2y_v1/`
- `parity_replay/` dirs excluded from version control (2.4 GB each);
  regenerate with the frozen packet + `CoreV21PointInTimeReplay` over the
  recorded `warm_start` slices (see `engine_history.main` parity block).
