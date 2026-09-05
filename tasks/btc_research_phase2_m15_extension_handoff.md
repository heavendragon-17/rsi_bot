# BTC Phase 2: one frozen M15 extension experiment

> Superseded before implementation by the owner's M5/1h-3h horizon correction
> on 2026-09-04. Do not execute this brief as the active next task. See
> [the M5 horizon brief](btc_research_phase2_m5_horizon_handoff.md). The protocol
> below is preserved as planning history; it produced no challenger results.

## Objective and scope

Test whether retaining less-extended, already-emitted BTC M15 alerts improves
their mean gross four-hour forward return. Build and run one offline experiment
with one implementation worker, using the accepted Phase 1 packet below. This
is the next research job for the eventual manager/executor pipeline.

Read `docs/INDEX.md`, `docs/agent-workflow.md`, and the BTC research/backtest
documentation. Preserve current uncommitted work. Use
`C:/ProgramData/anaconda3/envs/rsi/python.exe`. No live strategy/config changes,
new indicators, M5 search, exit optimization, on-chain work, API calls, agent
framework, scheduling, dependency installation, commit, or push belongs here.

## Accepted parent

`research/results/phase1_runs/run_20260904T073543149279Z_2572884b`

Manager review closed all three Phase 1 findings: preparation-based validity,
per-event comparator eligibility, and staged-code provenance. The 27 focused
tests pass; signal CSV and all horizon/monthly numerical results match the
previous accepted packet. Four source hashes were independently verified.

The parent remains INCOMPLETE because the requested end exceeds coverage and
12 long-horizon targets are absent. Preserve that status. Validate the narrower
M15/four-hour experiment independently: verify parent file hashes, parent
preparation coverage, unique event identities, source metadata, causal H4
timestamps, and complete exact four-hour outcomes in the eligible evaluation
window. Do not treat execution SUCCESS as sufficient or blanket-ignore parent
warnings. Other missing evidence blocks the experiment with explicit reasons.

## Frozen protocol: btc-m15-h4-extension-v1

Write the following protocol to a machine-readable file and record its hash
before computing challenger results. Run exactly one challenger; changing any
choice below requires a new experiment ID and retained prior results.

- **Population:** one row per already-emitted M15 event in the accepted packet.
  Select its `4h` row; do not count the other three horizons as extra events.
- **Feature:** `h4_gap_pct = 100 * (h4_close_price / h4_price_ema21 - 1)`.
  Require finite values, positive denominator, and H4 close no later than the
  trigger close. Use exported point-in-time values; do not recompute with future
  candles or pass outcome columns into the feature/selection interface.
- **Fit window:** parent requested start through, but excluding,
  `2025-09-01T00:00:00+07:00`. Estimate from M15 features only; outcome returns
  must not influence cutoff fitting or fitting-population selection.
- **Cutoff:** the fit-window feature quantile at `q = 1/3`, with linear
  interpolation. This lower-third convention was motivated by earlier
  exploratory buckets; it is not an independently discovered hypothesis.
- **Challenger:** retain events with `h4_gap_pct <= fitted_cutoff`. Freeze that
  single numerical cutoff for the entire later evaluation window. Record tie
  counts and actual retention rather than assuming exactly one third survives.
- **Evaluation window:** from `2025-09-01T00:00:00+07:00` inclusive through the
  earlier of parent requested end and native M15 last close minus four hours,
  inclusive. Persist both boundaries in UTC. Disclose excluded boundary/tail
  events. Do not shift the window or refit after seeing results.
- **Primary metric:** evaluation mean gross 4h return of retained alerts minus
  evaluation mean gross 4h return of all original alerts, in percentage points.
  Use the same eligible evaluation dates and exact outcome rules for both.
- **Diagnostics:** original/retained/rejected counts, retention, mean, median,
  5th percentile, monthly counts and mean differences. Report pooled raw means
  and monthly results separately. No annualized Sharpe, portfolio return, or
  realized P&L can be inferred from this event table.
- **Cost illustration:** show each population's mean less 0.10 percentage points
  using the existing Phase 1 convention. Equal per-alert cost cancels in the
  primary mean difference; this is not an executable cost model or evidence of
  profitability. Show absolute retained mean as well as incremental improvement.
- **Search accounting:** `new_candidate_count = 1`,
  `prior_search_count = UNKNOWN`, `evidence_role = EXPLORATORY_RETROSPECTIVE`,
  `alpha_assessment = NOT_ASSESSED`. Do not label the later period untouched.

This is a post-alert selection diagnostic. Keep original signal identities and
cooldown history. Rejecting an alert does not release its cooldown or cause a
previously suppressed alert to appear. Do not replay each split separately.
A production rule that changes cooldown/state would require a later full replay.

## Bounded uncertainty diagnostic

Add a paired circular calendar-block bootstrap for the primary difference:

1. Aggregate the evaluation interval by UTC calendar day, including zero-event
   days. Store original and retained sums of return percentages and counts.
2. Sample seven-day contiguous blocks of day indices with replacement, wrapping
   at the end, until the original number of days is reached; truncate the final
   block. Apply identical sampled indices to both populations.
3. Recompute each population mean as sampled sums divided by sampled counts,
   then their difference. Never average daily means or sample the populations
   independently. Keep the fitted cutoff fixed; these are conditional intervals.
4. Use NumPy `default_rng(20260904)` and exactly 2,000 replicates. Report the
   2.5th/97.5th percentile endpoints using linear interpolation. Count undefined
   zero-denominator replicates without retrying; if any occur, report uncertainty
   INCOMPLETE rather than silently conditioning on successful replicates.

Seven days is a frozen diagnostic choice, not an estimated optimal block length.
Do not search block lengths. State that dependence beyond the block, regime
changes, cutoff-estimation uncertainty, and previous hypothesis selection are
not resolved by this interval. It must not produce an automatic alpha PASS.
Block resampling and its assumptions are discussed in
[Politis, The impact of bootstrap methods on time series analysis](https://math.ucsd.edu/~politis/impactBOOT.pdf).
The prior-search limitation follows the problem described by
[Bailey et al., The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

## Deliverables and checks

Provide one repository-root offline command accepting the parent packet and
output directory. Save immutable run-specific protocol, manifest, event-level
feature/selection/outcome rows, summary, bootstrap results, and a short report.
Include parent artifact SHA-256 hashes, protocol hash, actual code identity,
command, versions, cutoff, timezone semantics, seed, exclusions, and statuses.
Feature/decision records must remain separate from outcome inputs during fitting
and selection, even if the final evidence export joins them for review.

Meaningful tests must show: changed future labels cannot change the cutoff or
selection; changed evaluation features cannot change the fitted cutoff; split
boundaries and quantile ties are handled as specified; duplicate events and
future-dated H4 context are rejected; retained IDs form a subset of parent IDs;
an all-retained synthetic case has zero mean difference in every bootstrap
replicate; calendar sampling is shared; and repeated runs are deterministic.
Exercise a missing/empty population and missing-outcome failure path explicitly.

Update relevant research/backtest docs and task records. Run focused tests, one
real experiment and an unchanged-input repeat. Compare stable outputs and
independently spot-check feature values and selection. Preserve failures and
negative results; do not tune the protocol to rescue a result.

Return the packet path, original versus retained evaluation metrics, primary
difference and interval, retention/monthly stability, verification, and remaining
limitations. Stop for manager review. No new data collection or prospective
campaign is authorized by this handoff.
