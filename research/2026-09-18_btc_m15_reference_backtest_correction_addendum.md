# BTC M15 reference backtest: correction addendum (v1 → v2)

Date: 2026-09-18. Repository `rsi_bot`, branch `mua-tren-the-nang`.
Superseded packet (preserved unchanged):
`research/results/m15_reference_backtest_runs/run_20260918T103453157146Z_991fd4d1`
(`btc-m15-reference-backtest-v1`).
Canonical corrected packet:
`research/results/m15_reference_backtest_runs/run_20260918T125747028014Z_991fd4d1`
(`btc-m15-reference-backtest-v2`).

**Research-only correction. No strategy, indicator, horizon, cost, sizing
constant, cooldown, or production behavior was changed. Nothing was optimized.
Funding remains `EXCLUDED_BY_DESIGN`; no funding data was downloaded and no
funding accounting was implemented. Every cost-adjusted number remains
`After assumed trading fees and slippage, before funding`.**

The version-1 packet is preserved byte-for-byte. This addendum identifies which
old outputs are affected and why. The version-2 packet's `manifest.json`
records the same supersession under `supersedes`, and `protocol.json` carries
the corrected execution, accounting, drawdown, and comparison contract.

## What changed and why

**A. Open-position equity.** Version 1 marked open equity as
`cash + quantity * mark` while `cash` still contained the reserved principal,
overstating open equity by one fixed entry notional (1,000 USDT at zero costs).
Version 2 marks open equity as wallet cash plus unrealized P&L
(`cash + unrealized`, equivalently available cash + reserved + unrealized).
Opening or closing a flat-price, zero-cost position now leaves equity
unchanged; paid fees enter exactly once. Unresolved rows retain the paid entry
fee in `cash` and the known exposure in `reserved`, report `unrealized` as
unknown (no price substituted), report `equity` as the fee-adjusted cash floor,
and use state `UNRESOLVED`, never `FLAT`.

**B. Drawdown and chronology.** Version 1 reused the shared
`app/backtest/engine/curves.py` helper through a timestamp-only dictionary. The
helper leaves stale drawdown at a new peak (balances `[100, 90, 110]` gave
`[0, 10, 10]` instead of `[0, 10, 0]`), and the dictionary collapses distinct
observations sharing a timestamp. Version 2 uses a research-local positional
calculation (`scheduled_m5_open_after`, `research_drawdown_curve`,
`calculate_research_portfolio_drawdown` in
`research/btc_m15_reference_backtest.py`); `app/` was not edited. Timestamps
stay monotonic when exits complete past the evaluation window end (no
window-end row is appended behind them). Marks use the available native M5
close.

**C. Execution edge cases.** Version 1 said "first existing native M5 candle
strictly after the signal close", which contradicts "no later candle is
substituted" when the exact scheduled candle is missing but a later candle
exists; version 1 implemented the jump-forward reading and reused the original
scheduled index for deferred fills. Version 2 derives the scheduled entry
arithmetically (`floor(signal, 5m) + 5m`, independent of which candles are
present), records a missing exact candle as `MISSING_ENTRY_CANDLE` without
substitution, and resolves a deferred fill from its actual deferred timestamp.
The corrected wording and both fixes are versioned in `protocol.json`
(`entry_correction_note`, `deferred_pricing_correction_note`).

**D. Comparison claims.** The capital-constrained account results are kept
unchanged. The version-1 statement that dividing by executed trades makes
results capital-independent or automatically like-for-like is removed. Per-trade
averages are conditional on affordability and timing (the capital stop
truncates to early affordable entries), not a full-opportunity average. A
separately labelled full-opportunity-set diagnostic (same frozen signals,
entry/exit rules, and cost scenarios, no cash admission, no overlap blocking,
no equity compounding) is reported alongside the account with counts and date
coverage for both views. The capital stop is described as inability to afford
the next fixed-size entry, not necessarily bankruptcy (policy B ends near 999
USDT, positive but below the 1,000 USDT threshold). Gate counts are clarified:
38,292 belonged to the diagnostic's earlier matched window
(`2022-08-30T04:15:00Z` → `2026-08-27T15:00:00Z`, 140,012 candidates), whereas
38,335 refers to this experiment's wider evaluation window
(`2022-08-28T00:00:00Z` → `2026-08-27T23:59:59.999999Z`, 140,256 candidates).

## Old-versus-new reconciliation (headline: fee 0.050%/side, slippage 0.010%/side)

| Output | Old (v1) | New (v2) | Difference and cause |
|---|---|---|---|
| Signal IDs A / B (SHA-256) | `f00d7963…` / `86b03001…` (1,175 / 11,196) | identical | No change: signals frozen. |
| `actions.csv` (21,409 rows) | `f5d54afa18c1c363` | identical | No change: gap-free dataset reports zero deferrals, so the two edge-case fixes do not alter this cohort's executions (verified, not hardcoded). |
| `trades.csv` (9,038 rows) | `4b89f3661380401f` | identical | No change: same entries, exits, quantities, and P&L components to the last digit. |
| Gross / friction / fee / net A | +9.01 / −234.98 / −1,174.89 / −1,400.86 | identical | No change: realized accounting untouched. |
| Gross / friction / fee / net B | +434.28 / −1,572.53 / −7,862.43 / −9,000.68 | identical | No change. |
| Final cash/equity A / B | 8,599.14 / 999.32 | identical | No change: flat equity still equals wallet cash. |
| Skip reasons | A `{}`; B `{"INSUFFICIENT_FREE_CASH": 3333}`; deferred 0/0; unresolved 0/0 | identical | No change. |
| Open-position equity | overstated by 1,000 USDT at zero costs | `cash + unrealized` | Corrected (A). Full-curve SHA: `b019a4d0…` → `63533f63…` (117,498 full rows; committed daily file `62507287…` → `272fd4f6…`, 10,440 rows). |
| Max drawdown A / B | 21.9178% / 90.9147% | 14.1416% / 90.0176% | Corrected (B): lower peaks plus peak-reset fix. |
| `cost_sensitivity.png` | `8a49121a57c1d354` | identical | Unchanged: realized net grid untouched. |
| `equity_gross_vs_cost.png` / `drawdown.png` | `a74cc237…` / `986e1eb6…` | `ca12cc3a…` / `9fda53a8…` | Redrawn from corrected equity/drawdown. |
| `protocol.json` | `9960a8b5…` (v1) | `663b3132…` (v2) | Versioned correction notes. |
| `report.md` comparison section | per-trade called capital-independent / like-for-like; single gate count | removed claim; separate diagnostic; both gate windows | Corrected (D). |
| Funding | `EXCLUDED_BY_DESIGN`, label `After assumed trading fees and slippage, before funding.` | identical | Retained by design. |

Account B's truncation is now explicit in both views: the account enters 7,863
of 11,196 signals (entries end 2025-05-16T20:05:00Z) while the diagnostic prices
all 11,196 hypothetically (through 2026-08-27T23:05:00Z) for a hypothetical net
of −12,934.04 USDT versus the account's realized −9,000.68 USDT. Policy A has
no capital stop, so its diagnostic (−1,400.86 USDT, 1,175 hypothetical) matches
its account. Diagnostic gross is invariant across cost scenarios (B: 500.17 USDT
in all nine), while account gross varies with affordability (e.g., B: 500.17 at
zero cost with 11,196 entered versus 427.18 at headline-high cost with 4,716
entered) — further proof that per-trade account averages are not
capital-independent.

## Verification

- `tests/test_btc_m15_reference_backtest.py`: 18 passed (one ledger assertion
  updated to the corrected `cash + unrealized` convention; the gate-count prefix
  assertion still holds).
- `tests/test_btc_m15_reference_backtest_correction.py`: 14 passed, covering
  constant-price equity, hand-computed unrealized gain/loss, peak-reset
  drawdown `[100, 90, 110] → [0, 10, 0]`, same-timestamp identities, monotonic
  exits past the window end, available-close marks, internal missing entry with
  later candles present, deferred-time pricing with materially different prices,
  unresolved fee/exposure retention, explicit missing/evaluation-end paths
  (`MISSING_ENTRY_CANDLE`, `ENTRY_AFTER_EVALUATION_END`,
  `UNRESOLVED_MISSING_EXIT_CANDLE`, `OPEN_AT_EVALUATION_END`), and the separate
  diagnostic. Expected values are hand-computed literals, never the
  implementation formula.
- Historical reproduction used the unchanged parent packet
  `research/results/phase1_reproduction_local/run_20260918T092140133007Z_97d3c169`
  with the command recorded in the new packet's `manifest.json`:
  `python -m research.btc_m15_reference_reporting --baseline-run "…/run_20260918T092140133007Z_97d3c169" --output-dir "…/m15_reference_backtest_runs"`.

## Exact reproduction (corrected packet)

```powershell
python -m research.btc_m15_reference_reporting --baseline-run "research/results/phase1_reproduction_local/run_20260918T092140133007Z_97d3c169" --output-dir "research/results/m15_reference_backtest_runs"
```

No tags, deployment, production edits, provider calls, or orders were used.
Unrelated work was preserved; history was never force-pushed.
