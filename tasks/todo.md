# Task Tracker

> Current work items. Update as you go — mark items complete, add new ones as they emerge.

## Current Tasks

### PR #148 CI remediation

- [x] Inspect the live PR head and all status checks.
- [x] Reproduce and isolate the Architecture Lint and mypy failures.
- [x] Split the two oversized modules without changing runtime behavior.
- [x] Correct the seven reported type-check errors.
- [x] Run focused and CI-equivalent validation.
- [x] Commit and push the fixes to the PR branch.
- [ ] Confirm the final PR checks pass.

#### Review

- Live PR root causes: two Python files exceeded the 400-line architecture
  limit, and mypy reported one unsafe numeric conversion plus six loop-variable
  type collisions in `SignalRunner`.
- Split the Core V2.1 models behind compatibility exports and extracted focused
  alert-worker helpers; no signal rules, runtime ordering, or public imports changed.
- Related integration suite: 209 passed. Linux-targeted mypy, Bandit, secret
  audit, circular imports, changed-file Ruff, compilation, architecture size/
  class/helper checks, and `git diff --check` pass locally.
- The repository-wide Windows coverage run was stopped after a CPU-bound
  backtest remained at 27%; GitHub's Linux coverage job will provide the final
  required full-suite result after push.

### BTC RSI Cross Alert (`btc_rsi_cross_alert`) — branch `codex/btc-rsi-cross-alert`

Spec: `docs/07_trading_strategies/btc-rsi-cross-alert-spec.md` (authoritative contract)

Environment recorded: Conda env `rsi` — **Python 3.13.12**, pandas 3.0.2, structlog 25.5.0,
pytest 9.0.2. Baseline before changes: focused existing tests
(`test_stream_manager_multi_tf`, `test_signal_runner`, `test_signal_runner_integration`,
`test_main_signal_mode`) → **38 passed**.

- [x] Read AGENTS.md, docs/agent-workflow.md, docs/INDEX.md, spec §1–20, docs/workflows/add-strategy.md
- [x] Inspect strategy_config.py, runner.py, strategy_worker.py, stream_manager.py, multiplexer.py,
      normalizer.py, notification path, telegram_bot.py (HTML parse_mode), constants.py, tests
- [x] Record conda rsi versions + focused baseline (38 passed)
- [x] Resolve Core V2.1 dependency: package absent on this branch → user approved **verbatim copy**
      of `app/trading/strategy/core_v2_1/` (6 files) + `tests/test_core_v2_1_indicators.py` +
      `tests/test_core_v2_1_config_models.py` from commit 6b287f8 (33 tests pass; index blobs
      byte-identical to source branch — zero drift)
- [x] Implement strict typed config + cross-component topic validation
      (`app/signal/btc_rsi_cross_alert/config.py`): locked symbol/timeframes/periods/settle,
      integer-strict periods, topic uniqueness across ordinary + BTC + debug, disabled entries
      reserve nothing
- [x] Implement pure models + preparation/evaluator + deterministic event identity
      (`app/trading/strategy/btc_rsi_cross_alert/{models,evaluator,__init__}.py`): exact §10
      reasons, UTC+7 naive-index normalization advanced exactly once, point-in-time slicing,
      maximal contiguous suffix (67 trigger / 66 H4 readiness), live-H4 observation set,
      SHA-256 event id `btc-rsi-cross-v1|BTC/USDT|tf|UTC close`
- [x] Implement deterministic HTML-safe formatter (`formatter.py`)
- [x] Implement queue-backed worker (`worker.py`): bootstrap gate (pre-ready discard +
      per-TF REST watermark + history-ready instant), point-in-time evaluation via defensive
      `get_dataframe()` copies, single H4 settle/retry on a `threading.Condition`
      (synchronous H4 confirmation never queued), per-TF cursor + emitted-id dedupe
      (no wall-clock cooldown), consecutive-failure budget with requeue-ahead + one debug
      notification + worker-only termination, bounded idempotent `request_stop()`
- [x] `BinanceStreamManager` optional `history_complete_callback`: fetch all → callback once
      → WS loop; exceptions isolated; default None backward compatible
- [x] SignalRunner integration: aggregate resolver, target union incl. (BTC/USDT, 5m/15m/4h),
      alert-only startup, `_alert_workers`/`_alert_threads`, `alert_components` property,
      ordinary-only `strategies` (so `/test_signal` stays VP-scoped), shutdown joins both groups
- [x] main.py startup text renders `btc_rsi_cross_alert — topic N · BTC/USDT · 5m,15m · H4 filter`
- [x] config.yaml locked component entry checked in with `active: false` (topic 1007)
- [x] Focused test modules: `_config` (26) / `_preparation` (24) / `_evaluator` (18) /
      `_formatter` (9) / `_worker` (21); shared fixtures in `tests/btc_alert_fixtures.py`
- [x] Extended tests: stream manager (+4 history-hook), signal runner (+8 component cases),
      runner integration (+1 end-to-end qualifying candle → BTC topic, empty VP store),
      main signal mode (+2 startup-text / no-fake-card)
- [x] Docs updated: system-overview.md, configuration.md, live-data-flow.md, signal-bot.md,
      strategy-reference.md, notifications.md, testing-strategy.md, INDEX.md routing row

## Review

### Verification evidence (spec §17, Conda env `rsi`, Python 3.13.12)

| Check | Command | Result |
|---|---|---|
| Interpreter | `conda run -n rsi python --version` | Python 3.13.12 |
| Focused suite | pytest of the 9 spec-named files, `-q` | **170 passed** |
| Full suite | `pytest tests -q` | **1046 passed, 12 skipped** (skips pre-existing API-key-gated), 0 failed |
| Ruff | `ruff check app tests` | **All checks passed!** (18 initial findings fixed: import order, UP017 datetime.UTC, zip strict, B007/B017, unused imports; no logic changes) |
| Compilation | `compileall -q app tests` | exit 0 |
| Import smoke | `python -c "from app.signal.btc_rsi_cross_alert.config import resolve_btc_rsi_cross_alert_config; ..."` | `btc_rsi_cross_alert import OK` |
| Whitespace | `git diff --check` | clean (exit 0) |
| Spec present | `Test-Path docs\07_trading_strategies\btc-rsi-cross-alert-spec.md` | True |
| INDEX routing | `Select-String docs\INDEX.md -Pattern "btc-rsi-cross-alert-spec.md"` | line 19 match |
| Config smoke ×3 | mocked-stream SignalRunner instantiation | PASS: ordinary+btc (1 worker + 1 alert worker, union stream), btc-only (0+1, stream started), all-disabled (clean no-op, stream not constructed) |
| Checked-in config | resolver against real `config.yaml` | mode=signal preserved, `rsi_no_retest` active, BTC entry disabled (topic not reserved) |

### Pre-existing issues (not introduced by this feature)

* structlog 25.x emits a `UserWarning` ("Remove format_exc_info …") when the app's logging
  chain logs exceptions — surfaced by worker-error-path tests; environmental, unchanged.
* 12 full-suite skips are pre-existing (API-key/integration gated).
* Baseline focused run before any change was already green (38 passed).

### Boundary review (final diff audit)

* Core V2.1 files verbatim (index blob hashes identical to commit 6b287f8); primitives imported,
  never modified; no Core V2.1 behavior touched.
* No secrets anywhere in the diff; token/key handling untouched.
* No order paths, exchange order APIs, virtual positions, SL/TP or exit-monitor references inside
  either `btc_rsi_cross_alert` package (grep-audited).
* Component absent from `app/trading/strategy/loader.py`, DB seed and UI strategy list.
* No live Telegram send, deployment, commit or push performed.

### Remaining v1 limitations (documented in spec §20, mirrored in docs)

* Indicator seed = current REST bootstrap window (no permanent anchor like Core V2.1).
* In-memory dedupe/state; restart re-bootstraps silently; delivery is best-effort async Telegram
  (no durable outbox). Exactly-once delivery is NOT promised.
* Binance BTC/USDT only; fixed M5/M15/H4 rule set; no short alerts.
