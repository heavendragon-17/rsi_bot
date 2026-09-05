# AI research pipeline: cross-device handoff

Snapshot date: 2026-09-05. Repository: `heavendragon-17/rsi_bot`.
Handoff branch: `codex/research-pipeline-handoff-20260905`.
Base before this handoff: `447ad20` on `mua-tren-the-nang`.

## Start here, next agent

Continue from this branch, not the old base commit. Read `AGENTS.md`,
[docs/INDEX.md](docs/INDEX.md) and
[docs/agent-workflow.md](docs/agent-workflow.md), then this file. The user wants
an AI-driven research pipeline and asked to preserve the completed work on
GitHub so another agent can continue on another device.

The implementation and retrospective benchmark are complete. The next research
milestone is a prospective, paired comparison against a scripted policy using
new decision packets. Prepare that evaluation before spending further model
calls. The previous authorization was **12 total provider calls, all used**.
The subsequent benchmark made **zero new provider calls**. This handoff/push
does not renew the model-call budget. Do not run live commands or treat an old
`--confirm-live` example as authorization for another campaign.

No strategy, exchange execution, trading configuration or Telegram behavior was
changed by this research work. Do not turn the observed diagnostic into a live
filter without separate validation and user authorization.

## Findings and scientific limits

The verdict is **BENEFIT_NOT_ESTABLISHED**. AI found a useful historical
diagnostic lead, but a simple scripted policy also found weakness. One exposed
historical choice cannot establish general AI selection quality or cost benefit.

Both policies selected 180 minutes. The AI selected **volatility grouping**;
the scripted policy selected **calendar-year grouping**. The policies did not
individually select the HIGH or 2025 rows after seeing the catalog.

| Diagnostic row | Signals / comparator | Gap, percentage points | 28-day descriptive interval |
|---|---:|---:|---|
| AI volatility: HIGH | 423 / 63,936 | −0.08468 | [−0.17178, −0.01574] |
| AI volatility: LOW | 2,442 / 356,240 | +0.00131 | [−0.03420, +0.03323] |
| Scripted calendar year: 2025 | 695 / 105,120 | −0.05940 | [−0.11312, −0.01220] |

The HIGH gap-minus-pooled-gap contrast is −0.07329 points. Its seven-day
bootstrap interval crosses zero, [−0.16020, +0.00093]; its 28-day interval does
not, [−0.16001, −0.00250]. Concentration relative to the pooled result is
therefore sensitive to block length. HIGH spans 36 active signal weeks, with
7.09% of signals in the largest week. HIGH and the 2025 gap both remained
negative after individually deleting each of 53 consecutive 28-day blocks.
LOW changed sign in 14 deletion checks; its positive point estimate is not a
reliable positive effect.

The estimand uses all-four-horizon-complete events at 60/120/180/240 minutes,
reporting the first three horizons. Signal and comparator means have separate
denominators, and their observations overlap. The nine-candidate catalog is
three horizons times calendar year/causal trend/causal volatility. It is
reference coverage, not nine independent AI trials or an oracle ranking.

Statistics use one continuous 1,459-day UTC grid, including 621 zero-signal days,
2,000 paired circular draws per block setting, block lengths 7 and 28 days,
and seed 20260905. Intervals are pointwise **post-selection descriptive**
sensitivity intervals. There is no untouched holdout, selection adjustment,
multiple-comparison correction, execution-cost analysis or tradable-alpha claim.

The saved successful live campaign used five calls, 315.03 seconds of campaign
span, 130.36 seconds in providers, and 82,366 input / 3,689 output tokens.
The fresh scripted run took 73.90 seconds with no models; the separate evaluator
took 44.52 seconds. These are uncontrolled individual timing observations.
Reported historical cost 0.0017835 has incomplete coverage and is not total cost.

See [detailed findings](tasks/btc_selection_benchmark_outcome_20260905.md),
[human report](research/results/btc_selection_benchmark_20260905/report.md),
[machine report](research/results/btc_selection_benchmark_20260905/report.json),
[protocol](research/results/btc_selection_benchmark_20260905/protocol.json),
[all nine diagnostics](research/results/btc_selection_benchmark_20260905/diagnostics.json),
and [independent review](tasks/btc_selection_benchmark_review.md).

## What was implemented

`btc_ai_pipeline.py` exposes preflight, prepare-study, run, resume, status,
accepted-spec baseline replay, and the new selection benchmark.

| Files in `app/research_pipeline/` | Responsibility |
|---|---|
| `contracts.py`, `study_contracts.py` | Strict role schemas and bounded task catalog; required nonblank diagnostic rationale |
| `controller.py`, `controller_context.py`, `controller_runtime.py`, `controller_reporting.py`, `controller_utils.py`, `adaptive.py` | Durable bounded orchestration, adaptive follow-up, verified evidence and reporting |
| `providers.py`, `opencode_provider.py`, `provider_diagnostics.py` | Codex/fixture and OpenCode adapters; usage, timeout and recovery boundaries |
| `inputs.py`, `readiness.py` | Exact frozen-input and ancestry checks before each provider dispatch |
| `study_tools.py`, `study_checks.py`, `study_materialize.py` | Full raw-return/population/causal-label verification and missing-comparator reconstruction |
| `measurements.py`, `adaptive_fixture.py` | Usage accounting, zero-model accepted-spec replay and independent scripted policy |
| `benchmark_source.py` | Read-only SQLite snapshot and strict accepted-chain/artifact validation |
| `benchmark_data.py`, `benchmark_statistics.py` | One shared full verification, nine matching cohorts, paired uncertainty and deletion influence |
| `benchmark.py`, `benchmark_reporting.py` | Freeze policies/identities, run the separate scripted policy, recheck drift and publish descriptive comparison |

The source contract for `benchmark` deliberately requires the stopped live
two-study chain with five completed attempts, PROPOSE_NEXT then STOP, no failures,
and caps of three thinker calls, two executor calls and two jobs. It rejects
fixture campaigns and differing chains. Its production path never constructs a
controller/provider or mutates the source database. Tests may simulate saved
live labels with local fixture responses; those are not real provider calls.

Critical regression: excluded-only cohorts must remain in the statistics with
zero support and null estimates, and cannot extend the included-event calendar.
Labels are preserved separately per horizon; a label in one horizon must not
create a phantom cohort in another.

## Canonical runs and preserved failures

| Run | Identity and role |
|---|---|
| `btc_adaptive_live_final_20260905` | `campaign_3f13b814a0294bb6`: successful live summary → 180-minute volatility → STOP; five calls |
| `btc_mixed_live_acceptance_20260905` | `campaign_e7879087ffc941e2`: successful one-job mixed-provider smoke; three calls |
| `btc_mixed_live_smoke_20260905` | `campaign_889b9784bc04485a`: two calls; Muse rejected forced tool choice |
| `btc_adaptive_live_20260905` | `campaign_c2a7cbdad7b24288`: two calls; null rationale rejected by the local contract |
| `btc_adaptive_fixture_final_20260905` | `campaign_19cbc72a47114e1c`: real-data scripted summary → 180-minute calendar year; no model calls |
| `btc_selection_benchmark_20260905` | Completed retrospective comparison; no model calls |

All run directories above are below `research/results/`. The first four account
for all twelve authorized calls, including the failed integrations. Failures
are preserved for diagnosis and must not be silently resumed or retried.
The live call ledger is in
[live_validation_summary.json](research/results/btc_adaptive_prepared_20260905/live_validation_summary.json).

The accepted source snapshot hash is
`95d094cc5a9c08ed0e0d754e0d9622a8297e36ac96f2c824e5da0aacbd14a396`.
Use the stored protocol's fingerprints rather than copying new identities into
old evidence. The reviewer checked all nine pooled reconstructions, 30 cohort
calculations, seven input hashes, 30 code hashes and source/artifact fingerprints.

## Set up another device

```bat
git clone --branch codex/research-pipeline-handoff-20260905 https://github.com/heavendragon-17/rsi_bot.git
cd rsi_bot
```

If a clone already exists, fetch and check out the handoff branch without
overwriting local work. Use the project environment appropriate to that device.
On the original Windows host this was the existing Conda `rsi` environment;
`requirements.txt` and `requirements-dev.txt` are the dependency sources. They
are not a fully pinned environment lock.

```bat
conda activate rsi
python -m pytest tests/test_btc_ai_pipeline.py tests/test_btc_ai_pipeline_studies.py tests/test_btc_ai_pipeline_adaptive.py tests/test_btc_ai_pipeline_benchmark.py tests/test_btc_ai_pipeline_benchmark_source.py tests/test_btc_ai_pipeline_benchmark_data.py tests/test_btc_ai_pipeline_benchmark_statistics.py -q
python scripts/check_markdown_links.py
```

These are offline checks. To rerun the full focused pipeline suite, use the
test files matching `tests/test_btc_ai_pipeline*.py` with the shell's glob or
file-enumeration support. On Windows PowerShell:

```powershell
$pipelineTests = @(Get-ChildItem tests -Filter test_btc_ai_pipeline*.py | Select-Object -ExpandProperty FullName)
python -m pytest $pipelineTests -q
```

OpenCode 1.18.29 was installed and authenticated only on the original computer,
with a loopback server at `http://127.0.0.1:4096`. Authentication and that running
server do not travel with Git. Follow the
[OpenCode Windows guide](docs/03_setup_and_installation/opencode-windows.md)
for separate setup when needed. Never copy or commit account credentials.
No provider setup is needed to inspect the findings or run synthetic tests.

The successful configuration was a Codex thinker requesting `gpt-5.6-sol/high`
and an OpenCode executor requesting/reported as
`opencode-go/muse-spark-1.3-contributor/high`. The Codex runtime model ID was
unavailable. Recheck availability before future use. Muse required persisted
`--opencode-output-mode json_text`: it rejected forced tool choice in the default
schema mode. Text mode denies model tools and still validates the entire JSON
response locally; no silent retry or fallback is allowed.

## Data portability: what Git contains and what it does not

The publication includes the implementation, tests, documentation, compact JSON
and Markdown evidence, and small research SQLite archives. Raw market inputs
and original signal packets were already committed at `447ad20`. Large generated
CSVs remain ignored. In particular the prepared horizon `baseline.csv` is
262,073,730 bytes: 420,176 comparator events and 1,680,704 four-horizon rows.
The prepared signal population contains 2,865 events. Do not force-add these
large regenerated CSVs or assume their presence merely because a manifest exists.

The `.gitattributes` rules preserve exact bytes for fingerprinted code, raw CSV
inputs and this handoff's dated evidence. CRLF/LF conversion changes SHA-256 even
when arithmetic is identical. Preserve these rules and never rewrite a frozen
artifact to make its fingerprint appear valid.

Reconstruct a **new derived packet** using the original committed packets,
not an incomplete prepared directory from the archive:

```bat
python btc_ai_pipeline.py prepare-study --repo-root . --data-dir research/data/btc_four_year_20220828_20260828 --baseline-packet research/results/phase1_four_year_runs/run_20260904T084317586748Z_97d3c169 --horizon-packet research/results/m5_four_year_horizon_runs/run_20260904T084448776441Z_97d3c169 --workspace research/results/device_prepared_study
```

Use a new workspace name if that directory exists. The original missing
baseline CSV's byte identity was unknown; reconstruction records a new derived
hash after checking historical counts/statistics and population/raw invariants.
Read the generated materialization report before using the derived paths.

Then use these prepared packet subdirectories for a fresh no-model campaign:

```bat
python btc_ai_pipeline.py run --adaptive --offline-fixture --use-saved-data --baseline-packet research/results/device_prepared_study/run_20260904T084317586748Z_97d3c169 --horizon-packet research/results/device_prepared_study/run_20260904T084448776441Z_97d3c169 --data-dir research/data/btc_four_year_20220828_20260828 --db research/results/device_fixture/pipeline.sqlite --output-dir research/results/device_fixture
```

This creates new fixture-provider records; it does not recreate a historical
live AI choice. The old SQLite archives, requests and report identities contain
absolute paths from the original Windows host. Therefore **the archived
`benchmark` command is not portable unchanged to a different checkout path**.
It will reject mismatched paths or missing prepared CSVs. Reading archived
results is supported; transparently relocating a hash-bound accepted campaign
has not been implemented or validated on a second device.

Do not patch the old DB, bypass its checks, recast the new fixture campaign as
live, or overwrite the frozen report. If replaying the archived AI choice on
another root is needed, implement an explicit relocation/import boundary with
provenance, logical-to-local path mapping, original identity preservation and
tamper tests before attempting it. New paths require a new derived record.

## Suggested continuation order

1. Inspect the committed findings and run the offline tests. Confirm data and
   provider availability on the destination device without issuing model calls.
2. Rebuild a fresh derived packet and complete a zero-model fixture campaign.
   Address explicit, provenance-preserving relocation if historical replay is
   required; do not weaken existing source/checker gates.
3. Design several new decision packets whose outcomes were not shown to either
   policy. Freeze questions, allowed experiments, inputs, independent scripted
   policy and equal experiment budgets before selection.
4. Predefine diagnostic usefulness, support, unsupported-claim, reproducibility
   and resource criteria. Use blinded review and paired comparisons across
   packets. Avoid a hindsight largest-effect or smallest-interval winner.
5. Prepare exact provider prompts, data-exposure previews and a bounded new call
   budget for user review. Only then seek authorization for the live evaluation.

## Verification and known limitations

The completed research change passed 293 focused pipeline tests, including 72
benchmark tests. Ruff passed and mypy passed all 26 pipeline modules. Independent
review matched event-level bootstrap and deletion arithmetic within 1e-12 points
and verified coherent SQLite snapshots while a writer committed WAL changes.
The publication rechecks the focused suite and Markdown links.

Architecture lint has one known pre-existing violation:
`app/backtest/btc_research_phase1.py` is 865 lines against a 600-line limit. It
was already present at the base commit. No exemption was added for it; do not
claim every repository check is green. The full repository test suite was not
rerun for this documentation/publication handoff. No new live calls are part of
publication.

Publication review found 504 secret-scanner candidates across the staged files
and expanded SQLite text: recorded fingerprints, canonical packet paths and
one deliberately fake password in the credential-redaction test. All were
classified as nonsecrets in a read-only review. **The repository's detector
baseline is unchanged**, so its unmodified CI scan can still report those
findings. Automatic approval review rejected adding baseline exceptions without
explicit user authorization; do not silently add exceptions or disable scanning.

`git diff --check` also reports an existing extra blank line at EOF in four
fingerprinted modules: `adaptive.py`, `controller_runtime.py`,
`opencode_provider.py` and `provider_diagnostics.py`. Their exact bytes were
preserved to keep the archived code hashes valid. A later formatting change
needs a new code identity; do not retroactively alter the old protocol.
See the [publication verification record](tasks/btc_research_handoff_publication.md).

Additional history: [adaptive implementation outcome](tasks/btc_adaptive_pipeline_outcome_20260905.md),
[benchmark implementation plan](tasks/btc_selection_benchmark_plan.md),
[research workflow](docs/06_quant_research/research-workflow.md), and
[benchmark contract](docs/06_quant_research/research-selection-benchmark.md).
