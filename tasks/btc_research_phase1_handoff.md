# BTC research Phase 1: reproducible baseline

## Objective

Implement the first small component of a BTC research pipeline: one offline CLI
that reproduces the current BTC signal baseline and saves a verifiable evidence
packet. This is the foundation for a later strong-model research manager with
cheaper implementation workers. Keep this milestone small enough for one worker
task. Model orchestration is a later milestone.

The owner wants BTC first and wants to conserve ChatGPT Plus usage. On-chain
research is deferred pending their clarification. Do not expand into Core V2.1,
new trading rules, an agent framework, UI work, paid APIs, or scheduled jobs.

## Working instructions

Read AGENTS.md, docs/INDEX.md, and docs/agent-workflow.md. Inspect git status and
preserve existing work. The repository may contain concurrent/uncommitted edits;
do not overwrite them. Research documents and this handoff may be uncommitted,
so verify their presence when using a fresh worktree. Reuse the project Python
environment at C:/ProgramData/anaconda3/envs/rsi/python.exe when available.

Use one implementation agent for this bounded milestone; avoid broad parallel
research or repeated planning. Read targeted source files. Use focused meaningful
tests, a real local-data run, and applicable repository verification gates. Fix
relevant failures; do not broaden into unrelated repairs.

## Existing material

- app/backtest/signal_replay.py and its signal_replay_* helper modules.
- app/trading/strategy/btc_rsi_cross_alert/ for the authoritative evaluator.
- docs/07_trading_strategies/btc-rsi-cross-alert-spec.md.
- app/backtest/data/BTCUSDT_5m.csv, BTCUSDT_15m.csv, BTCUSDT_1h.csv,
  and BTCUSDT_4h.csv.
- research/results/btc_signal_ev_signals.csv and btc_signal_ev_summary.csv.
- research/2026-09-04_alpha_research_pipeline_proposal.md and
  research/2026-09-04_hierarchical_research_architecture.md are background only;
  this handoff defines the narrower implementation scope.

Previous saved results contain 1,399 M5 and 589 M15 alerts. Four-hour mean gross
forward returns are approximately +0.013275% and +0.042165%, respectively.
Reported intervals cross zero. These are historical comparisons, not counts or
metrics to hardcode. Source/config revisions may legitimately change them; explain
discrepancies. The original generating BTC research notebook/script was absent
during assessment, so recover it if readily available or rebuild a small auditable
baseline script. Do not claim to reproduce its bootstrap algorithm from CSVs.

## Deliverable

Provide one documented repository-root command accepting data directory, output
directory, and an optional date window. It should:

1. Validate source identity, candle timestamps, duplicate/cadence issues, native
   timeframe coverage, and required warmup. Reuse existing loaders/evaluators;
   do not duplicate production trading rules.
2. Generate M5/M15 signals with current point-in-time logic and cooldown behavior.
3. Calculate gross close-to-close forward returns at 1h, 4h, 12h, and 24h; report
   missing/incomplete intervals explicitly. A candle after the exact target time
   must not silently turn a shorter horizon into a longer one. Gaps invalidate
   the affected outcome rather than being bridged silently.
4. Produce per-timeframe/horizon counts, means, medians, and monthly summaries.
   Include the same-timeframe all-eligible-bar baseline with matched coverage.
   Clearly distinguish illustrative return-minus-cost sensitivity from simulated
   fills or strategy P&L. Do not invent a TP/SL policy in this milestone.
5. Write manifest.json, signals.csv, summary.json, and report.md into a run-specific
   output directory. Include input SHA-256 hashes, UTC windows, strategy/config
   identity, git revision plus dirty-code identity, executed command, environment
   versions, metric definitions, warnings, and machine-readable completion status.
6. Separate operational validity (VALID / INVALID / INCOMPLETE) from alpha
   assessment. Without reserved evaluation and selection-aware evidence, alpha
   remains NOT_ASSESSED. Successful execution is not evidence of profitability.

No new bootstrap/DSR/PBO/walk-forward implementation is required here. Do not
reuse the existing audit PASS as proof of alpha. Statistical evaluation and the
first extension-filter experiment follow after baseline review.

## Acceptance criteria

- One real-data baseline run completes with the exact reproduction command.
- Focused tests cover exact horizon matching, incomplete tail/gaps, return units,
  and source/provenance behavior. Independently recompute a few sampled outcomes.
- Repeating a run on unchanged inputs produces identical signal identities and
  numerical summaries; run timestamps may differ.
- Compare against available historical artifacts without forcing identical
  counts when source versions differ. State what was and was not reproduced.
- Update the relevant research/backtest documentation and validate local links.
- Keep production signal rules and live configuration unchanged.

## Return to the research manager

Finish with a concise handoff containing changed files, reproduction command,
artifact paths, validation performed, counts/summary differences, and remaining
limitations. Stop after this baseline milestone. Do not begin strategy search,
install an agent framework, commit/push, or start external services.

The next review will decide whether the foundation is adequate for a bounded
BTC M15 extension experiment. The strong model is used at this decision point,
rather than supervising every implementation step.
