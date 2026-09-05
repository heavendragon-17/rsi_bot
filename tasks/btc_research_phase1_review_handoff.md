# BTC Phase 1 review: bounded corrections

## Objective and scope

Correct three independently identified readiness/provenance defects before the
first BTC extension experiment or model orchestration. Use one implementation
worker and the existing Python environment at
`C:/ProgramData/anaconda3/envs/rsi/python.exe`. Read `docs/INDEX.md`,
`docs/agent-workflow.md`, and `tasks/btc_research_phase1_handoff.md`; preserve the
existing uncommitted work. Do not alter production signal rules or live config,
start strategy search, install tools, call paid models, commit, or push.

## Accepted evidence

Reviewed packet:
`research/results/phase1_runs/run_20260904T065228614040Z_2572884b`.
The reviewer independently checked all four input SHA-256 hashes and cadences,
all 7,940 complete returns against raw CSV close prices and exact target times,
the 12 missing tails, horizon means/medians, closed-context timestamps, and
one-hour signal cooldown spacing. Counts are 1,399 M5 and 589 M15 events, with
7,952 event-horizon rows. Three other saved packets have byte-identical signals
and summaries. The five focused Phase 1 tests pass. This review did not rerun
the full two-year signal generator or independently repeat the reported
37-test combined suite.

These findings do not show incorrect returns in that saved packet. It correctly
reports INCOMPLETE and NOT_ASSESSED. They block general automated use on other
data/revisions.

## Required corrections

1. **Operational validity must account for preparation readiness.** In
   `app/backtest/btc_research_phase1.py`, status currently depends only on source,
   boundary, and emitted-outcome warnings. A synthetic input containing two
   regular candles in each timeframe, with no requested boundaries, produces
   SUCCESS / VALID, zero signals, no warnings, both warmups `None`, and four
   not-ready trigger events. This was reproduced through the actual runner and
   replay with in-memory loaders and mocked artifact writes. Record evaluable
   coverage and preparation exclusions. Missing required warmup or no evaluable
   requested coverage must not produce VALID. Preserve the distinction between
   insufficient data and a valid, fully evaluated period with zero signals.

2. **Match the all-eligible-bar comparator to per-event data readiness.**
   `_baseline_outcomes` checks only the first warmup timestamp. It includes bars
   rejected by replay after missing H1/H4 context or a gap requiring fresh
   contiguous history. A synthetic warmed-up series missing the H4 close at
   `2026-01-05T08:00:00Z` includes M5 09:00 and 13:00 outcomes even though shared
   preparation rejects them as `H4_EXPECTED_CLOSE_MISSING` and
   `H4_INSUFFICIENT_CONTIGUOUS_HISTORY`. Reuse per-event readiness from shared
   preparation, without requiring bullish gates, signal conditions, or signal
   cooldown. Record exclusion counts/reasons so the comparator is auditable.

3. **Fingerprint staged code as well as unstaged/untracked code.**
   `_git_identity` currently hashes `git diff --binary`, status, and untracked
   contents, omitting staged contents. In an isolated Git fixture with fixed
   HEAD, staging `value = 1` in `logic.py` and then staging `value = 2` returns
   the same digest and `M  logic.py` status. Include content identity covering
   HEAD-to-index and index-to-worktree changes, or equivalently hash the actual
   relevant working files. Keep generated packets excluded. Do not modify the
   real repository's index to test this; use an isolated temporary repository.

## Verification and return

- Add focused regressions that fail for each counterexample, including the
  valid zero-signal case and retained readiness of unaffected comparator bars.
- Verify staged, unstaged, and untracked content changes affect code identity;
  repeated calls without changes are stable and generated outputs are excluded.
- Run the focused replay/research regression tests and one canonical local-data
  baseline. Explain any numerical changes. With the supplied gap-free data,
  existing signal counts and return arithmetic should remain unchanged; new
  readiness fields and code identity may legitimately differ.
- Update the matching research/backtest documentation, validate Markdown links,
  and run applicable static checks. Preserve the old evidence packets.
- Return changed files, focused test results, exact new packet path, numerical
  comparison, and remaining limitations. Stop after these corrections.

## Deferred research decisions

Replay currently initializes cooldown at the requested window start. Document
that boundary behavior; do not silently change shared replay semantics here.
The researcher must account for it before comparing separately replayed windows.
The existing two-year sample has already been explored and must not be relabeled
as untouched evaluation data. The next milestone will define one bounded BTC M15
extension experiment and its evaluation protocol after this review is closed.
