# Copy-Paste Agent Prompt — BTC RSI Cross Alert

Copy everything inside the block below into the implementation agent's task.

```text
You are working in the existing rsi_bot repository. Implement the BTC RSI
Cross Alert feature completely according to:

docs/07_trading_strategies/btc-rsi-cross-alert-spec.md

Treat that file as the authoritative feature contract. Read it completely
before changing any file; do not skim or omit later sections.

Mandatory reading order:

1. AGENTS.md
2. docs/agent-workflow.md
3. docs/INDEX.md
4. docs/07_trading_strategies/btc-rsi-cross-alert-spec.md
5. docs/workflows/add-strategy.md
6. The existing source and tests named in the specification's file-level map

Objective:

Add a BTC-only, Telegram-only signal component to the existing SignalRunner.
On M15, require a fresh EMA9(RSI21) cross above WMA45(RSI21). On M5, do not
require a fresh cross; require current `RSI21 > EMA9 > WMA45`. Both require the
exact latest fully closed native H1 and H4 candles to close strictly above their
price EMA21 values. Do not calculate an RSI bundle for the context gates. For
M5 only, also require RSI21 < 60, EMA9(RSI21) − WMA45(RSI21) >= 2, and
WMA45(RSI21) > 45. Require both M5 close > M5 EMA21(price) and M15 close >
M15 EMA21(price); equality fails. Do not apply the M5-only RSI filters to M15.

Non-negotiable boundaries:

- Extend the existing repository and signal runtime; do not create a separate
  repository or unrelated bot.
- Implement pure domain models/evaluation under
  app/trading/strategy/btc_rsi_cross_alert/ and runtime/configuration under
  app/signal/btc_rsi_cross_alert/.
- Do not register this component in app/trading/strategy/loader.py or expose it
  to the backtest UI/database seed.
- Do not change the behavior, indicator contract, anchor, persistence, or
  runtime of Core V2.1.
- Do not repurpose the existing rsi_alert strategy.
- Do not place orders, create virtual positions, calculate SL/TP, or make PnL
  or profitability claims.
- Use only fully closed candles and point-in-time H1/H4 context. Missing, stale,
  forming, duplicated, backward, non-finite, or recently gapped data must fail
  closed. An older gap is allowed only when the authoritative specification's
  maximal contiguous suffix remains long enough for exact readiness.
- Suppress every historical bootstrap alert. The first eligible public signal
  is a subsequent live M5/M15 candle close.
- Keep M5 and M15 independent and deduplicate by deterministic event identity.
  Apply the fixed one-hour cooldown only to emitted M5 alerts, measured by
   candle close time rather than the process wall clock; M15 has no cooldown.
- Preserve all existing single-timeframe SignalRunner behavior and tests.
- Keep /test_signal trade-like fake cards scoped to ordinary strategies; the
  BTC alert must never fabricate a virtual position.
- Never hard-code or display Telegram tokens, API keys, or other secrets.

Working rules:

- The working tree may already contain user changes. Inspect git status first,
  preserve unrelated edits, and do not reset, discard, overwrite, or reformat
  files outside this feature's scope.
- Use the existing Conda environment named rsi. Record its actual Python and
  dependency versions before considering any environment change. Do not create
  a replacement environment unless the existing one is genuinely unusable and
  the user approves it.
- Write the implementation checklist to tasks/todo.md and update it as work
  progresses. Do not erase the existing task history.
- Follow the repository's documentation-maintenance matrix for every code path
  changed.
- Use structlog; add no production print statements.
- Maintain typed, deterministic, testable boundaries. The evaluator must be
  pure and independent of clocks, threads, network, filesystem, Telegram, and
  mutable global state.
- Reuse the existing tested rsi_wilder, ema, and wma primitives exactly as the
  specification directs. Do not change those Core V2.1 functions.
- Do not stop after analysis, planning, scaffolding, or writing tests. Implement
  every required slice, fix failures, update documentation, and verify the
  complete result.
- Do not commit, push, deploy, alter remote infrastructure, or send a real
  Telegram message unless the user separately authorizes that action.

Required execution sequence:

1. Inspect the current config resolver, SignalRunner, StrategyWorker,
   TimeframeMultiplexer, BinanceStreamManager, notification path, timestamp
   normalization, indicator primitives, and relevant tests.
2. Record a focused baseline and note any pre-existing failures separately.
3. Implement strict typed configuration and cross-component Telegram topic
   validation.
4. Implement the pure models, indicator preparation, decision evaluator, and
   deterministic event identity.
5. Implement the queue-backed alert worker, point-in-time slicing, H1/H4 boundary
   settle/retry, bootstrap gate, per-timeframe deduplication, failure budget,
   and bounded shutdown.
6. Integrate the worker into SignalRunner, including alert-only startup, target
   union, history-complete activation, accurate startup text, and backward
   compatibility for ordinary strategies.
7. Add deterministic unit and integration tests covering every case listed in
   section 16 of the specification.
8. Update every documentation file listed in section 15.
9. Run all verification commands in section 17 using Conda rsi. Fix all
   feature-related failures rather than weakening or deleting tests.
10. Review the final diff for accidental scope expansion, secret exposure,
    order/virtual-position paths, Core V2.1 drift, and documentation drift.

Acceptance standard:

All criteria in section 18 of the specification must be demonstrably true.
Do not call the work complete if focused tests, the full suite, Ruff,
compilation, configuration smoke checks, or documentation validation fail.

Final response requirements:

- Lead with whether implementation is complete.
- Summarize the delivered behavior and architecture.
- List the important files changed.
- Report exact focused-test, full-suite, Ruff, compilation, and smoke-check
  results.
- Clearly separate pre-existing failures from regressions, if any.
- State that no live Telegram send, deployment, commit, or push was performed
  unless separately authorized.
- Link the implementation specification and the principal implementation
  files using absolute local paths when the client supports them.
- Report any remaining limitation honestly; never claim exactly-once delivery,
  automated execution, or profitability.
```
