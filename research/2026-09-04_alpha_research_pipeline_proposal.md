# Long Core V2 and BTC: alpha research and an AI research pipeline

Assessment date: 2026-09-04. Status: proposal, not an implemented pipeline or validated strategy change.

Follow-up scope clarification: the first application is BTC signals, with a strong
research manager directing cheaper execution models. See the
[architecture comparison](2026-09-04_hierarchical_research_architecture.md) for
model delegation, economics, adaptive research, and generalization to on-chain work.

## Recommendation

Build a small, reproducible research system around the existing evaluators. Let AI propose hypotheses, implement bounded experiments, and explain failures. Give a separate, fixed evaluation process control of the evidence and advancement decisions. Keep the current strategy as a frozen comparison throughout research.

The first investment should be reliable outcome measurement and independent validation. Current evidence suggests researching payoff asymmetry, entry extension, redundant filters, and BTC exposure before increasing model complexity. There is no demonstrated guarantee that these changes will produce alpha.

## What the repository currently establishes

“Long V2” maps to the current Core V2.1 signal runtime. Its pure evaluator, exact closed-candle dependencies, deterministic seeding, state transitions, and replay ledger are useful foundations. Its signals are advisory; reference levels are not executed trades. See the [Core contract](../docs/07_trading_strategies/core-v2-1.md) and [execution decisions](../docs/07_trading_strategies/core-v2-1-execution-decisions.md).

### BTC evidence

The saved `results/btc_signal_ev_summary.csv` (local-only output, git-ignored) contains 1,399 M5 and 589 M15 signals. At the four-hour horizon:

| Measure | M5 | M15 |
|---|---:|---:|
| Mean gross forward return | +0.0133% | +0.0422% |
| Reported 95% interval | -0.0726% to +0.0775% | -0.0585% to +0.1387% |
| Same-timeframe all-bar baseline | +0.0116% | +0.0117% |
| Mean less illustrative 0.10% round-trip cost | -0.0867% | -0.0578% |

All eight timeframe/horizon intervals in the saved summary cross zero. These are forward-return observations, not a simulated TP/SL trading strategy. The 0.10% hurdle is an illustration, not a verified account fee schedule. Actual assessment needs fees, spread, slippage, funding, and executable entry/exit timing.

An interesting exploratory result appears in the `results/btc_signal_ev_feature_buckets_4h.csv` (local-only output, git-ignored): M15 signals in the lowest H4 price-to-EMA gap group averaged +0.1546% over four hours (197 observations), versus -0.0411% in the highest group (196). M5 shows the same ordering: +0.0799% versus -0.0408%. This motivates an anti-extension hypothesis; it is not confirmation. The groups were examined on the same history, and their boundaries and selection need out-of-sample testing.

The historical task record mentions a BTC study notebook/script and provenance export that are absent from this checkout. The four CSV outputs survive. This assessment checked their contents and summary arithmetic; it did not independently reproduce the original confidence intervals. Recover or rebuild the generating source before using the study as a reproducibility benchmark.

### Core evidence

The [Core replay summary](../artifacts/core_v2_1/README.md) covers June 29–August 20, 2026. It contains 63 A+ and 19 confirmed pullback setups: **82 actionable events**. Of 207 WAIT events, 19 confirmed, 72 cancelled, and 116 expired. Approximately 9.2% confirmed.

This is an event audit without fills, costs, portfolio exposure, or P&L. Neither the 98,550 evaluated symbol-candles nor the 125,000 ledger rows are independent trades. Current evidence is too sparse for credible per-coin models. A read-only aggregation also found 2,274 rejected cross cycles: useful candidates for studying whether each gate adds value.

The June 29 feature anchor deliberately excludes older history from this replay. Longer CSV files do not make this a multiyear Core backtest. Use a separately versioned historical research contract with an explicit seed/warmup convention to study earlier periods; preserve the production anchor and verify overlap parity where applicable.

### Earlier notebook evidence

Cached Run 35 output in the [Phase 1 notebook](2026-04-28_phase1_audit_exploration.ipynb) reports 66.6% wins, average winning trade-row P&L of $103.36, average loss of $293.35, and profit factor 0.702. Candle-stop exits account for a large negative contribution.

This motivates researching loss tails and exit behavior: a high win rate can coexist with negative expectancy. Run 35 is not established as the current Core V2.1 configuration. Recover strategy/configuration and clarify partial-fill versus trade-row accounting before attributing those losses. The notebook also has mutable-panel reuse and an assumed portfolio-risk versus trade-return unit comparison that need cleanup before reproduction.

## Prioritized strategy experiments

### 1. Define payoff and costs before optimizing entries

Keep two measurements: signal predictiveness and executable strategy performance. Preserve signal-close reference returns for diagnosis, but use the next executable price for trade simulations. The Core execution policy already distinguishes signal close from next-M15-open plus adverse slippage.

Freeze a small set of exit policies before comparing entry changes. For Core, the documented strategy stop is a closed M15 close below EMA21; the displayed candle-low minus 0.25 ATR stop is an advisory risk ruler. Disaster-stop behavior and TP allocation must be explicitly specified in each research scenario. Measure time-stop alternatives and tail loss, without retrospectively choosing the best exit for each trade.

Record net expectancy, adverse/favorable excursion, time to exit, drawdown, and costs relative to initial risk. An attractive maximum favorable excursion is not a realizable profit unless the exit rule captures it causally. If TP and SL touch within one bar, use finer data or report ambiguity/conservative bounds. Do not assume favorable intrabar ordering.

### 2. BTC: test extension and signal freshness

Predeclare a simple extension feature, initially the existing H4 EMA gap and then an ATR-normalized version. Compare identical BTC entries/exits with and without it. Estimate cutoffs only from training data; do not import full-sample bucket boundaries into validation.

M5 is an alignment condition with a cooldown, whereas M15 requires a fresh cross. Test whether M5's first eligible alert in an alignment episode is better than later cooldown-eligible alerts. Test M15 signal followed by an M5 execution trigger separately from running both independently. Preserve causal timestamps: a later M5 confirmation cannot justify an earlier M15 fill.

Evaluate against BTC entries matched on bullish H1/H4 context, volatility, and time exposure. Otherwise the study may attribute ordinary bullish-regime returns to the RSI trigger. Treat overlapping M5/M15 signals as related observations and evaluate their combined exposure.

### 3. Core: test pullback quality at confirmation

Current [pullback logic](../app/trading/strategy/core_v2_1/evaluator.py) permits a zone touch followed by a re-extended close: it deliberately does not recheck the original distance/range thresholds or EMA slope. A [regression test](../tests/test_core_v2_1_evaluator.py) explicitly permits a 1.5 ATR close distance and 1.775 ATR candle range. This is intended behavior, not a code defect.

Compare the frozen baseline with a confirmation-distance constraint. Examine close location and adverse fill distance as diagnostics. Separately investigate a small predeclared WAIT-window comparison. The high expiry count alone does not justify extending waits; compare both captured opportunities and later failures.

### 4. Test subtraction before adding more gates

Create a row for every fresh cross, including rejected candidates. Compare the baseline with one gate group removed at a time: alt H1 confirmation, BTC regime conditions, local trend conditions, and anti-chase classification. Correlated rejection counts do not establish that a gate helps.

For each ablation, report signal coverage, incremental net return, adverse tails, and portfolio exposure under identical execution assumptions. Fully replay the state machine because an altered rejection changes future arming and WAIT states. A filtered CSV alone cannot faithfully evaluate those changes.

### 5. Core: measure alt-specific strength and rank concurrent opportunities

Start with trailing BTC-relative or beta-adjusted momentum, ATR-normalized trend strength, relative volume, and market breadth. All transformations, beta estimates, and ranking thresholds use past data only. Compare against a same-time, similar-exposure BTC or liquid-alt benchmark to distinguish selection value from simply being long crypto.

At the portfolio layer, compare taking every alert with selecting a small ranked subset under the same capital budget. Control total BTC beta and correlated simultaneous positions. Improved risk allocation can improve the strategy without creating new predictive alpha; report the two effects separately.

Historical research finds cryptocurrency market, size, and momentum factors, which motivates these controls. It does not establish a current intraday edge for this implementation. [Liu, Tsyvinski and Wu, Common Risk Factors in Cryptocurrency](https://www.nber.org/papers/w25882).

### 6. Introduce a small learned selection model only after the dataset is reliable

Begin with a transparent rule score or regularized logistic model estimating the outcome of a fixed entry/exit policy. Compare it against the simple extension filter. Add a small tree model only if it provides stable incremental value.

Useful initial features are extension, volatility, relative volume, regime strength, setup age, and BTC-relative strength. Calibrate probability estimates on training/validation data. Score expected net payoff, including timeout outcomes, rather than assuming win probability alone determines value. Human quality labels can be auxiliary research data; they are not objective profitability labels.

Funding, basis, open-interest changes, and taker flow are later feature families. Archive them with observation/availability timestamps before relying on them. Binance's open-interest-history endpoint currently exposes only the latest month, so a two-year OI study cannot be reconstructed from that endpoint alone. [Binance Open Interest Statistics](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics).

Defer deep networks, reinforcement learning, per-symbol models, and an unlimited indicator search. Their added search flexibility is difficult to justify with the present event counts.

## Repair the evaluator before automating selection

| Current limitation | Required change |
|---|---|
| [DSR](../app/backtest/audit/deflated_sharpe.py) raises for `n_trials > 1`; current output is PSR | Register every attempted hypothesis/configuration and implement selection-aware statistics with explicit assumptions about correlated trials |
| PSR computes excess kurtosis but uses `excess/4` in its variance term | Correct and independently validate the formula and numerical examples; the standard term is `(raw kurtosis - 1)/4`, equivalent to `(excess + 2)/4` |
| [PBO](../app/backtest/audit/pbo.py) aligns dollar P&L by trade ordinal and zero-pads | Build a common calendar-time matrix of net portfolio returns with consistent capital and costs |
| [Audit report](../app/backtest/audit/report.py) can skip failed/missing components and pass remaining tests | Return PASS, FAIL, or INCOMPLETE; missing required evidence blocks advancement |
| Generic [signal panel](../app/backtest/audit/signal_panel.py) studies RSI14 across bars | Test the actual RSI21 event/score and conditional baselines from frozen run data |
| [Optimization package](../app/backtest/optimization/__init__.py) is a placeholder despite documentation advertising walk-forward services | Implement and verify chronological evaluation; do not rely on a UI endpoint existing |

The PSR formula can be cross-checked against the [published DSR paper](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) and this [independent documented implementation](https://fynance.readthedocs.io/en/v2.7.0/_modules/fynance/research/guards.html). Selection correction depends on the search history; a large number labeled “DSR” is not a substitute for that history. [Bailey and colleagues' PBO paper](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) provides the calendar-comparable candidate-matrix methodology to implement and validate.

Also change the interpretation of existing research rules: 50 trades is not an automatic significance threshold; reward/risk below one is not automatically negative expectancy; and raw RSI correlation does not establish the edge of a conditional crossing strategy. Statistical precision depends on payoff variability, dependence, and the magnitude of the claimed benefit.

## Proposed AI research loop

1. **Freeze inputs and protocol.** Content-addressed data, venue/instrument identity, listing eligibility, source timezone, close time, availability time, code revision plus dirty diff, config, costs, benchmark, objectives, and split manifest. Core already supplies useful hashing/identity conventions; BTC replay needs equivalent immutable source references.
2. **Register the hypothesis before execution.** Store the economic mechanism, predicted direction, falsification condition, parent experiment, parameter search limits, primary metric, allowed validation access, random seed, and compute budget. Record failures and abandoned candidates permanently.
3. **Run a bounded experiment.** The researcher agent produces a configuration or isolated candidate patch. A deterministic runner invokes the shared evaluator, then labels outcomes and produces timestamp-aligned portfolio returns. Initially allow one changed hypothesis at a time.
4. **Check independently.** A separate reviewer inspects the evidence and attempts counterexamples. Executable checks own the verdict. The researcher cannot edit metric code, remove failed results, relax gates, or access the sealed final period. Separation should be enforced through data/tool permissions, not only role prompts.
5. **Advance to shadow evaluation.** A surviving challenger receives the same live inputs as the frozen champion, logs simulated outcomes, and reports incremental net value, calibration, and drift. Research success does not itself authorize changing the live signal contract or placing orders.
6. **Update research memory.** Summarize what failed, where it failed, uncertainty, and what experiment would discriminate between explanations. Use this memory to choose the next bounded batch. Retain negative and inconclusive findings so iteration becomes more informative, not merely more selective.

The three AI roles can be researcher, experiment implementer, and skeptical reviewer. More agents do not provide statistical independence if they share the same repeatedly inspected test set. The fixed evaluator and withheld data matter more than the number of agents.

### Dataset and registry requirements

Each candidate event should include strategy/configuration version, data hash, market identity, event/episode IDs, source close and available-at times, as-of features, every gate outcome, original state, suppression reason, reference levels, simulated fills and costs, exit/timeout times, and outcome-label version. Keep future outcome columns outside the feature interface.

The BTC review UI hides future chart candles, but [signal detail responses](../app/backtest/signal_replay_service.py) include forward metrics and [an API endpoint](../app/api/routes/signal_replays.py) exposes them separately. Human labels/plans can also be revised after reveal. Therefore an AI feature feed must use a dedicated as-of schema. Store the first pre-reveal judgment/plan immutably and append revisions with reveal timestamps; do not train on revised plans as if they were known at entry.

Use a small research SQLite registry, immutable Parquet/JSON result artifacts, versioned experiment specifications, and a CLI first. Notebooks should consume artifacts rather than hold the only reproducible implementation. A separate research database avoids confusing experimental candidates with production positions.

### Validation that can reject the AI's favorite idea

- Use chronological outer walk-forward with inner training/validation. Fit transformations and choose parameters only inside the training process. Group concurrent altcoin and M5/M15 observations by calendar time; random row splits leak shared market episodes.
- Purge training events whose label intervals overlap validation/test intervals. Apply an appropriate gap/embargo for the evaluation design; derive it from actual outcome horizons rather than an arbitrary percentage.
- Use a genuinely unseen final period once per preregistered campaign. The history already explored in the existing notebook/CSV study is development evidence. Repartitioning it now cannot make it untouched. Prospective data is the cleanest final check; repeated access consumes a holdout.
- Calculate block-based uncertainty for net returns and matched-baseline differences. Measure raw event count and effective independent exposure. Require a predeclared economically useful benefit and acceptable tail risk; do not choose acceptance thresholds after seeing results.
- Test higher fees/slippage, delayed fills, adverse funding, removal of exceptional months/assets, parameter neighborhoods, and regime stability. Report fragility rather than averaging it away.
- Perturb or truncate future rows: earlier features and decisions must remain identical when the historical prefix/seed is preserved. Check batch versus sequential replay and sampled live/replay parity. Include intentionally leaky controls that the checker must catch. Freqtrade's [lookahead-analysis](https://docs.freqtrade.io/en/latest/lookahead-analysis/) demonstrates a related comparison-based diagnostic; adapt the principle to this evaluator.
- Require all mandated checks to complete. A noisy or sparse result is INCOMPLETE, not a reason to loosen gates. “All candidates rejected” is a valid research outcome.

Shadow monitoring should distinguish input drift, outcome drift, and delivery/fill failures. Record signal-generation, delivery and actionable timestamps separately; an enqueued notification is not proof it reached the user. Use predeclared review times or sequential methods so daily checking does not quietly become another unlimited search.

## External systems worth considering

| Option | Fit for this project |
|---|---|
| A small custom loop around the existing replay code | Recommended first: preserves exact RSI seeds, state transitions, venue identity and signal contracts |
| [Microsoft RD-Agent](https://github.com/microsoft/RD-Agent/blob/main/README.md) | Strong reference for iterative hypothesis, implementation and feedback workflows; its current README says Linux-only. Its [quant paper](https://arxiv.org/abs/2505.15155) studies coordinated factor/model research, not proof of profitability for these crypto signals |
| [Qlib](https://github.com/microsoft/qlib) | Useful broader ML research platform; its documented Alpha158/Alpha360 dataset examples target US/China markets, so crypto data and execution adapters would require work |
| Freqtrade diagnostics | Borrow causal/recursive and intrabar-validation ideas without replacing the current strategy engine |

Start with the custom loop and borrow ideas from RD-Agent. Avoid a platform migration until one complete reproducible experiment demonstrates a concrete need.

## First implementation sequence

**Foundation:** recover the BTC research source, reconcile notebook units/state, fix audit semantics/formulas, add immutable event/outcome artifacts, and reproduce the frozen baseline with explicit execution scenarios. Deliver one CLI producing a manifest and evidence report.

**First preregistered campaign:** BTC M15 extension control; BTC M5 first-episode versus repeat-alert comparison; Core pullback confirmation-distance control. Hold exits constant within each comparison. Count every variation and report losers. Expand Core's historical research coverage before fitting a model.

**Then:** gate ablations and same-exposure benchmarks; a small learned selection model if simpler hypotheses survive; AI orchestration over these proven commands; prospective champion/challenger shadow evidence.

A useful first milestone is: one command reproduces a baseline, evaluates one preregistered challenger, catches a deliberately invalid candidate, and explains PASS/FAIL/INCOMPLETE with exact artifacts. No live strategy change is needed to establish that capability.

## Assessment scope

This assessment inspected current source, specifications, cached notebook output, saved BTC CSVs and Core replay artifacts, with independent read-only subreviews and primary web sources. It did not run a new full backtest, fit a model, reproduce the original bootstrap intervals, alter trading logic, or create a scheduled autonomous job. The recommendations are testable research priorities; none is presented as confirmed new alpha.
