# Task Tracker

> Current work items. Update as you go — mark items complete, add new ones as they emerge.

## ⚪ ACTIVE — BTC Signal Review TP/SL outcome capture (2026-09-02)

- [x] Add fixed signal-candle entry with adjacent TP/SL inputs to the Signal Review UI.
- [x] Evaluate the signal-timeframe candles for the first TP/SL touch and elapsed time,
      without deriving a 1R win/loss classification.
- [x] Persist the configured levels and objective first-touch result without changing
      the separate human quality/outcome labels.
- [x] Allow TP/SL to be saved before quality selection; defer first-touch
      evaluation until quality unlocks the future candles.
- [x] Keep the Human review section above the chart and TP/SL work area.
- [x] Add focused tests, regenerate schema/database docs, and run frontend/backend checks.

### Review

The Signal Review detail view starts with the Human review section, followed by
a chart-left, TP/SL-right work area. The signal candle close is the read-only
entry; both positive long-side levels must be entered together before quality
selection. Saving the plan persists it while future candles remain hidden.
Selecting a quality label unlocks the future, then scans later native M5/M15
candles and stores the first-touch reason, exit candle, elapsed minutes,
evaluation warning, and evaluation timestamp.
TP-first, SL-first, open, no-data, and same-candle ambiguity are explicit
states. The automatic result never calculates 1R/PnL and never changes the
manual quality or WIN/LOSS/SKIP fields.

| Check | Result |
|---|---|
| Focused replay/review/database tests | **24 passed** |
| Full repository tests | **1297 passed, 12 skipped, 49 warnings** |
| Feature-file Ruff | **Passed**; repository-wide run still reports four pre-existing generic-type errors in `app/signal/core_v2_1` and `app/trading/strategy/utils` |
| Frontend production build | **Passed** (`tsc --noEmit` + Vite) |
| Live browser layout and interaction check | **Passed** at 1850px and 1280px; chart left, TP/SL right, inputs enabled before quality selection, no console errors |
| Python compilation | **Passed** |
| Markdown links | **133 files passed** |
| `git diff --check` | **Passed**; only existing Windows LF→CRLF warnings |

## ✅ COMPLETE — Deploy-bot crash fix and production rollout (2026-09-02)

> Implementation, regression tests, documentation, release promotion, and VPS
> self-heal are complete. The detailed
> handover is intentionally kept local because it contains operational access
> details and is not part of the tracked release.

- [x] Diagnose why v1.2.8 never reached the VPS: `check_deploy.sh` `write_state` missing `import tempfile` → NameError kills the script between the production checkout and `deploy.sh`, every minute, silently (traceback only in journald).
- [x] Fix `write_state` import + add EXIT trap and stderr-to-log redirection in `deploy/check_deploy.sh` (uncommitted).
- [x] `tests/test_deploy_scripts.py` functional regression tests (embedded Python helpers execute for real; cross-platform Bash shim fixed).
- [x] Finish tests → docs (common-issues row 19, lessons) → commit `cc33429`; the first `v1.2.9` tag remains immutable after its documentation-gate failure.
- [x] Correct the local-only handover link in commit `e7b1166`, tag `v1.2.10`, and pass the full release workflow (`33589342525`, including production promotion `100120388350`).
- [x] Verify VPS auto-deploy self-heals: the old checker failed once at 06:06:30 while resetting to `v1.2.10`; the repaired checker deployed it at 06:07:35, passed smoke test and health check, and completed at 06:08:14.
- [x] Confirm production health: `/opt/rsi_bot/VERSION`, deploy state, runtime status, checkout, `rsi-bot`, and `check-deploy.timer` all report `v1.2.10` / `e7b1166c15ab25c54cd1846c9e5c22928f03b3ee` and running. The alert worker initialized and a Telegram startup message was logged as sent; no qualifying natural M5/M15 signal occurred during the bounded verification window, so no synthetic alert was sent.

## ✅ COMPLETE — Passwordless VPS SSH access (2026-09-02)

- [x] Reuse the device's existing Ed25519 key; no new private key was generated.
- [x] Install only its public key for the VPS `cut_lap` account, idempotently.
- [x] Verify OpenSSH authentication with `BatchMode=yes` and password authentication disabled; the connection used `publickey` and both production services remained active.
- [x] Leave password login unchanged as a fallback; no private key, password, or other credential is stored in this repository.

## ⚪ ACTIVE — Telegram forum-topic inventory and failure visibility (2026-09-02)

- [x] Distinguish configured strategy routes from actual Telegram forum topics.
- [x] Record observed forum topic IDs/names from incoming Telegram updates and
      show observed topics with no configuration mapping in `/topics`.
- [x] Make failed Telegram sends, notification queue drops, and worker
      exceptions visible with a rate-limited fallback developer alert plus
      structured logs.
- [x] Add regression tests for topic discovery, fallback delivery, queue/drop
      reporting, and strategy failure notification.
- [x] Update notification and operations documentation.
- [x] Run focused validation and review release/deployment status: 172 focused
      signal/notification tests passed; architecture, Markdown-link, Ruff,
      mypy, compile, and diff checks passed.
- [x] Release/push/deploy this change after explicit production approval: v1.2.12
      (`e60dcc7`, GitHub workflow `33612360676`) promoted and picked up by the
      VPS deploy check; `rsi-bot`, the Core V2.1 process, and
      `check-deploy.timer` are running. Live follow-up remains for the
      `rsi_momentum` topic-44 queue overflow observed immediately after restart.

## ⚠ ACTIVE — Switch to Core Long V2 and clarify signal startup status (2026-09-02)

- [x] Identify the newest non-BTC entry as `rsi_momentum` and name it `RSI Momentum` in the operator-facing startup message.
- [x] Clarify the startup count as active configuration components, with M5/M15 routes shown inside the single BTC alert component.
- [x] Disable `rsi_momentum` after the production queue-overflow evidence on topic `44`.
- [x] Keep Core V2.1 active on the verified Long V2 topic `1576`.
- [x] Improve startup output to show active runtime groups, advisory-only execution,
      Core Long V2 scope, and BTC per-timeframe topics without ambiguous counts.
- [x] Run focused/full validation, release, and verify both production workers and topic routing:
      30 focused tests passed; release `v1.2.13` (`4c88e4d`) passed all hosted
      CI gates and production promotion; the VPS restarted `rsi-bot` and
      `rsi-core-v2-1`, and the fresh startup log reports no legacy strategies.

## Telegram alert delivery: HTML entity rejection fix (2026-09-01)

- [x] Diagnose why 12 `btc_rsi_cross_alert_enqueued` produced only 3 channel messages (9 × Telegram 400 "can't parse entities", raw `<` in card text; all 4 M15 alerts lost).
- [x] Escape static `<`/`<=` glyphs in `app/signal/btc_rsi_cross_alert/formatter.py` (dynamic text was already escaped).
- [x] Add plain-text fallback retry on entity rejection in `TelegramBot.send_message` (formatting may degrade, delivery must not).
- [x] Regression tests: `TestHtmlEscaping.test_card_is_html_send_safe` / `test_static_comparison_glyphs_are_escaped`; new `tests/test_telegram_bot_send_fallback.py`.
- [x] Guardrails for future agents: AGENTS.md convention, notifications doc, BTC spec rules, agent-prompt non-negotiable, common-issues row 18, lessons entry.
- [x] Full test suite + arch lint + ruff + mypy + bandit + markdown link check.
- [x] Repair the pre-existing red CI gates that blocked tag promotion (mypy ORM typing, bandit subprocess findings, arch executor layering + 600-line threshold).
- [x] Commit, push `mua-tren-the-nang`, tag `v1.2.8` to trigger the deploy pipeline.

## Dark-theme native select readability (2026-08-30)

- [x] Reproduce the Replay scope popup and inspect its computed browser theme.
- [x] Make native select popups readable in every dark application theme.
- [x] Verify Replay scope, dataset, quality, outcome, and sensitivity selectors.
- [x] Run TypeScript/build, Markdown, and diff checks and create a focused commit.

### Root cause

- The document has the `dark` class, but Tailwind's form-control reset forces
  native selects to `color-scheme: light`.
- Options inherit the application's white text with a transparent background,
  while Windows Chromium paints the light native popup white. Unselected rows
  therefore render as white text on white.

### Review

Dark themes now set native selects to `color-scheme: dark` and give option and
option-group rows explicit theme foreground/background colors. The rule is
scoped to the root `dark` class, so light themes retain their light native
controls and dark text.

The production build passed TypeScript checking and Vite compilation; all 129
Markdown links and `git diff --check` passed. Live browser verification covered
Replay scope, replay dataset, quality, outcome, and Sensitivity metric selects.
Deep Space rendered every popup row with a dark background and light text,
Paper retained a light popup with dark text, the original Deep Space theme was
restored, and the page produced no console warnings or errors.

## Multi-timeframe Signal Review charts and indicators (2026-08-30)

- [x] Audit the chart API, replay-source metadata, signal anchoring, indicator payload, and reviewer store flow.
- [x] Let reviewers switch the selected signal chart between M5, M15, H1, and H4.
- [x] Anchor non-trigger timeframes to the latest fully closed candle at or before the signal time.
- [x] Add price EMA21/EMA200 and RSI21 with EMA9(RSI)/WMA45(RSI) overlays and clear legends.
- [x] Keep future-locking, 2,000-candle extensions, and chart position behavior correct on every timeframe.
- [x] Add API/analysis regression coverage and update frontend, backtest, API, and reviewer documentation.
- [x] Run focused tests, generated-type refresh, TypeScript/build, Markdown/diff checks, and live UI verification.

### Audit findings

- The chart endpoint always selects the signal's own replay source, even though each run records native M5, M15, H1, and H4 source metadata.
- Higher-timeframe candles do not necessarily close exactly at an M5/M15 signal timestamp; the safe point-in-time anchor is the latest native candle closed at or before that timestamp.
- The payload and chart already include EMA21 plus the requested RSI21/EMA9/WMA45 family, but EMA200 is absent and the RSI-derived legend labels are ambiguous.
- Lazy extension currently derives duration from the signal timeframe instead of the chart timeframe, so it must move with the new chart selection state.

### Review

The signal detail chart now switches independently between native M5, M15,
H1, and H4 data without changing the review queue or the signal's stored entry
timeframe. Higher-timeframe views use the latest fully closed native candle at
or before the signal as their point-in-time anchor. Each view keeps the staged
human-review gate and supports the existing 2,000-candle future extensions in
the selected chart timeframe.

The price pane now shows EMA21 and EMA200. The RSI pane shows RSI21 together
with EMA9(RSI) and WMA45(RSI), using separate, explicit legends and stable
colors. Timeframe changes are race-safe, reset only the chart viewport, and
retain the reviewer's quality, outcome, note, and queue position.

Verification passed with 32 replay/reviewer/executor tests, Ruff, Python
compilation, TypeScript type-checking, a production frontend build, all 129
Markdown links, and `git diff --check`. Live API checks loaded all four native
timeframes with the requested indicators and valid point-in-time anchors. The
rebuilt page was exercised across M5, M15, H1, and H4 in the in-app browser
with no console warnings or errors.

## Human-first Signal Review detail redesign (2026-08-30)

- [x] Audit the current rating hierarchy, chart unlock window, and signal navigation.
- [x] Increase the post-quality chart window and each forward extension from 500 to 2,000 candles.
- [x] Move entry-quality and WIN/LOSS/SKIP controls into a prominent sticky decision bar above the chart.
- [x] Add clear two-step reviewer guidance, larger controls, review position, and a stronger next-signal action.
- [x] Add regression coverage and update frontend/backtest/reviewer documentation.
- [x] Run focused tests, TypeScript/build, Markdown/diff checks, and live UI verification.

### Audit findings

- The review controls are the last card in the secondary column, below the Telegram snapshot and structured confirmation, even though rating is the page's primary task.
- The chart unlocks only 500 forward candles, and the frontend loads only 500 more per extension; this is too little room for manual strategy-outcome confirmation.
- `Newer` and `Older` describe chronology rather than the review workflow, and the detail view does not show the reviewer's position in the current queue.
- Quality, outcome, note, and save state are visually grouped as a generic form instead of a staged Entry quality → Future outcome decision.

### Review

The unlocked chart and every forward extension now load up to 2,000 trigger-
timeframe candles, four times the previous window. The chart initially keeps a
readable signal-centered viewport and preserves the reviewer's pan position as
additional candles arrive. The detail page now starts with a desktop-sticky,
two-step human decision surface, keeps all six rating buttons above the chart,
shows queue position and Previous/Next signal actions, and flushes note drafts
before navigation.

Verification passed with 31 replay/reviewer/executor tests, TypeScript type-
checking, a production frontend build, Python compilation, all 129 Markdown
links, and `git diff --check`. The rebuilt bundle was served from
`http://127.0.0.1:8100`, rendered the reviewer-first layout in the in-app
browser with no console warnings/errors, and exposed the expected Human review,
Next signal, and 2,000-candle extension copy. A canonical-M5 benchmark returned
2,000 future candles (2,121 total with context) in 0.905 seconds when source data
was available; the live newest signal correctly showed only the 48 candles that
exist before the current CSV boundary.

## BTC Signal Review flow audit and repair (2026-08-30)

- [x] Reproduce the 75% stall and audit the launcher, run selection, signal list, chart, and review-save flow.
- [x] Replace arbitrary manual dates with a data-aware replay scope derived from the canonical M5/M15/H1/H4 coverage.
- [x] Optimize forward-metric persistence and expose meaningful progress after signal detection.
- [x] Scope the review list to one replay run and resume visible progress for an active run.
- [x] Stop note/outcome saves from unnecessarily reloading the signal list and chart.
- [x] Add backend/frontend regression coverage and update routed product documentation.
- [x] Run focused/broader backend checks, frontend type-check/build, Markdown validation, live API/SSE replay, and served-bundle verification; attempt and isolate unrelated full-suite stalls.

### Audit findings

- The replay reaches 75% after signal detection, then computes forward metrics by rescanning the full source frame for every signal. A two-year run with 1,988 signals remains CPU-bound with no intermediate progress.
- The launcher accepts dates the local canonical CSV set cannot satisfy and does not show the common available range.
- The default signal query omits `replay_run_id`, so repeated replays mix duplicate historical events from multiple datasets.
- Every review save reloads the list and chart; debounced note typing therefore causes repeated chart reconstruction.

### Review

The launcher now reads the aligned canonical coverage, defaults to all usable
data, and offers only bounded recent-period presets. The latest completed run
opens as a review queue filtered to `UNREVIEWED`; reviewers can switch datasets
without mixing runs. Refreshing during a live replay reconnects to the current
executor queue, while interrupted rows are reconciled to failed after restart.

Forward metrics now reuse one timestamp/NumPy source per trigger timeframe and
use binary-search slices. On the canonical two-year dataset, a live run stored
1,988 signals (1,399 M5 and 589 M15) in 10.67 seconds with 25 SSE updates; the
old run remained silent after 75% for roughly ten minutes. Review writes update
local state and reload the chart only when the future-data gate changes; saves
are serialized so labels cannot overwrite a pending note draft.

Validation: 12 focused tests passed, 38 replay/API tests passed, TypeScript
type-check and production build passed, Python compilation passed, Markdown
links passed, `git diff --check` passed, and live availability/range/run/SSE/
run-scoped-list checks passed. The repository-wide suite was attempted but two
unchanged legacy fixtures were isolated as pathological in this environment:
`tests/test_engine_results.py::test_returns_dict` stalls in its module-level
`BacktestEngine.run()`, and `tests/test_indicators.py::TestCompute::test_returns_expected_columns`
stalls in `Indicators.compute()` before its first assertion. In-app browser
control could not start because its local kernel assets failed to initialize;
the newly built bundle was verified through the running server instead.

## Add H1 trend gate and M5 RSI ceiling (2026-08-29)

- [x] Trace the existing BTC alert live/replay contracts and preserve unrelated worktree changes.
- [x] Add native H1 EMA21 context to the BTC alert configuration, preparation, worker, and replay.
- [x] Reject M5 alerts when current RSI21 is 60 or higher.
- [x] Update regression tests, alert cards, replay snapshots, and routed documentation.
- [x] Run compile and diff checks; focused pytest is blocked because the available Python environments lack the project dependencies.

## Current Tasks

### Apply one-hour cooldown to M15 BTC alerts (2026-08-29)

- [x] Add independent M15 cooldown state to the live worker and historical replay.
- [x] Add M15 boundary coverage for suppression through +45m and eligibility at +60m.
- [x] Update replay counters, cooldown telemetry, and BTC strategy documentation.
- [x] Document the native H1 input required by the historical replay command.
- [x] Run compile, Markdown-link, and diff checks; record the local pytest dependency blocker.

#### Review

M15 alerts now use the same fixed one-hour candle-close policy as M5 alerts,
but each timeframe stores and updates its own last-emitted close. Suppressed
M15 decisions do not reset the cooldown or enter event-ID deduplication. The
replay requires a native BTC H1 CSV because the H1 EMA21 gate is point-in-time
and must not be silently synthesized from another timeframe.

### BTC M5/M15 Signal Review Lab (2026-08-28)

- [x] Add purpose-specific replay-run, signal, review, and forward-metric database models.
- [x] Persist deterministic M5/M15 replay snapshots, exact Telegram cards, provenance, and objective observations.
- [x] Add FastAPI replay launcher, SSE status, list/detail/chart/metrics/review endpoints.
- [x] Add the Signal Review workspace with M5/M15 tabs, Good Signals filter, detail navigation, staged chart, and notes.
- [x] Add focused backend/API coverage and regenerate database/OpenAPI TypeScript documentation.
- [x] Add and validate a Windows-friendly human-validation guide for the Signal Review Lab.
- [x] Simplify the reviewer path to one-click launch and plain-language chart review.
- [x] Keep generated UI/build, frontend dependencies, environments, and non-canonical local data out of Git.
- [x] Version the four canonical BTC Signal Review CSV inputs while keeping other downloaded data ignored.
- [x] Run frontend type-check/build, backend focused/full tests, Markdown validation, and final diff review.

#### Review

Implemented the Signal Review Lab as a separate human-labeled alert dataset.
Raw signals remain distinct from simulated trades and PnL: SQLite stores
immutable replay provenance, exact Telegram cards, structured snapshots,
latest quality/outcome review, and trigger-close forward observations. The
chart is locked to the trigger until `GOOD`, `BAD`, or `UNCERTAIN` is saved;
human `WIN`/`LOSS`/`SKIP` remains a separate label. The frontend uses one
M5/M15 workspace with saved Good Signals filtering, full-page detail, synced
price/RSI charts, crosshair/pan/zoom, forward loading, and debounced notes.


### Change BTC M5 alert cooldown to one hour (2026-08-28)

- [x] Update the shared M5 cooldown from 15 minutes to 1 hour.
- [x] Update worker and replay boundary tests for +55m suppression and +60m eligibility.
- [x] Update the current BTC alert, architecture, replay, and testing documentation.
- [x] Run focused tests, static checks, and final diff review.

#### Review

`M5_ALERT_COOLDOWN` now equals one hour and is shared by the live worker and
historical replay. Worker and replay tests cover suppression through +55m and
eligibility at +60m. Targeted files compile, Markdown links pass for all 128
checked files, the direct constant assertion passes, and `git diff --check` is
clean. Focused pytest could not run because the available Python environments
do not contain the project dependencies (`pytest`/`pandas`).

### Repository documentation, CI/CD, and infrastructure review (2026-08-28)

- [x] Read repository workflow, documentation routing, onboarding, and prior lessons.
- [x] Inventory every documentation artifact and validate links, commands, and ownership.
- [x] Audit every CI/CD workflow and local enforcement configuration.
- [x] Implement focused documentation cleanup and consistency improvements.
- [x] Implement focused CI/CD reliability, security, and maintainability improvements.
- [x] Run documentation, workflow, lint, test, and diff validation.
- [x] Record a prioritized infrastructure improvement roadmap and final review evidence.

#### Review

Completed with a repository-wide documentation, CI/CD, and infrastructure review.
The active docs are routed through `docs/INDEX.md`; obsolete root specifications
are archived; generated `ui/build/` output is ignored and removed from the
working tree; CI uses least-privilege permissions, immutable action pins,
exact-ref checks, dependency auditing, coverage, documentation-link checks,
and frontend build validation; pinned pip-audit reports no known runtime
vulnerabilities; deployment scripts fail closed and verify
candidate identity plus rollback health. Local checks are green, including
1,089 tests and 71.74% coverage with Numba JIT disabled for the Windows
functional run, while the JIT-enabled backtest fixture exceeded the local
15-minute CI-equivalent boundary. Hosted GitHub execution, branch protection,
production approvals, and a real VPS rollback still require an external run.

### BTC historical replay — second performance pass

- [x] Benchmark and profile a two-year-scale replay on the current cached implementation.
- [x] Remove measured per-event overhead without changing point-in-time signal behavior.
- [x] Add output-parity and performance-regression coverage for the optimized path.
- [x] Update replay documentation with the final execution model and benchmark result.
- [x] Run focused tests, full tests, Ruff, compilation, architecture lint, and diff checks.

#### Review

- Real 2024-08-28 through 2026-08-28 data: 280,510 candidate candles and
  8,047 confirmed signals completed in 3.87 seconds versus 12.43 seconds
  before this pass (3.2x faster); fixed-generation Markdown was byte-identical.
- Vectorized homogeneous timestamp parsing, source-position/H4 array mapping,
  and NumPy WMA candidate scanning remove repeated hot-loop conversion and
  allocation. The scan is a conservative superset; exact locked WMA arithmetic
  and the existing M5/M15 evaluator remain authoritative for every possible
  signal.
- `tests/test_signal_replay.py`: 14 passed. Related BTC/replay suite: 222 passed.
  Full repository suite: 1,100 passed, 12 skipped. Changed-file Ruff,
  `py_compile`, focused mypy, and `git diff --check` pass.
- Architecture lint reports only the same four pre-existing violations in
  `app/core/constants.py` and `app/core/logging.py`; no changed replay module
  violates its file-size or architecture checks. The documented Markdown-link
  checker is not present on this branch, and this change adds no Markdown links.
- Intel Arc B580 supports oneAPI, but this replay remains CPU-only; at a
  sub-four-second two-year runtime, a GPU backend would add more complexity
  than practical benefit.

### BTC historical replay — split timeframe reports

- [x] Verify the default replay output produces separate M5 and M15 files.
- [x] Preserve the explicit combined `--output` compatibility path.
- [x] Add regression coverage and document the split-file review workflow.

#### Review

- Focused replay suite: 17 passed. Full repository suite: 1,103 passed,
  12 skipped, 58 warnings. Ruff, mypy, compilation, and diff checks pass.

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
- [x] Keep M15 behavior independent of the M5 cooldown state.
- [x] Add worker boundary tests and observable cooldown logging/state.
- [x] Update strategy, architecture, data-flow, and testing documentation.
- [x] Run focused/full tests and all static verification.

## Review — Add 15-Minute M5 Alert Cooldown

The worker now stores the close time of the last successfully emitted M5
alert. A new qualifying M5 decision is suppressed while its close is earlier
than `last_m5_alert_close + 15 minutes`; equality is allowed. Suppressed events
advance the M5 evaluation cursor but do not enter emitted-event dedupe and do
not restart the cooldown. M15 did not read this state in that historical
implementation; it was superseded on 2026-08-29 by the independent one-hour
M15 cooldown recorded above.

This historical 15-minute implementation was superseded on 2026-08-28 by the
one-hour M5 cooldown recorded above.

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
`RSI21 > EMA9 > WMA45`, followed by the H4 gate, spread>=2, WMA45>45, and
close>EMA21(price). It never checks the previous M5 point. M15 continues to
delegate to the unchanged shared fresh-cross evaluator. At that revision M5
had no cooldown; this was superseded first by the fixed 15-minute M5 cooldown
and then by the current one-hour M5 cooldown.
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
- [x] Require current M5 EMA9(RSI21) − WMA45(RSI21) >= 2.
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

---

### BTC RSI alert card verification snapshot (2026-08-27)

- [x] Add the chart candle close timestamp in UTC+7 alongside the timeframe.
- [x] Show trigger-timeframe price EMA21 and all M5/M15 condition values.
- [x] Show previous/current RSI EMA/WMA values needed to verify an M15 cross.
- [x] Add formatter regression coverage and update the authoritative alert spec.

---

## Fix Binance Futures market WebSocket endpoint (2026-08-28)

- [x] Update live kline and simulation aggTrade combined-stream endpoints.
- [x] Add regression coverage for the live multi-timeframe URL.
- [x] Update architecture/data-flow documentation and release notes.
- [ ] Run focused and repository validation.
- [ ] Merge into `mua-tren-the-nang` and promote tag `v1.2.6` through production.

---

### Historical BTC replay warmup and performance (2026-08-28)

- [x] Reproduce the H4 insufficient-contiguous-history messages at the replay window start.
- [x] Skip initial M5/M15 events until trigger and H4 indicator history is ready.
- [x] Precompute indicators once per contiguous segment for long replay performance.
- [x] Add warmup-skip and cached-preparation parity regression coverage.
- [x] Update replay and backtest documentation.
- [x] Run replay-focused tests, full regression tests, Ruff, compilation, and diff checks.

#### Review

The two-year replay previously called the pure preparation path for every
candle, repeatedly recalculating the full historical prefix. The replay now
precomputes RSI21, EMA9/WMA45 of RSI21, and price EMA21 once per contiguous
segment, then reuses the existing M5/M15 decision functions. Initial events
before the 67-row trigger and 21-row H4 minimums are skipped and counted as
warmup rather than logged as repeated not-ready failures.

## BTC signal-only EV study (2026-09-02)

- [x] Build a focused research notebook from the current BTC M5/M15 replay.
- [x] Measure complete-horizon forward return, MFE, and MAE by timeframe.
- [x] Compare alerts with same-timeframe all-candle baselines.
- [x] Add block-bootstrap uncertainty, non-overlapping robustness, monthly
  stability, and explicit cost-hurdle sensitivity.
- [x] Execute the notebook and validate source coverage, row counts, and
  calculations.

#### Review

The focused notebook `2026-04-28_btc_signal_ev.ipynb` (not committed; its outputs live under `research/results/btc_signal_ev_*.csv`)
replayed the current working-tree definition `btc-rsi-cross-v1` against the
canonical BTC M5, M15, H1, and H4 CSVs. It emitted 1,399 M5 and 589 M15
signals. All four source files passed duplicate/cadence checks, and the
provenance export records row counts, SHA-256 hashes, Git revision, and the
working-tree-dirty state.

The executed study found small positive point estimates at several horizons,
but every 95% chronological block-bootstrap interval crossed zero. At 4h,
M5 mean return was 0.0133% versus a 0.0116% same-timeframe baseline; M15 mean
return was 0.0422% versus a 0.0117% baseline. Neither lift is statistically
supported by this study, and neither survives the illustrative 0.10% cost
hurdle. The non-overlapping checks and monthly table are included for further
review; no timeframe is currently confirmed as robust EV+.

Validation: executed notebook passed `nbformat.validate` with no error cells;
signal invariants passed for all 1,988 alerts; two independent 4h return spot
checks matched exactly; compilation and tracked-file whitespace checks passed.
Ruff was not available in the named `rsi` environment, so lint remains an
environment limitation rather than a passed check.

## Long Core V2 / BTC alpha and AI research pipeline assessment (2026-09-04)

- [x] Inspect current strategy logic, existing research results, and reusable validation infrastructure.
- [x] Review primary research and relevant open-source research automation options.
- [x] Produce prioritized alpha hypotheses and a concrete pipeline proposal with independent evaluation gates.
- [x] Verify cited results and save the assessment; record scope and limitations.

Review: saved [the assessment](../research/2026-09-04_alpha_research_pipeline_proposal.md).
Independent read-only reviews covered Core V2.1, BTC signals, and the research/audit
infrastructure. Checked saved BTC summary arithmetic, Core event counts, source
contracts, and primary web references. The proposal's local Markdown links pass;
tracked-file whitespace checks pass. No trading code or configuration changed,
no new backtest/model was run, and the original BTC confidence intervals were not
independently reproduced because their source notebook/script is absent here.

## Research manager and worker architecture comparison (2026-09-04)

- [x] Compare a strong research manager with cheaper workers against the prior validation-focused proposal.
- [x] Check primary sources for orchestration, model routing, and on-chain data caveats.
- [x] Explain a BTC-first workflow, sustainability criteria, and reusable research architecture.
- [x] Save the architectural clarification and verify its references.

Review: saved the [manager/worker architecture comparison](../research/2026-09-04_hierarchical_research_architecture.md)
and linked it from the earlier assessment. Independent conceptual review found no
necessary corrections. Proposal links and whitespace checks pass. This remains
an architecture discussion; no model benchmark, API-backed pipeline, scheduled
research job, or strategy implementation was performed in this task.

## BTC implementation handoff with limited usage (2026-09-04)

- [x] Check current account usage and prepare a bounded BTC-only first milestone.
- [x] Save the worker brief in tasks/btc_research_phase1_handoff.md.
- [x] Implement the reproducible baseline in a subsequent implementation task.

Review: prepared a standalone handoff for one offline baseline CLI. It defers
model orchestration, statistical selection, trading-rule changes, and on-chain
research. No new task or implementation was started in this planning turn.

## Subscription-backed BTC orchestration options (2026-09-04)

- [x] Verify supported subscription/programmatic access for the thinker and executor.
- [x] Compare Astra on ChatGPT Pro with Z.AI Lite/API and OpenCode Go executor routes.
- [x] Record a practical recommendation, limits, and unresolved model/plan details.

Review: checked the installed Codex CLI's non-interactive and structured-output
options and current official provider documentation. A personal local controller
can use saved Codex CLI authentication and OpenCode's documented headless server;
subscription access does not provide unrestricted general-purpose API access.
Astra access in this account remains unverified. The documented GLM model is
GLM-5.3-Flash. OpenCode Go is a low-commitment worker pilot; Z.AI Lite has different
allowances and explicit supported-tool restrictions. Select the worker using
independently checked BTC jobs before committing to a provider or larger plan.
No paid model request, purchase, authentication change, or orchestration
implementation was performed. The BTC baseline handoff remains the first build
milestone.

## BTC research Phase 1 reproducible baseline (2026-09-04)

- [x] Inspect the existing BTC replay/evaluator, data contracts, targeted tests, and worktree state.
- [x] Implement one repository-root CLI for provenance-validated M5/M15 signal replay and exact-horizon research outputs.
- [x] Add focused tests for exact horizon matching, gaps/incomplete tails, return units, determinism, and provenance/source validation.
- [x] Update the matching research/backtest documentation and validate local Markdown links.
- [x] Run the focused tests, a real local-data reproduction, and applicable static/whitespace verification.
- [x] Record the review handoff with changed files, command, artifact paths, validation, differences, and limitations.

#### Review

Implemented the bounded repository-root CLI `btc_research_phase1.py` and the
thin `app/backtest/btc_research_phase1.py` wrapper around the existing
point-in-time BTC replay/evaluator. It validates the four native CSV identities,
schema, timestamps, duplicate/cadence facts, common coverage, and warmup;
records SHA-256/config/Git/environment provenance; and writes exact-horizon
`manifest.json`, `signals.csv`, `summary.json`, and `report.md` packets. Exact
target candles are required, gaps invalidate affected outcomes, and no later
candle or partial tail is substituted. Signal rules, live configuration, and
execution behavior were unchanged.

Reproduction command:

```powershell
C:\ProgramData\anaconda3\envs\rsi\python.exe btc_research_phase1.py `
  --data-dir app/backtest/data `
  --output-dir research/results/phase1_runs `
  --start 2024-09-01 `
  --end 2026-08-28
```

Final packet: the latest timestamped child under
`research/results/phase1_runs/` (the exact path is printed by the command and
linked in the task handoff).
It emitted 1,399 M5 and 589 M15 signals, matching the available historical
artifact counts exactly. The historical 4h means also match to the recorded
precision: M5 `0.01327507724%`, M15 `0.042164508657%`. The run is operationally
`INCOMPLETE` only because the requested window reaches beyond common source
coverage and 12 signal-horizon tails lack exact 12h/24h targets; alpha is
`NOT_ASSESSED`.

Validation: focused Phase 1 tests `5 passed`; existing replay/review regression
tests plus Phase 1 tests `37 passed, 6 warnings`; canonical real-data run and
unchanged-input repeat both completed; `signals.csv` and `summary.json` were
byte-identical across repeats; three independent pandas spot checks matched;
`python scripts/check_markdown_links.py` passed with 154 Markdown files;
`compileall` passed; `git diff --check` was clean. Ruff was unavailable because
the installed Python wrapper could not locate its platform binary. Pytest's
default global temp root was permission-blocked, so the passing test commands
used the workspace-local `--basetemp .pytest-basetemp`.

The original historical generator/notebook is absent, so this is an auditable
baseline rebuild and does not claim to reproduce the prior bootstrap algorithm.
No bootstrap/DSR/PBO, reserved evaluation, walk-forward, strategy search,
fills/P&L simulation, UI, service, agent framework, on-chain research, or paid
API work was started.

## BTC Phase 1 research-manager review (2026-09-04)

- [x] Review implementation timing, eligibility, provenance, and status contracts against the handoff.
- [x] Independently check saved packet arithmetic and source hashes; run focused regression tests.
- [x] Record any blocking findings and the next bounded BTC milestone.

Review: independently verified four source hashes/cadences, all 7,940 complete
returns, 12 incomplete tails, horizon statistics, context timing, and cooldown
spacing in the supplied packet. Three saved repeat packets have identical
signals/summaries; focused tests pass (5 tests). The full two-year generator and
combined 37-test suite were not rerun in this review. Reproduced staged-code
fingerprint collisions in an isolated Git fixture. One read-only review agent
also reproduced false VALID status without warmup and comparator inclusion of
bars with missing context/post-gap insufficient history. Saved the bounded
correction brief in [btc_research_phase1_review_handoff.md](btc_research_phase1_review_handoff.md).
Saved baseline arithmetic is accepted; automation readiness requires those
corrections. No strategy or implementation code changed in this review.

## BTC Phase 1 bounded readiness/provenance corrections (2026-09-04)

- [x] Reproduce the three review counterexamples with focused regressions.
- [x] Make operational status reflect warmup/readiness and evaluable requested coverage.
- [x] Restrict all-eligible-bar baselines to shared per-event preparation readiness and record exclusions.
- [x] Include staged, unstaged, and untracked content in the dirty-code identity while excluding generated packets.
- [x] Update matching documentation, run focused regressions and a canonical baseline, and record the final review handoff.

### Review

The bounded correction is implemented in the Phase 1 baseline runner. Each
requested M5/M15 trigger close is checked through shared point-in-time
preparation, with requested/evaluable counts and exclusion reasons persisted in
the manifest and summary. Missing warmup or no evaluable requested coverage is
`INVALID`; a fully prepared, complete zero-signal period remains `VALID`.
Comparator rows use those per-event readiness results without bullish gates or
cooldown. Dirty-code identity hashes the actual tracked and untracked working
files, which covers staged and unstaged content changes, while generated packet
directories are excluded.

Validation completed with 27 focused replay/research tests passed, Python
compilation passed, 175 Markdown files passing link checks, and
`git diff --check` clean. Ruff could not run because the installed Python
wrapper could not locate its platform binary. The canonical command completed
with `SUCCESS` execution and `INCOMPLETE` operational status; it retained 1,399
M5 and 589 M15 signals, 7,940 complete signal-horizon outcomes plus 12
incomplete tails, and byte-identical `signals.csv`/unchanged signal and
baseline arithmetic versus the accepted packet. The resulting packet path is
returned with the final review handoff.

## BTC Phase 1 correction acceptance and next experiment (2026-09-04)

- [x] Recheck the three corrections and run the 27 focused replay/research tests.
- [x] Compare the new packet with the accepted baseline and verify source hashes.
- [x] Freeze one BTC M15 extension experiment in a bounded worker handoff.

Review so far: all three prior findings are closed. The independent reviewer
reran the original missing-H4/post-gap cases and confirmed exclusion, while an
unaffected bar remained eligible. The 27 tests pass after creating the absent
local pytest parent directory. Signals are byte-identical to the accepted
packet; signal/replay counts and every horizon/monthly numerical summary match.
All four current source hashes match the new manifest. Preparation is
278,974/278,974 and the comparator 277,887/277,887. The packet remains INCOMPLETE
for documented coverage/tails and alpha NOT_ASSESSED. No new two-year replay or
full repository suite was needed to resolve this review.

Next worker brief: [btc_research_phase2_m15_extension_handoff.md](btc_research_phase2_m15_extension_handoff.md).
It freezes one feature, one fit-period lower-third cutoff, one temporal split,
one four-hour primary comparison, and a paired calendar-block uncertainty
diagnostic. Prior history remains exploratory; no alpha promotion or changed
cooldown semantics are authorized. No experiment code or challenger results
were generated during this review.

## BTC M5 one-to-three-hour horizon correction (2026-09-04)

- [x] Replace the unexecuted M15/4h plan with the user's M5 1h/2h/3h diagnostic.
- [x] Implement and run a bounded reproducible horizon profile with 4h reference.
- [x] Independently verify returns, inspect excursion definitions, and record results.
- [x] Acquire and validate a separate four-year dataset with earlier warmup and exact outcome coverage.
- [x] Run the unchanged signal logic over four years and report fixed-horizon results by year and causal regime.

Review: saved [four-year findings](../research/2026-09-04_btc_m5_four_year_findings.md)
with reproducible commands and exact evidence links. Verified 108 public archive
checksums and native overlaps; canonical inputs remain unchanged. The new
four-year replay has 2,865 M5 signals and the M5 horizon diagnostic has 11,460
complete outcomes with zero exclusions, plus 420,176 comparator bars. All
2,000 bootstrap replicates per horizon are valid. Raw-CSV recalculation matches
all horizon summaries; original and expanded M5 IDs agree on the 1,398-event
common window. All four-year events have causal regime labels; 60 focused tests
pass. Parent Phase 1 remains INCOMPLETE for longer horizons; M5 1h-4h evidence
is complete and alpha NOT_ASSESSED. No strategy/configuration or live execution
changed. The earlier M15 extension brief is superseded before execution.

## Refocus on BTC AI orchestration MVP (2026-09-04)

- [x] Record the owner's scope correction and freeze a pipeline-building handoff.
- [x] Reuse existing BTC data/evaluators as tools and define one full feedback-loop demo.
- [x] Implement the orchestrator, durable job state, first provider adapter, checker gates, and bounded demo in the Luna task.

Review: the active next implementation is
[btc_ai_pipeline_mvp_handoff.md](btc_ai_pipeline_mvp_handoff.md). It distinguishes
Luna as software builder from configurable runtime models, specifies Codex first
with OpenCode next, and requires evidence-driven thinker feedback, durable
history, controlled execution and explicit budgets. No further alpha campaign,
model calls, purchases, task creation, or orchestrator implementation was started
in this handoff-preparation turn.

## BTC AI research pipeline MVP (2026-09-04)

- [x] Implement configurable thinker/executor provider contracts and Codex CLI adapter.
- [x] Add SQLite campaign/job/attempt/decision/budget persistence with resume-safe state.
- [x] Register bounded BTC research tools and implement deterministic evidence checking.
- [x] Implement fixture loop plus explicit preflight/live opt-in CLI commands.
- [x] Add contract, branching, budget, timeout/failure, tamper, and crash/resume tests.
- [x] Run the existing-data verification demo, update matching documentation, and record limitations.

## BTC AI research pipeline MVP implementation (2026-09-04)

- [x] Implement the bounded thinker/executor/checker/reviewer loop.
- [x] Persist campaign, job, attempt, decision, failure, result, and budget state in SQLite.
- [x] Add offline fixtures, tamper/branch cases, resume-safe idempotency, and the Codex adapter boundary.
- [x] Document preflight, offline reproduction, explicit live opt-in, and known limitations.
- [x] Run targeted tests/static checks and record artifact paths.

Review: the offline STOP loop, PROPOSE_NEXT limit branch, and tampered-evidence
REPAIR branch completed with durable SQLite state. The real-data checker verified
one saved four-year M5 event at 1h/2h/3h under approved local read access. No
runtime model was called, so live thinker/executor integration remains
unverified; OpenCode is intentionally unsupported. Targeted pipeline tests and
Markdown link checks pass; Ruff could not run because its wrapper cannot locate
the platform binary.

Final review correction: fixture providers can now run the complete loop over the
saved raw BTC CSV with `--use-saved-data`; auth failures pause resumably; provider
exit/usage metadata and failure-to-attempt links are retained; and verified
evidence reuse is keyed by parameters, source/packet hashes, horizon definitions,
and checker/evaluator code identity. Final focused validation is 57 tests passed.

## ✅ COMPLETED — BTC AI pipeline bounded acceptance corrections (2026-09-04)

- [x] Reproduce and close the review handoff's consent, frozen-resume,
      crash-recovery, job-cap, evidence-binding, cache-integrity, and provider
      control/reporting findings without invoking a model or adding OpenCode.
- [x] Add focused regressions for unauthorized dispatch, stored-config resume,
      durable completed-attempt recovery, idempotent job reservations, changed
      execution/review references, current-input cache validation, evidence and
      packet tampering, and provider timeout cleanup.
- [x] Demonstrate corrected offline STOP, follow-up-limit, tamper/REPAIR, and
      crash/resume paths; update matching docs and task records.

Plan: preserve the existing thinker/executor/checker architecture and BTC
evaluator, keep provider calls explicitly bounded, and leave live verification
as an owner-selected follow-up.

Review evidence: `tests/test_btc_ai_pipeline.py` plus the four existing BTC
research suites pass with 79 tests. Corrected offline artifacts are recorded in
`research/results/btc_ai_pipeline_mvp_review_corrected_stop_final/`,
`research/results/btc_ai_pipeline_mvp_review_corrected_limit2_final/`,
`research/results/btc_ai_pipeline_mvp_review_corrected_repair_final/`, and the
approved local-data run in
`research/results/btc_ai_pipeline_mvp_review_corrected_saved_final2/`. The
local-data run verified one existing M5 event at 1h/2h/3h with fixture
providers and no model call. The explicit live Codex smoke command remains
unrun; OpenCode is unsupported at this milestone, and alpha assessment remains
`NOT_ASSESSED`.

## Independent BTC AI pipeline MVP acceptance review (2026-09-04)

- [x] Inspect implementation and saved evidence against the bounded handoff.
- [x] Re-run the focused offline pipeline tests.
- [x] Reproduce material gaps in opt-in, evidence binding, cache identity, and durable recovery without model calls.
- [x] Deliver a bounded correction brief before provider expansion or a live run.

Review: the 15 existing pipeline tests pass with a new repository-local pytest
base directory. Independent no-call probes reproduced offline dispatch to a
patched Codex adapter, saved configuration loss on resume, repeated completed
executor work after interruption, job-limit bypass, unbound event/review
references, and stale source validation on a cache hit. See the bounded
[acceptance correction handoff](btc_ai_pipeline_mvp_review_handoff.md) and its
linked evidence. Source review also found unenforced provider settings.
The main pipeline implementation was not changed by this review; live usage and
OpenCode integration remain deferred until these corrections pass.

## Prepare the first BTC pipeline live integration test (2026-09-04)

- [x] Read the correction report and independently run 37 pipeline tests.
- [x] Verify normal-local CLI login and dataset access without model calls.
- [x] Prepare a bounded live-test handoff with exact candidate models and caps.
- [x] Fix the post-decision-commit recovery gap and run its focused regression.
- [x] Attempt one live loop only after explicit owner opt-in to the selected pairing.

### Live smoke follow-through plan

- [x] Replay committed review-decision effects idempotently on resume.
- [x] Regression-test a crash after decision commit for STOP, REJECT, and REPAIR
      without new provider calls, results, decisions, or budget reservations.
- [x] Run the focused pipeline regression and matching static/documentation checks.
- [x] Run the no-call preflight with Sol/high and Luna/high under supported local access.
- [x] Run exactly one fresh live campaign with the owner-authorized invocation caps.
- [x] Save and report the proposal, execution plan, checker evidence, decision,
      usage, counters, models, campaign ID, and elapsed time; then stop.

Review: The controller now replays the committed review decision's state effects
before skipping its checked job. The focused recovery regression passed all three
STOP/REJECT/REPAIR cases; the complete pipeline file passed 40 tests; Python
compilation and the 186-file Markdown-link check passed. No-call preflight found
the selected Codex executable, models, high efforts, and all BTC inputs; login
status reported ChatGPT.

The single live campaign was created at
`research/results/btc_ai_pipeline_live_smoke_v1/` with ID
`campaign_9fedf039c2974b23`. It failed on its first thinker proposal call with
`provider_exit` (Codex exit 1), after one thinker reservation and one job
reservation; executor calls, results, decisions, and model-reported usage were
zero/absent. No retry, substitution, second campaign, or fixture fallback was
performed. Stop here; the failure is the live integration finding for this
milestone.

## Diagnose and repair failed BTC live proposal without retry (2026-09-04)

- [x] Recover the exact rejection from the original saved Codex session.
- [x] Correct strict structured-output schemas and add offline compatibility tests.
- [x] Retain bounded, sanitized provider failure diagnostics for actionable reports.
- [x] Run focused validation and document the diagnosis with unchanged live counters.

Plan: the saved session reports HTTP 400 invalid_json_schema: the schema field
lacks a type key. Fix provider integration locally; no model calls, retries,
substitutions, authentication changes, campaign edits, or new live campaign.

Review: recovered HTTP 400 invalid_json_schema from the original saved CLI
session, fixed all three strict output schemas, and added actionable redacted
failure reporting. Pipeline/schema/provider-error tests: 69 passed; Python
compilation and whitespace checks passed. No new runtime model calls. The
original campaign/report/database were not changed. See
[diagnosis and next-call boundary](../research/2026-09-04_btc_pipeline_live_failure_diagnosis.md).
A newly authorized complete smoke test needs two thinker invocations and one
executor invocation; the original remaining thinker budget is insufficient.

## Authorized BTC live smoke v2 (2026-09-04)

- [x] Record explicit owner authorization for one new smoke test after the schema repair.
- [x] Run no-call readiness checks in the supported local execution context.
- [x] Run exactly one new campaign with Sol/high and Luna/high, at most two thinker invocations, one executor invocation, and one job.
- [x] Verify saved evidence/counters and report the outcome; stop without retries on any failure.

Plan: use research/results/btc_ai_pipeline_live_smoke_v2, which does not yet
exist. Preserve the failed v1 campaign. No model substitution, extra campaign,
budget increase, provider integration, or new research study is authorized.

Review: normal-local login status is ChatGPT and all BTC inputs are readable.
The v2 campaign `campaign_3a869ced481f44ab` ran once with a read-only Codex
child sandbox. Sol/high completed one proposal call with usage available, but
the controller rejected the returned `task` string because it was a natural
language instruction rather than the registered `verify_m5_horizons` task.
The campaign stopped before proposal persistence, executor dispatch, checker
verification, or thinker review. Counters are thinker 1/2, executor 0/1, jobs
1/1; no retry, substitution, extra campaign, or v1 mutation occurred. Full
proposal response, usage, and diagnostic details are in the saved report.

## Correct the BTC v2 task identifier contract without a live retry (2026-09-04)

- [x] Inspect the saved natural-language task rejection and current schemas/prompts.
- [x] Constrain task/tool identifiers and supply the registered task contract explicitly to all role prompts.
- [x] Replay the rejected response through offline regressions and verify the fixture loop.
- [x] Document fixes, validation, preserved v1/v2 evidence, and remaining live integration status.

Plan: this is a local contract fix. Do not mutate a saved proposal to force
acceptance, retry a model, alter budgets, or start a v3 campaign.

Review: canonical registered task constants, explicit role task context, matching
nonempty schema constraints, and semantic validation within the attempt boundary
are implemented. Existing 69 pipeline tests plus 14 new regressions pass. The
saved v2 response is rejected without rewriting it or dispatching an executor;
a complete offline fixture still succeeds. v1/v2 live counters remain 1/0/1
(thinker/executor/jobs), with no new runtime calls or live campaign. See
[v2 task-contract diagnosis](../research/2026-09-04_btc_pipeline_v2_task_contract.md).

## Add the OpenCode local-server executor adapter (2026-09-04)

- [x] Implement the provider-neutral OpenCode server adapter for the configured
      `opencode-go/muse-spark-1.3-contributor` model.
- [x] Add no-call contract, structured-output, usage, timeout, auth, and
      preflight regressions without invoking a model.
- [x] Update the matching architecture/research documentation and report
      reproduction metadata while preserving the existing Codex path and live
      campaign artifacts.
- [x] Run focused tests, offline fixture validation, compilation, and Markdown
      link checks; do not launch a new live campaign in this adapter milestone.

Plan: use OpenCode's documented local HTTP server (`opencode serve`) so its
provider authentication remains in OpenCode's own credential store. Pass the
fully qualified provider/model ID, structured JSON schema, explicit zero
structured-output retries, and a deny-all tool permission set; the controller
continues to execute only its registered BTC tool. Keep the server URL and
optional local basic-auth settings outside the repository via environment
variables, and report server/model reachability separately from any model call.

Review: implemented `OpenCodeProvider` as a provider-neutral local HTTP adapter
using the documented OpenCode server routes. It requires an explicit qualified
provider/model ID, sends the structured pipeline schema with `retryCount=0`,
denies the OpenCode session's tool permissions, applies the configured variant,
records reported model/usage/cost metadata, redacts bounded server errors, and
uses one overall request deadline. `preflight` checks local health and the
provider catalog without invoking a model. The controller's registered BTC tool
remains the only execution surface; the OpenCode server process is not owned or
terminated by the pipeline.

Validation: 89 focused BTC pipeline tests passed; targeted Python compilation
passed; the no-call OpenCode preflight reported the local server reachable, the
`opencode-go` provider connected, the exact Muse Spark model available with the
requested `high` variant, and `live_call_performed=false`; and the Markdown link
check passed for 194 files. The fixture artifact is
[report.json](../research/results/btc_ai_pipeline_opencode_offline_fixture_final/campaign_6f9da3a0f03648a2/report.json)
with [report.md](../research/results/btc_ai_pipeline_opencode_offline_fixture_final/campaign_6f9da3a0f03648a2/report.md).
The existing-data artifact is
[report.json](../research/results/btc_ai_pipeline_opencode_offline_saved_final/campaign_4fdb9927075b43cf/report.json),
whose checker evidence is
[evidence.json](../research/results/btc_ai_pipeline_opencode_offline_saved_final/campaign_4fdb9927075b43cf/job_07bf41462a3147b4/artifacts/evidence.json).
That packet is `STOPPED` after one `VERIFIED` job and independently matches the
existing event at 1h, 2h, and 3h; it is real-local-data evidence, not live-model
evidence. No model invocation, new live campaign, authentication change,
credential file, or BTC evaluator change was made in this milestone.

## Review AI research pipeline progress and next milestone (2026-09-05)

- [x] Trace recent commits, implemented orchestration, and provider boundaries.
- [x] Compare saved campaign evidence with the intended thinker/executor workflow.
- [x] Run focused offline tests and assess material remaining gaps.
- [x] Record findings and recommend a concrete next milestone.

Scope: review existing implementation and evidence without runtime model calls,
new research campaigns, or implementation changes.

Review: 109 focused tests passed. Saved live v3 evidence confirms the complete
Codex thinker/executor/checker/review loop; OpenCode has offline validation only.
Read-only probes reproduced a relocated-source-path failure despite healthy
preflight and lost OpenCode session identity after a message timeout. Current
research remains limited to a single registered evidence-verification task.
See the [progress review and next milestones](btc_ai_pipeline_progress_review_20260905.md)
for evidence, provider-boundary findings, and the recommended readiness repair,
mixed-provider smoke, and meaningful two-experiment adaptive campaign.

## Implement bounded adaptive BTC research (2026-09-05)

Owner approved the reviewed next milestones with "yes lets do it".
Plan: [bounded adaptive pipeline](btc_adaptive_pipeline_plan.md).

- [x] Correct exact-input readiness and checkout portability.
- [x] Correct OpenCode lifecycle persistence, uncertainty and tool permissions.
- [x] Add checked population research tools and adaptive controller behavior.
- [x] Verify offline and saved-data integrations; measure the scripted baseline.
- [x] Run bounded mixed-provider live acceptance and adaptive demonstration:
      one checked/reviewed summary passed, then the owner raised the total limit
      to twelve calls. The final five-call campaign verified a horizon summary
      and an evidence-dependent 180-minute volatility comparison, then stopped.
      Both original failed campaigns remain preserved. No automatic retries.
- [x] Complete independent review and matching documentation.

Review closure: independent review reproduced and closed both readiness findings:
mismatched parent packets fail before any provider attempt, and changed source
bytes prevent resumed review. The final suite passes 221 pipeline tests; the
earlier 42 related horizon/regime/Phase 1/acquisition tests also passed. Ruff,
mypy (21 modules) and Markdown link checks pass. The existing Phase 1 module's
architecture size violation remains unchanged.

OpenCode 1.18.29 is installed and authenticated, with a healthy local server.
Live testing exposed and corrected forced-tool-choice incompatibility through
explicit JSON-text mode, then a nullable-schema/nonblank-rationale mismatch.
All failed responses and usage remain preserved. The successful one-job live
acceptance verified the full loop; the final two-job campaign independently
checked a horizon summary and its selected 180-minute volatility comparison.
Both real-data fixture and live accepted-spec replays produce identical evidence.

The owner approved the [research payload preview](../research/results/btc_live_request_preview_20260905/README.md)
after the initial automatic approval rejection, then raised the call limit from
eight to twelve. Exactly twelve calls were used: ten completed and two failed.
No automatic retries, subscription purchases, trading changes or strategy edits
were made. Reported cost coverage remains partial, and alpha is unassessed.

Final evidence and remaining next step are recorded in
[the implementation outcome](btc_adaptive_pipeline_outcome_20260905.md).

## Research selection quality benchmark (2026-09-05)

User approved measuring diagnostic value after the live two-study campaign.
Plan: [selection benchmark](btc_selection_benchmark_plan.md).

- [x] Freeze a zero-new-model-call retrospective comparison design.
- [x] Implement source validation, checked candidate catalog and paired statistics.
- [x] Run the historical comparison and assess diagnostic value versus resources.
- [x] Verify implementation, review results and update affected documentation.

Review: [measured outcome](btc_selection_benchmark_outcome_20260905.md) and
[independent review](btc_selection_benchmark_review.md). The offline pilot
completed with zero new provider calls; AI selection benefit is not established.
293 tests, Ruff, mypy (26 modules) and Markdown links (216 files) pass.
Architecture lint reports only the unchanged 865-line Phase 1 module.

## Portable research handoff and GitHub publication (2026-09-05)

- [x] Write a root handoff with findings, limits, implementation map and safe continuation commands.
- [x] Package the related pipeline code, tests, compact evidence and reproducibility notes; keep local credentials and large regenerated CSVs out.
- [x] Verify the publication contents, tests, documentation links and frozen evidence bytes.
- [x] Prepare the dedicated codex branch and reviewed publication contents.

Publication target: `origin/codex/research-pipeline-handoff-20260905`.
The pushed commit and remote verification are reported in the final response.
Review: [portable handoff](../RESEARCH_PIPELINE_HANDOFF.md) and
[publication checks and known limitations](btc_research_handoff_publication.md).
