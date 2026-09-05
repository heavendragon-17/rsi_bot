# BTC research Phase 1 reproducible baseline

- Completion: `SUCCESS`
- Operational status: `INCOMPLETE`
- Alpha assessment: `NOT_ASSESSED`
- Window (UTC): `2024-08-31T17:00:00Z → 2026-08-28T16:59:59.999999Z`
- Signals: M5 `1399`, M15 `589`

This is a descriptive signal-close forward-return baseline. It is not a TP/SL policy, fill simulation, strategy P&L, or profitability finding. The original historical generator was absent; this CLI is an auditable rebuild using the existing replay evaluator.

## Reproduction

`btc_research_phase1.py --data-dir app/backtest/data --output-dir research/results/phase1_runs --start 2024-09-01 --end 2026-08-28`

## Source and provenance

- Definition: `btc-research-phase1-v1`; strategy: `btc_rsi_cross_alert`.
- Git revision: `62656448062f975190eea6f65ca0117b111e3da8`; dirty-code identity: `5527f78bcf5c26ea848d0396226f0610c990b14fca1f8d80dc276b8e12c77ce0`.
- Source identity is Binance USD-M Futures, BTC/USDT, native M5/M15/H1/H4 local CSVs. Hashes and cadence facts are in `manifest.json`.
- Warnings: 12 signal-horizon outcomes are incomplete or invalid; exact targets were not substituted.

## Signal and matched all-eligible-bar summaries

| Timeframe | Horizon | Signal n / complete | Signal mean % | Signal median % | Baseline n / complete | Baseline mean % | Baseline median % |
|---|---:|---:|---:|---:|---:|---:|---:|
| 5m | 1h | 1399 / 1399 | -0.000633714308 | -0.017679687116 | 209218 / 209218 | 0.002897721322 | 0.002947417375 |
| 5m | 4h | 1399 / 1399 | 0.01327507724 | -0.017737982151 | 209182 / 209182 | 0.01157417051 | 0.012644852478 |
| 5m | 12h | 1396 / 1396 | 0.01150960066 | -0.0088734447 | 209086 / 209086 | 0.034611309018 | 0.037757439291 |
| 5m | 24h | 1394 / 1394 | 0.054158739939 | -0.033212259386 | 208942 / 208942 | 0.06921566316 | 0.073835751865 |
| 15m | 1h | 589 / 589 | 0.010415363625 | -0.015983666824 | 69740 / 69740 | 0.002896105239 | 0.003158857657 |
| 15m | 4h | 589 / 589 | 0.042164508657 | 0.000454490193 | 69728 / 69728 | 0.011567066121 | 0.012524367897 |
| 15m | 12h | 588 / 588 | 0.011577297248 | -0.038772002659 | 69696 / 69696 | 0.034581733121 | 0.037462956305 |
| 15m | 24h | 586 / 586 | 0.037734244197 | -0.017508227186 | 69648 / 69648 | 0.069220668463 | 0.073967307221 |

Outcome statuses are exact: `COMPLETE`, `INCOMPLETE_TAIL`, `MISSING_TARGET`, or `GAP`. A target candle after the exact target time is never substituted, and gaps are not bridged.

## Monthly summaries

Monthly rows for signals and matched all-eligible bars are in `summary.json` under `monthly_summaries`; only complete exact-horizon outcomes enter monthly means.

## Limitations

- Alpha remains `NOT_ASSESSED`: no reserved evaluation, selection-aware analysis, bootstrap, DSR/PBO, walk-forward, or cost model is part of Phase 1.
- The 0.10% round-trip cost subtraction is illustrative sensitivity only; it is not an exchange fee, spread, slippage, funding, fill, or P&L simulation.
- Historical artifact counts and 4h means are reported for comparison, not hardcoded as acceptance targets.
- The run uses the available local CSV coverage; incomplete tails remain explicitly visible.
