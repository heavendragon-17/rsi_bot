# Lessons Learned

> Patterns captured from user corrections. Review at session start. Update after every correction.

<!-- Example:
## 2024-01-15: Always check for None before accessing .symbol
- **Mistake**: Assumed position was never None in backtest context
- **Rule**: Always guard `position` access with a None check — backtest engine passes None for flat positions
- **Files affected**: app/strategies/*.py
-->

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
