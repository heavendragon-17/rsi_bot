# Core V2.1 verification artifacts

This directory records the reproducible data-acquisition and point-in-time
replay evidence for the reviewer-approved Core V2.1 signal contract. It is an
event/decision audit, not an execution or profitability backtest.

## Inventory

| Path | Purpose | Repository policy |
|---|---|---|
| `binance_refresh.json` | Acquisition manifest for 24 Binance USD-M candidates plus Binance BTC benchmark | Reviewable |
| `hyperliquid_refresh.json` | Acquisition manifest for Hyperliquid `PUMP/USDC:USDC` | Reviewable |
| `full_replay/core_v2_1_replay.metadata.json` | Input hashes, coverage, anchor/seed/timestamp contracts, window, and aggregate event counts | Reviewable |
| `full_replay/core_v2_1_replay.csv` | Full 125,000-row audit ledger for filtering/spreadsheets | Generated locally; ignored because of size |
| `full_replay/core_v2_1_replay.jsonl` | Same ledger as structured line-delimited JSON | Generated locally; ignored because of size |

The manifests contain absolute source paths from the workstation that created
them. Use their venue/instrument identities, time boundaries, row counts, and
SHA-256 values for review; do not assume another checkout has the same absolute
path.

## Reproduce acquisition

Run from the repository root in the selected Conda environment:

```bat
call C:\ProgramData\anaconda3\Scripts\activate.bat rsi
python -m app.backtest.core_v2_1.binance_data --data-dir app\backtest\data --candle-count 5000 --manifest artifacts\core_v2_1\binance_refresh.json
python -m app.signal.core_v2_1.hyperliquid_export --data-dir app\backtest\data --candle-count 5000 --manifest artifacts\core_v2_1\hyperliquid_refresh.json
```

Both commands accept only fully finalized M15 candles using authoritative
exchange clocks. They validate the locked feature anchor, source identity,
schema, OHLCV, cadence, duplicate handling, venue-specific overlap rules, and
exact tail before an atomic replacement. Conflicting duplicate source rows are
rejected.

Binance can page a fresh file from the locked anchor. Hyperliquid exposes a
rolling tail capped at 5,000 candles, so the canonical anchored PUMP CSV is
extended incrementally with an immutable overlap. If that CSV is lost after
the API window moves past the anchor, the correct response is explicit
recovery/migration—not a new moving seed. The same canonical file seeds PUMP
into an empty live-runtime SQLite database before API-tail reconciliation.

## Reproduce the full replay

```bat
python -m app.backtest.core_v2_1 --universe-mode full --data-dir app\backtest\data --output-dir artifacts\core_v2_1\full_replay
```

The checked run used `full:common_window` with all 25 candidates and Binance
BTC reference data:

| Measure | Value |
|---|---:|
| UTC trigger window | `2026-06-29T11:30:00Z` through `2026-08-20T13:15:00Z` |
| Ledger records / processed closes | 125,000 |
| Evaluated | 98,550 |
| `NOT_READY` | 26,450 |
| Public lifecycle events | 477 |
| `A_PLUS_LONG` | 63 |
| `WAIT_FOR_PULLBACK` | 207 |
| `PULLBACK_LONG` | 19 |
| `WAIT_CANCELLED` | 72 |
| `WAIT_EXPIRED` | 116 |

Generated-file hashes for that exact run:

```text
core_v2_1_replay.csv       9C477EB68506947EFF8446C1EFCDEB46ACE7BED4D2A8537457D759961E9E7D52
core_v2_1_replay.jsonl     21B5E51F4E6C7679DEC065DF822E3EB4A372A5A7E0EC8E5A1CEF14245B287D56
core_v2_1_replay.metadata.json  54E37619BBCD3A0430F79626628BA9BDF1F0D1D48B8C2C29159D216C8D1E19AE
```

## What a reviewer can conclude

The artifacts demonstrate source coverage, venue-aware routing, fixed feature
seeding, timestamp normalization, exact point-in-time context, deterministic
state transitions, and public-event counts for the recorded input hashes.

They do **not** demonstrate that any signal was taken, that an order existed,
or that an entry/SL/TP filled. No order book, latency, fees, funding, slippage,
position sizing, PnL, win rate, or execution result is modeled. Reference
Entry/Stop/TP values are advisory outputs of the pure signal contract only.

For the rules being audited, read
[`docs/07_trading_strategies/core-v2-1.md`](../../docs/07_trading_strategies/core-v2-1.md).
