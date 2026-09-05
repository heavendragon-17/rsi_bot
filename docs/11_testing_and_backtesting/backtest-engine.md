# Backtest Engine

> Single backtest flow, portfolio mode, batch mode, tick-level paper replay, engine internals, and performance optimizations.

---

## Module Structure

The backtest module is organized into sub-packages under `app/backtest/`:

```
app/backtest/
├── signal_replay.py       # Offline BTC alert replay and Markdown audit log
├── signal_replay_cli.py   # Replay command-line argument parsing
├── btc_research_phase1.py # Reproducible BTC signal-return evidence baseline
├── signal_replay_data.py  # Vectorized CSV normalization and event loading
├── signal_replay_models.py # Typed replay result models
├── signal_replay_preparation.py # Cached point-in-time indicator preparation
├── engine/          # Core engines and event sources
│   ├── backtest_engine.py      # Single-symbol BacktestEngine
│   ├── portfolio_engine.py     # Multi-symbol PortfolioEngine
│   ├── event_source.py         # Candle event source for single backtest
│   ├── portfolio_event_source.py  # Time-sorted event multiplexer
│   ├── metrics.py              # Metrics computation
│   └── curves.py               # Equity/drawdown curve generation
├── exchange/        # Mock/simulated exchange adapters
│   ├── executor.py             # Order execution logic
│   └── mock_exchange.py        # MockExchange for backtesting
├── data/            # Data loading and downloading
│   ├── manager.py              # Data manager
│   ├── download.py             # OHLCV data download (CLI)
│   ├── inline_download.py      # API missing/stale CSV download, serialized per path
│   └── download_tick.py        # Tick data download
├── runners/         # Runner scripts for each backtest mode
│   ├── batch_runner.py         # Batch (multi-config) runner
│   ├── portfolio_runner.py     # Portfolio backtest runner
│   ├── tick_replay.py          # Tick-level paper replay
│   └── progress.py             # Progress reporting utilities
├── reporting/       # Report generation and export
│   ├── reporter.py             # Main report generator
│   ├── html.py                 # HTML report output
│   ├── export.py               # CSV/JSON export
│   ├── batch_report.py         # Batch run reports
│   └── styles.py               # Report styling
├── statistics/      # Statistical analysis and visualization
│   ├── analyzer.py             # Statistical analysis
│   ├── metrics.py              # Statistical metrics
│   └── visualize.py            # Chart/plot generation
├── optimization/    # (placeholder for future optimization tools)
├── service.py       # BacktestService — orchestrates runs
├── persistence.py   # DB persistence for backtest results
├── enrichment.py    # Result enrichment
├── config_builder.py # Config construction helpers
└── backtest.py      # CLI entry point
```

---

## Backtest Modes

The system supports 4 backtest modes via the `BacktestMode` enum:

| Mode | Runner | Description |
|------|--------|-------------|
| `single` | `BacktestEngine` | Single-symbol backtest against a local CSV |
| `portfolio` | `app/backtest/runners/portfolio_runner.py` | Multi-symbol chronological portfolio simulation |
| `batch` | `app/backtest/runners/batch_runner.py` | Batch runs across multiple configs/symbols |
| `tick_replay` | `app/backtest/runners/tick_replay.py` | Tick-by-tick replay through PaperExchange |

The repository also provides `app.backtest.signal_replay`, an offline
multi-timeframe replay for the Telegram-only `btc_rsi_cross_alert`. It is not
an order simulation and is intentionally separate from `BacktestEngine`.

## Historical BTC Alert Replay

Run the replay with native BTC M5, M15, H1, and H4 OHLCV CSVs:

```bash
python -m app.backtest.signal_replay \
    --m5 app/backtest/data/BTCUSDT_5m.csv \
    --m15 app/backtest/data/BTCUSDT_15m.csv \
    --h1 app/backtest/data/BTCUSDT_1h.csv \
    --h4 app/backtest/data/BTCUSDT_4h.csv \
    --start 2026-08-01 \
    --end 2026-08-28
```

By default this writes two independent manual-review files:
`app/backtest/report/signal_replay_2026-08-01_2026-08-28_m5.md` and
`app/backtest/report/signal_replay_2026-08-01_2026-08-28_m15.md`. Each file
contains only its own timeframe's confirmed cards, with the full Telegram
card fields and blank manual-review fields. To choose the paths explicitly,
use both `--output-m5 <path>` and `--output-m15 <path>`. The legacy combined
file remains available with `--output <path>`.

The public Python entry point is:

```python
run_btc_alert_replay(
    m5_path,
    m15_path,
    h4_path,
    start_utc7=None,
    end_utc7=None,
    output_path=None,
    *,
    h1_path=None,
    output_m5_path=None,
    output_m15_path=None,
)
```

When `output_path` is omitted, the API writes the default M5 and M15 files.
When `output_path` is provided, it writes one combined report for backward
compatibility. Explicit split paths must be supplied together, and cannot be
combined with `output_path`.

Each input CSV must contain `timestamp, open, high, low, close, volume`.
Naive source timestamps use the repository's fixed UTC+07:00 storage
convention and are converted to UTC exactly once before evaluation. CLI dates
and naive Python datetimes are interpreted as UTC+7; date-only `--end` values
include the entire local day.

The runner keeps the full frames available for indicator warmup, skips initial
M5/M15 candles until the trigger and both H1/H4 contiguous-history minimums are
available, and reports those skipped warmup candles separately from later
not-ready data. It precomputes the locked indicators once per contiguous
segment, then evaluates M5 and M15 trigger candles chronologically with
constant-time point-in-time lookups. This avoids recalculating the complete
historical prefix for every candle. Homogeneous CSV timestamps are parsed in
one vectorized operation, and each event retains its source-array position so
the hot loop does not repeat datetime normalization or dictionary lookup.

The replay first runs an allocation-light NumPy candidate scan. Its vectorized
WMA45 is used only to produce a conservative candidate superset with a numeric
safety margin. Every possible signal then rebuilds the exact locked WMA values
and passes through the existing M5/M15 evaluator before cooldown, deduplication,
or logging. Rejected candles therefore avoid unnecessary `Decimal`, domain
model, SHA-256 event-ID, and Telegram-card allocation without changing signal
semantics. It selects only point-in-time H1/H4 data, applies the live one-hour
per-timeframe M5/M15 cooldowns and event deduplication, and writes only confirmed alerts. Every
written alert reuses the exact Telegram card formatter, including its indicator
snapshot and UTC+7 candle-close time.

This replay path is CPU-only. An Intel Arc or other GPU does not accelerate
pandas/NumPy automatically and is not required for a two-year BTC replay. On
the development machine, the 280,510-candle 2024-08-28 through 2026-08-28
replay improved from 12.43 seconds to 3.87 seconds; this is a local benchmark,
not a runtime guarantee.

Each Markdown report includes a confirmed-signal count and blank `WIN`,
`LOSS`, and `SKIP` review fields. It does not calculate win rate, PnL, SL/TP,
orders, or any automated outcome because the alert card has no trade-lifecycle
levels; outcomes remain manual chart-review decisions.

## BTC Research Phase 1 Baseline

The repository-root [`btc_research_phase1.py`](../../btc_research_phase1.py)
command creates a run-specific evidence packet for the current BTC alert
baseline. It accepts a data directory containing the native
`BTCUSDT_5m.csv`, `BTCUSDT_15m.csv`, `BTCUSDT_1h.csv`, and `BTCUSDT_4h.csv`
files, an output-directory parent, and optional inclusive trigger-close
boundaries:

```powershell
C:\ProgramData\anaconda3\envs\rsi\python.exe btc_research_phase1.py `
    --data-dir app/backtest/data `
    --output-dir research/results/phase1_runs `
    --start 2024-09-01 `
    --end 2026-08-28
```

The command reuses [`run_btc_alert_replay()`](../../app/backtest/signal_replay.py)
and the existing BTC evaluator, including point-in-time preparation and the
independent one-hour M5/M15 cooldowns. It validates the source filename/schema,
timestamps, duplicates, native cadence, common coverage, and replay warmup.
Preparation is also audited for every requested M5/M15 trigger close through
the shared point-in-time preparation path. The packet records requested versus
evaluable bars and exclusion reasons such as missing context or insufficient
contiguous history. A missing required warmup or a timeframe with no evaluable
requested coverage is `INVALID`; partial readiness is `INCOMPLETE`; a fully
prepared, complete period with zero signals remains a valid descriptive result.
For each emitted M5/M15 signal, it reports gross close-to-close returns at
exactly 1h, 4h, 12h, and 24h. A missing exact target is recorded as incomplete
or missing, and any native cadence gap invalidates the affected outcome; a
later candle is never substituted.

Each run writes `manifest.json`, `signals.csv`, `summary.json`, and `report.md`
under a timestamped child directory. The manifest records source SHA-256
hashes, coverage, warmup, strategy/config identity, Git revision and dirty-code
identity, environment versions, the command, metric definitions, warnings, and
completion status. Summaries include complete/total counts, means, medians,
monthly rows, and a same-timeframe baseline over matched signal coverage. The
baseline applies shared per-event preparation only: it does not apply bullish
signal gates or cooldown, and its preparation exclusions are recorded in the
packet. The 0.10% return-minus-cost value is illustrative sensitivity only;
it is not a fill, fee, slippage, funding, order, or P&L simulation. Operational
status is reported separately from alpha assessment, which remains
`NOT_ASSESSED` in this milestone.

Replay cooldown state starts at the requested window boundary and is independent
for M5 and M15. Separate replay windows therefore do not inherit alerts from
one another; comparisons across separately replayed windows must account for
that boundary behavior.

### BTC AI research pipeline MVP

The repository-root [`btc_ai_pipeline.py`](../../btc_ai_pipeline.py) provides an
offline-first thinker/executor/checker/reviewer loop over the saved BTC evidence.
`preflight` performs no model call; `run --offline-fixture` completes the loop
with deterministic fixture providers; `--use-saved-data` keeps those providers
stubbed while checking the existing raw CSV; and `run --live --confirm-live` is
the explicit opt-in for configured non-fixture provider calls. Runtime thinker
and executor provider/model/effort/budget settings are separate. SQLite records the campaign,
frozen specification hash, every attempt and usage record, results, failures,
budgets, and evidence-linked decisions. `resume` skips completed provider
phases and replays a committed review decision's status effects before
skipping its checked job; uncertain in-flight attempts remain paused until an
explicit `--reconcile-uncertain` acknowledgement. A `REPAIR` decision is a durable
actionable pause rather than a second identical thinker call. A verified result
is reusable only when current source bytes, source/packet hashes, horizon
definitions, checker/evaluator code identity, durable evidence/result hashes,
and the evidence artifact all match.

The executor can select only the registered `verify_m5_horizons` tool. That tool
reuses `research.btc_m5_horizon_diagnostic.profile` and the Phase 1 exact-target
evaluator to check one existing M5 event at 1h, 2h, and 3h. The checker records
source/packet hashes and labels synthesized fixture evidence separately from
real local-data verification. Offline mode rejects non-fixture providers before
dispatch. The Codex adapter uses read-only structured output, passes the
supported `model_reasoning_effort` override, and cleans up its owned process
group on timeout. The OpenCode adapter uses the local `opencode serve` API with
an explicit provider/model reference, a no-call health/catalog preflight,
structured JSON schema, zero structured-output retries, and denied tool
permissions; it uses an overall HTTP deadline but does not own the server
process. Controller-side context/output estimates are not provider token caps.
Offline schema regressions validate all three provider schemas against the
strict output subset and realistic payloads, including nullable metadata and
nested follow-ups. Mocked provider-failure tests cover structured HTTP 400
schema rejection, actionable error persistence, redaction, and stopping after
one rejected call. These tests do not establish live acceptance of a new schema.
Task-contract regressions replay the saved v2 natural-language task rejection,
check exact registered IDs and nonempty schema fields, and exercise the full
fixture loop using the role prompts' task catalogs. Proposal, execution and
review context mismatches must retain the response and failure-to-attempt link
while preventing the next stage from dispatching.
OpenCode is implemented as the first subsequent executor adapter; GLM remains
the next missing provider integration. No candidate code, arbitrary shell,
strategy/configuration change, or alpha approval is in scope.

### Offline M5 horizon diagnostic

[`research/btc_m5_horizon_diagnostic.py`](../../research/btc_m5_horizon_diagnostic.py)
profiles fixed parent Phase 1 M5 IDs at exactly 1h, 2h, 3h, and 4h. Run it with
`python -m research.btc_m5_horizon_diagnostic --baseline-run <phase1-packet> --output-dir research/results/m5_horizon_runs`.
The command verifies all four native source SHA-256 hashes against the parent,
records hashes for the parent manifest/signals/summary/report, checks original
1h/4h outcome parity, and fails if parent or source content changes during the
run. Signals are read from the accepted packet rather than replayed, preserving
their emission IDs and one-hour cooldown boundary history.

The matched all-eligible-bar comparator calls shared preparation for every M5
bar between the first and last parent signal. Every horizon uses the same
all-four-complete signal IDs and baseline bars. `COMPLETE`, `INCOMPLETE_TAIL`,
`MISSING_TARGET`, and `GAP` remain explicit; later targets and partial excursions
are not substituted. MFE is nonnegative and MAE is nonpositive, each measured
from signal close using only future native candles through target close. These
are hindsight bounds, not captured P&L. UTC monthly summaries and optional
2,000-replicate paired circular seven-day calendar-block percentile intervals
are descriptive only; alpha is `NOT_ASSESSED`.

Each timestamped packet contains `signals.csv`, `baseline.csv`, `manifest.json`,
`summary.json`, and `report.md`. Long rows retain excluded outcomes and the
`included_all_horizons` flag. Summary metrics include total/complete/matched
counts, exact statuses, mean/median returns, positive-return share,
mean/median excursions, baseline means, and signal-minus-baseline differences.
The bootstrap resamples the same UTC calendar blocks for signal and baseline,
retains zero-signal days, and computes observation-weighted means from daily
sums/counts. `--no-bootstrap` omits it. There is no significance claim or
per-signal hindsight choice of horizon.

Focused offline tests:

```powershell
C:\ProgramData\anaconda3\envs\rsi\python.exe -m pytest tests/test_btc_m5_horizon_diagnostic.py -q
```

They cover exact 2h/3h targets, trigger/post-target candle exclusion,
zero-referenced excursions, gaps versus missing targets versus tails, fixed
complete populations, per-event baseline eligibility, parent price parity,
and reproducible paired calendar-block resampling.

### BTC M5 calendar and regime diagnostics

After producing the four-year M5 horizon packet, run:

```powershell
C:\ProgramData\anaconda3\envs\rsi\python.exe -m research.btc_m5_regime_review `
  --horizon-run <horizon-packet-directory> `
  --output-dir research/results/m5_regime_runs
```

This exports signal labels, population summaries, comparisons, and a report by
calendar year, consecutive August-to-August study year, and fixed trend/volatility
regime. It verifies the H1 input hash, requires complete native hourly cadence,
aggregates only completed UTC days, and joins regime features backward as of the
signal close. Trend uses trailing 90-day return (+/-10%); volatility uses 30-day
sample standard deviation of daily simple returns annualized by sqrt(365), with
a 60% boundary. Missing labels remain explicit. No subgroup significance or
executable P&L is claimed. Tests in `tests/test_btc_m5_regime_review.py` verify
future invariance, daily availability, missing hours, warmup, and study boundaries.
The separate acquisition fixtures in `tests/test_btc_four_year_data.py` cover
checksum, parsing, overlap, and source-validation behavior without network calls.

### BTC Signal Review Lab

The backtest UI's **Signal Review** workspace runs the same deterministic BTC
alert replay, but persists a research dataset instead of `RunResult` or
`Trade` rows. Each run is immutable and records the replay definition, Git
revision, requested UTC+7 window, source CSV facts, counters, and status.
Each emitted alert becomes an immutable `SignalReplaySignal` with the exact
Telegram card plus a versioned structured snapshot. A unique
`(replay_run_id, event_id)` constraint prevents duplicate alerts within a run;
rerunning a window creates a new run and never overwrites prior data.

The review layer keeps two labels independent:

- `quality`: `UNREVIEWED`, `GOOD`, `BAD`, or `UNCERTAIN`;
- `human_outcome`: `UNSET`, `WIN`, `LOSS`, or `SKIP`.

The initial chart exposes candles at or before the signal's point-in-time
anchor only. Reviewers can switch the same signal between native M5, M15, H1,
and H4 sources. Exact-alignment timeframes anchor on the signal close; otherwise
the anchor is the latest fully closed candle at or before the signal timestamp,
so H1/H4 inspection cannot use a forming or future candle.

Every chart includes price EMA21/EMA200 plus RSI21, EMA9(RSI21), and
WMA45(RSI21). Reviewers can save the fixed-entry TP/SL plan before selecting a
quality label; saving any explicit quality label then unlocks 2,000 candles in
the selected chart timeframe and the human outcome controls. Each manual/lazy
extension adds another 2,000 candles. The browser initially frames a smaller
signal-centered range and lets the reviewer pan through the loaded future
instead of compressing every candle into one unreadable viewport.

The chart uses the trigger candle close as its reference and shows 1h, 4h, 12h,
and 24h close-return, maximum favorable excursion, and maximum adverse
excursion observations. Reviewers may also save an optional long TP/SL plan
beside the chart. The entry is fixed to the signal candle close; the plan is
saved before quality selection and its outcome stays unevaluated while the
future is locked. After quality unlocks the future, the review service scans
future candles from the signal's native timeframe and records the first touched
level plus elapsed time. A same-candle TP and SL touch is marked ambiguous
because OHLC data cannot establish intrabar order. These remain market
observations, not simulated trade PnL: there are no fills, sizing, fees,
leverage, or execution assumptions, and no 1R-based WIN/LOSS classification.
The separate human outcome remains manual.

The availability endpoint validates the current M5, M15, H1, and H4 CSVs and
returns their common candle-close range. Omitted replay boundaries default to
that full intersection; supplied boundaries are rejected before job creation
when they fall outside it. Only one signal replay may run at a time, and a
`running` database row without an in-memory executor job is reconciled to a
clear interrupted/failed state after an API restart.

The worker uses the existing ThreadPoolExecutor/SSE infrastructure and loads
the four current CSVs. Forward observations prepare one timestamp index and
one set of NumPy OHLC arrays per trigger timeframe, then use binary searches
and bounded slices for every signal/horizon. This avoids rescanning an entire
source frame for every signal. SSE phases continue after signal detection as
`metrics` and `saving`, so the UI no longer appears frozen while rows are
prepared and committed. Signals, latest reviews, and forward metrics are
persisted in one transaction before the run is marked complete.

CSV candles remain outside SQLite; chart responses report missing historical
data, shortened future data, and incomplete horizons explicitly. Markdown
replay reports remain available through the existing CLI as an optional
audit/export format.

---

## Core V2.1 point-in-time replay

Core V2.1 has a separate deterministic event replay in
`app/backtest/core_v2_1/`. It calls the same pure evaluator as the live
signal-only runtime; it does not run `MockExchange`, synthesize fills, or
calculate portfolio metrics.

```bash
# Reviewer stepping stone: ETH, SOL, BNB, XRP, LINK, HYPE + BTC context
python -m app.backtest.core_v2_1 \
  --universe-mode six \
  --data-dir app/backtest/data \
  --output-dir artifacts/core_v2_1/replay

# Locked 25-candidate mixed-venue universe + BTC benchmark
python -m app.backtest.core_v2_1 \
  --universe-mode full \
  --data-dir app/backtest/data \
  --output-dir artifacts/core_v2_1/full_replay
```

`--universe-mode available` replays all valid discovered candidates;
`--symbols` chooses an explicit approved subset. `--start` and `--end` require
timezone-aware boundaries. The default/common-window mode uses the
intersection shared by the selected candidates and BTC; `--full-available`
retains every trigger close and records unavailable contexts as explicit
`NOT_READY` ledger rows.

### Data and point-in-time rules

1. Load the venue-specific M15 CSV for every selected candidate and Binance
   BTC benchmark. PUMP resolves only to
   `HYPERLIQUID__PUMP_USDC_PERP_15m.csv`.
2. Normalize the stored timezone-naive UTC+7 candle-open timestamp to aware
   UTC close time.
3. Strictly validate schema, OHLCV, duplicates, cadence, forming candles,
   locked anchor, source identity, and coverage.
4. Derive H1/H4 on UTC epoch boundaries from complete M15 buckets. Partial
   buckets are discarded.
5. At each candidate M15 close, require the exact latest expected Alt H1, BTC
   H1, and BTC H4 close. No future row and no one-bucket-stale fallback is
   allowed.
6. Process each candidate's state chronologically from the locked feature
   anchor and write every decision, including silent/rejected/not-ready rows.

### Audit outputs

Each run writes:

- `core_v2_1_replay.jsonl` for one complete structured record per trigger;
- `core_v2_1_replay.csv` for spreadsheet/filter workflows; and
- `core_v2_1_replay.metadata.json` for hashes, inputs, coverage, anchor,
  timestamp/seed conventions, counts, and requested/actual window.

The checked full-universe artifact under `artifacts/core_v2_1/full_replay/`
covers all 25 candidates plus BTC from `2026-06-29T11:30:00Z` through
`2026-08-20T13:15:00Z`: 125,000 ledger records, 98,550 evaluated rows,
26,450 `NOT_READY` rows, and 477 public events (`63 A_PLUS_LONG`,
`207 WAIT_FOR_PULLBACK`, `19 PULLBACK_LONG`, `72 WAIT_CANCELLED`, and
`116 WAIT_EXPIRED`). See the adjacent
[`artifacts/core_v2_1/README.md`](../../artifacts/core_v2_1/README.md) for
reproduction and artifact hashes.

These counts audit signal/state-machine behavior only. They make no claim
about orders, fills, fees, slippage, PnL, win rate, or strategy performance.
A future execution simulator must implement those separately under the
reviewed execution contract.

---

## System Architecture

```
React Frontend (Zustand stores)
    │ HTTP / SSE
FastAPI Backend
    ├── Routes: backtest_run.py, backtest_results.py, backtest_stream.py
    ├── BacktestService (app/backtest/service.py)
    ├── Executor (ThreadPoolExecutor, SSE queues)
    ├── BacktestEngine (MockExchange, Strategy, PortfolioManager)
    └── SQLite DB (runs, configs, results, trades)
```

---

## Single Backtest Flow

```
User clicks "Run Backtest"
    │
    ▼
POST /api/backtest/run
    1. Validate request; download a missing or stale CSV when required
    2. Create Run row (status="running") + RunConfig row
    3. Create asyncio.Queue for SSE progress
    4. Submit BacktestEngine.run() to ThreadPoolExecutor
    5. Return { run_id, status: "running" }
    │
Frontend opens SSE: GET /api/backtest/{run_id}/progress
    ├── "progress" events → update progress bar (0-100%)
    ├── "complete" event → fetch results
    └── "error" event → show toast + mark failed
    │
On complete:
    1. getRunDetail(run_id)  → metrics + trades
    2. getTimeseries(run_id) → equity/drawdown curves (zlib decompressed)
    3. Render ResultsDashboard
```

Inline downloads use one `threading.Lock` per CSV path. API jobs share a
single-process thread pool, so this prevents concurrent writes to the same
dataset without platform-specific file locking.

---

## BacktestEngine Internals

**Class**: `BacktestEngine(Engine)` in `app/backtest/engine/backtest_engine.py`

### Initialization

1. Read CSV, parse timestamps
2. Create `MockExchange(initial_balance, leverage, taker_fee=0.05%, maker_fee=0.02%)` (in `app/backtest/exchange/mock_exchange.py`)
3. Create strategy instance and `PortfolioManager`
4. `_prepare_dataframe()`: set index, mark all `closed=True`, add `ts` column, run `strategy.indicators.compute()` once for the full dataset (O(n) pre-computation instead of per-candle O(n²)). Works with any `IIndicators` implementation (the unified `Indicators` class supports all strategies).

### WARMUP = 220 candles

First 220 candles are skipped (indicators need warmup). Events start from candle 221.

### Candle Processing (`_handle_candle_close()`)

1. `exchange.update_candle(symbol, o, h, l, c, ts)` — MockExchange checks wicks against pending SL/TP orders. Supports both LONG and SHORT positions:
   - LONG: SELL limit (TP) triggers when `low <= price`; SELL stop_market (SL) triggers when `low <= stopPrice`
   - SHORT: BUY limit (TP) triggers when `low <= price`; BUY stop_market (SL) triggers when `high >= stopPrice`
2. If exit orders executed and symbol no longer in exchange.positions → position fully closed → clean up local state, reset context to SCANNING. Position amounts are **signed** (positive=LONG, negative=SHORT). PnL: `amount × (exit - entry)` works for both directions.
3. `portfolio.sync_from_exchange()`
4. `strategy.analyze(symbol, df_slice, position, context)` → dispatch actions
5. Report progress every 2%

### End of Run

1. Close any open positions at final CSV price (`exit_reason="EOD"`)
2. Fire `on_progress({"pct": 100})`
3. Return `compute_results()`

---

## Results Structure

`compute_results()` returns:

| Key                                                     | Contents                                                                                                                             |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `metrics`                                               | total_trades, win/loss counts, win_rate, pnl stats, profit_factor, expectancy, avg_hold_hours, exit_reason_counts, consecutive stats |
| `risk_metrics`                                          | sharpe_ratio, sortino_ratio, calmar_ratio, volatility, var_95                                                                        |
| `drawdown`                                              | max_drawdown_pct/value, max_dd_duration, avg_drawdown_pct                                                                            |
| `monthly_returns`                                       | Per-month: pnl, pnl_pct, trade count                                                                                                 |
| `equity_curve`                                          | [{date, balance}, ...]                                                                                                               |
| `drawdown_curve`                                        | [{date, drawdown}, ...]                                                                                                              |
| `round_trips`                                           | Complete trade cycles with avg_exit_price, exit_reason                                                                               |
| `initial/final_balance`, `net_profit`, `net_profit_pct` | Summary                                                                                                                              |

### Round-Trip Construction

Multiple partial fills (TP1, TP2, SL) grouped under one round-trip. `avg_exit_price` = weighted average. Exit reason priority: SL > TP3 > TP2 > TP1.

---

## Batch Mode (Multi-Symbol)

Single engine instance simulating portfolio across all symbols simultaneously (NOT N independent backtests).

- **Capital**: Shared pool, risk-based sizing per trade
- **Exposure cap**: Total open value cannot exceed `equity × max_position_pct`; new trades rejected if exceeded
- **Data sync**: Intersection-only date range; small gaps (<5 candles) forward-filled, large gaps rejected
- **Results**: Portfolio aggregate + per-symbol breakdown + correlation matrix

---

## Unified Portfolio Mode

A true chronological portfolio simulation via `app/backtest/runners/portfolio_runner.py`.

- **Event Multiplexing**: `PortfolioEventSource` (in `app/backtest/engine/portfolio_event_source.py`) loads pre-computed CSVs for all configured symbols and uses a priority queue to yield `CandleCloseEvent`s sorted strictly by time.
- **Global Liquidation**: `MockExchange.check_liquidation()` continuously monitors total portfolio equity (balance + margin + unrealized PnL). If it drops below zero, all positions are force-closed with an additional 0.5% liquidation fee penalty.
- **Sizing**: Trades use the exact same strategy config, but position sizing calculates risk based on a fixed initial portfolio capital percentage (if `use_initial_capital_for_risk` is set).
- **Auto Data Fetching**: On startup, it checks for missing historical data across all requested tickers and seamlessly attempts to download the data before processing to execution.

---

## Tick-Level Paper Backtest

Tick-by-tick replay through `PaperExchange` for high-fidelity SL/TP fill simulation.

**Entry**: `app/backtest/runners/tick_replay.py`

```bash
python -m app.backtest.runners.tick_replay \
    --ohlc app/backtest/data/BTCUSDT_5m.csv \
    --ticks app/backtest/data/BTCUSDT_ticks_2024_01.csv \
    --symbol BTC/USDT --timeframe 5m --balance 10000
```

- Exchange: `PaperExchange` — real FIFO SL/TP, gap fills, fees
- Tick CSV streamed line-by-line (low memory)
- OHLC and tick files must overlap in time range
- Runtime: 1-5 minutes per month of tick data

---

## Performance Optimizations

| Optimization            | Speedup             | Mechanism                        |
| ----------------------- | ------------------- | -------------------------------- |
| ProcessPoolExecutor     | 8-12× (grid search) | Bypasses GIL, parallel processes |
| float64 in MockExchange | 20-40% per run      | Replaces Decimal arithmetic      |
| Fixed-size tail window  | 10-25% per run      | O(1) DataFrame slicing vs O(n)   |

**Combined impact**: Grid search (200 params, 8 cores): ~600s → ~30-60s

---

## SSE Thread-to-Async Bridge

```python
# Worker thread → asyncio.Queue → SSE endpoint
mp_queue.put({"event": "progress", "pct": 42})
# Main thread polls mp_queue:
loop.call_soon_threadsafe(async_queue.put_nowait, msg)
# SSE endpoint:
event = await asyncio.wait_for(async_queue.get(), timeout=300)
```

### Crash Recovery

On server startup: query `runs` where `status='running'`, mark as `status='failed'` with note "Server restart — run interrupted".
