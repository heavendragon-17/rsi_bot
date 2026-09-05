# AI research pipeline progress review — 2026-09-05

Reviewed implementation commit `9553715` and evidence commit `447ad20` in the
current OneDrive checkout. This was a review of existing software and evidence;
no runtime model invocation or new research campaign was performed.

## Assessment

The repository has a working bounded orchestration MVP. Autonomous experiment
selection, meaningful delegated research work, and demonstrated cost savings
remain unfinished.

The implemented process is:

1. A thinker proposes a structured job.
2. An executor returns a structured plan using the registered task and frozen parameters.
3. Python executes the tool and verifies source identity and numerical evidence.
4. The thinker reviews the checker result and selects STOP, REJECT, REPAIR, or PROPOSE_NEXT.
5. SQLite preserves proposals, attempts, results, decisions, reservations, and recovery state.

The implementation is in [controller.py](../app/research_pipeline/controller.py),
[contracts.py](../app/research_pipeline/contracts.py),
[providers.py](../app/research_pipeline/providers.py),
[storage.py](../app/research_pipeline/storage.py), and
[tools.py](../app/research_pipeline/tools.py).

## Evidence of progress

| Milestone | Observed evidence |
|---|---|
| Data and deterministic evaluation | Four-year BTC inputs, baseline, horizon, and regime artifacts exist. |
| Offline orchestration | Tests cover contracts, budgets, evidence tampering, caching, and crash/resume behavior. |
| Live Codex integration | V3 completed proposal, execution, checker verification, and review. |
| OpenCode adapter | Implemented; contract tests and historical no-call preflight exist. No saved live OpenCode attempt was found. |
| Adaptive research | Fixed verification task only; no live evidence-driven experiment follow-up demonstrated. |

The successful [v3 report](../research/results/btc_ai_pipeline_live_smoke_v3/campaign_e895a5b494764ea2/report.json)
records one job, three completed provider attempts, one VERIFIED result, no
failures, and STOP. Requested models were Sol/high for proposal and review and
Luna/high for execution. The
[checker evidence](../research/results/btc_ai_pipeline_live_smoke_v3/campaign_e895a5b494764ea2/job_57568a847fb54954/artifacts/evidence.json)
verifies one existing event at exact 60-, 120-, and 180-minute targets. Alpha
remains NOT_ASSESSED. Runtime model IDs are null, so exact model identity is
reported as unverified.

V3 used 61,275 reported input tokens and 950 output tokens across the three
calls, with 60.524 seconds of campaign wall time. Dollar cost was not recorded.
The input count substantially exceeds the controller's prompt-only estimates;
the configured context/output budgets are estimates, not provider token caps.
This smoke does not establish that delegation saves money.

The latest [OpenCode-named saved-data report](../research/results/btc_ai_pipeline_opencode_offline_saved_final/campaign_4fdb9927075b43cf/report.json)
uses fixture providers with real local data. Its successful checker is valid
offline integration evidence; it does not establish OpenCode model execution.

V1's schema failure and V2's task-identifier rejection are historical failures
followed by local contract corrections and the successful v3 run. The old task
record omitted the v3 success; this review records that outcome without editing
historical campaign evidence.

## Findings to address before the next live run

1. **Relocated dataset paths cause failure after a healthy preflight.** The saved
   horizon manifest contains an absolute source under the old
   `C:\Users\hkpug\Documents\GitHub\rsi_bot` checkout. The current root is under
   OneDrive. Campaign creation preserves the old path (controller lines 119–129),
   and execution passes it to the checker (500–508). Preflight checks the current
   configured data directory instead (777–794). A read-only reproduction returned
   `data.readable=true` and both packet manifests present, then
   `ToolRestrictionError: source_csv is outside the registered research boundary`.
   This validation happens after proposal and executor dispatch. Resolve current
   data locations using configured paths and the expected source hash, retain
   original locations as provenance, and validate the exact checker inputs before
   any provider call. Preserve hash checks and path restrictions.

2. **OpenCode message timeouts lose the information needed to reconcile work.**
   The adapter creates a session and posts its message (providers lines 490–527).
   Its timeout error (658–663) drops the session ID and performs no abort/status
   request. The controller records a FAILED attempt and permits a later resume
   because the error is retryable; this bypasses the protection for uncertain
   RUNNING attempts. An injected opener reproduced two POST requests, a timeout,
   no retained session ID, and no abort request without contacting a server.
   Persist the session identity before dispatch; abort or reconcile that session
   before retrying uncertain work. OpenCode documents session status, messages,
   and an abort endpoint in its [server API](https://opencode.ai/docs/server/).
   The probe establishes missing lifecycle handling; it does not claim a live
   server continued generating after a client disconnect.

3. **The OpenCode permission list does not establish denial of every tool.**
   It enumerates built-in permission names (providers lines 40–57, 499–503)
   without a catch-all. Custom/MCP tool names are not covered by that list;
   their behavior depends on inherited configuration. OpenCode documents
   wildcard matching for those names in its
   [agent permissions](https://opencode.ai/docs/agents/#permissions).
   Add and verify a catch-all policy while allowing only the structured-output
   mechanism needed by the adapter. No unregistered tool execution was attempted
   or observed during this review.

## Scope limitations relevant to the original objective

- The only registered task is `verify_m5_horizons` (tools line 317). Model-owned
  parameters are `mode` and `event_index` (contracts lines 38–66). The initial
  prompt requests event zero (controller line 456).
- The executor must copy parameters and invariants (controller lines 486–488).
  It currently adds a model round trip without doing independent implementation
  or substantial analytical work.
- The reviewer receives current evidence and recent decisions/failures, but not
  the full current proposal, research question, or falsification criteria
  (controller lines 582–594).
- A `run()` processes one job and returns; another resume advances a follow-up
  (controller lines 168–194). REPAIR pauses without an implemented repair workflow.
- Reports hardcode `GLM adapter integration` as the next capability (controller
  line 719). Derive readiness and recommendations from observed milestones.
  Also distinguish provider-call success from full-loop success: the historical
  V2 report says `live_model_verified=true` despite having no executor/result.

## Recommended sequence

1. **Readiness correction.** Fix the three findings above. Acceptance: the current
   checkout passes exact-input preflight and a fixture-provider/saved-data check;
   invalid inputs consume zero model calls; uncertain OpenCode work cannot be
   blindly redispatched; the intended tool boundary is covered by offline tests.

2. **One mixed-provider integration smoke.** With explicit runtime authorization,
   use the configured Codex thinker and OpenCode executor with the existing two
   thinker calls, one executor call, and one job caps. Save requested/reported
   models, usage availability, elapsed time, structured output, checker evidence,
   and final decision. Treat missing metadata explicitly. Avoid automatic retries
   in this initial integration test.

3. **One meaningful adaptive research campaign.** Expose two or three existing
   BTC research capabilities through typed experiment specifications. Supply the
   thinker with compact study summaries, the objective, prior experiments, and
   rejection/falsification criteria. Give the executor a meaningful bounded
   analytical or implementation job. Keep numerical acceptance with the checker.
   Complete one experiment and one distinct follow-up selected because of the
   first result, within a fixed campaign budget, with no manual resume between
   ordinary completed jobs. Persist the reason for that choice and verify
   crash/resume idempotence. Rechecking the same event or reusing the same cache
   does not meet this research acceptance criterion.

4. **Measure the hierarchy before scaling it.** Compare a fixed task set using
   the hierarchy and an appropriate simpler baseline. Track accepted results,
   invalid plans, repairs, total tokens, available cost, and wall time. Add
   experiment memory that helps the thinker avoid repeated rejected ideas.
   Expand autonomous duration/concurrency only after these results justify it.

## Verification performed

Used the existing Conda `rsi` interpreter. The seven focused suites
`test_btc_ai_pipeline`, `test_btc_ai_pipeline_opencode`,
`test_btc_ai_pipeline_provider_errors`, `test_btc_ai_pipeline_schemas`,
`test_btc_ai_pipeline_task_contract`, `test_btc_research_phase1`, and
`test_btc_m5_horizon_diagnostic` passed: **109 tests in 27.97 seconds**.
Pytest emitted one cache-write permission warning. The unrelated full repository
test suite was not run. Read-only input checks and an injected OpenCode timeout
probe established the additional findings above. Production code and historical
campaigns were unchanged.
