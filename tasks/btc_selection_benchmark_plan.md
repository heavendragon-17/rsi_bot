# Research selection quality benchmark — 2026-09-05

The user accepted the next milestone: measure whether AI-selected experiments
improve diagnostic research quality enough to justify their resource use.
The existing twelve-call allowance is exhausted. This retrospective pilot uses
the saved live choice and makes zero new provider calls.

## Frozen design

- Validate the stopped live summary → cohort campaign from a read-only database
  snapshot and accepted artifacts. Freeze the source, code and input identities
  before computing additional cohorts in a new output directory.
- Compare the recorded AI choice against a separately applied scripted policy:
  largest absolute pooled gap, shorter horizon on ties, then calendar year.
- Evaluate the same nine combinations of 60/120/180 minutes and calendar year,
  causal trend or causal volatility. This catalog is reference coverage, not
  nine independent selection trials or a hindsight winner.
- Reuse the existing raw-return, population and causal-label checker without
  changing its historical hash. Preserve all-four-horizon complete eligibility
  and separate signal and comparator denominators.
- Report cohort gaps, contrasts to pooled gaps, support and week concentration.
  Use 2,000 paired circular calendar block draws, seed 20260905, with 7- and
  28-day blocks on one continuous UTC day grid shared by all populations and
  candidates. Intervals are pointwise post-selection descriptive sensitivity.
- Leave each consecutive 28-day block out to measure influence, undefined
  cases and sign changes. These are not untouched holdouts.
- Time one separate zero-model scripted summary → selected cohort run. Report
  historical AI usage and elapsed time separately from this single observation
  and the exhaustive evaluator's overhead. Missing costs remain unknown.
- Default verdict: BENEFIT_NOT_ESTABLISHED. One previously exposed historical
  choice cannot prove general selection superiority, alpha or cost benefit.

## Work

- [x] Inspect prior campaign, evidence, replay and policy boundaries.
- [x] Review the diagnostic comparison design independently.
- [x] Implement read-only source validation and policy freeze with tests.
- [x] Implement shared checked populations and nine-candidate parity with tests.
- [x] Implement paired uncertainty and influence statistics with tests.
- [x] Integrate a zero-provider CLI, source rechecks and readable reports.
- [x] Run the historical pilot and independently review actual findings.
- [x] Run focused validation, update architecture/workflow/testing documentation
      and record the outcome and limitations.

No provider dispatch, strategy change, trading operation, commit or source
artifact overwrite is part of this task.

Outcome: [completed pilot and measured findings](btc_selection_benchmark_outcome_20260905.md).
All 293 pipeline tests passed; Ruff and mypy passed. Documentation links passed
for 216 files. The only architecture lint finding is the pre-existing Phase 1
file-size violation. Independent code and artifact review found no unresolved
material discrepancy. The scientific verdict remains BENEFIT_NOT_ESTABLISHED.
