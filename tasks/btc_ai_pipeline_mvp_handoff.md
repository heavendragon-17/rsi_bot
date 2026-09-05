# Build the BTC AI research pipeline MVP

## Main objective

Implement a working local orchestrator: a strong thinker proposes a bounded
research job, a cheaper executor carries it out, deterministic checks verify
the artifacts, and the thinker uses the verified result to choose the next
action. Luna Max is building this software; runtime model roles are configurable.

The owner explicitly corrected scope drift into manual quant studies. We now
have enough BTC research tools to build the loop. Do not start a new filter,
TP/SL, or alpha campaign while implementing this milestone. Work directly in
this repository, preserving existing uncommitted files and datasets. Read
`docs/INDEX.md`, `docs/agent-workflow.md`, and this brief first. Use one
implementation agent; no broad parallel research or framework migration.

## Existing assets to reuse

- `btc_research_phase1.py` and `app/backtest/btc_research_phase1.py`.
- `research/btc_m5_horizon_diagnostic.py` and `research/btc_m5_regime_review.py`.
- `research/2026-09-04_btc_m5_four_year_findings.md`.
- Frozen data: `research/data/btc_four_year_20220828_20260828`.
- Baseline packet: `research/results/phase1_four_year_runs/run_20260904T084317586748Z_97d3c169`.
- Horizon packet: `research/results/m5_four_year_horizon_runs/run_20260904T084448776441Z_97d3c169`.
- Regime packet: `research/results/m5_four_year_regime_runs/run_20260904T084529594410Z`.

BTC context: M5 is the focus, 1h/2h primary interests, 3h diagnostic, 4h reference.
The four-year history is development evidence. Alpha remains NOT_ASSESSED.
Keep data/operational validity separate from scientific conclusions. A parent
packet can have incomplete long horizons while a specifically checked 1h-4h
job has complete inputs. The model cannot waive checks or relabel exposed data.

## Required behavior

Build a small Python package, repository-root CLI, and SQLite campaign/job log.
Provide commands equivalent to `preflight`, `run`, `resume`, and `status`, plus
an offline fixture mode. Use existing dependencies where practical. No UI,
daemon, scheduler, vector database, or external queue is required.

One campaign must perform the following actual workflow:

1. **Load context and limits.** Pin data/evidence hashes and the research question;
   retrieve concise previous decisions and failures from this campaign's log.
2. **Thinker proposes.** Return schema-validated JSON with hypothesis/question,
   rationale, expected evidence, named task/tool, parameters, invariants, and
   stop/falsification conditions. Freeze and hash this specification before work.
3. **Executor handles the job.** Receive only the task contract and needed
   context. Return a structured execution plan or bounded candidate files in a
   run-specific workspace, then produce verifiable output. For the first demo,
   use the existing research tools and a constrained independent recomputation.
4. **Controller runs/checks.** Map registered tool names and validated parameters
   to fixed Python functions or argument arrays; do not execute shell text from
   a model response. Capture exit status, paths, hashes, numerical checks,
   failures, usage metadata, and elapsed time. The executor's prose is not proof.
5. **Thinker reviews evidence.** A second thinker call must consume the actual
   checker output and choose REPAIR, PROPOSE_NEXT, REJECT, or STOP with reasons.
   A proposed next job links to its parent result. The controller enforces the
   campaign limits even when the thinker requests additional work.
6. **Persist before advancing.** Record every attempt and decision, including
   failures. At the demo's iteration limit, save the proposed next action and
   exit cleanly. Resume must continue from state without blindly rerunning work.

Explicitly separate campaign memory from model weights. This first version
improves the record used to choose the next experiment; it does not retrain LLMs
or automatically approve strategy changes.

## Model/provider integration

Config must distinguish thinker and executor provider, model ID, effort, timeout,
and context/output budgets. Do not hardcode a frontier model into the controller.
The intended future pairing is Astra through supported Codex access and a cheaper
GLM/OpenCode executor; Luna can also be configured as executor where available.
Model availability and chosen account integrations are not established by this
brief. Preserve requested identities; do not silently substitute another model.

Implement the Codex CLI adapter first using documented non-interactive structured
output and normal existing authentication. It can serve both roles with distinct
explicitly configured available models for the first integration demonstration.
Keep one small adapter interface; OpenCode's documented local server is the next
adapter, rather than a prerequisite to completing this first loop. Mark it
unsupported until implemented, not as a fake success path. Verify installed
interfaces and official docs:
[Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
and [OpenCode server](https://opencode.ai/docs/server/).
Keep provider mechanics separate from research logic. Test missing/unsupported
providers and malformed responses explicitly. Do not implement a raw HTTP client
that repurposes ChatGPT subscription credentials as a general API key.

Preflight reports executable/server reachability, configured models, data access,
and missing setup without exposing credentials or consuming a model call.
Record actual runtime-reported model/usage where available; otherwise use null
with an explanation. Do not invent dollar costs or infer quotas from token counts.

No installation, purchase, authentication change, paid API fallback, quota-reset
redemption, or model invocation is implicit in the default CLI. Provide explicit
live-call opt-in for the owner after preflight, while making fixture mode fully
runnable now. If requested models/providers are unavailable, complete the code
and offline verification and identify the precise missing integration. Never
describe a fixture-only run as a live multi-model pipeline demonstration.

## Budget and execution boundaries

For the first opt-in live demo: one job, one worker at a time, two thinker calls,
one executor call, and no automatic model retry. Count each provider invocation
before dispatch; distinguish provider-internal turns from controller call caps.
Set finite job/call timeouts and terminate owned child processes on timeout.
Persist rate-limit/auth failures as a resumable pause. No silent paid overflow.

Worker writes belong in an isolated run directory. Keep canonical data,
production strategies, and authoritative checker code outside its write access.
Use supported sandbox/permission controls; a prompt alone is not isolation.
If an adapter cannot enforce the chosen write boundary, keep its mode read-only
and let the controller execute registered jobs. Explain the supported boundary.
Do not claim the initial bounded tool catalog can safely run arbitrary generated
code. Candidate-code execution can use a documented isolated extension point;
do not build an unrestricted agent shell to make the demo work.

Reuse immutable evidence when its input/protocol/code identity matches. Cache
identity must include parameters and horizon definitions. An interrupted job
with uncertain completion is reconciled or paused before repeat dispatch.
Show when existing evidence was reused versus independently recomputed.

## Concrete first demonstration

Use the already accepted four-year M5 evidence. Ask the thinker to specify an
independent verification of one existing 1h/2h/3h diagnostic using frozen events
and exact raw-candle targets. The executor prepares/runs that bounded job through
the registered runner; numerical code does the arithmetic. The checker compares
event identities, source hashes, exact timing and saved results. Feed the
returned evidence to the thinker, which records what to investigate next.
Do not add a new trading hypothesis or rerun the entire four-year baseline just
to demonstrate orchestration.

Exercise a negative fixture with tampered source identity or an intentionally
incorrect target timestamp. It must fail verification, reach the thinker as a
failure, and produce a repair/rejection decision rather than fabricated success.
Also demonstrate STOP and PROPOSE_NEXT branches with different fixture evidence
so the workflow cannot pass as a hardcoded sequence of saved messages.

## Acceptance and return

- One offline command completes the whole propose/execute/check/review sequence,
  writes durable jobs/artifacts/decisions, and produces a concise report.
- Tests cover branching from evidence, invalid JSON, tool/path restrictions,
  tampered data, budget exhaustion, timeout/rate-limit handling, and crash/resume
  without duplicate completed work. The Codex adapter has contract tests;
  actual provider smoke status is reported separately. A live multi-model demo
  requires actual thinker and worker calls with distinct configured models;
  offline fixtures alone do not establish that acceptance item.
- Demonstrate the checker through actual local numerical work on the saved data,
  with model responses stubbed in fixture mode. Assert the recorded next decision
  refers to the current verified result rather than a canned unrelated answer.
- Update matching architecture/research/CLI documentation and task records. Run
  focused tests, applicable static checks, and Markdown link checks.
- Return changed files, commands for offline demo/preflight/opt-in live run,
  exact evidence paths, tests, implemented versus live-verified integrations,
  and the next one missing capability (normally OpenCode executor integration).
  Stop after the orchestration milestone.

Known environment issue: the acquired dataset's staging directory had restricted
read permissions for the sandbox. Prior replay/checks used approved local
execution access. Report this accurately in preflight; do not change access
controls or refetch four years of data to hide an access failure.
