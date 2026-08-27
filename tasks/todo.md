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
- [x] Confirm the final PR checks pass.

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
- GitHub Actions run `32879002023` passed all nine jobs on pushed head
  `3394b00`, including Architecture Lint, Type Check, and Tests + Coverage.

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
      maximal contiguous suffix (67 trigger / 21 H4 readiness as superseded by the
      H4 price-EMA gate), live-H4 observation set,
      SHA-256 event id `btc-rsi-cross-v1|BTC/USDT|tf|UTC close`
- [x] Implement deterministic HTML-safe formatter (`formatter.py`)
- [x] Implement queue-backed worker (`worker.py`): bootstrap gate (pre-ready discard +
      per-TF REST watermark + history-ready instant), point-in-time evaluation via defensive
      `get_dataframe()` copies, single H4 settle/retry on a `threading.Condition`
      (synchronous H4 confirmation never queued), per-TF cursor + emitted-id dedupe
      (no wall-clock cooldown; later extended with an M5 candle-close cooldown),
      consecutive-failure budget with requeue-ahead + one debug
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

### Production rollout — BTC RSI cross alert

- [ ] Verify active BTC alert configuration and release diff
- [ ] Run local config and safety checks
- [ ] Commit and push configuration to `mua-tren-the-nang`
- [ ] Tag and push the release for production promotion
- [ ] Verify GitHub Deploy and VPS `rsi-bot` health

---

### Split BTC RSI Cross Alert Timeframe Checkers (2026-08-27)

- [x] Add a dedicated `m5_checker.py` entry point for 5-minute candle preparation and evaluation.
- [x] Add a dedicated `m15_checker.py` entry point for 15-minute candle preparation and evaluation.
- [x] Dispatch worker preparation and decisions through the timeframe-specific checker.
- [x] Add focused tests proving timeframe isolation, parity, and worker dispatch behavior.
- [x] Update the BTC RSI cross alert specification, strategy reference, signal-bot flow, and testing documentation.
- [x] Run focused tests, full regression tests, Ruff, compilation, focused mypy, and `git diff --check`.

## Review — Split BTC RSI Cross Alert Timeframe Checkers

Implemented explicit M5/M15 entry points while retaining one shared financial
algorithm in `evaluator.py`. Each checker locks its preparation timeframe and
rejects a prepared input from the other timeframe. Worker preparation and
decision dispatch now select the matching checker.

Verification used Codex Python 3.12.13 with the repository virtualenv's
site-packages because the documented Conda `rsi` environment is absent and the
checked-in `venv` points to a removed Python installation.

| Check | Result |
|---|---|
| New checker + evaluator/preparation/worker tests | **86 passed** |
| Full BTC RSI cross focused suite (10 modules) | **180 passed** |
| Full repository suite | **1056 passed, 12 skipped, 32 warnings** |
| Ruff (`app tests scripts`) | **All checks passed** |
| Compileall (`app tests`) | exit 0 |
| Focused mypy (`app/.../btc_rsi_cross_alert`) | **Success: 10 source files** |
| `git diff --check` | clean; Git emitted only existing LF→CRLF checkout warnings |

Repository-wide mypy reached all 201 source files but reports four pre-existing
Windows-only `fcntl.flock`/`LOCK_EX`/`LOCK_UN` attribute errors in
`app/backtest/data/inline_download.py`; the two modified BTC packages pass
focused mypy with no issues.

---

### Simplify BTC RSI Cross H4 Gate (2026-08-27)

- [x] Confirm EMA9 and WMA45 are calculated from RSI21 on H4.
- [x] Change the H4 gate from `RSI21 > EMA9 > WMA45` to `EMA9 > WMA45`.
- [x] Add evaluator coverage proving RSI21 position no longer affects the H4 gate.
- [x] Update the authoritative spec, architecture/data-flow docs, strategy reference, agent prompt, and test matrix.
- [x] Run focused and full regression verification.

## Review — Simplify BTC RSI Cross H4 Gate

Confirmed in `evaluator._bundle_points()` that H4 `rsi_ema9` and `rsi_wma45`
are computed by applying EMA(9) and WMA(45) to the Wilder RSI(21) series. The
decision gate checked only `h4.rsi_ema9 > h4.rsi_wma45` at that revision. This
historical behavior is superseded by the later H4 close > EMA21(price) gate.

| Check | Result |
|---|---|
| Full BTC RSI cross focused suite (10 modules) | **181 passed** |
| Full repository suite | **1057 passed, 12 skipped, 32 warnings** |
| Ruff (`app tests scripts`) | **All checks passed** |
| Compileall (`app tests`) | exit 0 |
| Focused mypy (both BTC RSI cross packages) | **Success: 10 source files** |
| `git diff --check` | clean; Git emitted only LF→CRLF checkout warnings |

---

### Replace BTC RSI Cross H4 RSI Gate with Price EMA21 Gate (2026-08-27)

- [x] Replace the shared H4 `EMA9(RSI21) > WMA45(RSI21)` gate with strict H4 close > EMA21(price).
- [x] Remove H4 RSI-bundle fields and calculations from the alert decision input and Telegram message.
- [x] Reduce H4 preparation readiness to the 21 contiguous closed candles required by price EMA21.
- [x] Update M5/M15 evaluator, worker reason codes, boundary/preparation/formatter/integration tests.
- [x] Update authoritative strategy, architecture, data-flow, agent-prompt, and testing documentation.
- [x] Run focused and full regression verification, Ruff, compileall, mypy, and diff checks.

## Review — Replace BTC RSI Cross H4 RSI Gate with Price EMA21 Gate

Both M5 and M15 now require the exact selected fully closed H4 candle to have
`close > EMA21(price)`. Equality and a close below EMA21 fail with
`H4_CLOSE_NOT_ABOVE_EMA21`. H4 preparation no longer computes RSI21,
EMA9(RSI21), or WMA45(RSI21); it needs 21 contiguous H4 closes, calculates
EMA21 over the full point-in-time suffix, and passes the H4 close plus EMA21
into the immutable decision input. Telegram now displays those two H4 price
values instead of an H4 RSI bundle.

| Check | Result |
|---|---|
| Full BTC RSI cross focused suite (10 modules) | **191 passed** |
| Full repository suite | **1067 passed, 12 skipped, 32 warnings** |
| Ruff (`app tests scripts`) | **All checks passed** |
| Compileall (`app tests`) | exit 0 |
| Focused mypy (both BTC RSI cross packages) | **Success: 10 source files** |
| `git diff --check` | clean; Git emitted only LF→CRLF checkout warnings |

---

### Add 15-Minute M5 Alert Cooldown (2026-08-27)

- [x] Add a 15-minute cooldown based on the last successfully emitted M5 candle close.
- [x] Suppress qualifying M5 closes before `last_alert_close + 15m`; allow equality at 15 minutes.
- [x] Keep M15 behavior independent and without cooldown.
- [x] Add worker boundary tests and observable cooldown logging/state.
- [x] Update strategy, architecture, data-flow, and testing documentation.
- [x] Run focused/full tests and all static verification.

## Review — Add 15-Minute M5 Alert Cooldown

The worker now stores the close time of the last successfully emitted M5
alert. A new qualifying M5 decision is suppressed while its close is earlier
than `last_m5_alert_close + 15 minutes`; equality is allowed. Suppressed events
advance the M5 evaluation cursor but do not enter emitted-event dedupe and do
not restart the cooldown. M15 never reads this state and remains cooldown-free.

| Check | Result |
|---|---|
| Full BTC RSI cross focused suite (10 modules) | **192 passed** |
| Full repository suite | **1068 passed, 12 skipped, 32 warnings** |
| Ruff (`app tests scripts`) | **All checks passed** |
| Compileall (`app tests`) | exit 0 |
| Focused mypy (both BTC RSI cross packages) | **Success: 10 source files** |
| `git diff --check` | clean; Git emitted only LF→CRLF checkout warnings |

---

### Add Mandatory M15 Price EMA21 Filter (2026-08-27)

- [x] Confirm the existing M15 path already enforces H4 close > H4 EMA21(price).
- [x] Require strict M15 close > M15 EMA21(price) after the shared cross/H4 decision passes.
- [x] Add an explicit M15 price rejection reason and export it.
- [x] Add equality/below boundary tests while preserving M5-only filter isolation.
- [x] Update authoritative strategy, architecture, data-flow, agent-prompt, and testing docs.
- [x] Run focused/full regression tests and all static verification.

## Review — Add Mandatory M15 Price EMA21 Filter

Confirmed that `m15_checker.py` already delegates fresh-cross and strict H4
close > H4 EMA21(price) evaluation to the shared evaluator. It now additionally
requires the closed M15 candle price to be strictly above M15 EMA21(price)
after those shared conditions pass. Equality or a lower close returns
`M15_CLOSE_NOT_ABOVE_EMA21`. M5 behavior and the two M5-only RSI filters are
unchanged.

| Check | Result |
|---|---|
| Full BTC RSI cross focused suite (10 modules) | **194 passed** |
| Full repository suite | **1070 passed, 12 skipped, 32 warnings** |
| Ruff (`app tests scripts`) | **All checks passed** |
| Compileall (`app tests`) | exit 0 |
| Focused mypy (both BTC RSI cross packages) | **Success: 10 source files** |
| `git diff --check` | clean; Git emitted only LF→CRLF checkout warnings |

---

### Replace M5 Fresh Cross with Bullish Alignment (2026-08-27)

- [x] Replace the M5 fresh-cross requirement with strict `RSI21 > EMA9 > WMA45`.
- [x] Preserve the H4 gate and all three mandatory M5-only filters.
- [x] Keep M15 fresh-cross behavior unchanged.
- [x] Add tests proving M5 can alert without a new cross and rejects alignment equality.
- [x] Update M5 decision/message semantics and all affected documentation.
- [x] Run focused and full regression verification.

## Review — Replace M5 Fresh Cross with Bullish Alignment

M5 now evaluates the current closed candle independently using strict
`RSI21 > EMA9 > WMA45`, followed by the H4 gate, spread>2, WMA45>45, and
close>EMA21(price). It never checks the previous M5 point. M15 continues to
delegate to the unchanged shared fresh-cross evaluator. At that revision M5
had no cooldown; this is superseded by the later fixed 15-minute M5 cooldown.
Duplicate callbacks for the same candle remain suppressed by event identity.

The M5 Telegram title is now `BTC RSI BULLISH ALIGNMENT`; M15 retains
`BTC RSI BULLISH CROSS`.

| Check | Result |
|---|---|
| Full BTC RSI cross focused suite (10 modules) | **192 passed** |
| Full repository suite | **1068 passed, 12 skipped, 32 warnings** |
| Ruff (`app tests scripts`) | **All checks passed** |
| Compileall (`app tests`) | exit 0 |
| Focused mypy (both BTC RSI cross packages) | **Success: 10 source files** |
| `git diff --check` | clean; Git emitted only LF→CRLF checkout warnings |

---

### Add Mandatory M5-Only BTC RSI Cross Filters (2026-08-27)

- [x] Add trigger price EMA21 to the point-in-time prepared input.
- [x] Require current M5 EMA9(RSI21) − WMA45(RSI21) > 2.
- [x] Require current M5 WMA45(RSI21) > 45.
- [x] Require current M5 BTC close > EMA21(price).
- [x] Keep `m15_checker.py` decision behavior unchanged.
- [x] Add boundary tests, documentation, and full verification evidence.

## Review — Add Mandatory M5-Only BTC RSI Cross Filters

Implemented all three strict filters in `m5_checker.py` after the shared fresh
cross and H4 gate pass. Equality fails at every boundary. M15 continues to
return the shared evaluator decision without applying any M5-only filter.
Trigger price EMA21 is computed over the same maximal contiguous point-in-time
close suffix as the RSI bundle.

| Check | Result |
|---|---|
| Full BTC RSI cross focused suite (10 modules) | **189 passed** |
| Full repository suite | **1065 passed, 12 skipped, 32 warnings** |
| Ruff (`app tests scripts`) | **All checks passed** |
| Compileall (`app tests`) | exit 0 |
| Focused mypy (both BTC RSI cross packages) | **Success: 10 source files** |
| `git diff --check` | clean; Git emitted only LF→CRLF checkout warnings |

---

### Signal-mode Telegram topic listing command

- [x] Add `/topics` to display configured strategy/topic names and IDs.
- [x] Register the command for ordinary and alert-only signal configurations.
- [x] Add focused command and entry-point regression tests.
- [x] Update Telegram and signal-bot documentation.
- [ ] Run focused/full tests and static verification.

## Review — Signal-mode Telegram topic listing command

`/topics` is registered through the existing signal-mode runtime callback path.
It lists every configured strategy entry (including inactive entries) plus the
debug topic, and escapes labels before wrapping the response in Telegram HTML
`<pre>` markup. Alert-only signal mode receives `/topics` but not the
trade-like `/test_signal` command.

| Check | Result |
|---|---|
| Focused pytest suite | **Not run** — `pytest` is unavailable in the system Python, fallback `tele` environment, and bundled desktop Python |
| Isolated `/topics` handler smoke | **Passed** — active/inactive/debug output and HTML escaping |
| Topic-entry builder smoke | **Passed** — active/inactive/debug ordering and IDs |
| Compilation | **Passed** — `python -m compileall -q app tests main.py` |
| Whitespace | **Passed** — `git diff --check` (only existing LF→CRLF warnings) |

---

### Production release `v1.2.3`

- [x] Add release notes for `/topics`.
- [x] Commit the intended source, tests, docs, and release metadata.
- [x] Push `mua-tren-the-nang` and confirm source-branch CI (`33089386050` passed).
- [x] Push `v1.2.3` to trigger the production workflow.
- [x] Confirm production promotion and VPS health handoff (`33090032939`; GitHub deployment success).

---

## BTC RSI alert per-timeframe Telegram topics

- [x] Route M5 BTC alerts to topic `1147`.
- [x] Route M15 BTC alerts to topic `1003`.
- [x] Keep the ordinary `rsi_no_retest` strategy disabled.
- [x] Update `/topics`, startup output, tests, and strategy documentation.
- [ ] Run CI and deploy the verified configuration.
