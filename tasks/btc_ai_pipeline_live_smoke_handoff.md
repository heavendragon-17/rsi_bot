# BTC pipeline: first live integration smoke test

## Aim

Prove one real thinker -> executor -> deterministic BTC check -> thinker review
loop. Keep the existing four-year M5 event verification as the single job.
This is integration validation; it is not an alpha study or a general autonomous
research campaign. No OpenCode adapter or new research tool is required here.

Read `docs/INDEX.md` and `docs/agent-workflow.md` first. Preserve current files.

## Readiness checked on 2026-09-04

- The corrected pipeline suite independently passes: 37 tests.
- With approved normal local access, `codex login status` reports ChatGPT login
  and preflight reports all BTC source files readable. Managed-sandbox commands
  can instead report a missing home directory or unreadable data. Use supported
  local execution access; do not change ACLs or authentication to hide this.
- The local model cache lists `gpt-5.6-sol` and `gpt-5.6-luna`. This is evidence
  for selecting candidates, not a successful live access test. The report's bare
  `astra` and `glm` strings were not validated as model IDs for this adapter.
- For this integration test only, propose Sol/high and Luna/high. Both effort
  values pass the current adapter. Its static effort allowlist currently rejects
  `max` despite the local cache listing it. Do not silently treat `max` as `high`;
  use the explicitly selected high settings for this test. Astra/GLM remains the
  intended later pairing, subject to supported access and the OpenCode adapter.
- The supported structured-output and saved-login mechanism is described in
  [official Codex documentation](https://learn.chatgpt.com/docs/non-interactive-mode).

## One remaining recovery correction before dispatch

In `app/research_pipeline/controller.py`, `_next_incomplete_job` skips a CHECKED
job once a decision exists. A process crash after `create_decision` commits but
before `_apply_decision_status` therefore prevents applying the saved decision
on resume. A local fixture probe saved STOP, resumed, and remained RUNNING with
three attempts: [probe evidence](../research/results/btc_pipeline_smoke_readiness_cffaf6e8/readiness_probe.json).

Replay the committed decision's state effects idempotently before skipping that
job, or atomically persist the decision with those effects. Add a focused
regression that crashes *after* decision commit, then proves STOP/REJECT/REPAIR
state is restored with no new calls, results, decisions, or budget reservation.
Update matching documentation and run the focused suite. No broader redesign.

## Execution boundary

Preparing this brief and passing offline tests do not authorize model calls.
Run the live command only when the owner's task message explicitly asks to run
this smoke test with the selected pairing and limits. Otherwise stop with the
ready command. Existing live opt-in remains required by the CLI.

Use one fresh campaign/database. Cap the entire test at two thinker invocations,
one executor invocation, and one job. Do not create another campaign, switch
models, increase limits, or retry paid/model work after a failure. Record the
failure and stop; local diagnosis may continue. These are controller invocation
caps, not a guarantee of three provider-internal turns or a fixed token charge.
No paid API fallback, installation, authentication change, or usage reset.

Run no-call preflight first under the same supported local execution context:

```powershell
C:\ProgramData\anaconda3\envs\rsi\python.exe btc_ai_pipeline.py preflight --thinker-provider codex --thinker-model gpt-5.6-sol --thinker-effort high --executor-provider codex --executor-model gpt-5.6-luna --executor-effort high
```

After the recovery fix and explicit owner opt-in:

```powershell
C:\ProgramData\anaconda3\envs\rsi\python.exe btc_ai_pipeline.py run --live --confirm-live --thinker-provider codex --thinker-model gpt-5.6-sol --thinker-effort high --executor-provider codex --executor-model gpt-5.6-luna --executor-effort high --max-thinker-calls 2 --max-executor-calls 1 --max-jobs 1 --timeout-seconds 120 --db research/results/btc_ai_pipeline_live_smoke_v1/pipeline.sqlite --output-dir research/results/btc_ai_pipeline_live_smoke_v1
```

If that database already contains a campaign, inspect it and stop rather than
starting another live attempt under a fresh name. Ensure the actual model
prompts identify the registered task and allowed parameters; a schema alone is
not a full task instruction. Address any concrete interface problem locally
before another model invocation, and report it if it prevents this single test.

## Return

Return the saved proposal, execution plan, raw-source/checker evidence, and
thinker decision, plus campaign ID, actual invocation counters, requested and
reported models, available usage, and elapsed time. Show no call beyond the cap.
The next proposal must be saved but not executed. A failure is an integration
finding, not an excuse to fabricate success or fall back to fixtures.

Stop after this milestone. After success, the next integration is the cheaper
executor adapter; actual BTC hypothesis search will need a separately bounded
research-job contract beyond today's one-event verifier.
