# BTC M5: four-year horizon and regime findings

## Result

The requested four-year study is complete for the M5 1h/2h/3h/4h horizon
diagnostic. It contains 2,865 emitted M5 alerts, all complete at all four exact
horizons. Gross average returns are close to zero, all medians are negative,
and every descriptive 95% block-bootstrap interval for signal mean and
signal-minus-baseline spans zero. Alpha remains NOT_ASSESSED.

| Horizon | N | Mean gross % | Median gross % | Positive share | Matched all-bar mean % |
|---|---:|---:|---:|---:|---:|
| 1h | 2865 | -0.000061 | -0.023712 | 45.97% | 0.005178 |
| 2h | 2865 | 0.002605 | -0.028007 | 46.60% | 0.010319 |
| 3h | 2865 | 0.004101 | -0.026338 | 47.33% | 0.015492 |
| 4h | 2865 | -0.004139 | -0.046802 | 46.39% | 0.020639 |

These are signal-close forward returns, not fills or realized P&L. Fees,
slippage, funding, and overlapping positions are not modeled. The comparator
uses preparation-ready M5 bars over the first-to-last-signal window and the
same complete horizon coverage; it applies no bullish signal gates or cooldown.

There are substantial within-window movements: median favorable/adverse
excursions are +0.1989%/-0.1923% at 1h and +0.2893%/-0.2855% at 2h. Those
future-bar extremes are hindsight bounds. Their existence does not show that
an executable exit would capture the favorable excursion before a loss.

## Variation through time

| August-to-August study year | M5 alerts | Mean gross 2h % |
|---|---:|---:|
| 2022-2023 | 666 | 0.001801 |
| 2023-2024 | 801 | 0.006746 |
| 2024-2025 | 768 | 0.029324 |
| 2025-2026 | 630 | -0.034381 |

Predeclared regime labels use only the last completed UTC day's data. Trend is
the trailing 90-day return (>+10% UP, <-10% DOWN, otherwise SIDEWAYS); volatility
is the sample standard deviation of 30 daily simple returns annualized by
sqrt(365), with 60% separating HIGH and LOW. These are descriptive choices,
not universal regime definitions or optimized entry filters.

The DOWN/HIGH group averages -0.115148% at 2h (174 alerts), versus +0.028784%
for DOWN/LOW (616 alerts). UP/HIGH averages -0.041038% (167), versus +0.019526%
for UP/LOW (1,093). Subgroup uncertainty and earlier selection are not corrected
here. This motivates a future preregistered volatility/entry-quality study;
it does not authorize applying a filter or treating positive groups as alpha.

## Coverage, provenance and validation

- Requested signals: `[2022-08-28T00:00:00Z, 2026-08-28T00:00:00Z)`.
  Warmup begins May 1, 2022. Later native candles provide outcomes only.
- Retrieved and SHA-256 checked 108 Binance USD-M monthly archives, verified
  overlapping OHLCV against existing files, and published a separate dataset.
  All four canonical source files retain their original hashes. The exchange
  documents its archives and checksums in [Binance Public Data](https://github.com/binance/binance-public-data).
- All 561,024 requested M5/M15 trigger bars passed preparation; the full replay
  emitted 2,865 M5 and 1,175 M15 alerts. M15 was not optimized in this study.
- M5 diagnostic: 11,460 complete event-horizon rows, 420,176 matched eligible
  comparator bars, zero preparation/horizon exclusions. Every horizon has
  2,000 valid paired seven-day calendar-block replicates and none undefined.
- Regime labels are available for every signal/comparator event and each
  grouping partitions all 2,865 signals. Source daily closes never postdate
  their signal. Calendar 2022 and 2026 are partial; study years are full.
- Independently recalculated all M5 horizon means, medians, positive shares,
  and excursions from raw CSVs. The original/expanded signal sets match on
  all 1,398 IDs within their shared window. More history can alter recursive
  indicator seeding in general, so this agreement was checked rather than forced.
- Focused acquisition/replay/horizon/regime tests: 60 passed. The full repository
  suite was not run; Ruff is unavailable because its installed wrapper lacks
  its binary. No live strategy or configuration changed.
- The parent Phase 1 packet remains INCOMPLETE for its additional 12h/24h tails.
  This does not hide a missing 1h-4h outcome in the separately checked M5 cohort.

Four years provides broader coverage, not proof that all possible regimes or an
independent complete market cycle are represented. Retrospective results remain
development evidence. The next decision should focus on M5 1h/2h behavior and
explicit entry/exit assumptions, with 3h as a diagnostic, before selecting a
filter from these observed subgroup results.

## Reproduction and evidence

```powershell
C:\ProgramData\anaconda3\envs\rsi\python.exe -m research.btc_four_year_data --workers 4 --timeout 20 --retries 3
C:\ProgramData\anaconda3\envs\rsi\python.exe btc_research_phase1.py --data-dir research/data/btc_four_year_20220828_20260828 --output-dir research/results/phase1_four_year_runs --start 2022-08-28T00:00:00Z --end 2026-08-27T23:59:59.999999Z
C:\ProgramData\anaconda3\envs\rsi\python.exe -m research.btc_m5_horizon_diagnostic --baseline-run research/results/phase1_four_year_runs/run_20260904T084317586748Z_97d3c169 --output-dir research/results/m5_four_year_horizon_runs
C:\ProgramData\anaconda3\envs\rsi\python.exe -m research.btc_m5_regime_review --horizon-run research/results/m5_four_year_horizon_runs/run_20260904T084448776441Z_97d3c169 --output-dir research/results/m5_four_year_regime_runs
```

Acquisition refuses to overwrite an existing completed dataset. Reuse the
validated dataset for repeat research runs or choose a new dataset path.
For new baseline/horizon executions, substitute their returned packet paths
in the following command. Network acquisition may need explicit local execution
access; this run's downloaded staging files also required that context to read.

- [Acquisition manifest](data/btc_four_year_20220828_20260828/acquisition_manifest.json)
- [Four-year Phase 1 report](results/phase1_four_year_runs/run_20260904T084317586748Z_97d3c169/report.md)
- [Four-year horizon report](results/m5_four_year_horizon_runs/run_20260904T084448776441Z_97d3c169/report.md)
- [Four-year regime report](results/m5_four_year_regime_runs/run_20260904T084529594410Z/report.md)
- [Preliminary two-year report](results/m5_horizon_runs/run_20260904T083923276439Z_2572884b/report.md)
