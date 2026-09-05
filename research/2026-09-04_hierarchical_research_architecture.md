# A strong research manager with cheaper execution agents

> Current build priority after the owner's scope correction:
> [BTC AI pipeline MVP](../tasks/btc_ai_pipeline_mvp_handoff.md). The data,
> baseline, M5 horizon and four-year regime tools now exist; implement their
> thinker/executor/checker loop next. The M15 example below is historical
> architectural discussion, not the active experiment or implementation task.

Status: architecture discussion, 2026-09-04. First application: improving BTC signals. No pipeline, model calls, scheduled job, or strategy changes are implemented by this note.

## Clarified objective

Use a frontier model as principal investigator: it researches mechanisms, proposes experiments, delegates implementation to cheaper models, inspects returned evidence, and decides what to investigate next. This adds explicit model hierarchy and adaptive research direction to the [earlier validation proposal](2026-09-04_alpha_research_pipeline_proposal.md).

The common name is **orchestrator-worker** or **manager-worker architecture**. More precisely, it is a hierarchical, heterogeneous multi-agent research system: hierarchical because a manager directs workers, heterogeneous because roles may use different models, and closed-loop because results determine subsequent experiments. “Agentic research pipeline” is a suitable product description. These are descriptive terms, not one mandatory industry standard.

For this design, the manager retains control and calls workers as bounded capabilities. OpenAI calls this **agents as tools**, distinguishing it from a handoff in which a specialist takes over the conversation. [OpenAI orchestration documentation](https://developers.openai.com/api/docs/guides/agents/orchestration).

This does not itself train model weights. Improvement initially means better experimental memory, hypothesis selection, delegation, tools, and measured routing decisions. Fine-tuning would be a separate project.

## Comparison with the previous suggestion

| Question | Manager-worker idea | Earlier emphasis | Combined design |
|---|---|---|---|
| Who chooses the next question? | Strong lead model | AI proposes bounded hypotheses | Strong lead chooses adaptive development experiments |
| Who performs implementation? | Cheaper workers | Deterministic runner and implementation agents | Workers build/repair bounded code; runner performs numerical work |
| Who establishes validity? | Lead interprets worker reports | Independent, fixed validation | Lead interprets verified evidence; cannot waive required checks |
| How does it improve? | Feedback informs the next idea | Permanent experiment history and validation | Better research decisions plus reproducible evidence |
| Main cost risk | Coordination and worker repairs | Upfront evaluator/data engineering | Small initial hierarchy, measured routing, reused tools |

The prior proposal already allowed AI-driven research. It underexplained model assignment and delegation. There is no need to choose between the two concepts: one distributes intellectual work, while the other determines whether the resulting claims deserve belief.

## Critical assessment

### The architecture is plausible; its advantage must be measured

The useful decomposition is scientific judgment, bounded implementation, numerical execution, and evidence review. Strong models can spend their effort choosing informative experiments while cheaper workers handle well-specified work. Separate worker contexts can also prevent the lead from repeatedly reading irrelevant logs.

However, a higher token price does not imply a higher completed-task cost. A capable model may finish faster with fewer repairs. Anthropic documents both savings from delegation and cases where a solo model at lower effort was cheaper; it particularly distinguishes large separable work from dependent reasoning chains. These are task-specific measurements, not predictions of savings for BTC research. [Anthropic cost/intelligence guidance](https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence).

Do not fix Sol/Fable to every decision and Luna at maximum effort or a Flash model to every implementation on reputation alone. Treat model and effort as routing choices. Measure correctness, retries, review effort, context costs, latency, and total spend on this repository's tasks. No comparative benchmark of those exact combinations was run here.

### Quant implementation is often scientifically consequential

A wrong timestamp join, fee denominator, outcome interval, or treatment of partial fills can manufacture an apparent edge. These are not safely dismissible as routine work. The lead should specify such semantics; workers implement against reference cases. Escalate ambiguous scientific meaning instead of repeatedly guessing.

Passing tests is not conclusive if the worker also invented tests that repeat its own mistaken assumptions. Use independently specified examples, sampled recomputation, and deliberately leaky/incorrect candidates that the checker must reject.

### The lead can rationalize weak evidence

The manager is attached to its own hypothesis and receives summaries that may omit failures. Require machine-generated artifacts containing all attempts, exact metric definitions, sample counts, uncertainty, data/code identities, and failures. Allow direct inspection of source and outputs.

A second model agreeing is not statistical replication. The reviewer needs a concrete challenge: reproduce a calculation, inspect an as-of join, remove a dominant period, or verify that earlier features do not change when future data changes. Different model families can diversify some errors but do not guarantee independence.

### More experiments increase the search problem

If the manager repeatedly changes thresholds, horizons, and cost assumptions after disappointments, the best remaining backtest becomes increasingly selected. Register campaigns and all variants; preserve negative findings. The manager can revise a research question, but this creates a visible new protocol and does not reset the search history.

Keep adaptive iteration on development data. The evaluator controls access to final evaluation, including detailed reports. A manager that repeatedly sees final-test outcomes learns from that period even if it never reads raw data. A final period ceases to be untouched after evaluation; do not recycle it as a fresh test.

“No useful evidence,” “collect more data,” and “stop this campaign” must be valid outputs. A requirement to continually improve trading performance would encourage activity and rationalization rather than science.

## A sustainable initial design

Start with one research manager, one implementation worker, an independent checker invoked at milestones, and a deterministic research runner. Add parallel workers when tasks can run independently. No LLM is needed for every parameter combination or every backtest candle.

The manager works at decision points: selecting a question, approving an experimental contract, interpreting an evidence packet, and resolving contradictions. Workers handle ordinary debugging within bounded retries. Return concise structured results with links to complete artifacts, rather than forwarding every transcript.

Each task contract states:

- Research question and falsification condition.
- Exact inputs, allowed files/tools, and expected output artifacts.
- Permitted changes and invariant comparison assumptions.
- Primary metric, costs, data splits, and trial allowance.
- Time/token/compute limits, retry limits, and escalation conditions.

Use durable jobs and an append-only experiment log so interruption or a model replacement does not lose the research state. Preserve resumable checkpoints, artifact hashes, model/prompt/tool versions, and explicit task ownership. Isolate worker edits and keep the evaluation harness outside candidate write access. Provider adapters should accommodate differing tool-call formats, structured-output support, context limits, and rate limits; replacing a model should not replace research logic.

Track total campaign cost: manager, workers, retries, review/reproduction, data access, and compute. Evaluate it against reliable conclusions and eliminated hypotheses. A small cheap-model bill followed by expensive human correction is not a saving.

The researcher can operate autonomously inside a campaign's protocol and budget. Changes to the actual live strategy remain a separate release decision supported by a concrete evidence packet.

## BTC-first example

Research question: **Does avoiding highly extended BTC trends improve M15 alerts after realistic costs?** The saved study's H4 EMA-gap grouping motivates this hypothesis; it is already explored history, not new validation.

First reproduce the current baseline and repair the known evaluator limitations from the earlier proposal. Fix entry timing, costs, and exit policy before comparing filters. Maintain separate descriptive signal-close forward returns and executable-policy results.

The manager writes a small experiment specification. Workers perform these jobs, sequentially where one needs another's output:

| Job | Required result |
|---|---|
| Data preparation | As-of feature table, continuity checks, source hashes, explicit label intervals and availability timestamps |
| Implementation | Original alerts versus one extension-filter family; training-only threshold selection; implementation diff and exact commands |
| Evidence review | Independent timing/cost checks, reproduction, period breakdowns, uncertainty, and known limitations |

Start with the existing price/EMA gap or a separately declared ATR-normalized variant. Do not silently choose the better one after viewing final results. Preserve M5 as a later related question: first alert in an alignment episode versus hourly repeat alerts. Keep Core changes outside this first campaign.

The lead then follows evidence-dependent branches:

| Result | Next action |
|---|---|
| Implementation or data invalid | Repair the specific defect; no profitability interpretation |
| No economically useful effect after costs | Reject/archive the hypothesis |
| Effect concentrated in one regime or exceptional month | Investigate within development data; label fragility |
| Effect promising but imprecise | Collect more independent evidence or report INCOMPLETE |
| Stable development evidence, checks complete | Freeze candidate and submit to reserved evaluation |
| Final evaluation passes | Prospective shadow comparison with the frozen current signal |
| Final evaluation fails | Archive result; mark period exposed; no repeated final-test tuning |

This preserves meaningful research autonomy. The manager can choose a different mechanism or request a better experiment while the evaluator prevents favorable storytelling from becoming a passing result.

## Evaluate the architecture as well as the strategy

Compare a scripted baseline, one strong model, and the proposed hierarchy on the same research brief, tools, evidence access, budget, and maximum research trials. Include a cheaper solo model if evaluating routing choices. Repeat a small representative suite because individual agent runs vary.

Use tasks with known answers: reproduce the BTC summary, detect a planted lookahead error, repair a cost-accounting bug, implement a constrained feature, and correctly reject an unconvincing hypothesis. Measure reproducibility, undetected critical errors, rework, elapsed time, and total cost. Do not choose the architecture based on which found the highest historical Sharpe; that selects for both luck and hidden mistakes.

Only increase autonomy or concurrency when this comparison demonstrates value. Prefer the simplest system that meets the quality bar. Success on workflow benchmarks establishes research reliability, not tradable alpha.

## Generalization to on-chain and other research

The screenshot describes someone experimenting with Fable and on-chain trading strategies. It establishes a relevant use case, not the profitability or validation quality of their work.

The reusable layer contains the manager, workers, job system, artifact storage, experiment memory, budgets, and model routing. The domain-specific layer supplies data semantics, hypotheses, features, outcome definitions, evaluators, and acceptable evidence. Keep that boundary explicit.

For on-chain BTC features used to trade BTC on an exchange, the execution model remains the exchange model; add point-in-time on-chain features and realistic publication lags. For directly trading DEX tokens, add historical liquidity, gas, transaction ordering/MEV, failed transactions, and price-impact assumptions.

On-chain research has additional pitfalls:

- Block timestamps differ from observation, indexer publication, and finality times.
- Address labels and entity clustering can revise historical exchange-flow metrics. Glassnode documents revisions from newly acquired labels and offers point-in-time data. Preserve the vintage that was available at decision time. [Glassnode point-in-time explanation](https://research.glassnode.com/introducing-point-in-time-data/).
- Choosing today's profitable “smart wallets” and testing their old trades uses future selection information. Wallet eligibility must be determined from information available then.
- Delisted/dead tokens, token migrations, decimals, self-transfers, and missing pool history can distort a historical universe.
- A daily on-chain metric does not automatically justify a five-minute entry; test whether it supplies regime information or incremental signal value at the chosen horizon.

A concrete later question is whether point-in-time exchange-flow information adds value to the frozen BTC signal after controlling for price momentum, volatility, and derivatives conditions. It should earn incremental value before being included.

Other domains can reuse the research workflow, but their evaluators differ: software performance needs controlled benchmarks; literature research needs source-quality and claim verification; scientific findings may require physical experiments. There is no universal numerical proof-of-quality score.

Build and validate the BTC application first, then extract the reusable orchestration components when a second domain demonstrates which abstractions are shared.

## Recommended decision

Proceed with the manager-worker idea as a bounded BTC research pilot. Treat independent evidence evaluation as a core component of that design. Demonstrate one complete campaign and benchmark its reliability/economics before building an always-running general research platform.
