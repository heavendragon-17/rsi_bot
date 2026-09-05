# Research selection quality outcome — 2026-09-05

The retrospective benchmark completed with **zero new model calls**. The AI
choice produced a useful diagnostic lead, but its advantage over a simple
scripted policy is **not established**. Both policies selected 180 minutes; the
AI chose volatility grouping while the scripted policy chose calendar years.

## Measured diagnostic value

| Recorded choice | Main negative cohort | Signal count | Signal-minus-comparator gap | 28-day gap sensitivity interval |
|---|---|---:|---:|---|
| AI: 180-minute volatility | HIGH | 423 | −0.08468 percentage points | [−0.17178, −0.01574] |
| Scripted: 180-minute calendar year | 2025 | 695 | −0.05940 percentage points | [−0.11312, −0.01220] |

The AI's HIGH cohort covers only 36 active signal weeks across the four-year
calendar, with 7.09% of its signals in its largest week. Its negative gap stayed
negative after each of 53 consecutive 28-day blocks was individually removed;
the largest absolute change was 0.01825 points. The scripted 2025 cohort also
had no sign reversal under those deletions, with a maximum change of 0.01410
points. Neither finding depended on a single deletion block.

The AI's HIGH gap-minus-pooled-gap contrast was −0.07329 points. Its seven-day
bootstrap interval, [−0.16020, +0.00093], crosses zero; its 28-day interval,
[−0.16001, −0.00250], does not. The inference about concentration relative to
the pooled result is therefore sensitive to block length. The LOW cohort's
near-zero gap (+0.00131 points) had intervals spanning zero and changed sign
under 14 deletion checks. The original nonnegative LOW point estimate is not
evidence of a reliable positive effect.

The scripted 2025 diagnostic also exposed a negative gap, with negative gap and
contrast intervals under both block settings. Comparing interval endpoints or
the two selected effect magnitudes cannot rank policy quality. These are
different, potentially overlapping subpopulations, evaluated after historical
exposure. There is one AI selection, no untouched holdout, no adjustment for
selection/multiple comparisons, and no measured tradable alpha.

## Resources

- Saved successful AI campaign: five provider attempts, 315.03 seconds from
  creation to stop, including 130.36 seconds in provider calls; 82,366 reported
  input tokens and 3,689 output tokens across all five calls.
- Fresh scripted summary and selected cohort: 73.90 seconds, zero model calls.
- Shared nine-candidate evaluator: 44.52 seconds, including 2.31 seconds for
  bootstrap and influence calculations; zero model calls.
- Provider-reported historical cost is 0.0017835 with incomplete coverage.
  This is not a total cost estimate. Timings are individual observations under
  uncontrolled machine load/cache state, not a controlled speedup measurement.

The previous twelve-call authorization remains exhausted. This benchmark did
not consume additional provider calls or change any trading behavior.

## What to do next

Keep the scripted policy as the default research baseline, and use AI proposals
as optional diagnostic suggestions until their added value is demonstrated.
The measured volatility split is worth carrying forward as a hypothesis, not
promoting directly into a trading filter.

The next evaluation should freeze several new decision packets before either
policy sees their outcomes, use equal experiment budgets, and have a blinded
reviewer assess whether each chosen experiment answers its question with valid,
adequately supported evidence. Predefine acceptance criteria for diagnostic
usefulness, unsupported claims, reproducibility and resource overhead. Compare
paired results across packets rather than selecting the largest historical gap.
Prepare the exact packets/prompts and a new call budget for review before any
new live calls. This task has not dispatched or scheduled that prospective work.

## Delivered and verified

The new `benchmark` CLI validates the accepted source in a read-only SQLite
transaction, freezes policies and fingerprints before evaluation, preserves
existing inputs/artifacts, reproduces the saved AI tables and independently
executed scripted tables, and checks all nine statistical table sets against
the registered arithmetic. The calendar includes 1,459 days, including 621
days with no included signals. Each block setting uses 2,000 paired draws with
seed 20260905. Zero-support cohorts remain explicit, including excluded-only
labels. Source/input/code drift cannot publish a completed result.

- 293 focused pipeline tests passed, including 72 added benchmark tests.
- Ruff passed; mypy passed all 26 pipeline modules.
- Documentation link verification passed for 216 Markdown files after removal
  of this task's three repository test-output directories.
- Architecture lint reported only the unchanged 865-line
  `app/backtest/btc_research_phase1.py` size violation already present at HEAD.
- Independent review reproduced and closed the excluded-only cohort bug and
  matched event-level bootstrap/deletion arithmetic within 1e-12 points.
- Independent artifact review matched the source snapshot, protocol, four
  benchmark artifact hashes, two historical artifact hashes, 30 code hashes
  and seven input hashes; all 30 cohort calculations and nine weighted pooled
  reconstructions agreed within 1e-12 points.

## Evidence and repeatable command

- [Human benchmark report](../research/results/btc_selection_benchmark_20260905/report.md)
- [Machine report](../research/results/btc_selection_benchmark_20260905/report.json)
- [Frozen protocol](../research/results/btc_selection_benchmark_20260905/protocol.json)
- [All nine diagnostics](../research/results/btc_selection_benchmark_20260905/diagnostics.json)
- [Independent review](btc_selection_benchmark_review.md)
- [Implementation plan](btc_selection_benchmark_plan.md)
- [Protocol and CMD guide](../docs/06_quant_research/research-selection-benchmark.md)

```bat
conda activate rsi
python btc_ai_pipeline.py benchmark campaign_3f13b814a0294bb6 --db research/results/btc_adaptive_live_final_20260905/pipeline.sqlite --workspace research/results/my_selection_benchmark
```

Choose a new workspace when rerunning. Historical source, results and the
completed benchmark are preserved; no commit or push was made.
