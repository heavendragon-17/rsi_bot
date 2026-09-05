# BTC AI pipeline MVP: bounded acceptance corrections

## Objective and scope

Complete the existing pipeline's controller guarantees before a live demo or
OpenCode integration. This is the next Luna implementation task. Keep the
thinker/executor/checker design and registered BTC tool; do not start another
alpha study, expand the tool catalog, replace the framework, or refetch data.
Use one implementation agent. Preserve existing uncommitted work.

Read `docs/INDEX.md`, `docs/agent-workflow.md`, and the
[original MVP handoff](btc_ai_pipeline_mvp_handoff.md).

The existing 15 pipeline tests pass independently. The saved-data report
records a fixture-model loop with real local arithmetic. No real model run has
been established. The new review probes used only local fixtures and patched
providers; no Codex, API, or network invocation occurred.

Evidence: [review probe results](../research/results/btc_ai_pipeline_review_81535d43/review_probes.json).
The source-change probe uses dedicated synthetic candles under a separate
`research/data/btc_pipeline_review_fixture_*` directory; it did not access or
modify the canonical four-year data.

## 1. Enforce invocation consent and restore frozen configuration (P1)

Locations: `btc_ai_pipeline.py:37,78`,
`app/research_pipeline/controller.py:130`, and the unused
`PipelineStore.config()` reader.

Observed: `run --offline-fixture --thinker-provider codex` reached the patched
Codex adapter twice despite no live flags. Separately, resuming a paused
campaign saved with `verification_mode=real` and model `saved-thinker`
completed using `fixture_validation` and model `fixture-thinker`.

Required:

- Reject incompatible offline/provider selections before any dispatch. Enforce
  non-fixture invocation authorization centrally, not only in argument parsing.
- Restore stored campaign settings before constructing providers for resume.
  Preserve model/provider identities, data mode, paths, effort, and budgets.
  Persisted original authorization may govern a normal resume; do not silently
  substitute defaults or expand authorization through new command-line values.
- A read-only status query must not require constructing runtime providers.
- Add mocked CLI and controller tests for both reproduced failures. No real
  provider call is needed to prove these restrictions.

## 2. Recover completed phases and enforce job limits (P1)

Locations: `controller.py:86-161,189-219,233-253`,
`storage.py:reserve_call`, `reserve_job`, and state persistence methods.

Observed: after a simulated crash immediately following persistence of a
completed executor response, resume called the executor again. With two calls
allowed, the counter rose from one to two; with the normal one-call limit this
would instead exhaust the budget before continuing local work. With
`max_jobs=2` and sufficient call budget, three jobs were checked while
`jobs_started` remained one.

Required:

- Recover completed, validated proposal/execution/review responses from durable
  attempts when downstream state has not yet been committed. Do not spend
  another model call to recreate a response already saved.
- Make corresponding job/result/decision transitions idempotent. Test crashes
  after provider completion and before result/decision state changes, not only
  resume of an already terminal campaign.
- Reserve each actual job exactly once, including follow-ups. Reject work at
  the cap and retain the unexecuted next proposal. Keep reservations and state
  transitions atomic enough to prevent two resumes claiming the same work.
- Keep genuinely uncertain calls paused until explicitly reconciled; do not
  turn a second generic resume into an implicit blind redispatch.
- Make REPAIR a durable actionable pause (or bounded repair job), so ordinary
  resume does not spend another thinker call reviewing identical failed evidence.

## 3. Bind execution and review to the frozen job (P1)

Locations: `controller.py:197,233-241`, `contracts.py:validate_review`.

Observed: thinker proposed `event_index=0`; executor changed it to `1` and
verification ran successfully. Thinker's review cited `unrelated-result`, yet
the controller saved a STOP decision attached to the current verified result.

Required:

- Define typed parameters for the registered tool. Validate the task and
  parameters before dispatch; reject event/source/mode changes to the frozen
  proposal except for documented controller-owned path resolution.
- Require review evidence references to identify the current result. Validate
  follow-up parent-result linkage. Preserve what the model actually cited;
  never manufacture a matching reference in the stored decision.
- Keep checker status authoritative. A malformed review or unverified input
  cannot authorize follow-up research as if verification succeeded. STOP may
  still mean stop on failure; it must not imply verification passed.
- Add negative tests for changed parameters and wrong/empty evidence references.

## 4. Validate current inputs before reusing verification (P1)

Locations: `tools.py:128-156`, `controller.py:205-219`.

Observed: after a verified synthetic real-mode run, changing the raw source
bytes without changing the packet manifest returned a cached VERIFIED result.
The source hash in the manifest was used as cache identity without checking
the current source file first.

Required:

- Check actual resolved source identity against the campaign's frozen inputs
  before a real-data cache hit. Pin and compare relevant packet hashes too.
  Changed or unreadable inputs must not produce a current verified success.
- Validate stored evidence integrity and artifact identity when reusing it.
  Keep historical evidence distinguishable from current-input validation.
- Route scientific identity/check mismatches into explicit failed checker
  evidence for review; record access/infrastructure failures as clear pauses
  without inventing numerical success.
- Add a test that warms the cache, changes raw bytes, and reruns with the same
  manifest. Also cover packet/evidence tampering and unchanged-input reuse.

## 5. Make provider controls and reporting truthful (P2, before live demo)

Locations: `providers.py:106-120`, `controller.py:262`.

Source review: configured effort, context budget, and output budget never reach
the adapter command or a local enforcement check. The report hardcodes
`live_model_verified=False` for every run. The subprocess timeout does not
implement the original handoff's owned-child-process cleanup requirement.

Required:

- Apply supported effort controls using verified local CLI documentation.
  Enforce controller-owned input/output limits where possible; clearly expose
  requested versus enforced/unsupported provider limits. Do not describe stored
  numbers as enforced token or cost caps when they are not.
- Verify structured-output schemas against the supported interface, including
  nested tool parameters. Keep schema validation consistent with local checks.
- Retain runtime usage/model metadata when actually available; otherwise null
  with a precise explanation. Derive live verification status from successful
  real-provider attempts and distinguish requested model IDs from reported IDs.
- Bound owned provider processes on timeout, including descendants. Test
  cleanup with local dummy processes or mocks; do not start a model to test it.

## Acceptance and return

Turn the reproduced cases above into focused regressions, fix the existing
implementation, and demonstrate the corrected offline STOP, follow-up-limit,
tamper/REPAIR, and crash/resume paths. Keep the existing arithmetic evaluator
unchanged. Update matching docs and task records.

Return changed files, tests, evidence paths, which review cases are now fixed,
and preflight plus an explicit opt-in live smoke command. Do not call a model,
install providers, change authentication, redeem usage, or add OpenCode in this
correction task. Live verification remains a separate owner-selected step
after these guarantees pass. Then integrate the cheaper executor adapter.
