# Task Tracker

> Current work items. Update as you go — mark items complete, add new ones as they emerge.

## Current Tasks

- [x] 1. Use the user-selected Conda `rsi` environment and run the existing baseline test suite.
  - [x] Resolve pytest in `C:\ProgramData\anaconda3\envs\rsi` without creating a second environment.
  - [x] Record the exact baseline result and isolate pre-existing failures.
- [x] 2. Implement Core V2.1 as a pure evaluator with typed state and dedicated deterministic indicators.
  - [x] Lock the 25-candidate universe, venue map, thresholds, and BTC H4 rule.
  - [x] Implement RSI21, RSI EMA9, RSI WMA45, EMA21, EMA200, and ATR14 with explicit warm-up behavior.
  - [x] Cover fresh cross, mandatory filters, A+, WAIT, pullback, cancel, expiry, consumption, and re-arm with unit/golden tests.
- [x] 3. Build a point-in-time-safe six-symbol replay using the local CSV data and emit an audit ledger.
  - [x] Normalize stored UTC+7 candle-open timestamps to aware UTC close times.
  - [x] Derive fully closed H1/H4 context from M15 data on UTC boundaries and prevent lookahead.
  - [x] Replay ETH, SOL, BNB, XRP, LINK, and HYPE with BTC as reference-only and export reproducible events/coverage metadata.
- [x] 4. Add a restart-safe Binance signal-only coordinator and Core V2.1 Telegram messages.
  - [x] Separate M15 evaluation triggers from Alt H1 and BTC H1/H4 dependencies.
  - [x] Add chronological catch-up, gap/staleness checks, persisted per-symbol state, event deduplication, and a durable notification outbox.
  - [x] Bootstrap silently and expose readiness; never place exchange orders.
- [x] 5. Acquire and validate the remaining Binance Futures M15 history required by the approved universe.
  - [x] Download only fully closed candles through a resumable/reconciling path.
  - [x] Validate schema, cadence, gaps, duplicates, coverage, and instrument/venue identity.
- [x] 6. Add Hyperliquid PUMP historical/live market data and venue-aware routing.
  - [x] Add public market-data access that does not require wallet credentials.
  - [x] Route by `(venue, instrument, timeframe)` and integrate PUMP without treating BTC as a trade candidate.
  - [x] Validate mixed-venue history and signal-only runtime behavior.
- [x] 7. Run cross-cutting verification and update all affected documentation.
  - [x] Run focused tests, full baseline suite, replay determinism checks, and offline runtime integration tests.
  - [x] Document setup, strategy, data-source, backtest, signal runtime, persistence, operations, and known limits.
- [x] 8. Write an implementation-ready specification for the BTC RSI cross Telegram alert.
  - [x] Lock M5/M15 fresh-cross behavior and the strict H4 bullish gate.
  - [x] Define SignalRunner integration, bootstrap suppression, deduplication, configuration, and Telegram behavior.
  - [x] Define file-level deliverables, regression tests, verification commands, acceptance criteria, and rollback.
  - [x] Add a copy-paste execution prompt that directs another AI agent to implement and verify the full specification.

<!-- Example:
- [x] Implement feature X
- [ ] Write tests for feature X
- [ ] Update docs for feature X
-->

## Review

- Scope explicitly excludes automated order placement. Reference Entry/SL/TP values are advisory and auditable signal levels only.
- Authoritative V2.1 source: the reviewer-approved Core V2 Clean Updated packet supplied on 2026-08-20. Its delta from V2 is strict BTC H4 bullish alignment: `RSI21 > RSI_EMA9 > RSI_WMA45`.
- Baseline (before V2 code): Python 3.13.12, pytest 9.0.2, `881 passed, 12 skipped, 45 warnings` in 14.92 seconds.
- Final Core V2.1 seven-module verification: `161 passed` in 67.52 seconds. The full 25-candidate × 5,000-M15 bootstrap clears its `<30s` measured bootstrap gate and matches the reference/restart state and database evidence.
- Final repository verification in the selected Conda `rsi` interpreter: `1042 passed, 12 skipped, 58 warnings` in 74.77 seconds. Ruff is clean across all Core V2.1 code/tests.
- The locked feature anchor is `2026-06-29T11:15:00Z`. An explicit versioned migration is required to change it or any recursive-indicator seed convention.
- Full replay evidence: all 25 candidates plus BTC, 125,000 ledger rows, 98,550 evaluated, 26,450 `NOT_READY`, and 477 public lifecycle events over the common anchored window. This is a decision audit, not a PnL backtest.
- An independent rerun reproduced the replay CSV, JSONL, and metadata byte-for-byte (SHA-256 `9c477eb6…`, `21b5e51f…`, and `54e37619…`), and both acquisition manifests verified all 26 source hashes against the locked anchor.
- The standalone runtime uses public Binance/Hyperliquid data, canonical PUMP cold seeding, authoritative venue clocks, exact-tail fail-closed polling, optimized/precomputed bootstrap, durable SQLite state/audit, and an at-least-once leased Telegram outbox.
- No Core V2.1 component currently places or manages orders, models fills/fees/slippage, tracks positions, or calculates PnL/win rate. Those claims require the separate future execution implementation.
- BTC RSI cross alert specification created at `docs/07_trading_strategies/btc-rsi-cross-alert-spec.md`; this task produced the specification only and did not implement or activate the feature.
- Copy-paste implementation prompt created at `docs/07_trading_strategies/btc-rsi-cross-alert-agent-prompt.md`.

<!-- Add review notes, test results, and verification outcomes here after completing tasks. -->
