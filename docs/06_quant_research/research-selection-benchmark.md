# Research selection quality benchmark

`btc_ai_pipeline.py benchmark` compares a saved live AI choice with a fixed
scripted selection policy. It makes no provider calls. This is a retrospective
diagnostic pilot: it measures the recorded choice on its already exposed data,
not general AI selection superiority or tradable alpha.

## Run from Windows CMD

Use the existing `rsi` Conda environment from the repository root. Choose a new
workspace for each run; existing output directories are rejected.

```bat
conda activate rsi
python btc_ai_pipeline.py benchmark campaign_3f13b814a0294bb6 --db research/results/btc_adaptive_live_final_20260905/pipeline.sqlite --workspace research/results/my_selection_benchmark
```

The source must be a stopped, live, real-data adaptive campaign containing a
verified horizon summary followed by one verified cohort study, five completed
provider attempts, PROPOSE_NEXT then STOP, and caps of three thinker calls, two
executor calls and two jobs. Failed, resumed-with-extra-attempts and fixture
campaigns are outside this pilot's source contract.

## Comparison protocol

Before any additional cohort calculations, the benchmark writes `protocol.json`
and a source snapshot. The protocol records accepted AI parameters, independently
derived scripted parameters, source/artifact/input/code fingerprints, runtime
versions, candidate space and statistical settings. SQLite is read in a single
read-only transaction without constructing a controller, store or provider.
Proposal, execution, review, decision, parent, result and artifact identities
must agree. The source and input identities are rechecked before completion.

The scripted policy selects the largest absolute pooled signal-minus-baseline
gap from the checked summary, prefers the shorter horizon on ties, and always
uses calendar year. Its choice does not inspect additional cohort results. The
AI choice is the accepted execution plan from the saved campaign.

A separate scripted summary and follow-up run is timed. The evaluator then
loads one fully checked population and constructs all nine combinations of
60/120/180 minutes and calendar year/causal trend/causal volatility. Existing
raw-return, parent-population, eligibility and causal-label checks remain
authoritative. Catalog tables must reproduce both accepted AI evidence and the
fresh scripted run. The catalog is descriptive reference coverage, not an oracle
policy or nine independent AI trials.

## Estimands and uncertainty

All calculations retain the original all-four-horizon-complete population.
Signal and comparator means use their own counts; the comparator overlaps the
signals. A cohort gap is its signal mean minus its comparator mean. A contrast
is that gap minus the pooled gap at the same horizon. No average of daily gaps
or common-weight cohort gaps replaces these population estimands.

Daily sums and counts share one continuous UTC calendar, including days with no
signals. The default is 2,000 paired circular calendar block draws, seed
20260905, with 7- and 28-day sensitivity settings. Each draw uses identical day
weights for both populations and every candidate. It concatenates circular
blocks and truncates to the original calendar length. The 2.5th and 97.5th
percentiles use finite replicates; both joint and individual estimand validity
counts expose undefined draws. Zero-support cohorts remain explicit with null
estimates, and excluded events do not extend the bootstrap calendar.

The report also shows distinct active Monday-based UTC weeks, the largest
week's share of each population, partial-calendar-year coverage, and influence
from leaving out each consecutive 28-day block anchored at calendar start.
Strict positive/negative sign reversals and undefined deletions are counted;
deletion blocks are historical influence checks, not independent holdouts.

These are pointwise **post-selection descriptive** intervals. They do not adjust
for the model's previous exposure, candidate selection or multiple comparisons.
Seven and 28 days do not guarantee all temporal dependence has been captured.
Group effect size, interval width and number of groups are not quality scores.

## Outputs and decision

- `protocol.json`: choices, identities and settings frozen before evaluation.
- `source_snapshot.json`: validated accepted campaign and artifact fingerprints.
- `scripted_policy/`: separate standard summary/cohort evidence.
- `evaluation/verification/`: full standard population verification evidence.
- `candidate_catalog.json`: nine checked table sets and shared validity checks.
- `diagnostics.json`: nine candidates' support, intervals and influence results.
- `report.json` and `report.md`: selected-policy comparison and resource accounting.

Historical AI usage, fresh scripted elapsed time and exhaustive evaluator time
are reported separately. One run under uncontrolled load/cache state is not a
controlled performance comparison. Missing provider cost or token usage stays
unknown; provider-reported partial cost is not a total cost estimate.

`COMPLETED` means the benchmark and its checks finished. Its scientific verdict
is `BENEFIT_NOT_ESTABLISHED`: a single exposed historical choice cannot establish
general diagnostic or cost superiority. An evaluation failure writes a FAILED
report without a scientific verdict and preserves partial artifacts for review.

The next qualification requires multiple decision packets that the models have
not seen, matched selection budgets, frozen acceptance criteria and blinded
diagnostic-quality review. It needs separately authorized provider calls; this
offline benchmark does not dispatch or schedule that work.
