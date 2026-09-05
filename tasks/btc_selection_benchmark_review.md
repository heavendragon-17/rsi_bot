# Independent benchmark review — 2026-09-05

The study-tools agent independently reviewed the statistics, source boundary and
integration against `tasks/btc_selection_benchmark_plan.md`. The agent authored
`benchmark_data.py`; its implementation and tests are therefore implementation
validation, not an independent review of that module. No production source was
edited during this review, and no provider or full market-data run was performed.

## Finding and resolution

A material catalog parity defect was reproduced in the initial statistics code.
A cohort represented only by excluded events remained in the checked catalog
with zero signal/baseline support and a null gap, but disappeared from statistics
because labels were discovered after eligibility filtering. The integration
correctly rejected this mismatch. The smallest reproduction used one included
`up` event and one excluded `down` event in both populations.

The statistics owner fixed label discovery to retain the full per-horizon label
universe while keeping only eligible observations in estimates. The reviewer
inspected the fix and its new excluded-only and cross-horizon regression tests.
The owner reported 23 statistics tests passing. Excluded-only cohorts now have
zero support and undefined estimates; they do not expand the eligible calendar
or introduce labels into unrelated horizons. The strict integration parity
check remains intact. No further material code defect was found.

## Independent statistical verification

The initial statistics and integration suites passed 26 tests, which did not
expose the excluded-only case. An additional event-level reference calculation
used unequal per-day signal and comparator counts, two cohorts, and a continuous
41-day calendar containing zero-event days. It generated 150 paired circular
draws for each of the 7- and 28-day block lengths with test seed 19. Twelve
interval and deletion comparisons matched the implementation within `1e-12`
percentage points.

The reference recomputed separate population sums and denominators on every
draw, then subtracted the same-draw pooled gap for each cohort contrast. Direct
deletion of consecutive 28-day segments also matched maximum delta/contrast
changes, strict sign reversals and undefined-case counts. Code inspection
confirmed common draws across populations and candidates, Monday-based UTC week
support, explicit finite-draw interval rules, and separate joint/per-estimand
validity counts. Production defaults match the frozen 2,000 replications, seed
20260905 and 7/28-day sensitivity settings.

The reporting caveats correctly describe pointwise post-selection sensitivity,
overlapping observations, unadjusted multiple comparisons, and historical
influence rather than untouched holdouts. Nine catalog entries are reference
coverage, not nine independent policy trials or a hindsight winner. These
calculations do not establish alpha or AI selection benefit.

## Independent source verification

After the source owner released the finalized implementation, all 26 source
tests passed independently in 64.10 seconds. Reviewed checks bind the stopped
campaign, budgets, ordered attempts, accepted proposals/executions/reviews,
parent/result links, table structure, result/cache/evidence hashes, checker and
input identities, and exact artifact locations and bytes. Malformed, duplicate
or nonfinite JSON and cross-record drift are rejected.

A separate synthetic SQLite probe committed a WAL transaction between the
campaign and budget reads. The active read transaction consistently returned
the old campaign and old budget; a fresh snapshot returned both new values.
The reader executed only `PRAGMA query_only=ON`, `BEGIN`, and `SELECT` statements.
This confirms transaction consistency and visibility of committed WAL changes.
The source hash covers the selected campaign's logical snapshot; artifact byte
hashes are recorded separately. Verification reloads the complete record, so
selected-row, artifact and in-memory drift are detected while unrelated
campaign writes do not invalidate the source.

## Reviewed versions and remaining scope

SHA-256 fingerprints at completion of this code review:

| File | SHA-256 |
|---|---|
| `benchmark_source.py` | `6a41f14b2591500e732f7e9cfb17ce63fcfded1334d83240f8c98e79deb1db7b` |
| `benchmark_statistics.py` | `139482ac61736a6ba42972a5541008ae5deeb776986c23cccaf1ad1797e9afa4` |
| `benchmark.py` | `fe9226f23d1535fd4328e72a22e5cbdfd7ab9c0d761871c231741960394adae8` |

The historical pilot was running when the code review finished. Further heavy
tests were deferred to avoid interfering with that timing observation. The
completed output was subsequently reviewed as described below.

## Completed historical pilot artifact review

Output: `research/results/btc_selection_benchmark_20260905`. The reviewer checked
the completed artifacts without rerunning the raw-data checker, statistics or
providers. The following independent lightweight checks passed:

- Canonical protocol and selected-campaign snapshot hashes agree with the
  report. A fresh read-only SQLite transaction reproduced every frozen selected
  campaign row. The source SHA-256 is
  `95d094cc5a9c08ed0e0d754e0d9622a8297e36ac96f2c824e5da0aacbd14a396`.
- All four report-listed benchmark artifacts, both historical evidence
  artifacts, all 30 current code files and all seven current input files match
  their recorded SHA-256 values.
- The recorded AI tables and separately executed scripted tables match their
  catalog entries. All nine candidates reconstruct their saved pooled signal
  and baseline means using their separate cohort counts. All 30 cohort gaps,
  contrasts and counts agree with the checked catalog within `1e-12` percentage
  points. Bootstrap bounds are finite/ordered and valid plus undefined draws
  total 2,000.

The final protocol uses the frozen 2,000 replications, seed 20260905 and 7/28-day
block lengths. Its common calendar contains 1,459 days, including 621 days
without included signals. Both policies selected the 180-minute horizon. The
recorded AI choice groups by volatility; the scripted choice groups by calendar
year. Neither policy selects an individual group within that comparison.

The AI comparison's HIGH group contains 423 signals across 36 active weeks,
against 63,936 baseline events. Its gross signal-minus-baseline gap is
`-0.0846774091` percentage points. Its gap intervals are negative at both block
lengths, and none of the 53 consecutive 28-day deletions reverses that gap's sign.
The HIGH contrast to the pooled gap is `-0.0732866014` percentage points, but its
zero-crossing interpretation is sensitive to block length: the seven-day
interval `[-0.1602018802, 0.0009271518]` crosses zero, whereas the 28-day interval
`[-0.1600083203, -0.0024958139]` excludes zero. The LOW contrast has the same
block-length sensitivity in the opposite direction. A user-facing account must
preserve this sensitivity rather than call the contrast stable or significant.

Among the five years reported by the scripted comparison, 2025 contains 695
signals across 51 active weeks and has a gap of approximately `-0.05940`
percentage points. Its seven- and 28-day gap intervals are negative and none of
the 28-day deletions reverses its gap's sign. This is an observation within the
reported year table, not a separately selected scripted experiment or an
independent discovery trial. The partial 2022 year has nine undefined 28-day
draws, correctly exposed in the report.

The saved AI campaign reports five provider attempts, 315.03 seconds of campaign
span, 130.36 seconds in provider calls, and 82,366 input/3,689 output tokens.
Provider cost coverage is incomplete. The fresh scripted run took 73.90 seconds;
the nine-candidate evaluator took 44.52 seconds, including 2.31 seconds for
statistics. These are distinct, uncontrolled timing observations, so the review
does not interpret their ratio as a controlled speed or cost comparison.

No material artifact discrepancy was found. The report's
`BENEFIT_NOT_ESTABLISHED` verdict is consistent with the evidence: this exposed
historical choice, descriptive intervals and single timing observation do not
demonstrate superior AI selection, tradable alpha or justified extra cost.
