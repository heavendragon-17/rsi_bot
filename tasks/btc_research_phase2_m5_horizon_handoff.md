# BTC Phase 2: M5 horizon profile

## User-directed objective

Assess the already-emitted M5 setup at 1h and 2h, with 3h also checked and 4h
retained as a reference. These are holding horizons, not changes to the native
H1/H4 confirmation gates. This replaces the unexecuted M15/four-hour extension
proposal. The user's hypothesis is that much of the move happens earlier;
the diagnostic must test it rather than assume it.

## Frozen scope

The owner expanded the required study to four years while the original-parent
diagnostic was running. Keep that first result as a preliminary two-year check.
The required signal window is `[2022-08-28T00:00:00Z, 2026-08-28T00:00:00Z)`;
download from May 2022 for indicator and regime warmup and retain native data
at least four hours beyond the final eligible signal. Preserve the existing
native CSVs and build a separate checksum-verified USD-M futures dataset.
Rebuild Phase 1 on this data, then apply the identical 1h/2h/3h/4h diagnostic.

Report calendar years (mark partial years), consecutive August-to-August study
years, and the following predeclared descriptive regimes. From the last fully
closed UTC day available at each signal, use trailing 90-day close return:
above +10% is UP, below -10% DOWN, otherwise SIDEWAYS. Use trailing 30 daily
simple returns' sample standard deviation times sqrt(365), with annualized
volatility at least 60% HIGH and below 60% LOW. These fixed labels organize
results; they are not optimized trading filters or universal market definitions.
No future candles may affect labels. Keep missing-label events explicit.

- Parent: `research/results/phase1_runs/run_20260904T073543149279Z_2572884b`.
- Keep the original M5 signal identities, timestamps, indicator values, and
  cooldown history; no strategy modification or separate-window replay.
- Exact horizons: 60, 120, 180, and 240 minutes. Report all four together.
- Use a common complete event cohort to compare horizons, disclosing all
  missing targets/tails/gaps. Retain per-horizon statuses in the export.
- Report gross close-to-close mean, median, positive-return share, monthly
  counts/means, and matched all-eligible-bar returns using shared preparation.
- Report favorable/adverse excursion from bars after the signal closes,
  excluding the trigger bar. Include zero reference and distinguish these
  hindsight bounds from a realizable exit or P&L.
- If uncertainty is included, freeze the seed and a paired calendar-block
  method before running it; preserve calendar dependence and shared sampling
  for signal-versus-comparator differences. No independent-trade assumption.
- No threshold search, per-signal hindsight exit, learned filter, TP/SL policy,
  M15 experiment, on-chain work, paid API, deployment, or orchestration setup.
- This is an exploratory descriptive profile. Record all horizons; do not call
  the best observed horizon confirmed alpha. Alpha remains NOT_ASSESSED.

## Output and review

Implement a small reproducible research command with parent/source hashes,
code/environment identity, event outcomes, summary, and report. Preserve prior
packets. Test exact 2h/3h targets, gaps/tails, and exclusion of the trigger candle
from excursions. Run the actual local data and independently cross-check returns.
Update the research/backtest docs and record the exact result path here.

After the profile is reviewed, define any filter or execution-policy experiment
for M5 around the requested horizons. Do not automatically revive the old M15
proposal or optimize an exit on the same historical results.

## Completed study

Both preliminary two-year and required four-year runs are complete. See
[the consolidated findings](../research/2026-09-04_btc_m5_four_year_findings.md)
for exact packets, commands, validation and limitations. Four-year M5 counts:
2,865 signals, 11,460 complete 1h-4h outcomes, zero exclusions. Average gross
returns are near zero and all descriptive intervals span zero. Regime/year
variation provides hypotheses for the next research decision, not approved
live filters or a validated trading edge.
