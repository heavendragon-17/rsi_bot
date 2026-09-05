# Content proposed for the bounded live BTC research tests

Approval received: after reviewing this content, the owner explicitly replied
"yes do it" to the payload, destinations and eight-call limit. The resulting
smoke campaign is `campaign_889b9784bc04485a`; it paused after the thinker
succeeded and the executor returned an API error. Two calls were used, with
no automatic retry. The earlier blocked command and this local preview remain
preserved below as provenance.

Both provider connections are ready. The live command was rejected before it
started, so no live campaign or external model call was created. This preview
was generated entirely locally with scripted responses and a real numerical
check of the frozen BTC event.

## Destinations and caps

- Codex CLI, using the existing ChatGPT login, requested model `gpt-5.6-sol`,
  effort `high`: at most two thinker calls for the smoke and three for the
  adaptive demonstration.
- OpenCode Go, through the installed local OpenCode server, requested model
  `opencode-go/muse-spark-1.3-contributor`, effort `high`: at most one executor
  call for the smoke and two for the adaptive demonstration.
- Maximum total: eight model calls and three research jobs. No automatic retry
  after a provider failure. Calls use account quota and may have provider charges;
  no monetary price is assumed or subscription purchased by this task.

## Research content

The requests contain the research objective/hypothesis, registered task names,
JSON response schemas, budget limits, frozen parameters and invariants, local
dataset/result paths (including usernames), SHA-256 hashes and source provenance.
The reviewer also receives verified event timestamps, prices, horizon returns,
checker results and preceding model proposals/decisions. Adaptive studies add
signal/baseline counts and gross-return tables for 60/120/180-minute horizons,
plus the chosen calendar-year or causal regime comparison.

Credentials are not included in these prepared prompts. Provider authentication
is handled by the existing local clients. The current Codex CLI runs from this
repository with its existing read-only sandbox and can load repository
instructions/context; OpenCode permits only its structured-response operation.

The three smoke request examples are directly inspectable:

1. [Initial thinker request](proposal_request_preview.json)
2. [Executor request](execution_request_preview.json)
3. [Thinker review request](review_request_preview.json)

These show the actual prompt construction and response schemas with fixture
proposal wording. Live model wording and generated identifiers will differ.
The checker data are real local evidence, not fabricated returns. The saved
[two-study report](../btc_adaptive_fixture_final_20260905/campaign_19cbc72a47114e1c/report.json)
shows the corresponding population evidence available to the adaptive phase.

## Approval-review block

Automatic approval review rejected the live command because research inputs and
derived prompts could be sensitive and would be transmitted to external
Codex/OpenCode services, with possible account usage, without explicit approval
of that payload and those destinations. Bounded call limits did not satisfy
that requirement. The rejected command was not retried or routed around.

## Owner approval and bounded execution

The owner approved this content, these destinations and the original maximum
eight calls with "yes do it". Two failed integrations used four calls; a
corrected one-job live acceptance then passed all three role calls, independent
checking and final review. Its zero-model replay matched exactly.

With seven calls used, the owner explicitly selected "Approve up to 12 total
calls" in response to the request to finish the two-study live test. The next
campaign permits at most three thinker calls, two executor calls and two jobs,
using the same research content and provider destinations. It starts with the
population summary and selects one distinct cohort study from verified evidence.
There are no automatic retries. OpenCode uses explicit `json_text` mode, which
denies all tools and validates the returned object locally.
