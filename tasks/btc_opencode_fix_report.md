# OpenCode lifecycle and permission correction

Date: 2026-09-05. Scope: task 2 of the
[approved implementation plan](btc_adaptive_pipeline_plan.md).

## Implemented behavior

- The adapter validates an optional synchronous
  `request.metadata['persist_provider_session']` callable before creating a
  session. Immediately after validating the returned session ID, it invokes
  the callback with a fresh dictionary containing exactly `provider`,
  `session_id`, and `server_url`, before posting a model message.
- Callback failure prevents model dispatch. The resulting retryable
  `session_persistence` error retains the identity, marks
  `provider_call_performed=False`, and records only the exception type rather
  than an arbitrary persistence error message. A deadline exhausted during
  persistence similarly preserves identity without posting a message or abort.
- Timeouts, connection failures, incomplete HTTP reads, and ambiguous HTTP
  408/5xx responses after message dispatch preserve identity and issue exactly
  one `POST /session/{id}/abort` with the same directory and session header.
  Cleanup has its own five-second HTTP timeout, available even after the main
  request deadline. There is no provider retry or server-process termination.
- Only the documented JSON boolean `true` confirms cancellation. With that
  response, the original retryable timeout/transport failure is retained and
  `manual_reconciliation_required=False`. False, empty, object-shaped, or failed
  abort responses produce retryable `interrupted_uncertain` with
  `manual_reconciliation_required=True`, the original error kind, session
  identity, and bounded abort diagnostics. Explicit 4xx authentication/rejection
  errors preserve session identity without issuing an unnecessary abort.
- Session permissions now deny `permission='*', pattern='*'`, covering built-in,
  custom, and MCP tool names. The only subsequent allowance is the exact
  `StructuredOutput` name. OpenCode injects that built-in schema-return tool,
  then applies permission filtering; denying it would break structured output.
  The prompt still uses `format.type='json_schema'` and `retryCount=0`.
- `OpenCodeProvider` remains importable from `providers.py`. Its implementation
  moved to `opencode_provider.py`; shared error extraction moved to
  `provider_diagnostics.py`. Existing Codex diagnostic helper imports remain
  available. Minor type narrowing/import cleanup and explicit Codex timeout
  exception chaining make the touched files lint clean.

## Evidence

All Python commands used the existing
`C:/Users/hkpug/miniconda3/envs/rsi/python.exe`. No model was invoked, credentials
were unchanged, and no commit or server-management action was performed.
The current OpenCode suite mocks every HTTP call, including unreachable-server
preflight.

1. Before implementation:
   `python -m pytest tests/test_btc_ai_pipeline_opencode.py -q -p no:cacheprovider --tb=short`
   produced **19 failed, 5 passed**. Failures demonstrated the missing callback,
   unsafe dispatch after persistence/deadline failure, absent session identity,
   missing abort, unclassified incomplete reads, and fixed-list permissions.
2. After implementation, extraction, and cleanup:
   `python -m pytest tests/test_btc_ai_pipeline_opencode.py tests/test_btc_ai_pipeline_provider_errors.py tests/test_btc_ai_pipeline.py -q -p no:cacheprovider -k 'not test_controller_persists_actionable_failure_and_does_not_retry'`
   produced **72 passed, 1 deselected**. All **24 OpenCode tests** are included.
3. The initial combined run without the exclusion produced **72 passed,
   1 failed**. `test_controller_persists_actionable_failure_and_does_not_retry`
   expects one mocked Codex call against real checkout data, but the concurrent
   exact-input readiness change stops before dispatch, leaving the count zero.
   The parent task was notified to update that controller-dependent fixture;
   this provider task did not edit that test or bypass input readiness.
4. `C:/Users/hkpug/miniconda3/Scripts/ruff.exe check` over the three provider
   files and the OpenCode test file passes. Ruff is absent as a module in the
   `rsi` environment; the existing executable was used without installing
   packages. Its only remaining warning is the repository's obsolete `UP038`
   ignore entry.
5. `python -m mypy app/research_pipeline/opencode_provider.py app/research_pipeline/provider_diagnostics.py app/research_pipeline/providers.py --follow-imports=silent --platform linux`
   reports **no issues in three files**. The explicit platform resolves the
   existing platform-specific Codex `os.killpg`/`os.getpgid` typing on this
   Windows host. Unused existing mypy override sections produce notes.
   A separate native Windows mypy run over `opencode_provider.py` and
   `provider_diagnostics.py` also passes with no issues in two files.
6. `git diff --check` passes. Provider source sizes at handoff are 314 lines
   for `providers.py`, 494 for `opencode_provider.py`, and 157 for
   `provider_diagnostics.py`, all below 600 lines.
7. `python scripts/check_markdown_links.py` passes for **329 Markdown files**.

## Parent integration requirements

- Provide the callback for every durable OpenCode attempt and commit its
  dictionary into the attempt's `request_json` before returning from the
  callback. Do not serialize the callable itself. A failure must propagate
  back to the provider so the model message cannot be sent.
- Persist `interrupted_uncertain` as a paused attempt/campaign requiring
  explicit reconciliation. Its `retryable=True` permits an explicit recovery
  path; it must not authorize generic resume or automatic retry. Retain the
  session/server identity for operator inspection of OpenCode's state.
- Preserve normal retry behavior only after confirmed cancellation, subject to
  the campaign's persisted budget and retry policy. Report that the five-second
  cleanup allowance is additional to the main HTTP request deadline.
- Update current architecture/research/backtest documentation with the callback,
  catch-all plus schema-return permission exception, and cancellation semantics.
  Product documentation and the overall task checklist are parent-owned.
- Independently review the changes and resolve the controller-dependent test
  above before integrated completion. Live provider verification is parent-owned
  and was not part of this no-call adapter task.

## Official contract references

The server documents the synchronous message endpoint and boolean-returning
abort endpoint in its [session and message API](https://opencode.ai/docs/server/).
The [permission documentation](https://opencode.ai/docs/permissions/) specifies
wildcard matching and last matching rule precedence. Source inspection confirms
that [prompt assembly injects StructuredOutput](https://github.com/anomalyco/opencode/blob/v1.18.28/packages/opencode/src/session/prompt.ts)
and [LLM request preparation applies permission filtering to the resulting tools](https://github.com/anomalyco/opencode/blob/v1.18.28/packages/opencode/src/session/llm/request.ts).
These references justify the exact schema-return allowance; they are not a
claim that a live installed provider was exercised.
