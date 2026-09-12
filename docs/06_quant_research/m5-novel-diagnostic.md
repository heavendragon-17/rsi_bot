# M5 novel diagnostic: UTC hour-of-day seasonality (frozen declaration + results)

## Frozen declaration (pre-execution, 2026-09-12)

- **Mechanism (exploratory):** US cash-open liquidity/volatility may shift
  short-horizon BTC forward returns. No causal claim is made; this is a
  descriptive seasonality probe, absent from the existing catalog
  (four-horizon profiling, regime review, monthly summaries).
- **Estimand:** difference in mean 60-minute close-to-close return,
  candidate minus baseline, in percentage points.
- **Population:** every eligible 5-minute bar with decision close in
  `[2022-08-28T00:00:00Z, 2026-08-28T00:00:00Z)` whose exact 60-minute
  target exists with contiguous 5-minute cadence. Candidate: decision hour
  (UTC) in `{13, 14, 15, 16}`. Baseline: all other eligible hours in the
  same window. A later revised hypothesis gets a new linked identity.
- **Baseline:** same window, same horizon, same eligibility; no signal
  gates or cooldown. Candidate and baseline eligible sets are disjoint by
  construction.
- **Point-in-time rule:** `available_at_utc == decision_time_utc` (the
  close is known at its close). `target_time_utc == decision_time_utc +
  60 minutes` exactly. Missing targets or cadence gaps exclude the bar
  with retained counts; a later candle is never substituted.
- **Exact horizon:** 60 minutes (12 x 5-minute bars).
- **Inputs (development data only):** the stitched four-year 5-minute
  source `research/data/btc_four_year_20220828_20260828/BTCUSDT_5m.csv`
  SHA-256 `97d3c169eaa68cbfeadfea5251180ab581dc09506b066306a544e27b5c0fb18d`
  (455,097 rows, `Z`-timestamped 5-minute opens; closes are exactly five
  minutes later), exposure `development`, holdout `none-claimed`. No
  untouched holdout exists. The shorter app slice
  (`app/backtest/data/BTCUSDT_5m.csv`, `2572884b…`, 210,816 rows, naive
  timestamps) is a different file and was not used for this diagnostic.
- **Metric:** primary `difference_pp = mean(candidate) - mean(baseline)`;
  supporting `n`, `mean`, `median`, `positive_share` per group.
- **Rejection rule:** reject the seasonality hypothesis when
  `difference_pp <= 0`. A rejection is a valid scientific outcome.
- **Costs:** gross close-to-close returns; fees, spreads, slippage,
  funding, fills and overlapping-position constraints are omitted and
  stated as limitations.
- **Uncertainty/sensitivity plan:** descriptive only; no p-values,
  confidence intervals or alpha claim. Sensitivity (frozen, budgeted but
  not executed in the primary trial): 120-minute horizon with the same
  hour split, and 12-17 UTC window with the 60-minute horizon. Total
  frozen budget: at most 2 trials, 600 seconds, one process.
- **Code/parameter identities:** `research/experiments/m5/
  hour_seasonality.py` version `m5-hour-seasonality-v1`, frozen horizon
  `(60,)` and hours `(13, 14, 15, 16)` enforced by the module; parameters
  `{"horizon_minutes": 60, "target_hours_utc": [13, 14, 15, 16]}`.
- **Access:** scoped real development-data run after the frozen
  `examples/m5/btc/btc-manifest.json` references; no holdout, trading,
  deployment or publication is authorized by this diagnostic.

## Execution record (post-execution)

See `research/results/m5-hour-seasonality/` for the frozen outputs
(`candidate.csv`, `baseline.csv`, `summary.json`, `result.json`,
`m5-check.json`, `acceptance.json`, `run-meta.json`). The run used the
exact frozen code, parameters and candle hash above; the
rejected-or-succeeded verdict is preserved. Wall time and usage are
recorded in `run-meta.json`; unavailable fields are `unknown`, not zero.

Provenance limit, stated plainly: the diagnostic process ran directly via
`hour_seasonality.py`, not through the runner reservation chain, so no
pre-execution registration, reservation journal or runner trial records
exist for this run and none are claimed. The frozen declaration is stored
as `research-spec.json` (digest `cfe6c875…500`) and registered post-hoc in
the results-local `ledger.jsonl` (sequence 1, still `registered`, zero
trials) solely to bind the spec digest — not to backdate preregistration.
Integrated workflow acceptance (task/plan binding, durable reservations,
journal-anchored packets) is demonstrated synthetically by the
agent-workbench rehearsal and its regression tests, and prospectively on
this diagnostic by the owner-authorized integrated run recorded below.

## Independent verification

The frozen `research.m5_checks` verifier (`m5-scientific-check-v1`)
recomputed timing, exact horizons, candle closes, returns and population
disjointness over the same candles. `m5-check.json` reports `passed` and
retains excluded counts. The acceptance layer (`m5-acceptance-v1`,
`acceptance.json`) additionally reconstructed the declared eligible
population from the raw candles — exact group agreement (70,128/350,640,
zero omitted, zero unexpected) — and bound the summary/result metrics and
verdict to that reconstruction. Process success alone was insufficient;
both verdicts were required.

Distinctions preserved: the generic research-workflow packet fields
(`plan_id`, `candidate_id`, `verification_id`) identify execution
provenance — the authorizing plan label, the executed code bound to its
captured evidence, and the terminal journal event — not an independent
verification result or an accepted implementation review. Scientific
acceptance lives in this diagnostic-specific layer (`acceptance.json`),
which the generic workflow never imports; the workflow boundary stays
free of bot code. `run-meta.json` carries the outer completion binding
(`artifact_hashes`): exact SHA-256 of the frozen declaration, spec,
parameters, code modules, outputs and both verification reports.

## Prospective integrated run (owner-authorized, 2026-09-12)

`research/results/m5-hour-seasonality-integrated/` holds a second,
prospective execution of the same frozen diagnostic, this time through the
accepted workbench research workflow (entry point:
`agent-workbench/examples/m5/btc/integrated_run.py`, binding:
`project.rsi-bot.toml`). Unlike the first run, this one has pre-execution
registration and durable trial accounting:

- New linked declaration `btc-hour-seasonality-02`
  (`research-spec.json`, digest `9793289f…04ec`) with
  `parent_experiment_id = btc-hour-seasonality-01`, a fresh ledger
  (`ledger.jsonl`) and run root (`runner/`). The first run's artifacts were
  not modified.
- Ledger order: `spec_registered` (seq 1) → `running` (seq 2) →
  `trial_recorded` outcome `rejected` (seq 3). Journal order:
  `reserved` (seq 1) → `launched` (seq 2) → `completed` (seq 3), so the
  durable reservation precedes launch.
- Packet (`packet.json`) binds task `m5-btc-integrated`, plan
  `plan-btc-hour-seasonality-02-a1`, `candidate_id`, `verification_id`
  (`f9157390…53dd`, the terminal journal event), and the exact
  spec/script/parameter/dataset hashes; `verification.json` passed every
  journal-anchored check with zero failures.
- The frozen `m5-scientific-check` (`m5-check.json`) passed and the
  `m5-acceptance` layer (`acceptance.json`) accepted with exact group
  agreement (70,128/350,640, zero omitted, zero unexpected) and full
  metric/verdict binding.
- Reproduces the first run exactly: identical candidate/baseline CSV bytes,
  identical n, identical `difference_pp` (`-0.009375291130767531`) and
  verdict `rejected`. `run-meta.json` records all outer hashes (journal,
  ledger, identity bundle, outputs, checker, acceptance) plus the validated
  execution environment identity.

## Scientific interpretation (exploratory, not alpha)

TBD after the run — see Results below. A well-supported rejection ends
the diagnostic as a valid outcome. No publication, strategy change or
live-trading inference follows from this exploratory probe. Comparison
with the simple scripted baseline (ten-line pandas groupby over the same
candles/estimand) covers quality, reproducibility, wall time and observed
usage.

## Results

Primary trial (scoped development-data run, 2026-09-12):

- Candidate (13-16 UTC): n = 70,128, mean = -0.002602%, median =
  -0.001699%, positive share ≈ 49.76%.
- Baseline (other hours): n = 350,640, mean = +0.006773%, median ≈
  +0.004011%, positive share ≈ 50.65%.
- Difference (candidate minus baseline): **-0.009375 pp** → verdict
  **rejected** under the frozen rule (`difference <= 0` rejects).
- Excluded: 34,329 bars outside the frozen window (warmup), 0 gaps, 0
  missing targets; retained in `summary.json` and `m5-check.json`.
- Independent verification: `m5-check.json` reports `passed: true` with
  zero timing/horizon/data/numerical/population/schema violations; the
  rejected verdict is a valid scientific outcome, not a process failure.
- Reproduction: `baseline.json` from the ten-line vectorized baseline
  matches counts and difference exactly; diagnostic wall ≈ 8.9 s versus
  baseline ≈ 0.6 s on the same machine (implementation speed, not science).
  Usage beyond local CPU is `unknown`, not zero; no model calls, spend,
  trading or deployment occurred.

Interpretation: the pre-declared US-open window does not outperform other
hours on 60-minute forward mean return in this development window; the
difference is tiny, negative and descriptively indistinguishable from
noise. This well-supported rejection ends the diagnostic — no filter,
strategy change, publication or live-trading inference follows. The probe
demonstrates end-to-end reproducibility (frozen code/params/data hashes,
independent checker, baseline match) with appropriate exploratory limits:
gross returns, no costs, no significance testing, no holdout and no alpha
claim. The prospective integrated run reproduces the same numbers through
the registered, reserved and journal-verified workflow (see above).
