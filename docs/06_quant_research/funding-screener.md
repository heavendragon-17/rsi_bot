# Delta-neutral funding screener

Standalone research tool in `research/funding_screener/`. It is not part of
the live bot and imports nothing from `app/`. Stdlib only (no `pip install`).

## Run

```bash
cd research/funding_screener && python screener.py   # http://localhost:8787
PORT=10000 python screener.py                         # hosts that inject PORT
pytest tests/test_funding_screener.py                 # offline fixture tests
```

Public deploy: `render.yaml` at the repo root is a Render Blueprint
(free plan, Singapore region, `rootDir: research/funding_screener`).
Manual alternative: New Web Service, runtime Python, root directory
`research/funding_screener`, build `pip install -r requirements.txt`,
start `python screener.py`, health check `/healthz`.

Env vars: `PORT` (8787), `HOST` (0.0.0.0), `REFRESH_S` (60),
`MAX_HISTORY_PAIRS` (220), `SCREENER_CACHE` (history cache path,
default `research/funding_screener/cache/history.json`), `LOG_LEVEL`.

## Files

| File | Role |
|---|---|
| `venues.py` | One adapter per venue: current snapshot, 30d history, optional enrich (bid/ask, OI) |
| `metrics.py` | Pair building, signed spread, sustainability, spike/flip, spread risk |
| `screener.py` | Snapshot loop, per-venue history workers, HTTP server (`/`, `/api/opps`, `/api/pair`, `/healthz`) |
| `static/index.html` | Board UI; break-even, verdict and size tier are computed client-side so fee edits apply instantly |

## Venues and public endpoints

| Venue | Snapshot | History | Bid/ask | OI |
|---|---|---|---|---|
| Hyperliquid (+ every HIP-3 dex as `HL:<dex>`) | `POST /info metaAndAssetCtxs` | `fundingHistory` | `impactPxs` | `openInterest × markPx` |
| Lighter | `/orderBookDetails` + `/funding-rates` (lighter rows) | `/fundings` 1h | `/orderBookOrders` (candidates only) | `open_interest_usd` |
| QFEX | `/md/contracts` (USD-quoted only) | `/funding/{symbol}` | `/md/orderbook/{symbol}` (candidates) | `open_interest_usd` |
| Extended | `/info/markets` | `/info/{market}/funding` | `bidPrice/askPrice` | `openInterest` (USD) |
| Variational | `/metadata/v2/stats` | none: recorded locally from snapshots | RFQ `quotes` | long + short trader OI |
| Aster | `premiumIndex`, `fundingInfo`, `bookTicker`, `24hr` | `fundingRate` (expanded to hourly) | `bookTicker` | `openInterest` (candidates) |
| Paradex | `/markets/summary` | none: recorded locally | `bid/ask` | `open_interest × mark` |

Not covered: TxFlow, PopDEX, Phoenix (no documented public funding API found).

## Metric definitions

- Rates are normalised to an hourly decimal, positive = longs pay.
- Pair direction is the one with positive current carry. Carry per hour =
  `rate_short − rate_long` (signed; never the sum of absolute values).
- Pairs are only formed when unit prices agree within 4% (guards ticker
  collisions; `kPEPE`/`1000PEPE` are rescaled first).
- `avg24/avg7/avg30` = mean hourly carry over the window, as APR %.
- `sust30` = % of hours in the last 30 days with carry > 0.
- `spike`: now ≥ 30% APR and > max(2 × ref, ref + 30) where ref = max(avg24, avg7, 0).
- `flip`: ≥ 4 sign changes of the daily mean carry in 30d, or sign(avg7) ≠ sign(avg30).
- `risk` (own approximation, not ProFunding's formula): coefficient of variation
  of hourly carry over 7d. HIGH if mean ≤ 0, CV > 3 or sust < 70; LOW if
  CV < 1 and sust ≥ 85; else MED.
- Hard drop (needs ≥ 72 history hours): avg30 < 0 or sust30 ≤ 61%.
- Break-even (client): cost = Σ legs (2 × fee + full bid/ask spread), fee is
  taker or maker per the UI toggle; expected carry = min(now, avg7) when avg7 > 0;
  hours = cost / expected hourly carry. Missing bid/ask uses an assumed spread (default 0.05%).
- Size tier from min leg OI: < $10k SKIP, < $50k SMALL, < $170k OK, else ROOM.
- Verdict: CLEANEST = sust > 93, risk LOW/MED, BE ≤ 14h, OI ≥ $50k, no spike.

## Backtest (`backtest.py`)

```bash
cd research/funding_screener
python backtest.py --days 45 --lookback 14 --sizes 10000,20000 --max-positions 3 --hold-days 3
```

Walk-forward replay on real hourly funding history of venues with a history API
(Hyperliquid + HIP-3, Lighter, QFEX, Extended, Aster). Universe = cross-venue
pairs whose legs both have OI ≥ `--min-oi` today. Each 00:00 UTC, using only
prior data: close positions held ≥ `--hold-days` or with trailing-24h carry ≤ 0,
then open the best-ranked pairs (lookback avg > 0, sust > 61%, 24h avg > 0, no
spike, no HIGH risk with sust < 85, break-even ≤ `--max-be-h`), one per symbol,
up to `--max-positions`. Each fill pays taker fee + half bid/ask + `--impact`.
A naive baseline (highest last-hour carry, no filters) runs alongside.
Outputs `results/backtest_report.md` and `results/backtest.json`.
Biases: today's OI/bid-ask, no basis or liquidation simulation, 8h funding spread
evenly per hour.

## Assumptions to re-check against live data

- Lighter `/funding-rates` lighter rows are treated as 8h-normalised fractions
  (divided by 8); `/fundings` `rate` as percent per hour with `direction`
  `long` = longs pay. Inferred from BTC values, not stated in the docs.
- Paradex `funding_rate` is treated as the rate per `funding_interval_minutes`.
- History is only fetched for the legs of the top `MAX_HISTORY_PAIRS` pairs by
  current APR (with QFEX/Lighter pairs prioritised); other rows show "THIẾU LỊCH SỬ".
