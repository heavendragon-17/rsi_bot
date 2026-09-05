# BTC live proposal failure: diagnosis and local fix

Campaign `campaign_9fedf039c2974b23` failed on its first thinker invocation.
The original report recorded exit 1 but discarded the provider's explanation.
The corresponding saved Codex session contains the exact rejection at
2026-09-04T12:01:31.513Z: HTTP 400, `invalid_json_schema`, parameter
`text.format.schema`. Its message identifies `properties.schema` as lacking a
`type` key. No proposal was produced. This is evidence of a request-schema
failure, not evidence that the selected model cannot perform the research.

[Recovered diagnostic record](results/btc_ai_pipeline_failure_diagnosis_20260904/diagnosis.json)
contains the source session filename and line, the error envelope, original
report hash, and original invocation counters. The failed campaign, database,
saved schema, and reports remain unchanged.

## Local corrections

- All three output schemas explicitly type const/enum fields, require every
  declared property, close objects, use nullable optional metadata, and express
  the optional nested proposal through `anyOf`. This follows the documented
  [Structured Outputs subset](https://developers.openai.com/api/docs/guides/structured-outputs#supported-schemas).
- New offline tests check the schema structure and realistic proposal,
  execution, review, and nested follow-up payloads. Legacy fixture records can
  still omit optional local metadata.
- Provider failures now retain bounded structured error details and session ID
  where available. Common credential formats are redacted. A structured schema
  error takes precedence over generic stderr warnings and is non-retryable.
  Full assistant output is not copied into failure diagnostics.

## Status and next invocation

No runtime model was invoked during diagnosis or repair. No retry, model
substitution, budget change, authentication change, or second live campaign
was made. The corrected schemas still need actual service acceptance; offline
validation cannot establish that.

The original campaign remains at one thinker invocation, zero executor
invocations and one job. Its remaining one-thinker allowance cannot complete a
fresh proposal plus final thinker review. Do not silently resume and exhaust
that budget, raise it, or create a new campaign. A newly authorized complete
smoke test would need two thinker invocations and one executor invocation,
while preserving the failed first campaign in history. Keep the same selected
Sol/high and Luna/high pairing unless the owner changes it, and stop after any
failure without automatic retries.
