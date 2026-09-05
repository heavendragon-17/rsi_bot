# Adaptive BTC research pipeline outcome — 2026-09-05

OpenCode 1.18.29 is installed, authenticated and connected to the research
pipeline. The full live adaptive campaign completed: a horizon summary led to
a 180-minute volatility diagnostic, both VERIFIED, followed by STOP. Replaying
both studies without models produced identical evidence. All twelve approved
calls have been used, including four from two preserved failed integrations.
No trading changes or strategy edits were made.

## Delivered behavior

- Preflight resolves current dataset paths and verifies exact frozen bytes and
  parent ancestry. Every model dispatch rechecks inputs before reserving a call.
- OpenCode session identity is persisted before dispatch; a failed cancellation
  pauses the campaign for explicit reconciliation. Wildcard permissions deny
  all tools except the structured response operation.
- Adaptive campaigns can compare 60/120/180-minute signal and baseline outcomes,
  then inspect one horizon by year or causal trend/volatility. The thinker
  proposes a distinct evidence-dependent follow-up; the executor can choose one
  bounded diagnostic with a rationale. Model code is never executed.
- Campaign budgets, durable recovery and numerical evidence remain authoritative.
  Reports distinguish fixture providers, real-data checks, successful live calls,
  complete live loops and two-study sequences. Usage/cost coverage remains explicit.
- A zero-model baseline reruns the same accepted experiment specifications and
  checks tables, input hashes and checker identities for exact equality.

## Four-year evidence

The committed historical horizon packet omitted its large baseline CSV. The
new materializer rebuilt 420,176 comparator events (1,680,704 four-horizon rows)
and checked historical counts/statistics plus raw-return/population invariants.
This supports only the frozen all-bar comparator with zero preparation
exclusions. Original missing-file byte identity is unknown; the derived packet
records a new baseline hash. Historical source packets remain intact.

- [Materialization report](../research/results/btc_adaptive_prepared_20260905/materialization_report.json)
- [Final real-data campaign](../research/results/btc_adaptive_fixture_final_20260905/campaign_19cbc72a47114e1c/report.json)
- [Final scripted replay](../research/results/btc_adaptive_fixture_final_20260905/campaign_19cbc72a47114e1c/baseline_report.json)
- [No-model preflight](../research/results/btc_adaptive_prepared_20260905/final_preflight.json)
- [OpenCode installation/readiness evidence](../research/results/btc_adaptive_prepared_20260905/opencode_install_readiness_20260905.json)
- [Installed OpenCode readiness](../research/results/btc_adaptive_prepared_20260905/opencode_installed_readiness_20260905.json)

The final fixture-provider campaign stopped after two VERIFIED studies and five
scripted role responses (three thinker, two executor), with no failures. It
first compared all three horizons using 2,865 signal events and 420,176 baseline
events, then selected the 180-minute calendar-year diagnostic from the largest
absolute pooled signal-minus-baseline difference. This demonstrates bounded
adaptive mechanics on real data, not autonomous live-model judgment or alpha.

The completed campaign span was 119.05 seconds, including planning previews
and repeated identity checks; numerical checks took 56.43 seconds. The final
scripted replay matched both studies in 27.29 seconds. Elapsed times are single
local observations under varying machine load, not a performance benchmark.
Monetary costs are unavailable for these fixture runs. The separate live smoke
is recorded below and must not be mixed with fixture-provider measurements.
The initial real-data run's equivalent replay matched both studies in 54.91
seconds; its orchestration span was 115.03 seconds. Accepted-spec replay does
not evaluate independent hypothesis-selection quality.

## Verification and review

- 221 focused pipeline tests pass, including provider boundaries, schema
  contracts, readiness, numerical studies, materialization and adaptive recovery.
- 42 related horizon, regime, Phase 1 and acquisition tests pass.
- Independent review reproduced and closed both discovered readiness bugs:
  wrong parent packets consume zero calls, and changed inputs block resumed review.
- Markdown link verification passed (211 files after generated-test cleanup).
- Ruff passes all pipeline modules and focused tests; mypy passes all 21
  pipeline modules on this Windows host. The typed controller support boundary
  is explicit, including shared state and required provider/validation callbacks.
- Architecture lint now permits and bounds the research subsystem. Its only
  remaining violation is the unchanged 865-line `app/backtest/btc_research_phase1.py`
  already present at HEAD; no size-limit exception was added for it.

Supporting records: [independent review](btc_adaptive_implementation_review.md),
[study implementation](btc_study_tools_report.md),
[provider changes](btc_opencode_fix_report.md), and
[implementation plan](btc_adaptive_pipeline_plan.md).
Current user commands and limitations are in the
[research workflow](../docs/06_quant_research/research-workflow.md#adaptive-population-studies).

## Installation and initial live failures

The owner confirmed OpenCode was not installed and authorized installation and
configuration on this host. Official npm installation completed at
`C:\Users\hkpug\AppData\Roaming\npm\opencode.cmd`, version 1.18.29.
The hidden server (PID 30368 at setup time) listens at `127.0.0.1:4096` and
reports healthy. Its catalog lists the exact
`opencode-go/muse-spark-1.3-contributor` model with `high`. A visible CMD window was opened for private `auth login
--provider opencode-go` entry, and the official account page was opened for the
owner. No subscription or credits were purchased. See
[the CMD setup guide](../docs/03_setup_and_installation/opencode-windows.md).

Authentication is now confirmed by a no-model preflight and `codex login status`.
The requested live smoke command was rejected before process creation by
automatic approval review: research inputs/prompts might be sensitive, and
explicit approval of transmission to Codex/OpenCode and account usage was
required. No rejected action was retried or bypassed. A
[local request preview](../research/results/btc_live_request_preview_20260905/README.md)
documents the content, destinations and maximum eight calls across both tests.

The owner then explicitly approved the previewed content, destinations and
maximum eight calls with "yes do it". The approved smoke produced
[campaign_889b9784bc04485a](../research/results/btc_mixed_live_smoke_20260905/campaign_889b9784bc04485a/report.json):
the Sol/high request returned a valid proposal in 27.03 seconds, and OpenCode
returned an assistant APIError in 5.21 seconds. The campaign is PAUSED after
two attempts, with zero checker results and no retries. Codex reported 19,085
input tokens and 729 output tokens; its runtime model ID and monetary cost
were unavailable. Executor token/cost usage was not available in the adapter
failure record. A successful thinker call does not verify a complete live loop.

Read-only diagnosis recovered the nested cause: HTTP 400, non-retryable;
Muse only accepts automatic tool choice, while OpenCode's structured-output
mode forces a choice. The original failure is preserved, with a separate
[diagnostic record](../research/results/btc_mixed_live_smoke_20260905/campaign_889b9784bc04485a/diagnostic_followup.json).
The adapter now preserves redacted nested API errors and offers explicit,
persisted `json_text` mode. This mode omits the forced-format request, denies
all model tools and locally validates the complete JSON object; its schema is
included in the prompt budget. There is no silent fallback or retry.

The JSON-text correction passed 205 pipeline tests and independent review.
The next [adaptive attempt](../research/results/btc_adaptive_live_20260905/campaign_c2a7cbdad7b24288/report.json)
then exposed a local contract mismatch: its schema allowed
`diagnostic_rationale: null`, while the validator required nonblank study text.
The failed response and its usage remain intact; this attempt consumed two
calls and produced no checker result. The corrected schema and summary prompt
now agree with the validator. Six null/empty/whitespace regressions failed
before that fix and pass afterward; independent review confirmed parity.

## Successful live acceptance

[Campaign `campaign_e7879087ffc941e2`](../research/results/btc_mixed_live_acceptance_20260905/campaign_e7879087ffc941e2/report.json)
completed with STOP, three successful live role calls, one VERIFIED population
study and zero failures. The horizon summary covers 2,865 signals and 420,176
eligible baseline events. All 27 checks passed, including exact source identity,
saved prices/returns, all-four-horizon completeness and population eligibility.
The final review cites its exact result ID and does not propose another job.

The full campaign span was 148.23 seconds; provider calls took 71.40 seconds and
the recorded checker took 29.72 seconds. The
[zero-model replay](../research/results/btc_mixed_live_acceptance_20260905/campaign_e7879087ffc941e2/baseline_report.json)
matched tables, input identities and checker hashes in 29.47 seconds. These are
single observations under varying load, not a general performance benchmark.

All three calls report input/output usage: 51,774 input and 1,496 output tokens.
OpenCode reports `runtime_cost=0.0008059`; Codex cost and runtime model ID remain
unavailable, so this is not total campaign cost. The executor's reported model
and `high` variant match the requested configuration. A reporting-only follow-up
adds Codex's reasoning/cache-write aliases to supplemental aggregation while
preserving raw usage and separate output totals.

Both models saw explicitly unverified preview tables before the numerical check.
Their monotonic-gap hypothesis therefore demonstrates specification/review
mechanics on known summaries, not independent discovery or out-of-sample alpha.
Strategy gates were not rerun; signal eligibility is inherited from the frozen
parent packet and checked for identity/population consistency.

## Live adaptive completion

The owner approved raising the total allowance from eight to twelve calls after
seven had been used. [Campaign `campaign_3f13b814a0294bb6`](../research/results/btc_adaptive_live_final_20260905/campaign_3f13b814a0294bb6/report.json)
completed all five calls and both jobs with no failures, repairs or repeated
experiments. It recorded PROPOSE_NEXT after the first verified result and STOP
after the second, with exact evidence references and the child linked to its
parent result. Both `live_loop_verified` and `adaptive_sequence_verified` are true.

The thinker selected 180 minutes because its verified pooled signal-minus-
baseline gap was largest in magnitude. OpenCode selected volatility cohorts
with a rationale based on point-in-time regime availability. The horizon
summary passed 27 checks; the volatility comparison passed 29. The final
comparison retained all 2,865 signals and 420,176 baseline events:

| Volatility | Signals | Baseline events | Signal-minus-baseline mean return, percentage points |
|---|---:|---:|---:|
| HIGH | 423 | 63,936 | -0.0846774091 |
| LOW | 2,442 | 356,240 | +0.0013107811 |

This descriptively supports the stated concentration criterion for the selected
grouping. It is a selected historical diagnostic over dependent observations;
neither the positive LOW gap nor the negative HIGH gap establishes tradable alpha.

Campaign span was 315.03 seconds, recorded provider time 130.36 seconds, and
checker time 90.60 seconds. All five calls report input/output usage: 82,366
input and 3,689 output tokens, with 3,042 supplemental reasoning tokens reported
separately. `runtime_cost=0.0017835` covers the two OpenCode calls only; Codex
cost and runtime model IDs remain unavailable. No monetary savings are inferred.

The [two-study zero-model replay](../research/results/btc_adaptive_live_final_20260905/campaign_3f13b814a0294bb6/baseline_report.json)
matched both tables, input identities and checker hashes in 35.78 seconds.
This measures replay of accepted specifications; it does not compare independent
experiment selection or establish general speed/cost savings.

The [final call and validation audit](../research/results/btc_adaptive_prepared_20260905/live_validation_summary.json)
accounts for all twelve calls: ten completed and two failed, with none remaining.
Input/output usage is available for eleven calls; cost values cover only four.
Original campaign reports and failed responses remain intact. The audit also
recomputes supplemental usage from raw records with the tested Codex aliases.

Next, compare actual research decisions and reported usage against a fixed
experiment set before expanding worker freedom or campaign size. Do not infer
monetary savings or research-selection quality from accepted-spec replay alone.
