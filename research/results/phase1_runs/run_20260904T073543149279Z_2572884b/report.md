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
- Git revision: `62656448062f975190eea6f65ca0117b111e3da8`; dirty-code identity: `e81d641d3502cf8ba5f811aa3cbff638a0374ec76a7c82cdd5b60d97e59277b4`.
- Config SHA-256: `4ffedb7ac41c4b4af9db140c89c6facf3df4f91747b3ed86273eb7884eb32d72`.
- Source identity is Binance USD-M Futures, BTC/USDT, native M5/M15/H1/H4 local CSVs. Hashes and cadence facts are in `manifest.json`.
- Common native close coverage: `2024-08-29T04:00:00Z` → `2026-08-28T04:45:00Z`.
- Warnings: Requested end exceeds the common native close-time coverage.; 12 signal-horizon outcomes are incomplete or invalid; exact targets were not substituted.

## Preparation and operational validity

Preparation is evaluated independently of bullish signal gates and cooldown. A `READY` trigger bar is evaluable; missing H1/H4 context, non-finite data, and insufficient contiguous history are recorded as preparation exclusions.
- Requested trigger bars: `278974`; evaluable after shared preparation: `278974`.
- Preparation exclusions: `0`; per-timeframe counts and reasons are in `manifest.json` and `summary.json`.
- Operational status is `INCOMPLETE` while execution completion is `SUCCESS`. Missing warmup or no evaluable requested coverage is `INVALID`; partial readiness or incomplete outcomes is `INCOMPLETE`; a fully prepared zero-signal period may be `VALID`.

## Comparator eligibility

The matched all-eligible-bar comparator uses the same per-event point-in-time preparation as replay, but does not apply bullish gates, signal rules, or cooldown. Comparator exclusions and reasons are recorded under `baseline_comparator`.

## Signal and matched all-eligible-bar summaries

| Timeframe | Horizon | Signal complete / total | Signal mean % | Signal median % | Baseline complete / total | Baseline mean % | Baseline median % |
|---|---:|---:|---:|---:|---:|---:|---:|
| 5m | 1h | 1399 / 1399 | -0.000633714308 | -0.017679687116 | 208427 / 208427 | 0.0029705261 | 0.003016161915 |
| 5m | 4h | 1399 / 1399 | 0.01327507724 | -0.017737982151 | 208427 / 208427 | 0.01158635136 | 0.012600344197 |
| 5m | 12h | 1396 / 1399 | 0.01150960066 | -0.0088734447 | 208331 / 208427 | 0.03518049734 | 0.038223223626 |
| 5m | 24h | 1394 / 1399 | 0.054158739939 | -0.033212259386 | 208187 / 208427 | 0.071009078718 | 0.074697316936 |
| 15m | 1h | 589 / 589 | 0.010415363625 | -0.015983666824 | 69460 / 69460 | 0.00295105944 | 0.003295877948 |
| 15m | 4h | 589 / 589 | 0.042164508657 | 0.000454490193 | 69460 / 69460 | 0.011744626029 | 0.012561331568 |
| 15m | 12h | 588 / 589 | 0.011577297248 | -0.038772002659 | 69429 / 69460 | 0.035519251487 | 0.038136937808 |
| 15m | 24h | 586 / 589 | 0.037734244197 | -0.017508227186 | 69381 / 69460 | 0.071881851533 | 0.075442762442 |

Outcome statuses are exact: `COMPLETE`, `INCOMPLETE_TAIL`, `MISSING_TARGET`, or `GAP`. A target candle after the exact target time is never substituted, and gaps are not bridged.

## Monthly summaries

Monthly rows for signals and matched all-eligible bars are in `summary.json` under `monthly_summaries`; only complete exact-horizon outcomes enter monthly means.

## Limitations

- Alpha remains `NOT_ASSESSED`: no reserved evaluation, selection-aware analysis, bootstrap, DSR/PBO, walk-forward, or cost model is part of Phase 1.
- The 0.10% round-trip cost subtraction is illustrative sensitivity only; it is not an exchange fee, spread, slippage, funding, fill, or P&L simulation.
- Historical artifact counts and 4h means are reported for comparison, not hardcoded as acceptance targets.
- The run uses the available local CSV coverage; incomplete tails remain explicitly visible.
- Replay initializes cooldown at the requested window start. Separate windows have independent one-hour boundary state; comparisons must account for that behavior.
