# Quant Research Workflow

> End-to-end process for discovering, evaluating, and deploying trading signals using this bot's infrastructure.

---

## Overview

```
Hypothesis → EDA → Signal Discovery → Signal Evaluation → Manual Handoff → Validation → Paper Trading → Live
```

The research phase happens in Jupyter notebooks. Once a signal is validated, it is manually coded into a strategy class and registered in the bot.

---

## Branch and publication policy for research work

Research-only work may be published directly to the main working branch
(`mua-tren-the-nang`) after validation. This policy exists so future agents do
not have to guess, and so nobody publishes something that could restart the bot.

**Allowed on `mua-tren-the-nang`, after validation:**

- Research-only code under `research/`, focused tests under `tests/`, evidence
  packets and charts under `research/results/`, findings reports under
  `research/`, and the matching documentation under `docs/`.

**Never on `mua-tren-the-nang` without a separate branch:**

- Anything that could affect production signals, shared indicators, trading,
  sizing, risk controls, execution, or live configuration. Those changes need
  their own branch and must not be merged automatically.
- Never commit to, push to, or merge the unrelated branch literally named `main`.

**Git safety:** preserve unrelated local work; no force-push, no rebase of shared
history, no destructive commands, and no switching the active checkout.

**Deployment safety — check before publishing.** A normal push to
`mua-tren-the-nang` triggers **CI only**. Deployment is tag-gated:
`.github/workflows/deploy.yml` runs only on a `v*` **tag** push (or a manual
`workflow_dispatch`), promotes the tag to the `production` branch, and the VPS
`deploy/check_deploy.sh` timer polls **`origin/production`** for a SemVer tag
before restarting `rsi-bot`. Therefore:

- Push ordinary commits with an explicit branch push. **Never** push tags, and
  never use `--tags` / `--follow-tags`, from a research task.
- Do not add or edit `.github/workflows/*` or `deploy/` from a research task: a
  commit that adds a workflow changes what runs on that same push.
- Confirm before pushing that the commit does not touch `deploy/`,
  `.github/workflows/`, `config.yaml`, `main.py`, `app/trading/`, `app/signal/`,
  or any live configuration.

**Never, from a research task:** deploy, restart the bot, send Telegram messages,
place orders, access trading credentials, or invoke external model providers.

**Do not publish:** credentials, unrelated files, duplicate raw datasets, or
unnecessarily large generated artifacts. For any artifact left out, record its
SHA-256 and an exact regeneration command in the packet and the findings report.

---

## Step 1: Hypothesis

Define a clear, testable hypothesis about market behavior:

- **Good**: "RSI divergence at EMA21 reclaim predicts a 1-2R move within 10 candles"
- **Bad**: "Find something that makes money"

Document in the notebook:
- Market regime assumption (trending, ranging, volatile)
- Asset class (BTC, ETH, altcoins — behavior differs)
- Timeframe (5m, 15m, 1h — different noise levels)
- Expected edge (why would this work? who is on the other side?)

## Step 2: Exploratory Data Analysis (EDA)

Download historical data using the bot's scripts:

```bash
python app/backtest/data/download.py --symbol BTC/USDT --timeframe 5m --limit 50000
```

In your notebook, explore:
- Price distribution, volatility regimes
- Indicator behavior (RSI, EMA crossovers, volume patterns)
- Correlation between signals and subsequent price moves
- Visual inspection of candidate setups on charts

## Step 3: Signal Discovery

Identify specific entry/exit conditions:
- Entry trigger (e.g., "RSI crosses above WMA while price reclaims EMA21")
- Exit conditions (TP levels, SL placement, time-based exits)
- Filter conditions (trend filter, volatility filter, time-of-day filter)

Code the signal logic in the notebook and apply it vectorized across the dataset.

## Step 4: Signal Evaluation

Run the signal through evaluation criteria (see [signal-evaluation.md](signal-evaluation.md)):
- Compute key metrics: Sharpe, drawdown, profit factor, win rate
- Check for overfitting red flags
- Test parameter sensitivity (small param changes shouldn't cliff performance)
- Validate across different time periods and market regimes

Use the bot's backtest engine for accurate simulation:
```bash
python app/backtest/backtest.py --data app/backtest/data/BTCUSDT_5m.csv --balance 10000
```

### BTC Phase 1 reproducible baseline

Before any signal search, run the bounded BTC evidence baseline described in
the [backtest documentation](../11_testing_and_backtesting/backtest-engine.md#btc-research-phase-1-baseline):

```powershell
C:\ProgramData\anaconda3\envs\rsi\python.exe btc_research_phase1.py `
    --data-dir app/backtest/data `
    --output-dir research/results/phase1_runs `
    --start 2024-09-01 `
    --end 2026-08-28
```

This is a descriptive, offline signal-close study. It reuses the current
point-in-time BTC replay, validates the four native source files, and writes a
run-specific manifest, signal rows, summary, and Markdown report. Forward
returns use exact native-timeframe target closes; gaps and incomplete tails are
explicitly excluded from complete-return statistics. The all-eligible-bar
comparison is matched to the emitted-signal coverage window and retains only
bars that pass shared per-event preparation; exclusion counts and reasons are
recorded separately, without applying signal gates or cooldown. A missing
required warmup or a requested timeframe with no evaluable bars is `INVALID`,
while a fully prepared zero-signal period can remain `VALID`. Replay cooldown
state starts at each requested window boundary, so separately replayed windows
must be compared with that limitation in mind. No TP/SL policy,
fill simulation, strategy P&L, bootstrap, walk-forward selection, or alpha
claim belongs in Phase 1. Review `alpha_assessment: NOT_ASSESSED` before
starting the next extension experiment.

### Fixed-population M5 horizon diagnostic

For a preliminary profile of the accepted Phase 1 packet's current coverage,
run the bounded offline command:

```powershell
C:\ProgramData\anaconda3\envs\rsi\python.exe -m research.btc_m5_horizon_diagnostic `
    --baseline-run research/results/phase1_runs/run_20260904T073543149279Z_2572884b `
    --output-dir research/results/m5_horizon_runs
```

The diagnostic retains the parent's emitted M5 IDs and cooldown history,
verifies its source hashes and original 1h/4h arithmetic, and compares exactly
60, 120, 180, and 240 minutes using the same all-four-complete signal population.
The comparator covers the first through last parent M5 signal and uses shared
per-event preparation without signal gates or cooldown. Baseline comparisons
also retain the same all-four-complete bars at every horizon. Exclusions and
exact-target statuses remain in the exported long rows and summary.

MFE and MAE use only future M5 bars: the first opens at signal close and the
last closes at the exact horizon. MFE includes a zero lower bound; signed MAE
includes a zero upper bound. They are hindsight excursion bounds, not captured
P&L, and longer windows mechanically allow larger excursions. Gross
close-to-close returns remain separate. The optional default uncertainty
summary uses 2,000 paired circular seven-day UTC calendar-block bootstrap draws
with seed 20260904, including zero-signal days and observation-weighted means.
Use `--no-bootstrap` to omit it. These are descriptive percentile intervals,
without a selection adjustment or significance claim. Monthly summaries use UTC.
Alpha remains `NOT_ASSESSED`; this is neither training nor untouched evaluation,
and it adds no horizon selection rule, parameter sweep, or live filter.

### Focused M15 signal-and-gate diagnostic

To separate "the alert fired" from "the bar was in a bullish context", run the
bounded offline M15 comparison against an accepted Phase 1 packet:

```powershell
python -m research.btc_m15_signal_diagnostic `
    --baseline-run research/results/phase1_reproduction_local/run_20260918T092140133007Z_97d3c169 `
    --output-dir research/results/m15_signal_diagnostic_runs
```

It compares three frozen populations over the parent's matched M15 window using
only the fixed 1-hour and 4-hour horizons, with no horizon or threshold search:

- `m15_signal` — the emitted replay alerts (fresh RSI21 EMA9/WMA45 bullish cross
  plus the M15, H1 and H4 close-above-EMA21 gates), with the replay's one-hour
  per-timeframe cooldown already applied.
- `gate_ready_no_cross` — preparation-ready M15 bars whose M15, H1 and H4 closes
  are all above their native EMA21, with no RSI crossover requirement and no
  cooldown.
- `all_eligible_bars` — every preparation-ready M15 bar in the window, matching
  the Phase 1 comparator.

The three nest (`m15_signal` ⊂ `gate_ready_no_cross` ⊂ `all_eligible_bars`).
Only observations whose both fixed horizons are `COMPLETE` enter every statistic,
so the groups share one complete-outcome basis. The parent's own 1h/4h rows are
re-derived and must match exactly. Uncertainty reuses the M5 diagnostic's paired
circular seven-day UTC calendar-block bootstrap (2,000 draws, seed 20260904,
observation-weighted means); it is a post-selection descriptive interval, not a
significance test and not corrected for overlapping observations. The packet
also writes three separate charts under `charts/`.

Adjacent M15 bars are at most 15 minutes apart and their 1h/4h windows overlap,
so none of these observations are independent trades: never compound them into
an equity curve and never read a signal-candle close as an execution price.
Alpha remains `NOT_ASSESSED`, and the diagnostic changes no strategy rule,
cooldown, live configuration, or dataset.

### Frozen M15 reference backtest (two policies)

Once the descriptive M15 work is accepted, the next bounded step is one **frozen,
offline reference backtest** that turns the descriptive populations into an
explicit execution and accounting exercise:

```powershell
python -m research.btc_m15_reference_reporting `
    --baseline-run research/results/phase1_reproduction_local/run_20260918T092140133007Z_97d3c169 `
    --output-dir research/results/m15_reference_backtest_runs
```

The engine is `research/btc_m15_reference_backtest.py`; charts, packet writing
and the CLI are `research/btc_m15_reference_reporting.py`. Both are read-only
research code and reuse the accepted signal research rather than re-deriving it.

Two policies are traded on the same protocol:

- `A_emitted_alerts` — the emitted replay M15 alerts, unchanged, with the replay's own one-hour per-timeframe cooldown.
- `B_gate_cooldown` — the same three price-above-EMA21 gates **without** the RSI crossover, with **its own independent** one-hour cooldown. This is deliberately **not** the descriptive `gate_ready_no_cross` population, which had no cooldown at all.

Execution is a delayed candle-price proxy: entry at the open of the first existing
native M5 candle strictly after the signal close, exit exactly 60 minutes later at
that candle's open. No stop-loss, take-profit, trailing rule, or alternative
horizon; one active position per policy; exits processed before entries at the
same timestamp; a signal arriving while a position is open may defer at most one
entry to that position's scheduled exit. Frozen research constants are 10,000
USDT initial equity and 1,000 USDT fixed entry notional, with explicit capital
reservation and `INSUFFICIENT_FREE_CASH` skipping.

**Funding is excluded by design** (`funding_status = EXCLUDED_BY_DESIGN`). Do not
download funding data or implement funding accounting for this experiment, and
never present excluded funding as observed zero funding. Every cost-adjusted
number is labelled *After assumed trading fees and slippage, before funding* and
is not fully net profit. The fee/slippage grid is frozen before performance is
computed and every scenario is reported with fees and execution friction
separately.

Protocol, signal-set hashes, code hashes, machine-readable `actions.csv`,
`trades.csv` and `equity_curve.csv` ledgers, a summary with exposure and
turnover, three charts, and `report.md` are written to one packet directory. All
conclusions are historical development evidence: no untouched holdout, no
optimization, no shadow collection, and no promotion to live trading.

### Four-year M5 regime review

For the fixed four-year BTC M5 study, preserve the canonical dataset and acquire
a validated longer prefix using the
[historical data workflow](../05_data_pipeline/historical-data.md). Rebuild the
baseline on that versioned input, then run the M5 1h/2h/3h/4h horizon diagnostic.
The requested signal window is August 28, 2022 inclusive through August 28,
2026 exclusive in UTC; earlier data provides warmup and later data provides
outcomes. Prepending history can change recursive indicator seeds, so old signal
counts must not be forced onto the expanded dataset.

`python -m research.btc_m5_regime_review --horizon-run <packet> --output-dir <directory>`
groups the resulting fixed signal population by calendar year, consecutive
August-to-August study years, and predeclared past-data regimes. A trailing
90-day return above +10% is UP, below -10% DOWN, otherwise SIDEWAYS. Thirty daily
simple returns' sample standard deviation times sqrt(365), at least 60%, is HIGH
volatility; below 60% is LOW. Features become available only when a full UTC day
has closed. These descriptive thresholds are not optimized filters. Report
missing labels, subgroup sample sizes, and partial calendar years. Four years
does not by itself establish a complete independent market cycle or alpha.

### Bounded BTC AI research pipeline

The bounded orchestration loop lives in [`app/research_pipeline/`](../../app/research_pipeline/)
and is invoked from [`btc_ai_pipeline.py`](../../btc_ai_pipeline.py). It is
offline-first. The default verification run performs one
thinker proposal, one executor plan, deterministic verification of an existing
M5 1h/2h/3h result, and a second thinker review. The fixed tool registry is the
only execution surface; model shell prose is never executed. Results and
decisions are durable in SQLite; a resumed campaign replays any committed
review-decision state effects idempotently before skipping a checked job.

```powershell
python btc_ai_pipeline.py preflight --executor-provider opencode --executor-model opencode-go/muse-spark-1.3-contributor --executor-effort high
python btc_ai_pipeline.py run --offline-fixture --fixture-case stop
# Fixture models, but the deterministic checker reads the existing raw BTC CSV:
python btc_ai_pipeline.py run --offline-fixture --use-saved-data --fixture-case stop
# Explicit opt-in only; this may call the configured Codex CLI:
python btc_ai_pipeline.py run --live --confirm-live --thinker-provider codex --executor-provider codex --thinker-model <model> --executor-model <model>
# Explicit opt-in only; OpenCode must already be running `opencode serve`:
python btc_ai_pipeline.py run --live --confirm-live --thinker-provider codex --executor-provider opencode --thinker-model <model> --executor-model opencode-go/muse-spark-1.3-contributor --executor-effort high
python btc_ai_pipeline.py status <campaign-id>
python btc_ai_pipeline.py resume <campaign-id>
```

The default fixture report is labelled `fixture_validation`; it does not
establish a real-model run or real-data verification. `--use-saved-data` keeps
the thinker/executor stubbed while the checker uses the saved horizon packet's
native M5 path and source hash, and labels the result `real_local_data`.
Matching verified evidence is reusable only after the current raw source bytes,
packet manifest/signals hashes, parameters, horizon definitions, checker/code
identity, durable result hash, and evidence artifact all match. A changed or
unreadable input cannot become a cache-hit success: scientific identity changes
produce explicit failed checker evidence, while access failures pause the
campaign without numerical claims.

Offline mode rejects non-fixture providers before dispatch. Resume restores the
campaign's persisted provider, model, effort, paths, verification mode, and
budgets. Completed proposal/execution/review responses are recovered from
SQLite; generic resume does not redispatch an uncertain in-flight call or
repeat a durable review. If a process stops after the review decision commits
but before its campaign/job status mutation, resume restores that mutation
from the saved STOP, REJECT, PROPOSE_NEXT, or REPAIR decision. Use
`python btc_ai_pipeline.py resume <campaign-id> --reconcile-uncertain` only
after reconciling that external provider state. One atomic job reservation is
recorded for each actual job, including follow-ups, and a cap leaves the next
proposal as `DEFERRED_LIMIT`.

`--opencode-output-mode json_schema` is the default and asks OpenCode to enforce
the response schema through its structured-output tool. The Muse Spark 1.3
Contributor endpoint rejected its forced tool choice in the 2026-09-05 live
smoke (HTTP 400; only `tool_choice=auto` supported). For that endpoint, explicitly
select `--opencode-output-mode json_text`: the controller includes the schema in
the prompt and counts it against the input budget, OpenCode gets no `format`
field and all tool permissions are denied, and the returned JSON object must
pass the same local structural and frozen-proposal checks. Provider schema
enforcement is reported false in this mode. There is no automatic fallback or
retry. The selected mode is stored in the campaign and restored on resume.
Nested OpenCode errors retain bounded, redacted status/code/message details;
headers, request bodies and raw response bodies are not recorded as diagnostics.

The Codex adapter passes the supported `model_reasoning_effort` configuration
override and owns process-group cleanup on timeout. The OpenCode adapter passes
the fully qualified provider/model ID and requested variant through its local
server, denies model tool permissions, and rejects a reported variant mismatch.
Its health/catalog preflight is no-call; it does not start or stop the OpenCode
server. Context and output budgets are controller-enforced estimates, not
provider token caps. Reports distinguish requested model IDs from
runtime-reported IDs and leave usage null with an explanation when unavailable.
Supplemental usage recognizes Codex `reasoning_output_tokens` and
`cache_write_input_tokens` as well as OpenCode's native fields. Explicit zero
counts as reported coverage; missing values stay unknown. Supplemental reasoning
is kept separate from output-token totals, and a missing total is not inferred.
`live_model_verified` is false for fixtures and real-local-data runs until a
successful non-fixture provider attempt exists. Alpha remains `NOT_ASSESSED`.

The provider schemas follow the strict Structured Outputs subset: explicitly
typed fields, closed objects, all properties required, nullable optional
metadata, and a nested `anyOf` for an optional follow-up proposal. Local
validation also accepts legacy fixture records that omit optional metadata.
Nonzero Codex exits retain bounded, credential-redacted error code, message,
parameter and HTTP status when the CLI emits them, plus a session ID when
available. `invalid_json_schema` is recorded as non-retryable `invalid_schema`;
fix the local contract before requesting another explicitly authorized call.
The pipeline does not save full provider stdout or assistant messages as failure
diagnostics. A process invocation still counts against the campaign cap even
when the service rejects its request and reports no token usage.

`task` and executor `tool` are machine identifiers constrained to the registered
`verify_m5_horizons` constant by default in both provider schemas and local validation.
Human descriptions belong in the hypothesis/question/rationale fields. Every
role prompt includes the registered tool's scope, typed parameters, frozen mode
and campaign budget. Executors copy the proposal's parameters and ordered
invariants exactly; reviewers receive the current result and follow-up rules.
Required nonempty text/list fields carry matching schema constraints.
Context-dependent validation happens before marking an attempt completed.
An invalid response within the output budget is retained on its FAILED attempt
with usage and linked failure details; it is never promoted to an accepted job
or silently rewritten. Historical failed campaigns retain their original records.

#### Adaptive population studies

Every study execution plan requires a nonblank `diagnostic_rationale`, including
a horizon summary with fixed parameters. Both the provider schema and the local
validator reject null, empty or whitespace-only explanations. A rejected model
response remains a failed attempt; the controller never fills in its rationale.

`--adaptive` additionally registers `summarize_m5_horizons` and
`compare_m5_cohorts`. The first compares signal and eligible-baseline gross
returns at 60, 120 and 180 minutes; the second compares one horizon across UTC
calendar years or causal trend/volatility labels. Every study preserves the
original all-four-complete population (including the 240-minute completeness
condition), independently checks saved returns against exact raw M5 candles,
and checks parent IDs, comparator eligibility and H1 label availability.
Outputs include counts, mean/median return, positive share and signal-minus-
baseline differences. These are dependent descriptive observations; they do
not establish net P&L, statistical significance or tradable alpha.

The thinker receives the objective and an explicitly unverified saved-data
preview, and reviews authoritative checked evidence before proposing a distinct
follow-up. A cohort proposal may set `grouping: choose`; the executor selects
one registered grouping and supplies a diagnostic rationale. All other
parameters and ordered invariants remain frozen. Paths belong to the
controller. Default adaptive caps are two jobs, three thinker calls and two
executor calls. Ordinary follow-ups progress automatically; a failure, repair,
uncertain attempt or budget boundary stops progression. A model may stop early.
Study evidence is not reused from cache; its identity binds the numerical
checker, tool, loader, horizon and regime modules.

Some historical packets omit the large `baseline.csv`. The `prepare-study`
command reconstructs this file only for the supported frozen all-bar comparator
with zero preparation exclusions. It validates exact raw hashes, rebuilds all
four horizons, checks the original counts and saved summary statistics, and
writes a derived packet plus a copied parent into a new directory. Historical
files remain intact. Parent CRLF-to-LF repair is permitted in that copy only
when it restores the exact original manifest hash. Raw research CSVs are marked
`-text` in `.gitattributes` so Git preserves their byte identities on Windows.

```powershell
python btc_ai_pipeline.py prepare-study --baseline-packet research/results/phase1_four_year_runs/run_20260904T084317586748Z_97d3c169 --horizon-packet research/results/m5_four_year_horizon_runs/run_20260904T084448776441Z_97d3c169 --workspace research/results/my_prepared_study
$parentPacket = "research/results/my_prepared_study/run_20260904T084317586748Z_97d3c169"
$horizonPacket = "research/results/my_prepared_study/run_20260904T084448776441Z_97d3c169"
python btc_ai_pipeline.py preflight --adaptive --baseline-packet $parentPacket --horizon-packet $horizonPacket
python btc_ai_pipeline.py run --adaptive --offline-fixture --use-saved-data --baseline-packet $parentPacket --horizon-packet $horizonPacket --db research/results/my_adaptive/pipeline.sqlite --output-dir research/results/my_adaptive
python btc_ai_pipeline.py baseline <campaign-id> --db research/results/my_adaptive/pipeline.sqlite --output-dir research/results/my_adaptive
```

For live adaptive work, use the same packet arguments and explicit
`--live --confirm-live` provider/model arguments instead of `--offline-fixture
--use-saved-data`. Run provider preflight first. Existing Codex and OpenCode
authentication remain separate; the CLI does not configure credentials.
For installation, interactive provider connection and local server commands,
see [OpenCode Windows setup](../03_setup_and_installation/opencode-windows.md).

Preflight and every provider dispatch use the same frozen input identity and
parent ancestry checks. Configured current dataset paths take priority over
historical absolute manifest paths, which remain provenance. OpenCode session
identity is committed to the attempt before message dispatch. Permissions deny
all tools except the schema response tool `StructuredOutput`. An HTTP timeout
attempts a bounded session abort; absent a confirmed abort, the campaign pauses
as uncertain and ordinary resume cannot issue another call.

`report.json` distinguishes any successful real-provider attempt from
`live_loop_verified` (a checked result with real proposal, execution and review)
and `adaptive_sequence_verified` (two distinct checked studies). Usage totals
and cost coverage reflect provider reports; missing costs remain unknown. The
report also includes elapsed campaign span (including pauses), timed numerical
checks, invalid execution-plan attempts, repair decisions and token/cache
breakdowns with reporting coverage. These are observations, not provider price
estimates. The
`baseline` command reruns exactly the accepted study specifications with zero
model calls and compares tables, input identities and checker hashes. It
measures numerical equivalence and provider overhead; it does not measure
independent experiment-selection quality or establish monetary savings.

## Step 5: Manual Handoff

Code the signal as a strategy class following `docs/workflows/add-strategy.md`:
1. Create strategy file inheriting `BaseStrategy`
2. Implement `analyze()` method with stateless pattern
3. Define `DEFAULT_CONFIG` with all parameters
4. Register in loader, seed database

This is a manual process — the researcher translates notebook findings into production code.

## Step 6: Validation with Bot Tools

Use the bot's optimization suite:
1. **Grid search**: Sweep key parameters, check for sensitivity cliffs
2. **Walk-forward**: Out-of-sample validation to detect overfitting
3. **Sensitivity analysis**: Identify which parameters are fragile

Criteria for proceeding:
- Walk-forward verdict: "Robust" or "Marginal" (not "Overfit")
- Sensitivity: no parameter cliff within ±20% of chosen value
- Minimum trade count: 50+ trades in the test period

## Step 7: Paper Trading

Test with progressively more realistic execution:
1. `mock` mode — backtest on new, unseen data
2. `sim` mode — live ticks, simulated fills
3. `paper` mode — real exchange API, testnet funds

Monitor for at least 2-4 weeks in paper mode before considering live deployment.

## Step 8: Live Deployment

Switch to `live` mode with conservative position sizing. See `docs/12_deployment_and_ops/deployment-checklist.md`.

#### Measuring research selection quality

The zero-model `benchmark` command evaluates a saved live cohort choice against
an independently applied scripted policy. It freezes both choices before
calculating the nine-candidate reference catalog, verifies source/artifact/input
identity, and reports paired 7/28-day uncertainty, weekly support and 28-day
influence. Historical AI usage, fresh scripted runtime and evaluator overhead
remain separate. It is a retrospective descriptive pilot with no untouched
holdout; completing it does not establish AI superiority. See the
[selection benchmark protocol and CMD command](research-selection-benchmark.md).
