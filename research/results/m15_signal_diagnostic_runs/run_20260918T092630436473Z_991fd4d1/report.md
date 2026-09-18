# BTC M15 signal-and-gate diagnostic

Descriptive signal research. Every number below is a gross signal-close
forward return on overlapping historical observations. This is not realized
P&L, not a fill or fee model, and not evidence of a trading edge.
Alpha assessment: `NOT_ASSESSED`.

- Parent packet: `run_20260918T092140133007Z_97d3c169` (emitted M15 alerts `1175`)
- Matched M15 window (UTC): `2022-08-30T04:15:00Z` → `2026-08-27T15:00:00Z`
- Candidate M15 bars: `140012`; preparation-ready: `140012`; preparation exclusions: `0`
- Fixed horizons: `1h` and `4h` (fixed, not searched)

## Populations and cooldown policy

| Group | Rule | Cooldown | n |
|---|---|---|---:|
| `m15_signal` | Emitted replay alerts: fresh RSI21 EMA9/WMA45 bullish cross **and** M15, H1, H4 closes above native EMA21 | Replay one-hour per-timeframe cooldown applied | 1175 |
| `gate_ready_no_cross` | Preparation-ready M15 bars with M15, H1, H4 closes above native EMA21; RSI crossover not required | None | 38292 |
| `all_eligible_bars` | Every preparation-ready M15 bar in the matched window; no gate | None | 140012 |

`m15_signal` is a cooldown-thinned subset of `gate_ready_no_cross`, which is a
subset of `all_eligible_bars`. Two M15 bars are never more than 15 minutes apart,
so all three populations contain heavily overlapping observations; the 1h and 4h
windows of adjacent observations also overlap. These are not independent trades
and are never compounded into an equity curve.

## Mean and median forward returns

Only observations whose **both** fixed horizons are `COMPLETE` enter every
statistic, so the three populations are compared on one complete basis.

| Horizon | Group | n included / total | Mean % | Median % | Positive share |
|---|---|---:|---:|---:|---:|
| 1h | `m15_signal` | 1175 / 1175 | 0.000747 | -0.031662 | 45.19% |
| 1h | `gate_ready_no_cross` | 38292 / 38292 | 0.007310 | -0.020881 | 46.82% |
| 1h | `all_eligible_bars` | 140012 / 140012 | 0.005171 | 0.003473 | 50.55% |
| 4h | `m15_signal` | 1175 / 1175 | 0.001731 | -0.069309 | 45.11% |
| 4h | `gate_ready_no_cross` | 38292 / 38292 | 0.023076 | -0.048971 | 46.19% |
| 4h | `all_eligible_bars` | 140012 / 140012 | 0.020530 | 0.012043 | 50.97% |

## Descriptive time-block uncertainty

Reused from the existing M5 horizon diagnostic: paired circular 7-day UTC
calendar blocks, 2,000 replicates, NumPy `default_rng(20260904)`, identical
draws for both populations, observation-weighted means, 2.5th/97.5th
percentiles. These are post-selection descriptive sensitivity intervals over
already-examined history. They are not significance tests and do not correct
for prior exploration, overlapping observations, or horizon choice.

| Horizon | Contrast | Difference pp | Interval pp | Valid replicates |
|---|---|---:|---|---:|
| 1h | `m15_signal_minus_gate_ready_no_cross` | -0.006563 | [-0.036693, 0.023982] | 2000 |
| 1h | `gate_ready_no_cross_minus_all_eligible_bars` | 0.002139 | [-0.005725, 0.010454] | 2000 |
| 1h | `m15_signal_minus_all_eligible_bars` | -0.004424 | [-0.036585, 0.026645] | 2000 |
| 4h | `m15_signal_minus_gate_ready_no_cross` | -0.021345 | [-0.077259, 0.034819] | 2000 |
| 4h | `gate_ready_no_cross_minus_all_eligible_bars` | 0.002546 | [-0.024809, 0.030096] | 2000 |
| 4h | `m15_signal_minus_all_eligible_bars` | -0.018799 | [-0.075959, 0.039218] | 2000 |

## Monthly 1-hour means and observation counts

| Month (UTC) | Group | n | Mean 1h % |
|---|---|---:|---:|
| 2022-08 | `all_eligible_bars` | 175 | -0.040465 |
| 2022-08 | `gate_ready_no_cross` | 62 | -0.161696 |
| 2022-08 | `m15_signal` | 1 | 0.631420 |
| 2022-09 | `all_eligible_bars` | 2880 | -0.002137 |
| 2022-09 | `gate_ready_no_cross` | 612 | -0.033291 |
| 2022-09 | `m15_signal` | 19 | 0.002706 |
| 2022-10 | `all_eligible_bars` | 2976 | 0.007852 |
| 2022-10 | `gate_ready_no_cross` | 685 | 0.025663 |
| 2022-10 | `m15_signal` | 23 | 0.073826 |
| 2022-11 | `all_eligible_bars` | 2880 | -0.021569 |
| 2022-11 | `gate_ready_no_cross` | 570 | -0.035664 |
| 2022-11 | `m15_signal` | 21 | -0.032301 |
| 2022-12 | `all_eligible_bars` | 2976 | -0.004706 |
| 2022-12 | `gate_ready_no_cross` | 775 | 0.000363 |
| 2022-12 | `m15_signal` | 24 | -0.085241 |
| 2023-01 | `all_eligible_bars` | 2976 | 0.046047 |
| 2023-01 | `gate_ready_no_cross` | 1432 | 0.045367 |
| 2023-01 | `m15_signal` | 47 | -0.058345 |
| 2023-02 | `all_eligible_bars` | 2688 | 0.001586 |
| 2023-02 | `gate_ready_no_cross` | 574 | 0.042160 |
| 2023-02 | `m15_signal` | 13 | 0.168805 |
| 2023-03 | `all_eligible_bars` | 2976 | 0.030189 |
| 2023-03 | `gate_ready_no_cross` | 861 | 0.054174 |
| 2023-03 | `m15_signal` | 22 | 0.225736 |
| 2023-04 | `all_eligible_bars` | 2880 | 0.005057 |
| 2023-04 | `gate_ready_no_cross` | 755 | 0.009128 |
| 2023-04 | `m15_signal` | 22 | -0.036318 |
| 2023-05 | `all_eligible_bars` | 2976 | -0.009000 |
| 2023-05 | `gate_ready_no_cross` | 563 | -0.021045 |
| 2023-05 | `m15_signal` | 15 | -0.043140 |
| 2023-06 | `all_eligible_bars` | 2880 | 0.016705 |
| 2023-06 | `gate_ready_no_cross` | 829 | 0.009743 |
| 2023-06 | `m15_signal` | 24 | 0.106051 |
| 2023-07 | `all_eligible_bars` | 2976 | -0.005222 |
| 2023-07 | `gate_ready_no_cross` | 536 | -0.009482 |
| 2023-07 | `m15_signal` | 19 | 0.019592 |
| 2023-08 | `all_eligible_bars` | 2976 | -0.014842 |
| 2023-08 | `gate_ready_no_cross` | 373 | -0.030126 |
| 2023-08 | `m15_signal` | 10 | -0.097860 |
| 2023-09 | `all_eligible_bars` | 2880 | 0.005552 |
| 2023-09 | `gate_ready_no_cross` | 655 | 0.002335 |
| 2023-09 | `m15_signal` | 16 | -0.124961 |
| 2023-10 | `all_eligible_bars` | 2976 | 0.034551 |
| 2023-10 | `gate_ready_no_cross` | 1148 | 0.056459 |
| 2023-10 | `m15_signal` | 34 | -0.111168 |
| 2023-11 | `all_eligible_bars` | 2880 | 0.012640 |
| 2023-11 | `gate_ready_no_cross` | 963 | -0.011626 |
| 2023-11 | `m15_signal` | 34 | 0.021677 |
| 2023-12 | `all_eligible_bars` | 2976 | 0.017046 |
| 2023-12 | `gate_ready_no_cross` | 1004 | 0.025688 |
| 2023-12 | `m15_signal` | 32 | 0.130493 |
| 2024-01 | `all_eligible_bars` | 2976 | 0.001865 |
| 2024-01 | `gate_ready_no_cross` | 758 | 0.006032 |
| 2024-01 | `m15_signal` | 25 | -0.111341 |
| 2024-02 | `all_eligible_bars` | 2784 | 0.054329 |
| 2024-02 | `gate_ready_no_cross` | 1209 | 0.049534 |
| 2024-02 | `m15_signal` | 40 | -0.096149 |
| 2024-03 | `all_eligible_bars` | 2976 | 0.022215 |
| 2024-03 | `gate_ready_no_cross` | 1143 | 0.006779 |
| 2024-03 | `m15_signal` | 39 | 0.035400 |
| 2024-04 | `all_eligible_bars` | 2880 | -0.020427 |
| 2024-04 | `gate_ready_no_cross` | 627 | -0.031820 |
| 2024-04 | `m15_signal` | 13 | -0.159423 |
| 2024-05 | `all_eligible_bars` | 2976 | 0.016177 |
| 2024-05 | `gate_ready_no_cross` | 914 | 0.004877 |
| 2024-05 | `m15_signal` | 30 | -0.072087 |
| 2024-06 | `all_eligible_bars` | 2880 | -0.009668 |
| 2024-06 | `gate_ready_no_cross` | 394 | -0.025087 |
| 2024-06 | `m15_signal` | 12 | -0.115301 |
| 2024-07 | `all_eligible_bars` | 2976 | 0.005330 |
| 2024-07 | `gate_ready_no_cross` | 1005 | 0.026131 |
| 2024-07 | `m15_signal` | 28 | 0.152910 |
| 2024-08 | `all_eligible_bars` | 2976 | -0.009649 |
| 2024-08 | `gate_ready_no_cross` | 692 | -0.003935 |
| 2024-08 | `m15_signal` | 24 | -0.061759 |
| 2024-09 | `all_eligible_bars` | 2880 | 0.010966 |
| 2024-09 | `gate_ready_no_cross` | 906 | 0.015163 |
| 2024-09 | `m15_signal` | 24 | 0.285032 |
| 2024-10 | `all_eligible_bars` | 2976 | 0.015106 |
| 2024-10 | `gate_ready_no_cross` | 973 | 0.012490 |
| 2024-10 | `m15_signal` | 33 | -0.009761 |
| 2024-11 | `all_eligible_bars` | 2880 | 0.045607 |
| 2024-11 | `gate_ready_no_cross` | 1187 | 0.040285 |
| 2024-11 | `m15_signal` | 40 | 0.007390 |
| 2024-12 | `all_eligible_bars` | 2976 | -0.002295 |
| 2024-12 | `gate_ready_no_cross` | 706 | 0.003100 |
| 2024-12 | `m15_signal` | 27 | -0.088562 |
| 2025-01 | `all_eligible_bars` | 2976 | 0.013579 |
| 2025-01 | `gate_ready_no_cross` | 1064 | -0.011709 |
| 2025-01 | `m15_signal` | 34 | -0.038143 |
| 2025-02 | `all_eligible_bars` | 2688 | -0.027500 |
| 2025-02 | `gate_ready_no_cross` | 411 | -0.031432 |
| 2025-02 | `m15_signal` | 16 | 0.106044 |
| 2025-03 | `all_eligible_bars` | 2976 | -0.000679 |
| 2025-03 | `gate_ready_no_cross` | 828 | -0.025392 |
| 2025-03 | `m15_signal` | 19 | -0.041135 |
| 2025-04 | `all_eligible_bars` | 2880 | 0.019791 |
| 2025-04 | `gate_ready_no_cross` | 1041 | -0.004268 |
| 2025-04 | `m15_signal` | 34 | -0.170290 |
| 2025-05 | `all_eligible_bars` | 2976 | 0.014570 |
| 2025-05 | `gate_ready_no_cross` | 961 | -0.002646 |
| 2025-05 | `m15_signal` | 33 | -0.060284 |
| 2025-06 | `all_eligible_bars` | 2880 | 0.004214 |
| 2025-06 | `gate_ready_no_cross` | 767 | 0.004725 |
| 2025-06 | `m15_signal` | 22 | 0.002654 |
| 2025-07 | `all_eligible_bars` | 2976 | 0.010619 |
| 2025-07 | `gate_ready_no_cross` | 959 | 0.021311 |
| 2025-07 | `m15_signal` | 29 | 0.098844 |
| 2025-08 | `all_eligible_bars` | 2976 | -0.008460 |
| 2025-08 | `gate_ready_no_cross` | 509 | 0.020341 |
| 2025-08 | `m15_signal` | 11 | -0.014269 |
| 2025-09 | `all_eligible_bars` | 2880 | 0.007892 |
| 2025-09 | `gate_ready_no_cross` | 907 | 0.004978 |
| 2025-09 | `m15_signal` | 25 | 0.015239 |
| 2025-10 | `all_eligible_bars` | 2976 | -0.004219 |
| 2025-10 | `gate_ready_no_cross` | 867 | 0.015439 |
| 2025-10 | `m15_signal` | 23 | 0.097011 |
| 2025-11 | `all_eligible_bars` | 2880 | -0.027664 |
| 2025-11 | `gate_ready_no_cross` | 438 | -0.056563 |
| 2025-11 | `m15_signal` | 14 | 0.006465 |
| 2025-12 | `all_eligible_bars` | 2976 | -0.000523 |
| 2025-12 | `gate_ready_no_cross` | 681 | -0.044517 |
| 2025-12 | `m15_signal` | 19 | -0.140751 |
| 2026-01 | `all_eligible_bars` | 2976 | -0.013249 |
| 2026-01 | `gate_ready_no_cross` | 674 | 0.011727 |
| 2026-01 | `m15_signal` | 15 | 0.240307 |
| 2026-02 | `all_eligible_bars` | 2688 | -0.022286 |
| 2026-02 | `gate_ready_no_cross` | 412 | -0.030146 |
| 2026-02 | `m15_signal` | 12 | 0.071613 |
| 2026-03 | `all_eligible_bars` | 2976 | 0.004047 |
| 2026-03 | `gate_ready_no_cross` | 793 | 0.010155 |
| 2026-03 | `m15_signal` | 27 | 0.129927 |
| 2026-04 | `all_eligible_bars` | 2880 | 0.016901 |
| 2026-04 | `gate_ready_no_cross` | 910 | 0.018218 |
| 2026-04 | `m15_signal` | 27 | -0.105116 |
| 2026-05 | `all_eligible_bars` | 2976 | -0.004161 |
| 2026-05 | `gate_ready_no_cross` | 766 | -0.021205 |
| 2026-05 | `m15_signal` | 28 | 0.043061 |
| 2026-06 | `all_eligible_bars` | 2880 | -0.030781 |
| 2026-06 | `gate_ready_no_cross` | 508 | -0.040720 |
| 2026-06 | `m15_signal` | 19 | -0.010555 |
| 2026-07 | `all_eligible_bars` | 2976 | 0.010430 |
| 2026-07 | `gate_ready_no_cross` | 978 | -0.024118 |
| 2026-07 | `m15_signal` | 30 | -0.040222 |
| 2026-08 | `all_eligible_bars` | 2557 | 0.039262 |
| 2026-08 | `gate_ready_no_cross` | 907 | 0.065633 |
| 2026-08 | `m15_signal` | 27 | 0.046414 |

## Charts

- `charts/mean_returns_by_group.png` — mean forward return by horizon and group.
- `charts/monthly_1h_returns_and_counts.png` — monthly 1h means with monthly observation counts.
- `charts/m15_alert_1h_distribution.png` — distribution of 1h returns after M15 alerts, with the other two populations shown for context.

## Limitations

- Signal-candle closes are bookkeeping reference points, not guaranteed execution prices.
- No fee, spread, slippage, funding, fill, or position-size model is applied.
- Overlapping observations are not independent; the reported `n` overstates independent evidence.
- The populations were defined after the four-year history had already been examined, so this is development evidence.
- No threshold, horizon, cooldown, or strategy rule was searched or changed.
