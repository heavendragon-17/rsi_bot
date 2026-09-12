# M5 scientific checks (frozen v1)

Independent alignment and numerical verification for BTC M5 diagnostics.
The checker recomputes everything from raw 5-minute candles; it never calls
the diagnostic under test, never opens a real BTC dataset, holdout, trading
configuration or strategy, and never certifies the pre-existing
`app/research_pipeline/study_checks.py` (referenced as context only).

Two layers: the row-level checker validates supplied rows, while the
acceptance layer reconstructs the declared eligible population from the raw
candles and requires exact group agreement plus metric/verdict binding. A
pair that is internally consistent but omits, swaps, truncates or
re-windows rows passes the first layer and fails the second.

Boundaries the acceptance layer enforces: the declaration itself is
type/range/enum-validated before either checking path (malformed
declarations yield structured rejections, never vacuous passes or uncaught
exceptions); summary/result artifacts are parsed as strict JSON (NaN,
infinities and duplicate keys rejected) and every certified number must be
finite; per-group n/mean/median/positive share, the difference, the
rule-derived verdict, the exclusion counts and — when the summary carries
them — the window, horizon, hour split and candle identity are all compared
against recomputation, and the checked scope is recorded in the report
(`metrics.summary_scope_checked`). A summary without the optional
declaration fields binds only the metrics; the report states exactly which
scope was checked. The report also records SHA-256 hashes of every
submitted artifact (candles, candidate, baseline, summary, result).

## Layout

- `research/m5_checks/checker.py` — frozen row-level verification library
  (`SCHEMA_VERSION = "m5-scientific-check-v1"`).
- `research/m5_checks/acceptance.py` — diagnostic-specific acceptance
  (`ACCEPTANCE_SCHEMA = "m5-acceptance-v1"`): frozen `Declaration`
  (candles hash, window, horizon, target hours, rejection rule),
  `reconstruct` (expected decision sets per group from raw candles) and
  `accept` (checker must pass, then exact set agreement, then
  summary/result metric binding). `FROZEN_HOUR_SEASONALITY` is the
  hour-seasonality declaration.
- `research/m5_checks/cli.py` — stable direct-argv wrapper:
  `python -m research.m5_checks.cli --candles <csv> --candidate <csv>
  --baseline <csv> --horizon-minutes <int> --output <json>
  [--declaration <json> --summary <json> --result <json>]`.
  Without `--declaration` the output holds the row-level checker report;
  with it, the output holds the acceptance report (which embeds the checker
  outcome). Exit 0 on pass/accept, 2 on violations/rejection, 1 on usage
  errors. A declared horizon is evidence, never coerced: the CLI requires a
  non-boolean integer, rejects fractional or string values (for example
  `60.9` or `"60"`) before any checking, and refuses disagreement with
  `--horizon-minutes`; no report is written for a malformed declaration.
- `tests/test_m5_scientific_checks.py` — frozen protected owner tests over
  synthetic hand-calculated fixtures (positive, zero, negative, delayed
  availability, missing horizons, duplicates, invalid ordering, shifted
  horizon and future-information mutants, population overlap, CLI argv).
- `tests/test_m5_acceptance.py` — synthetic acceptance fixtures (correct
  split accepted; swapped, truncated, tampered-summary and wrong-hash
  inputs rejected).
- This document — frozen input/output schema, tolerances and policy.

## Input schemas

Candles CSV (`timestamp,open,high,low,close,volume`): `timestamp` is the bar
OPEN with an explicit timezone (`Z` or `+-hh:mm`), unique, strictly
increasing and aligned to the 5-minute grid; the close is exactly five
minutes later (matching `app/research_pipeline/study_checks.py`).
Decision/target times in diagnostics are CLOSE times. Closes must be
finite and positive.

Diagnostic CSV (candidate and baseline share the schema):
`event_id,decision_time_utc,available_at_utc,horizon_minutes,
target_time_utc,decision_close_price,target_close_price,outcome_status,
return_pct,included`. `outcome_status` is one of `COMPLETE`,
`MISSING_TARGET`, `GAP`; `included` is a boolean literal and must equal
`(outcome_status == COMPLETE)`. Every row must request the exact horizon
passed via `--horizon-minutes`.

## Frozen rules and tolerances

- `available_at_utc <= decision_time_utc` always; a later `available_at`
  is a timing violation (future information).
- `target_time_utc == decision_time_utc + horizon_minutes` exactly; any
  shift, including a later-candle substitution, is a horizon violation.
- Exact candle lookup, never a substitution: decision/target closes must
  match the candle closes within `1e-10` (absolute, relative 0).
- A missing target candle or a cadence gap between decision and target
  excludes the observation (`MISSING_TARGET`/`GAP` with empty return).
  Either mismatch direction is a data violation: claiming `COMPLETE` over
  a gap/missing target fabricates evidence, while marking an eligible
  `COMPLETE` bar as `MISSING`/`GAP` under-reports the population.
  Correctly marked non-`COMPLETE` rows are excluded with retained
  counts/reasons.
- `COMPLETE` returns must equal `(target/decision - 1) * 100` within
  `1e-9`; otherwise a numerical violation. Metrics (mean, median,
  positive share over eligible rows) reproduce within the same tolerance.
- Duplicate `event_id` or `decision_time_utc`, empty identities, unknown
  horizons/statuses, non-boolean `included` and `target <= decision` are
  schema violations.
- Candidate and baseline must share the candles source and horizon; their
  eligible `decision_time_utc` sets must be disjoint (two groups from one
  window). Overlap is a population violation.

## Output schema

`{schema, horizon_minutes, violations:{schema,timing,horizon,data,
numerical,population}, excluded:{candidate,baseline}, scientific:
{candidate,baseline,difference_pp,verdict}, inputs:{candles,candidate,
baseline}, passed}`. Timing/data/schema violations are reported separately
from the scientific verdict. When `passed` is true with eligible rows in
both groups the verdict is `succeeded` (candidate mean > baseline mean) or
`rejected`; both are valid scientific outcomes. When a group has no
eligible rows the verdict is `undecided` (still `passed` when no rule was
broken); callers that require a succeeded/rejected verdict must treat
`undecided` as not accepted. When any violation exists the verdict is
`INVALID` and `passed` is false.

## Context and limits

`app/research_pipeline/study_checks.py` already provides independent
arithmetic for saved four-horizon studies; it was inspected as context for
timestamp, contiguity and return handling but is not imported, wrapped or
certified here. This checker covers the single exact-horizon,
available-at-gated case required by M5 with frozen tolerances above.
Passing synthetic fixtures proves the checker's rejection power for the
tested mutants; it does not prove universal model safety, alpha or
holdout validity. Real-data use remains development data unless a
separate holdout design is explicitly authorized.
