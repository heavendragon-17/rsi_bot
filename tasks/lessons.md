# Lessons Learned

## 2026-08-20: Treat an annotated roadmap selection as implementation scope

- **Mistake**: Interpreted execution-policy answers as a documentation-only request after presenting an implementation roadmap.
- **Rule**: When the user selects roadmap items or says "these ones," turn the selected items into the active implementation checklist and execute them. Use later policy answers to resolve implementation boundaries, not to narrow the request unless the user says so.
- **Files affected**: `tasks/todo.md`, Core V2.1 implementation and documentation.

## 2026-08-20: Prefer the user's existing project environment

- **Correction**: The user identified the intended Conda installation and asked to use its `rsi` environment for this repository.
- **Rule**: Inspect and reuse the named project environment before creating a new one. Record its actual interpreter/dependency versions rather than preserving an earlier assumed version requirement.
- **Files affected**: project setup documentation and test commands.

> Patterns captured from user corrections. Review at session start. Update after every correction.

<!-- Example:
## 2024-01-15: Always check for None before accessing .symbol
- **Mistake**: Assumed position was never None in backtest context
- **Rule**: Always guard `position` access with a None check — backtest engine passes None for flat positions
- **Files affected**: app/strategies/*.py
-->

## 2026-09-02: Runtime-test embedded deployment helpers and log silent failures

- **Correction**: `check_deploy.sh` passed shell syntax validation but crashed at runtime because an embedded Python helper used `tempfile` without importing it. The crash happened after the production checkout reset and before `deploy.sh`, so the deploy log looked healthy while journald held the only traceback.
- **Rule**: Treat embedded interpreter code as executable production code: run helper functions in a sandboxed functional regression test, use the shell interpreter's path separator when constructing cross-platform test environments, redirect helper stderr to the operational log, and add an EXIT trap for abnormal checker termination. `bash -n` alone cannot prove embedded Python imports or runtime behavior.
- **Files affected**: `deploy/check_deploy.sh`, `tests/test_deploy_scripts.py`, `docs/15_debugging/common-issues.md`, and `docs/12_deployment_and_ops/vps-deployment-guide.md`.

## 2026-09-01: "Enqueued" is not "delivered" — verify the whole send path

- **Correction**: The production log reported 12 `btc_rsi_cross_alert_enqueued` events (8 M5, 4 M15) while the user's Telegram channel had received only 3 M5 cards and zero M15. Nine alerts were rejected by Telegram with HTTP 400 "can't parse entities" (raw `<` in the card text) and silently dropped.
- **Rule**: When debugging "no signal arrived", diff the delivery path end-to-end (enqueue → HTTP send result → channel export) instead of trusting upstream counters; an enqueue log proves nothing about delivery. Under `parse_mode="HTML"`, a raw `<` in message text — including static glyphs like `< 60.00` or `<=` inside templates, not just dynamic values — makes Telegram reject the entire message. Entity-escape every `<` in card text and keep `TestHtmlEscaping.test_card_is_html_send_safe` plus the plain-text fallback tests green.
- **Files affected**: `app/signal/btc_rsi_cross_alert/formatter.py`, `app/notification/telegram_bot.py`, `tests/test_btc_rsi_cross_alert_formatter.py`, `tests/test_telegram_bot_send_fallback.py`, `AGENTS.md`, `docs/08_execution_and_oms/notifications.md`, `docs/07_trading_strategies/btc-rsi-cross-alert-spec.md`, `docs/07_trading_strategies/btc-rsi-cross-alert-agent-prompt.md`, `docs/15_debugging/common-issues.md`.

## 2026-08-30: Verify native form-control popups in every theme mode

- **Correction**: The dark Signal Review page styled the collapsed Replay scope control, but its Windows native popup used a light surface with inherited white option text, hiding most choices.
- **Rule**: When a themed UI uses native selects, set the matching `color-scheme` on the control and explicit option foreground/background colors. Verify the opened native popup on the target OS; checking only the closed control is insufficient.
- **Files affected**: `ui/src/index.css`, frontend theme documentation, and live UI verification.

## 2026-08-30: Put reviewer decisions before supporting evidence

- **Correction**: The Signal Review detail page placed quality/outcome controls below secondary information and revealed too few future candles for a confident manual WIN/LOSS/SKIP judgment.
- **Rule**: In human review tools, keep staged decision controls visible above the primary evidence, show the reviewer's queue position, and size the unlocked evidence window for the actual judgment horizon rather than a generic chart chunk. Report the actual loaded evidence count at source boundaries instead of promising the configured target chunk.
- **Files affected**: `app/backtest/signal_replay_analysis.py`, `ui/src/components/signal-review/`, `ui/src/stores/signalReviewStore.ts`, tests, and reviewer documentation.

## 2026-08-30: Make review workflows data-aware and review-first

- **Correction**: The Signal Review page required manual dates even though replays can only use predownloaded canonical CSV coverage, then appeared frozen at 75% while post-processing signals.
- **Rule**: Derive replay scope from the intersection of available source data, make all available data the default, constrain optional presets to that range, expose post-replay progress, and keep dataset preparation secondary to the human review task.
- **Files affected**: `app/backtest/signal_replay_*`, `app/api/routes/signal_replays.py`, `ui/src/components/signal-review/`, the signal-review store/API, tests, and routed documentation.

## 2026-08-27: Keep timeframe gates tied to the requested market quantity

- **Correction**: The BTC RSI alert's H4 confirmation must use the closed H4 candle price above EMA21(price), not EMA9/WMA45 derived from RSI21.
- **Rule**: When a user changes an indicator gate from RSI-space to price-space, remove the obsolete RSI-derived input, readiness requirement, message field, and tests instead of retaining a hidden dependency.
- **Files affected**: `app/trading/strategy/btc_rsi_cross_alert/`, `app/signal/btc_rsi_cross_alert/`, related tests and strategy documentation.

## 2026-08-27: Cooldown must preserve timeframe independence

- **Correction**: M5 and M15 alignment/cross alerts both need a candle-close cooldown. The initial M5 implementation used 15 minutes; the current policy uses one hour for each timeframe.
- **Rule**: Store each timeframe's alert cooldown state separately from evaluation cursors and emitted-event dedupe; measure it from candle close time, update it only after a successful send, and test the equality boundary plus other-timeframe isolation.
- **Files affected**: `app/signal/btc_rsi_cross_alert/worker.py`, worker tests, and BTC RSI alert documentation.

## 2026-08-29: Historical BTC replay needs native H1 context

- **Correction**: The replay command failed because the BTC H1 CSV was omitted and no sibling `BTCUSDT_1h.csv` existed beside the M5/M15/H4 files.
- **Rule**: Download and pass native BTC `1h` data explicitly whenever replaying the H1 close > EMA21 gate; do not silently derive H1 context from another timeframe.
- **Files affected**: `app/backtest/signal_replay.py`, replay CLI/data documentation, and common troubleshooting guidance.

## 2026-08-27: Separate shared gates from timeframe-specific price filters

- **Correction**: M15 must keep the shared H4 close-above-EMA21 gate and also require its own close above its own price EMA21.
- **Rule**: When adding a same-named indicator condition across timeframes, verify the source series and timeframe explicitly, reuse an existing shared gate once, and add a distinct rejection reason plus equality-boundary tests for the new timeframe-specific filter.
- **Files affected**: `app/trading/strategy/btc_rsi_cross_alert/m15_checker.py`, domain reasons, timeframe-checker tests, and BTC RSI alert documentation.

## 2026-08-27: Keep architecture thresholds aligned with production CI

- **Correction**: The 400-line architecture threshold was too restrictive for the current BTC RSI alert modules; relax the enforcement rule rather than restructuring behavior solely to satisfy the threshold.
- **Rule**: When changing a CI quality threshold, update the executable rule, repository guidance, and enforcement documentation together, then rerun the same CI check before deployment.
- **Files affected**: `scripts/arch_lint.py`, `CLAUDE.md`, and architecture enforcement documentation.

## 2026-08-27: Route distinct BTC checkers to distinct Telegram topics

- **Correction**: The ordinary `rsi_no_retest` strategy is disabled; topic `1003` is reserved for the BTC M15 checker, while topic `1147` is reserved for the BTC M5 checker.
- **Rule**: Keep M5 and M15 evaluation logic in their existing checker modules and make topic selection explicit at the worker routing boundary.
- **Files affected**: `app/signal/btc_rsi_cross_alert/`, `config.yaml`, and BTC alert tests/documentation.

## 2026-08-27: Make BTC alert cards independently verifiable

- **Correction**: A BTC alert must list the exact indicator and price values used at the signal candle, including the trigger-timeframe price EMA21; the chart candle close timestamp must be easy to locate in UTC+7.
- **Rule**: Treat every condition in the M5/M15 signal contract as a visible card check, include previous/current RSI EMA/WMA values when proving an M15 cross, and label the UTC+7 candle timestamp as a chart locator.
- **Files affected**: `app/signal/btc_rsi_cross_alert/formatter.py`, formatter tests, and BTC RSI alert documentation.

## 2026-08-28: Replay warmup must be explicit and linear

- **Correction**: A two-year replay reported every initial trigger as `H4_INSUFFICIENT_CONTIGUOUS_HISTORY` and recalculated indicators for each candle.
- **Rule**: Derive readiness from the existing contiguous-history minimums, skip only the initial warmup events, and precompute recursive/rolling indicators once per contiguous segment while preserving point-in-time lookups.
- **Files affected**: `app/backtest/signal_replay*.py`, replay tests, and backtest documentation.

## 2026-08-28: Profile replay allocations before adding hardware backends

- **Correction**: The cached two-year replay still needed another speed pass, and the available Intel Arc B580 raised the question of GPU acceleration.
- **Rule**: Profile real replay data first; vectorize timestamp and rolling-array work, prefilter a conservative candidate superset, and defer domain/event-card allocation until the exact evaluator is needed. Do not add a GPU backend when the measured CPU path already completes interactively.
- **Files affected**: `app/backtest/signal_replay*.py`, replay performance tests, and backtest documentation.

## 2026-08-28: Match replay output to manual review workflow

- **Correction**: A combined report made it harder to review M5 and M15 signals against their respective charts.
- **Rule**: Make the default replay output one file per timeframe, while retaining an explicit combined-report option for compatibility.
- **Files affected**: `app/backtest/signal_replay*.py`, replay tests, and backtest documentation.

## 2026-08-29: Add multi-timeframe gates from the requested source timeframe

- **Correction**: BTC alerts must require H1 close > H1 EMA21 in addition to the existing H4 gate, and M5 RSI21 must stay below 60 to avoid buying a local top.
- **Rule**: When adding a timeframe-specific filter, carry that timeframe as an explicit native context through config, stream targets, point-in-time preparation, live confirmation, replay, and the visible alert snapshot; do not infer it from another timeframe. Treat “below 60” as a strict `< 60` boundary.
- **Files affected**: BTC alert config/evaluator/checkers/worker, historical replay, formatter, tests, and strategy documentation.

## 2026-08-29: Keep low-tech reviewer commands in Windows CMD syntax

- **Correction**: The human review guide used PowerShell commands for the one-time frontend build even though the reviewer workflow is Windows batch-file based.
- **Rule**: For low-tech Windows reviewer instructions, use `cmd` syntax (`cd /d`, `npm ci`, `npm run build`) and keep shell-specific commands out of the copy-paste path.
- **Files affected**: `wiki/btc-signal-review-guide.md`.

## 2026-09-02: Interpret unconfigured Telegram topics as forum inventory

- **Correction**: `/topics` was extended to list unconfigured strategy definitions, but the request meant Telegram forum topics that exist without a strategy/config mapping.
- **Rule**: Keep strategy definitions and observed Telegram forum topics in separate sections. A Bot API polling bot can only discover forum topics from updates it receives; it must label the inventory as observed rather than claim a complete historical list.
- **Files affected**: `app/notification/`, `main.py`, notification tests, and notification/operations documentation.

## 2026-09-02: Keep TP/SL review separate from 1R and human outcome labels

- **Correction**: The BTC Signal Review UI needs optional exchange-style TP/SL
  inputs with the entry fixed to the signal candle; it must not classify a
  result as a win or loss from whether it reached 1R.
- **Rule**: Persist the configured TP/SL and objectively report the first
  signal-timeframe level touched plus elapsed time, while leaving the existing
  manual quality and WIN/LOSS/SKIP review fields independent.
- **Files affected**: `app/backtest/signal_replay_analysis.py`,
  `app/backtest/signal_replay_service.py`, `app/api/`, `app/repository/`,
  `ui/src/components/signal-review/`, tests, and routed documentation.

## 2026-09-02: Capture the TP/SL plan before revealing future candles

- **Correction**: Reviewers must be able to enter and save exchange-style TP/SL
  levels before choosing whether the signal chart is good, bad, or uncertain.
- **Rule**: Keep the future-candle gate on the quality label, but allow the
  fixed-entry plan to persist while quality is `UNREVIEWED`; defer its objective
  outcome evaluation until the quality label unlocks future data. Present the
  chart on the left and the TP/SL controls in a dedicated right-side panel.
- **Files affected**: `app/backtest/signal_replay_service.py`,
  `ui/src/components/signal-review/SignalReviewLab.tsx`, tests, and routed
  documentation.

## 2026-09-02: Verify responsive layouts in the built browser before handoff

- **Correction**: The source used an arbitrary `xl:grid-cols-[...]` utility,
  but the built CSS omitted that class, so the live page stacked the chart and
  TP/SL panel despite a wide viewport.
- **Rule**: Verify the rendered layout at the user's target viewport after the
  production build. Prefer utility classes already emitted by the project's
  Tailwind build (the review work area now uses `lg:grid-cols-12` with explicit
  column spans), and check the actual interaction state in the browser.
- **Files affected**: `ui/src/components/signal-review/SignalReviewLab.tsx`,
  frontend documentation, and review task records.

## 2026-09-02: Keep Human review at the top of the signal detail

- **Correction**: The Human review section should be the first review surface,
  before the chart and TP/SL panel, even though the chart and plan remain
  side-by-side below it on desktop.
- **Rule**: Render the Human review section immediately after the signal header,
  then render the chart-left / TP/SL-right work area.
- **Files affected**: `ui/src/components/signal-review/SignalReviewLab.tsx`,
  frontend/reviewer documentation, and review task records.

## 2026-09-02: Resolve escaped research notebook paths correctly

- **Correction**: A notebook path shown with backslashes before underscores was
  Markdown-escaped text, not a nested directory path.
- **Rule**: When a user references a research notebook, check the repository's
  actual `research` tree and normalize display escaping before reporting it as
  missing.
- **Files affected**: `research/2026-04-28_phase1_audit_exploration.ipynb`.

## 2026-09-04: Distinguish model orchestration from research validation

- **Correction**: The intended AI research pipeline uses a strong lead model to
  generate hypotheses and direct cheaper execution models, then adapt from their
  results; the first domain is BTC signals.
- **Rule**: Address the manager/worker model hierarchy, delegation contracts,
  economics, and research autonomy explicitly. Treat deterministic validation as
  a complementary part of that architecture, not a replacement for it. Keep
  architecture discussion distinct from authorization to implement or schedule it.
- **Files affected**: research architecture proposals and task planning.

## 2026-09-04: Make research validity reflect evaluability and staged code

- **Correction**: The BTC Phase 1 packet could label a two-candle, zero-signal
  dataset `VALID`, compare all bars that lacked shared H1/H4 preparation, and
  reuse the same dirty-code fingerprint after staged content changed.
- **Rule**: Treat preparation readiness and evaluable requested coverage as part
  of operational validity; derive comparator eligibility from the shared
  point-in-time preparation path without applying signal gates or cooldown; and
  fingerprint HEAD-to-index, index-to-worktree, and untracked content while
  excluding generated evidence packets.
- **Files affected**: BTC Phase 1 baseline module/tests, research/backtest
  documentation, and task records.

## 2026-09-04: Match BTC research horizons to the intended M5 setup

- **Correction**: The owner wants the M5 setup assessed over one and two hours,
  with three hours also checked, before pursuing the proposed M15/four-hour
  extension experiment.
- **Rule**: Distinguish signal timeframe from holding horizon and higher-timeframe
  confirmation gates. Test the requested horizon profile on the same signals
  before selecting a filter experiment. Treat early-move timing as a hypothesis;
  report close-to-close returns and within-window excursions separately, since
  a favorable intrabar move is not a captured trade return.
- **Files affected**: Phase 2 research handoff and BTC horizon diagnostic.

## 2026-09-04: Expand the BTC study across four years and explicit regimes

- **Correction**: The owner wants four years of history to assess the setup
  across different crypto market conditions.
- **Rule**: Freeze exact signal/outcome boundaries, include earlier warmup,
  preserve the old dataset, and label regimes from information available at each
  signal. Four years is a requested coverage window, not proof that every regime
  or a complete independent market cycle has been sampled. Longer recursive
  indicator history can legitimately change early overlap signals.
- **Files affected**: Four-year BTC acquisition, regime review, and task records.

## 2026-09-04: Keep BTC research tools subordinate to the AI pipeline objective

- **Correction**: The owner pointed out that repeated manual studies displaced
  the primary objective: a strong thinker orchestrating cheaper executors and
  learning from verified research results.
- **Rule**: Once a reproducible dataset and evaluator exist, make the next
  milestone the working orchestration loop. Treat further alpha experiments as
  jobs for that pipeline rather than prerequisites invented by the assistant.
  Distinguish the model building the software from runtime thinker/executor
  roles and give the worker a bounded implementation brief.
- **Files affected**: BTC AI pipeline MVP handoff and architecture priorities.

## 2026-09-04: Keep the first AI research loop bounded and evidence-led

- **Correction**: The BTC milestone requires orchestration software around the
  existing evaluator, not another manual alpha campaign or an implicit model
  integration.
- **Rule**: Keep thinker/executor providers configurable, validate model JSON,
  map only registered tools to fixed callables, persist every transition before
  advancing, and label fixture, real-local, and live-model verification
  separately. Require explicit live opt-in and preserve the next missing
  adapter instead of faking support.
- **Files affected**: `app/research_pipeline/`, `btc_ai_pipeline.py`, matching
  architecture/research/backtest docs, and task records.

## 2026-09-04: Make bounded AI research resumes state-safe

- **Correction**: The acceptance review found that consent, resume recovery,
  budget reservation, evidence references, and cache identity could diverge
  from the persisted campaign state.
- **Rule**: Restore the stored configuration before dispatch, construct
  providers lazily, recover completed phases idempotently, reserve every job
  and provider call atomically, pause uncertain work until explicit
  reconciliation, and require current typed inputs plus authoritative checker
  and artifact hashes before reuse or follow-up. Report provider controls,
  runtime model/usage metadata, and live verification only when they actually
  occurred.
- **Files affected**: `app/research_pipeline/`, `btc_ai_pipeline.py`, focused
  pipeline regressions, architecture/research/backtest docs, and task records.

## 2026-09-04: Keep Codex and OpenCode authentication domains separate

- **Correction**: The owner clarified that the existing Codex CLI ChatGPT login
  is already available and that no API-key setup or `.env` change is wanted.
- **Rule**: Do not treat Codex login as OpenCode provider authentication. Keep
  the OpenCode adapter on its local `opencode serve` API so OpenCode retains its
  own credential store; use only non-secret endpoint/basic-auth environment
  settings when explicitly configured, and never persist credentials in the
  research campaign.
- **Files affected**: `app/research_pipeline/providers.py`, OpenCode pipeline
  documentation, and the adapter task record.
