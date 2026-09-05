# Independent BTC adaptive implementation review

Reviewed on 2026-09-05 against the [approved plan](btc_adaptive_pipeline_plan.md)
and [progress review](btc_ai_pipeline_progress_review_20260905.md).

Readiness review verdict: **both Important (P2) readiness findings are resolved and
independently verified**. No Critical or unresolved Important defect was
established within this review's scope. The checked population tools and bounded
adaptive flow substantially implement the approved design. Subsequent
transport and schema reviews are recorded at the end of this document;
this readiness verdict does not establish successful live integration.

The findings below preserve the original snapshot observations. The resolution
section records the independently repeated probes against the subsequent fixes.

## Findings

### 1. Resolved P2: Check parent ancestry before declaring the legacy inputs ready

Location: [inputs.py:75](../app/research_pipeline/inputs.py#L75),
`validate_inputs`, lines 75–82. The shared readiness check hashes the selected
baseline manifest but does not check that its run ID matches the horizon
packet's parent. That relationship is checked only inside
`verify_m5_horizons`, after proposal and executor dispatch.

Reproduction used the synthetic `real_fixture_layout` helper. Before campaign
creation, change only the configured baseline manifest's `run_id` to
`unrelated-parent`, leaving the horizon packet unchanged. Observed:

- `preflight(config)["inputs_ready"] == true`.
- Running with counting fixture providers consumes one thinker call and one
  executor call, then fails with `horizon packet is not descended from the
  requested baseline packet`.
- The durable attempt count is two and no numerical result is produced.

This directly affects the planned one-event mixed-provider smoke and violates
Task 1's requirement that invalid inputs consume zero model calls. Move the
checker-required parent relationship and applicable packet structural checks
into the shared readiness validation, so preflight and dispatch reject the
same incompatible packet pair.

### 2. Resolved P2: Revalidate frozen inputs before a resumed review consumes a call

Location: [controller.py:130](../app/research_pipeline/controller.py#L130),
lines 130–133, and [controller.py:482](../app/research_pipeline/controller.py#L482),
`_validate_result_artifact`, lines 482–490. The initial input gate runs only
when a campaign has no jobs. A recovered CHECKED job verifies its durable JSON
and evidence artifact, then sends the reviewer a result without checking the
current frozen source identities.

Reproduction used the synthetic adaptive packet and fixture policy. Interrupt
execution immediately before the first `_review`, leaving two completed
provider attempts and one VERIFIED result. Append a newline to the frozen M5
source, restore `_review`, and resume. Observed:

- Attempt count increases from two to three.
- The reviewer creates a `PROPOSE_NEXT` decision.
- Only the next study's preview detects the changed source hash and fails the
  campaign.

The historical result is still traceable to its original source hash; this
finding does not allege incorrect historical arithmetic. The defect is that a
campaign with invalid current inputs consumes another model call and advances
its adaptive decision before enforcing its frozen-input contract. Use the
shared input validation immediately before each new provider dispatch,
including recovered review phases. Preserve completed responses and historical
evidence; do not silently replace their identities.

## Independent resolution verification

The shared input validator now applies the legacy checker's ancestry rule.
Adaptive dispatch uses the study input identity validation, covering H1,
comparator, and parent signal bytes as well as the M5 source and manifests.
`ProviderRuntime._provider_call` invokes this gate before provider lookup and
budget reservation for every newly dispatched phase, including a recovered
review. These changes were inspected directly.

The exact two synthetic reproductions were then rerun with assertions:

| Probe | Original result | Corrected result |
|---|---|---|
| Wrong parent run ID before campaign creation | Preflight ready; two provider attempts | Preflight not ready; zero provider attempts or calls |
| Source bytes changed after checker commit and before review resume | Third provider attempt and PROPOSE_NEXT decision | Remains at two attempts; zero decisions; fails before reviewer dispatch |

Both assertions passed with the existing Conda `rsi` interpreter. New probe
directories use `readiness_fixed_probe_` and `review_resume_fixed_probe_`
prefixes beneath `.pytest_tmp_adaptive_review/`. No live calls, full-data
recomputation, or previously passed test-suite reruns were performed by the
reviewer to close these findings. Type annotation cleanup and later
documentation changes remain outside this focused verification.

## Scope and evidence

The reviewed snapshot was `.pytest_tmp_adaptive_review/review.patch`, including
its `NEW FILE` sections. Existing-file blob identities and normalized new-file
contents matched the current source when checked during the initial review.
The readiness changes received the focused independent verification recorded
above. Subsequent CLI, documentation, and checker-fingerprint changes remain
subject to the parent's integration verification.

The review inspected contracts, role prompts, controller/runtime/storage
recovery, portable input resolution, OpenCode session lifecycle, the population
tools and independent checker, reporting, baseline measurement, and covering
tests. The later `study_materialize.py` module was read for interface and
historical-input preservation; its full-data run was not repeated.

Only the two focused synthetic probe scenarios above, before and after their
corrections, were executed, using the existing
`C:/Users/hkpug/miniconda3/envs/rsi/python.exe`. Their temporary datasets and
SQLite campaigns are below `.pytest_tmp_adaptive_review/`. Neither probe used a
real provider. No implementation files, credentials, source datasets, or
historical campaigns were changed by the reviewer. Previously passing suites
were not rerun. The parent's reported test totals are integration evidence
supplied to the review, not independent test executions by this reviewer.

## Spec compliance and quality assessment

The implementation provides substantive numerical checks: exact raw trigger
and target lookup, gap/status classification, gross-return arithmetic,
all-four-horizon eligibility, parent signal identity, fixed population counts,
and an independent check of causal regime label joins. The output keeps sample
sizes and gross-return limitations explicit. No actionable Important/Critical
arithmetic defect was found in the reviewed code.

OpenCode persists its session before message dispatch and fails closed if that
write fails. Ambiguous transport/server failures attempt bounded cancellation;
unconfirmed cancellation becomes a durable uncertain attempt that generic
resume cannot redispatch. The catch-all deny and explicit structured-output
exception address the previously identified tool-boundary gap. No live
permission enforcement claim is made by this source review.

The adaptive path now carries a falsifiable proposal, uses typed task
parameters, lets the executor resolve a bounded cohort choice, requires checked
evidence for follow-up proposals, rejects repeated concrete studies, and
advances ordinary follow-ups without manual resume. This is a meaningful
bounded population experiment flow. The executor's analytical scope remains
narrow, and selection quality must be assessed from actual runtime decisions.

The deterministic baseline correctly replays accepted specifications and
compares numerical tables, input identity, and checker identity without model
calls. Its stated limitation is appropriate: it measures equivalence and
orchestration overhead, not independent hypothesis-selection quality or proven
monetary savings. The original snapshot lacked separate invalid-plan/REPAIR
counts, campaign/checker duration, and aggregate total/reasoning/cache usage
coverage. Subsequent source inspection confirms additions for these fields,
including an explicitly labelled campaign span and timing coverage for checker
results. Those additions were not independently benchmarked by this reviewer.
Comparative hypothesis-selection quality and monetary savings remain
unestablished by a replay of accepted specifications.

The missing historical baseline CSV was known and assigned for materialization,
so its absence is not reported as an overlooked defect. The materializer's new
derived packet, exact source checks, restricted zero-exclusion reconstruction,
and explicit unknown-original-byte-identity limitation fit the study input
contract. Live smoke, final adaptive evidence, documentation, and remaining
integration checks were still parent-owned work when this review was written.

## Explicit OpenCode JSON-text compatibility review

The explicit `opencode_output_mode=json_text` change received a separate
source review of configuration, CLI, runtime, persistence/resume, readiness,
reporting, adapter parsing, permission policy, and nested error diagnostics.
The default remains `json_schema`; neither mode introduces an automatic
fallback or provider retry. The runtime appends the required schema before
estimating the prompt budget and records the selected mode with the attempt.
Resume restores the stored mode instead of adopting current CLI arguments.

The initial JSON-text implementation accepted a valid first text part while
ignoring trailing prose, and its nested preflight controls still reported
`json_schema`. Both were identified during review and corrected before the
next live attempt. The explicit parser now concatenates all text parts and
parses once, ignores structured-field shortcuts, and rejects duplicate keys
and nonstandard NaN/Infinity constants. Preflight reports the selected mode
through its provider control record.

Independent in-memory FakeOpener probes against the corrections verified:

- Split JSON text parts form one accepted object.
- Trailing multipart prose, multiple objects, NaN, duplicate keys, and a
  structured-only shortcut are rejected without fallback or retry.
- Each completion probe issues exactly the expected two mocked requests:
  session creation and message dispatch. Permissions deny every tool, the
  message omits `format`, and the requested model and variant remain exact.
- Mocked preflight uses GET requests and reports `json_text` with
  `provider_enforced=false` and local validation enabled.
- Direct controller validation rejects an unregistered tool, a changed frozen
  horizon, and changed invariants.

No live calls, source edits, or passed-suite reruns were performed for this
compatibility review. Its closure establishes the explicit transport/parser
boundary; it does not establish that every outgoing adaptive schema exactly
matches all local semantic constraints. A subsequent live response exposed a
nullable `diagnostic_rationale` mismatch, which the parent assigned for a
separate schema audit and correction.

## Required diagnostic rationale correction

The subsequent outgoing adaptive execution schema now requires
`diagnostic_rationale` to be a string containing a non-whitespace character,
matching `validate_execution_plan`. The executor prompt explicitly requires
nonblank text even when the selected summary has fully fixed parameters and
forbids null. Both the source correction and its focused regression tests were
reviewed.

An independent in-memory JSON Schema/local-validator comparison covered both
study tasks with null, empty, whitespace-only, and meaningful rationale values.
All eight cases agreed: the first three values were rejected and meaningful
text was accepted. No model call, source edit, or full suite rerun was needed.

The broader audit also identified contextual combinations that the generic
wire schemas permit but the existing local validators reject, such as a changed
tool, mode, invariant list, or evidence reference. Those constraints are
already stated in the role context/prompts and remain enforced before tool
execution. More context-specific outgoing schemas are a possible improvement,
not a prerequisite introduced by this review. No remaining concrete blocker
was identified for the parent's stated bounded acceptance run: one population
summary followed by STOP with `next_job=null`, capped at two thinker calls,
one executor call, and one job.

## Completed live acceptance and adaptive evidence review

The one-job acceptance campaign `campaign_e7879087ffc941e2` completed three
provider calls, one VERIFIED population study, and a final STOP. Its saved
artifact, result hash, frozen input hashes, and zero-model baseline agree.
This establishes the corrected mixed-provider proposal/execution/checker/review
loop. The initial hypothesis was informed by a preview of the same population
statistics, so its descriptive agreement is not independent confirmatory
discovery. The two supplemental usage aliases in `measurements.py` and their
tests were also reviewed: Codex reasoning/cache-write counters now contribute
alongside OpenCode counters, canonical fields retain precedence, explicit zero
is preserved, and missing values remain unavailable.

The final adaptive campaign `campaign_3f13b814a0294bb6`, saved under
`research/results/btc_adaptive_live_final_20260905`, also passes this bounded
independent review. No Important or Critical finding remains in the reviewed
live evidence. Read-only assertions established:

- Both report evidence objects equal their saved artifacts and match their
  result hashes; both job specification hashes match their saved specifications.
- All seven current input byte hashes and all five current checker source
  hashes match the saved evidence. The summary has 27 passing checks and the
  cohort comparison has 29, including causal regime alignment with zero
  mismatches and zero unavailable regime events.
- The first PROPOSE_NEXT payload exactly equals the second job specification.
  Its `parent_result_id` is `result_a9abdd200b0c456e`, and its parent job points
  to the first job. The thinker selected 180 minutes because the first VERIFIED
  summary had its largest deficit there. OpenCode resolved `grouping=choose`
  to volatility, preserved all other parameters and ordered invariants, and
  recorded a rationale using the checked pooled statistics. The follow-up has
  a distinct task, cache key, and evidence ID; neither result reused evidence.
- Five COMPLETED attempts follow proposal/execution/review/execution/review.
  Three thinker calls, two executor calls, and two jobs equal the persisted
  caps. There are no failures. Both reviews reference the correct current
  result; the final action is STOP with `next_job=null`. Saved prompt estimates
  are below the controller's context cap; this is an estimate, not a provider
  token limit.
- The saved zero-model replay is MATCHED for both studies. Its artifacts agree
  on tables, identities, checker hashes/check records, evidence IDs, accepted
  parameters, and population rules. This checks numerical equivalence for
  accepted specifications, not independent model selection quality.

The numerical interpretation in the final review is accurate. At 180 minutes,
the HIGH-volatility signal-minus-baseline mean difference is
`-0.08467740912493296` percentage points, below the pooled
`-0.011390807758833159`; LOW is nonnegative at
`+0.0013107811085728734`. These meet the two explicitly stated descriptive
hypothesis conditions. HIGH/LOW counts sum to 2,865 signals and 420,176 baseline
events, all complete; separately weighting each population's subgroup means
reconstructs its pooled mean within floating-point tolerance. A common-weight
average of the subgroup differences is not required because signal and baseline
cohort proportions differ.

The chain supports operational adaptive-loop success and an evidence-informed
diagnostic choice. It does not establish independent discovery, statistical
significance, causation, alpha, executable P&L, or monetary savings. Eligibility
is inherited from the frozen preparation packet; strategy gates were not
replayed. Reported cost covers available OpenCode cost records, while Codex
cost remains unknown. No model calls, strategy/data suite reruns, or source
edits were performed during this evidence review.
