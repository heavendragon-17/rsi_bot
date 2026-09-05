# BTC M5 horizon diagnostic

Preliminary result for the accepted parent's current coverage. Alpha assessment: `NOT_ASSESSED`. Descriptive historical profiling; no trained or untouched evaluation.

The same all-four-complete signal IDs and all-four-complete eligible baseline bars enter every horizon statistic. Parent IDs and cooldown are retained without replay.

Parent: `run_20260904T073543149279Z_2572884b`. Source hashes and original 1h/4h arithmetic verified.
Matched UTC window: `2024-09-03T07:55:00Z` through `2026-08-28T00:45:00Z`.
Preparation exclusions: 0; horizon-excluded signals: 0; horizon-excluded baseline bars: 0.

| Horizon | Signal n | Mean % | Median % | Positive share | Baseline n | Baseline mean % | Difference pp |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1h | 1399 | -0.000634 | -0.017680 | 47.25% | 208427 | 0.002971 | -0.003604 |
| 2h | 1399 | 0.000278 | -0.019463 | 48.11% | 208427 | 0.005868 | -0.005590 |
| 3h | 1399 | 0.007067 | -0.021526 | 48.18% | 208427 | 0.008737 | -0.001671 |
| 4h | 1399 | 0.013275 | -0.017738 | 48.53% | 208427 | 0.011586 | 0.001689 |

## Cumulative future excursions

MFE=max(0, future high/entry−1); MAE=min(0, future low/entry−1), in percent. Only bars opening at or after signal close and closing at or before exact target close are used. These are hindsight bounds, not captured P&L; longer windows mechanically contain more opportunities and risks.

| Horizon | Mean MFE % | Median MFE % | Mean MAE % | Median MAE % |
|---|---:|---:|---:|---:|
| 1h | 0.303100 | 0.197687 | -0.277845 | -0.186756 |
| 2h | 0.437643 | 0.287154 | -0.410844 | -0.278728 |
| 3h | 0.544364 | 0.353285 | -0.518925 | -0.358365 |
| 4h | 0.641150 | 0.419176 | -0.601870 | -0.424092 |

## Descriptive uncertainty

Paired circular 7-day UTC calendar blocks use the same draws for signal and baseline, including zero-signal days. Each replicate divides sampled return sums by sampled observation counts. Percentile intervals do not adjust for prior exploration or horizon selection and support no significance or alpha claim.
- 1h: {"block_days": 7, "calendar_days": 725, "calendar_timezone": "UTC", "percentile_level": 0.95, "replicates": 2000, "seed": 20260904, "signal_mean_ci_pct": [-0.020964819562890688, 0.01841321464155645], "signal_minus_baseline_ci_pp": [-0.02201115473097448, 0.013254728517198432], "status": "DESCRIPTIVE", "undefined_replicates": 0, "valid_replicates": 2000}
- 2h: {"block_days": 7, "calendar_days": 725, "calendar_timezone": "UTC", "percentile_level": 0.95, "replicates": 2000, "seed": 20260904, "signal_mean_ci_pct": [-0.03533943752053366, 0.03457675522126657], "signal_minus_baseline_ci_pp": [-0.03740233922080566, 0.026068603027677724], "status": "DESCRIPTIVE", "undefined_replicates": 0, "valid_replicates": 2000}
- 3h: {"block_days": 7, "calendar_days": 725, "calendar_timezone": "UTC", "percentile_level": 0.95, "replicates": 2000, "seed": 20260904, "signal_mean_ci_pct": [-0.04027778216620163, 0.05334044130354698], "signal_minus_baseline_ci_pp": [-0.04478584690911822, 0.039993566660093724], "status": "DESCRIPTIVE", "undefined_replicates": 0, "valid_replicates": 2000}
- 4h: {"block_days": 7, "calendar_days": 725, "calendar_timezone": "UTC", "percentile_level": 0.95, "replicates": 2000, "seed": 20260904, "signal_mean_ci_pct": [-0.05077747171352428, 0.07591266309754434], "signal_minus_baseline_ci_pp": [-0.05725107849437053, 0.056412848742974774], "status": "DESCRIPTIVE", "undefined_replicates": 0, "valid_replicates": 2000}

## Audit and limitations

`signals.csv` and `baseline.csv` contain every eligible event/horizon, original status, and all-horizon inclusion flag. Exact statuses are COMPLETE, INCOMPLETE_TAIL, MISSING_TARGET, GAP; no later target or partial excursion is substituted. `summary.json` includes monthly UTC count/mean, statuses, and both populations' return/excursion summaries. Preparation failures are recorded separately in the manifest.

Gross close-to-close returns omit fees, spreads, slippage, funding, fills and overlapping-position constraints. The comparator uses per-event preparation only, without signal gates or cooldown. No per-signal best-horizon choice, parameter sweep, live filter, or strategy change is made.
