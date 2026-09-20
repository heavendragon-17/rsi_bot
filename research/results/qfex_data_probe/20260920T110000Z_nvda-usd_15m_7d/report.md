# QFEX equity data probe — report

Symbol: `NVDA-USD` (NVDA/USD) · Venue: QFEX · Timeframe: 15-minute · Window (UTC): `2026-09-13T00:00:00Z` → `2026-09-20T00:00:00Z`
Run (UTC): `2026-09-20T10:59:31Z`

## 1. Instrument selection (recorded before any price fetch)

- Rule: first ACTIVE EQUITY instrument in /refdata response order, chart-blind (no price data consulted); single-stock preferred and satisfied by the first match.
- Choice: `NVDA-USD` at refdata response index 2 of 216.
- Category/status census: {"COMMODITY/ACTIVE": 6, "EQUITY/ACTIVE": 171, "INDEX/ACTIVE": 11, "EQUITY/INACTIVE": 21, "INDEX/INACTIVE": 2, "EQUITY/DELISTED": 1, "FX/INACTIVE": 2, "FX/DELISTED": 2}.
- No chart was viewed before selection; the first ACTIVE EQUITY entry is NVDA-USD (single-stock).

## 2. Requests (exact identifiers and boundaries)

- `GET https://api.qfex.com/refdata` → HTTP 200, 337991 bytes, sha256 `a9d3b2484a53cba7…` (offline reconstruction: 0 new requests).
- `GET https://api.qfex.com/underlier/NVDA-USD?interval=15m&fromISO=2026-09-13T00%3A00%3A00Z&toISO=2026-09-20T00%3A00%3A00Z` → HTTP 200, 108245 bytes, sha256 `45ccc67d67654d2f…` (offline reconstruction: 0 new requests).
- `GET https://api.qfex.com/candles/NVDA-USD?resolution=15MINS&fromISO=2026-09-13T00%3A00%3A00Z&toISO=2026-09-20T00%3A00%3A00Z` → HTTP 200, 184125 bytes, sha256 `0317fd18c2c92aa0…` (offline reconstruction: 0 new requests).
- This directory was produced by offline finalize from preserved raw responses: no new market-data requests were made for these artifacts.
- Budget: 3/8 market-data requests (live fetch, 20 s timeout each, sequential, no retries; offline finalize adds 0).
- No auth, no private endpoints.
- Base URL `https://api.qfex.com` and parameter names verified against the official docs listed in metadata.
- Wire values: underlier `interval=15m`; candles `resolution=15MINS` (CandlesInterval wire value per docs enums.md; `15m` is rejected for candles with 400).

## 3. Loader verification (existing reader, no strategy/bot)

- Reader: `app.backtest.signal_replay_data.load_ohlcv_csv` with timeframe label `15m`.
- Result: 672 rows, 2026-09-13T00:00:00Z → 2026-09-19T23:45:00Z.
- Loader parses timestamps with pandas mixed-format; naive values are assumed UTC+7 storage time, tz-aware values convert to UTC. The probe writes tz-aware '+00:00' UTC stamps, so the loader resolves the exact canonical instants with no shift. BacktestEngine reads the same timestamp,open,high,low,close,volume columns via pd.read_csv (app/backtest/engine/backtest_engine.py:55) + pd.to_datetime (:76).
- File: `loader_instrument_15m.csv` (columns: timestamp,open,high,low,close,volume).

## 4. Coverage summary

- Underlier: 672 rows over 672 expected 15-min intervals; missing 0, out-of-window 0, duplicates 0, nulls 0, OHLC violations 0; range 2026-09-13T00:00:00Z → 2026-09-19T23:45:00Z.
- Instrument: 672 rows; missing 0, out-of-window 0, duplicates 0, nulls 0, OHLC violations 0; range 2026-09-13T00:00:00Z → 2026-09-19T23:45:00Z.
- Missing intervals are reported as observed gaps only; non-trading-session gaps are not classified as corruption, and this 7-day sample does not establish the API's full historical coverage.
- Underlier responses carry no volume/trade fields, so none is stored for underlier. Instrument loader `volume` := venue `usdVolume` (quote-notional); `baseTokenVolume`, `trades` (nullable), midpoint open/close and startingOpenInterest are retained in normalized_instrument_full.csv. No volume invented, no underlier-for-instrument substitution, no gap filling.
- Venue field sentinels (retained verbatim, not measurements, unusable as signal): trades null on 672/672 candles; zero `usdVolume` on 43; zero `baseTokenVolume` on 672; zero midpoint open/close on 672/672; zero startingOpenInterest on 672.

## 5. Chart

- `chart_underlier_vs_instrument_close.png`: underlier vs instrument closes on the full 15-minute grid; missing intervals render as visible breaks (NaN gaps, never interpolated or connected).
- Observed absolute close difference on 672 common intervals (reference vs traded, descriptive only, not a quality verdict): max 2.942788 USD at 2026-09-13T09:30:00Z, mean 0.181545 USD.

## 6. Files, hashes, reproduction

- `raw_refdata.json` sha256 `a9d3b2484a53cba7c9756d2b8c57380bbbe7c8b1a9aff42d2c62df43723b4ccc`
- `raw_underlier.json` sha256 `45ccc67d67654d2f6c25a6c7fa5704b509743b7bbb2f676a607955b78e37688e`
- `raw_candles.json` sha256 `0317fd18c2c92aa0fbcdad7400305512d38e191c9c04c2d59e721532afbcd357`
- `normalized_underlier.csv` sha256 `04adc33736cef3d207b84104684253aebcb33de4a1ac8cd039562e2e12ef3ddd`
- `normalized_instrument_full.csv` sha256 `679dcdafaf065e0f2d5decd183f369b0e6205ec437dc3035c5b5620383e7e75b`
- `loader_instrument_15m.csv` sha256 `ba58e886d7154f8c8b454d39b3cdc512e3f5455a0ccd6278309ce10fc9d8020a`
- Reproduction: `C:/Python314/python.exe research/qfex_data_probe.py --out research/results/qfex_data_probe/20260920T110000Z_nvda-usd_15m_7d --from-iso 2026-09-13T00:00:00Z --to-iso 2026-09-20T00:00:00Z --symbol NVDA-USD  # live (spends 3 requests) OR offline with 0 new requests: C:/Python314/python.exe research/qfex_data_probe.py --out research/results/qfex_data_probe/20260920T110000Z_nvda-usd_15m_7d --from-iso 2026-09-13T00:00:00Z --to-iso 2026-09-20T00:00:00Z --symbol NVDA-USD --raw-dir research/results/qfex_data_probe/20260920T110000Z_nvda-usd_15m_7d`
- Raw responses are preserved verbatim (`raw_*.json`); normalization never edits them in place.

## 7. Limitations

- One symbol / one timeframe / one 7-day window only; not a claim about full API history.
- Session gaps are expected for equities and are reported as observed, not as corruption.
- Loader `volume` is venue `usdVolume` (quote-notional); base-unit volume is retained separately.
- No strategy, signal, profitability, or trading-readiness claim is made.
