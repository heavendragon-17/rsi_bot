# BTC pipeline v2: task identifier correction

The v2 campaign `campaign_3a869ced481f44ab` reached Codex successfully and
received a structured proposal. Its `task` value was a natural-language
instruction. The old schema allowed any string, while the controller required
the exact identifier `verify_m5_horizons`. The prompt did not provide that
registered task contract. This was an integration-contract defect.

The [original report](results/btc_ai_pipeline_live_smoke_v2/campaign_3a869ced481f44ab/report.json)
retains the full produced response in the attempt, even though it was not
accepted as the job proposal. It records one thinker call, no executor call,
no result or decision. The reported 20,404 input tokens differ from the
controller's 305-token estimate for its own prompt: that estimate does not cap
the total input assembled by Codex. The supplied 6,000 context setting is not
a provider token limit. Larger research campaigns should account for this
measured overhead rather than treating a short controller prompt as total cost.

## Local correction

- One canonical task identifier is shared by the registry, schemas, fixtures
  and local validators. Proposal/follow-up `task` and execution `task`/`tool`
  are constrained to that exact value, without coercing descriptive prose.
- Every role gets the actual tool catalog, scope, parameter schema, frozen mode
  and budget. Proposal instructions specify the initial parent and event;
  executor instructions require exact parameter/invariant copying; review
  instructions specify current-result references and follow-up requirements.
- Schema constraints reject empty required text/list values before generation.
  The supported subset includes string patterns and array minimum sizes;
  see [official schema guidance](https://developers.openai.com/api/docs/guides/structured-outputs#supported-schemas).
- Semantic context checks now happen inside the recorded attempt boundary.
  Rejected responses within the output budget remain on FAILED attempts with
  their usage, attempt/job IDs and error. The controller does not mark them
  completed before discovering their task, mode, parameters or references
  violate the job contract.

## Validation and scope

All 69 existing pipeline/schema/provider-error tests pass, plus 14 new task
contract regressions. The new checks replay the actual v2 response, reject
descriptive identifiers in proposal/execution schemas and validators, verify
nonempty fields, retain failed response attribution across all three phases,
and complete one full fixture loop with explicit task context.

No new runtime model invocation or campaign was started. The v1/v2 reports and
databases were not edited, and no saved rejected proposal was rewritten to
force acceptance. No change was made to the BTC numerical evaluator or provider
authentication. Actual acceptance and behavior of the new prompts still require
an explicitly authorized live smoke test. The next integration milestone remains
one completed live loop, before cheaper-provider integration or hypothesis search.
