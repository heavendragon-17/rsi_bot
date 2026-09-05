# BTC M5 horizon diagnostic

Preliminary result for the accepted parent's current coverage. Alpha assessment: `NOT_ASSESSED`. Descriptive historical profiling; no trained or untouched evaluation.

The same all-four-complete signal IDs and all-four-complete eligible baseline bars enter every horizon statistic. Parent IDs and cooldown are retained without replay.

Parent: `run_20260904T084317586748Z_97d3c169`. Source hashes and original 1h/4h arithmetic verified.
Matched UTC window: `2022-08-30T00:00:00Z` through `2026-08-27T22:35:00Z`.
Preparation exclusions: 0; horizon-excluded signals: 0; horizon-excluded baseline bars: 0.

| Horizon | Signal n | Mean % | Median % | Positive share | Baseline n | Baseline mean % | Difference pp |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1h | 2865 | -0.000061 | -0.023712 | 45.97% | 420176 | 0.005178 | -0.005239 |
| 2h | 2865 | 0.002605 | -0.028007 | 46.60% | 420176 | 0.010319 | -0.007714 |
| 3h | 2865 | 0.004101 | -0.026338 | 47.33% | 420176 | 0.015492 | -0.011391 |
| 4h | 2865 | -0.004139 | -0.046802 | 46.39% | 420176 | 0.020639 | -0.024778 |

## Cumulative future excursions

MFE=max(0, future high/entry−1); MAE=min(0, future low/entry−1), in percent. Only bars opening at or after signal close and closing at or before exact target close are used. These are hindsight bounds, not captured P&L; longer windows mechanically contain more opportunities and risks.

| Horizon | Mean MFE % | Median MFE % | Mean MAE % | Median MAE % |
|---|---:|---:|---:|---:|
| 1h | 0.319100 | 0.198865 | -0.287158 | -0.192338 |
| 2h | 0.468905 | 0.289281 | -0.427704 | -0.285453 |
| 3h | 0.582636 | 0.365853 | -0.542692 | -0.368691 |
| 4h | 0.673493 | 0.423081 | -0.634419 | -0.436914 |

## Descriptive uncertainty

Paired circular 7-day UTC calendar blocks use the same draws for signal and baseline, including zero-signal days. Each replicate divides sampled return sums by sampled observation counts. Percentile intervals do not adjust for prior exploration or horizon selection and support no significance or alpha claim.
- 1h: {"block_days": 7, "calendar_days": 1459, "calendar_timezone": "UTC", "percentile_level": 0.95, "replicates": 2000, "seed": 20260904, "signal_mean_ci_pct": [-0.015354143145779809, 0.014794371925993586], "signal_minus_baseline_ci_pp": [-0.01965291582352631, 0.008569048773565471], "status": "DESCRIPTIVE", "undefined_replicates": 0, "valid_replicates": 2000}
- 2h: {"block_days": 7, "calendar_days": 1459, "calendar_timezone": "UTC", "percentile_level": 0.95, "replicates": 2000, "seed": 20260904, "signal_mean_ci_pct": [-0.02274307667043436, 0.0267177542254226], "signal_minus_baseline_ci_pp": [-0.031108512963732286, 0.014203128648511112], "status": "DESCRIPTIVE", "undefined_replicates": 0, "valid_replicates": 2000}
- 3h: {"block_days": 7, "calendar_days": 1459, "calendar_timezone": "UTC", "percentile_level": 0.95, "replicates": 2000, "seed": 20260904, "signal_mean_ci_pct": [-0.029464890951518247, 0.03758779812550695], "signal_minus_baseline_ci_pp": [-0.04050558186400906, 0.01764689476804273], "status": "DESCRIPTIVE", "undefined_replicates": 0, "valid_replicates": 2000}
- 4h: {"block_days": 7, "calendar_days": 1459, "calendar_timezone": "UTC", "percentile_level": 0.95, "replicates": 2000, "seed": 20260904, "signal_mean_ci_pct": [-0.04667529363709201, 0.036981411944146544], "signal_minus_baseline_ci_pp": [-0.060572319549738185, 0.012562075974793082], "status": "DESCRIPTIVE", "undefined_replicates": 0, "valid_replicates": 2000}

## Audit and limitations

`signals.csv` and `baseline.csv` contain every eligible event/horizon, original status, and all-horizon inclusion flag. Exact statuses are COMPLETE, INCOMPLETE_TAIL, MISSING_TARGET, GAP; no later target or partial excursion is substituted. `summary.json` includes monthly UTC count/mean, statuses, and both populations' return/excursion summaries. Preparation failures are recorded separately in the manifest.

Gross close-to-close returns omit fees, spreads, slippage, funding, fills and overlapping-position constraints. The comparator uses per-event preparation only, without signal gates or cooldown. No per-signal best-horizon choice, parameter sweep, live filter, or strategy change is made.
