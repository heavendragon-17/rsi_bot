# BTC research Phase 1 reproducible baseline

- Completion: `SUCCESS`
- Operational status: `INCOMPLETE`
- Alpha assessment: `NOT_ASSESSED`
- Window (UTC): `2022-08-28T00:00:00Z → 2026-08-27T23:59:59.999999Z`
- Signals: M5 `2865`, M15 `1175`

This is a descriptive signal-close forward-return baseline. It is not a TP/SL policy, fill simulation, strategy P&L, or profitability finding. The original historical generator was absent; this CLI is an auditable rebuild using the existing replay evaluator.

## Reproduction

`btc_research_phase1.py --data-dir research/data/btc_four_year_20220828_20260828 --output-dir research/results/phase1_four_year_runs --start 2022-08-28T00:00:00Z --end 2026-08-27T23:59:59.999999Z`

## Source and provenance

- Definition: `btc-research-phase1-v1`; strategy: `btc_rsi_cross_alert`.
- Git revision: `62656448062f975190eea6f65ca0117b111e3da8`; dirty-code identity: `5126112c9b0f2704d9c8c2e6f99d2bfb437f73892cf06a7bede848feda006519`.
- Config SHA-256: `4ffedb7ac41c4b4af9db140c89c6facf3df4f91747b3ed86273eb7884eb32d72`.
- Source identity is Binance USD-M Futures, BTC/USDT, native M5/M15/H1/H4 local CSVs. Hashes and cadence facts are in `manifest.json`.
- Common native close coverage: `2022-05-01T04:00:00Z` → `2026-08-28T04:45:00Z`.
- Warnings: 8 signal-horizon outcomes are incomplete or invalid; exact targets were not substituted.

## Preparation and operational validity

Preparation is evaluated independently of bullish signal gates and cooldown. A `READY` trigger bar is evaluable; missing H1/H4 context, non-finite data, and insufficient contiguous history are recorded as preparation exclusions.
- Requested trigger bars: `561024`; evaluable after shared preparation: `561024`.
- Preparation exclusions: `0`; per-timeframe counts and reasons are in `manifest.json` and `summary.json`.
- Operational status is `INCOMPLETE` while execution completion is `SUCCESS`. Missing warmup or no evaluable requested coverage is `INVALID`; partial readiness or incomplete outcomes is `INCOMPLETE`; a fully prepared zero-signal period may be `VALID`.

## Comparator eligibility

The matched all-eligible-bar comparator uses the same per-event point-in-time preparation as replay, but does not apply bullish gates, signal rules, or cooldown. Comparator exclusions and reasons are recorded under `baseline_comparator`.

## Signal and matched all-eligible-bar summaries

| Timeframe | Horizon | Signal complete / total | Signal mean % | Signal median % | Baseline complete / total | Baseline mean % | Baseline median % |
|---|---:|---:|---:|---:|---:|---:|---:|
| 5m | 1h | 2865 / 2865 | -6.0809744e-05 | -0.023712242813 | 420176 / 420176 | 0.005178491097 | 0.003252241114 |
| 5m | 4h | 2865 / 2865 | -0.004138656374 | -0.046801872075 | 420176 / 420176 | 0.020639485729 | 0.012319847411 |
| 5m | 12h | 2863 / 2865 | 0.017844903143 | -0.087005658464 | 420106 / 420176 | 0.061616317822 | 0.027196029465 |
| 5m | 24h | 2861 / 2865 | 0.08636495776 | -0.087942908415 | 419962 / 420176 | 0.124071332236 | 0.063066141417 |
| 15m | 1h | 1175 / 1175 | 0.000746629783 | -0.031662246004 | 140012 / 140012 | 0.005170834171 | 0.003472957034 |
| 15m | 4h | 1175 / 1175 | 0.001730586778 | -0.069309240121 | 140012 / 140012 | 0.020529709007 | 0.012042587218 |
| 15m | 12h | 1175 / 1175 | 0.052388446276 | -0.132772182975 | 140012 / 140012 | 0.061726794593 | 0.027359332518 |
| 15m | 24h | 1173 / 1175 | 0.081052899709 | -0.160765981681 | 139971 / 140012 | 0.124129904414 | 0.062515941565 |

Outcome statuses are exact: `COMPLETE`, `INCOMPLETE_TAIL`, `MISSING_TARGET`, or `GAP`. A target candle after the exact target time is never substituted, and gaps are not bridged.

## Monthly summaries

Monthly rows for signals and matched all-eligible bars are in `summary.json` under `monthly_summaries`; only complete exact-horizon outcomes enter monthly means.

## Limitations

- Alpha remains `NOT_ASSESSED`: no reserved evaluation, selection-aware analysis, bootstrap, DSR/PBO, walk-forward, or cost model is part of Phase 1.
- The 0.10% round-trip cost subtraction is illustrative sensitivity only; it is not an exchange fee, spread, slippage, funding, fill, or P&L simulation.
- Historical artifact counts and 4h means are reported for comparison, not hardcoded as acceptance targets.
- The run uses the available local CSV coverage; incomplete tails remain explicitly visible.
- Replay initializes cooldown at the requested window start. Separate windows have independent one-hour boundary state; comparisons must account for that behavior.
