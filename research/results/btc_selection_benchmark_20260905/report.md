# Research selection quality: retrospective pilot

**Benefit not established.** This evaluates one saved AI choice against a fixed scripted policy, using zero new model calls.

Both policies selected the same horizon: **true**. A larger cohort gap, narrower interval or smaller number of groups does not establish a better selection policy.

## Checked results

All gaps and intervals below are percentage points. A contrast is the cohort signal-minus-baseline gap minus the pooled gap. Intervals are pointwise post-selection sensitivity estimates; they are not significance decisions.

### Recorded AI choice: 180 minutes / volatility

| Cohort | Signals / baseline | Gap | Contrast | Active signal weeks | Largest signal-week share |
|---|---:|---:|---:|---:|---:|
| HIGH | 423 / 63936 | -0.08468 | -0.07329 | 36 | 7.09% |
| LOW | 2442 / 356240 | 0.00131 | 0.01270 | 174 | 1.35% |

| Cohort | Block days | Gap interval | Contrast interval | Valid / undefined paired draws |
|---|---:|---|---|---:|
| HIGH | 7 | [-0.17442, -0.00402] | [-0.16020, 0.00093] | 2000 / 0 |
| HIGH | 28 | [-0.17178, -0.01574] | [-0.16001, -0.00250] | 2000 / 0 |
| LOW | 7 | [-0.03075, 0.03282] | [-0.00049, 0.02679] | 2000 / 0 |
| LOW | 28 | [-0.03420, 0.03323] | [0.00035, 0.02797] | 2000 / 0 |

| Cohort | Maximum gap change leaving 28 days out | Gap sign changes | Undefined gap cases | Partial calendar year |
|---|---:|---:|---:|---|
| HIGH | 0.01825 | 0 | 0 | None |
| LOW | 0.00926 | 14 | 0 | None |

### Independent scripted choice: 180 minutes / calendar_year

| Cohort | Signals / baseline | Gap | Contrast | Active signal weeks | Largest signal-week share |
|---|---:|---:|---:|---:|---:|
| 2022 | 226 / 35712 | 0.02438 | 0.03577 | 17 | 10.62% |
| 2023 | 759 / 105120 | -0.01719 | -0.00580 | 51 | 4.35% |
| 2024 | 769 / 105408 | 0.00321 | 0.01460 | 51 | 4.03% |
| 2025 | 695 / 105120 | -0.05940 | -0.04801 | 51 | 4.60% |
| 2026 | 416 / 68816 | 0.02479 | 0.03618 | 33 | 5.77% |

| Cohort | Block days | Gap interval | Contrast interval | Valid / undefined paired draws |
|---|---:|---|---|---:|
| 2022 | 7 | [-0.04653, 0.10005] | [-0.03662, 0.11091] | 2000 / 0 |
| 2022 | 28 | [-0.03473, 0.08543] | [-0.02885, 0.10022] | 1991 / 9 |
| 2023 | 7 | [-0.06738, 0.03210] | [-0.05376, 0.03862] | 2000 / 0 |
| 2023 | 28 | [-0.06114, 0.02672] | [-0.05102, 0.03735] | 2000 / 0 |
| 2024 | 7 | [-0.06753, 0.07381] | [-0.04263, 0.06894] | 2000 / 0 |
| 2024 | 28 | [-0.07980, 0.07534] | [-0.05231, 0.07377] | 2000 / 0 |
| 2025 | 7 | [-0.10836, -0.00752] | [-0.09489, -0.00214] | 2000 / 0 |
| 2025 | 28 | [-0.11312, -0.01220] | [-0.10044, -0.00427] | 2000 / 0 |
| 2026 | 7 | [-0.05500, 0.10667] | [-0.03658, 0.10972] | 2000 / 0 |
| 2026 | 28 | [-0.04281, 0.09203] | [-0.02823, 0.10278] | 2000 / 0 |

| Cohort | Maximum gap change leaving 28 days out | Gap sign changes | Undefined gap cases | Partial calendar year |
|---|---:|---:|---:|---|
| 2022 | 0.03649 | 1 | 0 | True |
| 2023 | 0.01703 | 0 | 0 | False |
| 2024 | 0.03050 | 3 | 0 | False |
| 2025 | 0.01410 | 0 | 0 | False |
| 2026 | 0.01730 | 0 | 0 | True |

## Resources

The saved AI campaign used **5 provider attempts**, 315.03 seconds of campaign span and 130.36 seconds in provider calls. Reported tokens: 82366 input / 3689 output. All attempts have token usage: True.

Provider-reported cost: 0.0017835; complete cost coverage: False. This is not a total campaign cost estimate.

The separately executed scripted summary and chosen cohort took **73.90 seconds**, with zero model calls. This is a single local observation, not a controlled speed comparison.

The nine-candidate evaluator took 44.52 seconds, including 2.31 seconds for uncertainty and influence calculations. This evaluator overhead is separate from both policy runs.

## Interpretation and next step

The frozen protocol uses 2000 paired circular draws for block lengths [7, 28] and seed 20260905. The common UTC calendar contains 1459 days, including 621 days with no included signal events.

- One saved AI choice after exposure to the full historical preview; no untouched holdout or independent discovery.
- Pointwise post-selection intervals are descriptive sensitivity, without adjustment for candidate selection or multiple comparisons.
- Seven- and 28-day circular blocks are sensitivity settings, not proof that dependence has been fully captured.
- Leaving 28-day blocks out measures historical influence; it is not a prospective test.
- Nine candidates provide reference coverage, not nine independent trials, an oracle policy or an objective quality ranking.
- Gross returns against an overlapping all-bar comparator are descriptive; costs, execution and tradable alpha are not assessed.
- Historical and fresh run timings are single observations with uncontrolled load and cache state; missing provider costs remain unknown.

Freeze several unseen decision packets and matched AI/scripted budgets before a prospective evaluation, with blinded diagnostic review and predefined acceptance criteria.

Artifacts: [frozen protocol](protocol.json), [source snapshot](source_snapshot.json), [checked catalog](candidate_catalog.json), [all nine candidate statistics](diagnostics.json), [machine report](report.json).
