# Bounded adaptive BTC research implementation plan

Goal: implement the readiness corrections and meaningful two-experiment campaign
approved by the owner on 2026-09-05 in response to the progress review.
Spec: [approved progress review](btc_ai_pipeline_progress_review_20260905.md).

Architecture: extend the existing durable controller and fixed Python tools.
Preserve the one-event verification task. Add population horizon summaries and
cohort comparisons over frozen BTC data; allow the executor a constrained choice
of diagnostic and require numerical checker evidence before thinker adaptation.
Tech stack: existing Python/SQLite/pandas/pytest and local Codex/OpenCode adapters.

## Global constraints

- Use existing Conda rsi environment and provider authentication. Do not change .env.
- No strategy, trading configuration, order execution, or Telegram changes.
- Preserve historical campaigns and source packets. New outputs use new directories.
- Model responses remain structured data; never execute model-generated shell/code.
- Preserve durable budget reservation, recovery, immutable input hashes and cache checks.
- Treat the user's approval as authorization for the staged implementation and bounded
  live verification; avoid repeating already answered permission questions.
- Live smoke: requested Sol/high thinker, configured OpenCode Muse Spark/high executor,
  two thinker invocations, one executor invocation, one job, no automatic retries.
- Adaptive demonstration: at most two jobs, three thinker invocations and two executor
  invocations. No automatic retry after a provider failure. Report actual available
  usage and costs; never invent prices or identities.
- Changes and test evidence must be independently reviewed and documented.

## Task 1: Exact-input readiness and portable paths

Files: new app/research_pipeline/inputs.py; controller.py, tools.py; focused tests.

- [x] Add regressions for moved checkouts, preflight using actual checker inputs,
  changed source hashes, and failure before provider dispatch.
- [x] Resolve configured dataset files by their registered names and frozen hashes;
  retain manifest paths only as provenance. Validate exact packet and raw identities.
- [x] Use the same resolution in preflight, campaign creation/execution and cache checks.
- [x] Run covering tests and record evidence.

## Task 2: OpenCode lifecycle and permission boundary

Files: providers.py or extracted opencode_provider.py; focused OpenCode tests.

- [x] Add post-session timeout, abort uncertainty, callback persistence, and catch-all
  permission regressions and observe failure before implementation.
- [x] ProviderRequest.metadata may contain persist_provider_session: callable(dict).
  Invoke it with provider, session_id and server_url immediately after session creation,
  before posting a model message. Callback failure must prevent model dispatch.
- [x] Timeout/transport failure after message dispatch retains session identity and
  attempts bounded abort; mark external state uncertain unless cancellation is confirmed.
  Uncertain errors use kind interrupted_uncertain with manual_reconciliation_required.
- [x] Deny all tools using a catch-all rule; preserve structured output operation.
- [x] Parent integrates durable callback storage and blocks generic uncertain resume.
- [x] Run covering tests and record evidence. Do not call a live provider in this task.

## Task 3: Checked population research capabilities

Files: new study_tools.py and study_checks.py; focused study tests.

- [x] Implement summarize_m5_horizons with mode parameter, and compare_m5_cohorts with
  mode, horizon_minutes (60/120/180) and grouping (calendar_year/trend/volatility).
- [x] Return compact signal/baseline sample counts, mean/median returns, positive
  fractions and mean differences. Label descriptive gross returns and alpha NOT_ASSESSED.
- [x] Cohort labels must use information available at event time; use existing regime
  helpers and validated current H1 input for trend/volatility.
- [x] Validate saved returns against exact raw trigger/target candles independently;
  reject stale/tampered/incomplete identities and never claim a fill or profit.
- [x] Produce deterministic result/evidence identity and write artifacts under the job.
- [x] Unit-test known arithmetic, bad timestamps, missing/changed inputs and regime
  alignment using synthetic frames. Avoid full-data/model calls in unit tests.

## Task 4: Adaptive contracts, controller and measurement

Files: contracts.py; controller.py plus focused extracted helpers; storage.py;
providers fixture implementation; btc_ai_pipeline.py; new adaptive tests.

- [x] Extend typed proposal/execution/review schemas for the new tasks while keeping
  legacy verification records valid. Cohort proposals can leave grouping as choose;
  executor must select a concrete registered grouping and give a diagnostic rationale.
- [x] Supply objective, current proposal/falsification criteria, compact study context
  and relevant prior decisions/evidence to executor and reviewer.
- [x] Add opt-in adaptive campaign mode that progresses ordinary completed jobs in
  one run up to persisted caps. Require distinct research specs for follow-ups.
- [x] Persist provider session metadata; uncertainty requires explicit reconciliation.
- [x] Produce observed readiness/full-loop status and measured input/output tokens,
  reported cost availability, failures, results and elapsed time; remove hardcoded
  next-adapter recommendations.
- [x] Provide a deterministic baseline for the same experimental specifications and
  compare numerical identity, provider overhead and available measured usage.
- [x] Test two different jobs, evidence-dependent choice, budget stop, error pause,
  changed data and crash/resume without duplicate work or reservations.

## Task 5: Integration, evidence and documentation

- [x] Run focused suites and relevant static/documentation checks; independent review.
- [x] Run saved-data validation and no-call provider readiness checks in this checkout.
- [x] Run one bounded mixed-provider smoke if exact model/provider/data readiness passes.
      Corrected population acceptance `campaign_e7879087ffc941e2` completed all
      three live role calls, VERIFIED evidence and STOP; scripted replay MATCHED.
- [x] Demonstrate two distinct adaptive jobs with verified evidence and measured baseline.
  Label fixture, real-local and live-model demonstrations independently.
- [x] Update current architecture/research/testing docs and tasks/todo.md with exact
  commands, evidence paths, limitations and remaining external blockers.

Review interfaces: task 2 only writes provider files/tests; task 3 only writes new
study modules/tests. Parent owns controller, storage, contracts, input resolution,
CLI and documentation integration. Both consume existing ProviderRequest and
ToolContext; no overlapping implementation file ownership is permitted.

## Live integration adjustment after the first two calls

The initial thinker succeeded, but Muse rejected OpenCode's forced tool choice
with HTTP 400. That failed event-verification campaign remains preserved and
will not be resumed or retried automatically. The explicit JSON-text output
mode retains local validation and denies all model tools; its schema is counted
in the prompt budget, and the choice is persisted.

After offline tests and independent review of that correction, use one new
adaptive campaign (maximum three thinker and two executor calls). Its first
fully checked/reviewed population job is the corrected live integration check;
the controller only advances to job two on a valid evidence-backed follow-up.
This combines integration verification with the requested two-study test while
using at most seven calls including the two failed-smoke attempts, within the
owner's explicitly approved total of eight. No new call is permitted as an
automatic retry after a failure in this campaign.

## Contract correction after the next two calls

Campaign `campaign_c2a7cbdad7b24288` failed before checking data: the executor
returned `diagnostic_rationale: null`, which the outgoing adaptive schema allowed
but the local study contract correctly rejected. Four of the owner's eight
approved attempts have now been used. Both failed campaigns remain unchanged.

- [x] Reproduce null/empty rationale acceptance by the outgoing schema offline.
- [x] Require nonblank rationale text in the adaptive schema and clarify that
      fixed-parameter summaries also require an explanation; keep local checks.
- [x] Run focused regression checks and independent contract review: 213 pipeline
      tests pass, including six observed red cases before the rationale fix;
      mypy (21 modules), Ruff and independent eight-case contract parity pass.
- [x] Run a new one-job acceptance campaign with at most two thinker calls and
      one executor call, bringing the authorization total to at most seven.
      This is a deliberate test of a reviewed correction, with no automatic
      retries. A new two-job live run requires five calls and cannot fit within
      the remaining allowance; the two-job real-data fixture evidence remains
      separately labelled.
- [x] Replay any accepted live study without models and record exact outcome,
      usage coverage, failures and remaining validation work.

## Approved live adaptive completion

The one-job live acceptance used three successful calls and its zero-model
replay MATCHED (29.47 seconds). The total is seven attempts across the three
preserved live campaigns. The owner explicitly approved raising the total from
eight to twelve calls in response to the question about finishing the two-study
test. This authorizes one new campaign capped at three thinker calls, two
executor calls and two jobs, using the same previewed research content and
Codex/ChatGPT plus OpenCode Go destinations. No automatic retries.

- [x] Finish the new live population summary and evidence-dependent cohort study:
      `campaign_3f13b814a0294bb6` used five successful calls, selected a 180-minute
      volatility comparison from the first VERIFIED summary, verified both jobs
      and stopped without a third proposal or any failures.
- [x] Replay both accepted study specifications with no model calls: both MATCHED
      in 35.78 seconds, including tables, input identities and checker hashes.
- [x] Record final call accounting, reported usage and independent evidence:
      twelve calls total, ten completed and two failed; final audit is
      `research/results/btc_adaptive_prepared_20260905/live_validation_summary.json`.
