# Phase 1 Audit Pipeline

> Statistical gates that determine whether a strategy is trustworthy enough to
> deploy. A strategy must pass audit before being eligible for paper trading.

This module is **read-only on backtest results** — it never modifies the
strategies, the engine, or the trade history. It consumes `Trade` ORM rows
plus raw OHLCV CSVs and produces a verdict.

## Purpose

A normal backtest produces a measurement (Sharpe = 1.8, max DD = 18%). It does
not tell you whether the measurement is statistically distinguishable from
luck, whether the result was selected from many trials, or whether the
"best" parameters will underperform out-of-sample. Phase 1 closes that gap
through five tests, each gating progressively stronger claims.

## Module location

`app/backtest/audit/` — sibling to `statistics/`, `engine/`, `runners/`.

Each file has one responsibility. Files do not import from each other except
through the canonical inputs (trade log DataFrame, signal panel DataFrame).

## Inputs

Two canonical DataFrames, built once and passed to every test:

### Trade log (built by `trade_log.py`)

A per-trade DataFrame with these columns:

| Column | Type | Source |
|--------|------|--------|
| `entry_time` | datetime | `Trade.entry_time` |
| `exit_time` | datetime | `Trade.exit_time` |
| `side` | str | `Trade.side` |
| `symbol` | str | `Trade.symbol` |
| `entry_price` | float | `parseFloat(Trade.entry_price)` |
| `exit_price` | float | `parseFloat(Trade.exit_price)` |
| `qty` | float | `parseFloat(Trade.quantity)` |
| `ret_pct` | float | `parseFloat(Trade.pnl_pct)` |
| `ret_abs` | float | `parseFloat(Trade.pnl)` |
| `holding_hours` | float | `Trade.hold_time_hours` |
| `exit_reason` | str | `Trade.exit_reason` |
| `run_id` | int | `Trade.run_id` |

All `TEXT` columns in the ORM are Decimal-as-string. The adapter must call
`float(str_val)` (or `Decimal()` then `float()`) on every monetary read. There
is precedent for this conversion pattern in `app/api/routes/`.

Sorted by `entry_time` ascending. Indexed 0..N-1 (positional).

### Signal panel (built by `signal_panel.py`)

A per-bar DataFrame for one `(symbol, timeframe)` pair:

| Column | Description |
|--------|-------------|
| `close` | Close price |
| `rsi_14` / `rsi_ema9` / `rsi_wma45` | Indicator values from `Indicators.compute()` |
| `fwd_logret_1` | Log return over next 1 bar |
| `fwd_logret_4` | Log return over next 4 bars |
| `fwd_logret_16` | Log return over next 16 bars |
| `fwd_logret_96` | Log return over next 96 bars |

Indexed by timestamp. Built by reading the same CSV the engine consumed
(`app/backtest/data/{SYMBOL}_{timeframe}.csv`), running the same
`Indicators.compute()` call, and adding forward returns via shifted log
differences. NaN rows from indicator warmup and the tail are dropped.

No new persistence is required for Phase 1 — the panel is rebuilt on demand.
This costs a few hundred ms per audit, which is negligible against the
seconds-to-minutes spent on bootstrap and PBO.

## Tests, in execution order

The order matters. Cheap structural failures are caught before expensive
statistical computation. If a test in this list fails, downstream tests are
still run (the API returns the full audit report) but the verdict is FAIL.

### 1. Sanity audits — `sanity.py`

Three quick structural checks:

| Check | Pass criterion |
|-------|----------------|
| Top-5 trade PnL share | `< 0.50` of total |abs(PnL)| |
| Long/short symmetry | Both sides contribute positive aggregate PnL OR strategy is documented single-direction |
| Cost sensitivity | Total PnL with 2x fees + 1 tick extra slippage remains positive |

Returns a dict per check with `value`, `threshold`, `passed`.

A pass on concentration is necessary but not sufficient — borderline scores (>0.40) should be cross-referenced against bootstrap CI width before deployment.

### 2. Information Coefficient — `information_coefficient.py`

For the indicator that drives entries (RSI for the existing strategies),
compute the Spearman rank correlation against forward returns at horizons
`[1, 4, 16, 96]` bars.

| Output | Pass criterion |
|--------|----------------|
| `ic` per horizon | `|ic| > IC_MIN_ABS` (0.02 default) at any horizon |
| `p_value` per horizon | `< IC_MAX_PVALUE` (0.01 default) at the horizon meeting the IC threshold |
| Decile curve | Mean forward return across RSI deciles is roughly monotonic — provided as data, not a hard gate |
| Rolling IC | 6-month rolling window, returned for stability inspection |

Use `scipy.stats.spearmanr`.

### 3. Bootstrap confidence intervals — `bootstrap_ci.py`

Stationary block bootstrap on `trade_log['ret_pct']` for three metrics:

- Sharpe ratio — per-trade `mean / std`, **not annualized**. The CI lower bound > 0 test is invariant to any constant scaling factor, so annualizing would add noise (and a strategy- and timeframe-dependent constant) without statistical content.
- Profit factor — `sum(positives) / abs(sum(negatives))`; `+inf` if no losers.
- Win rate — fraction in `[0, 1]` (NOT a percentage).

The three metrics are reimplemented inline in `bootstrap_ci.py` rather than imported from `app/backtest/statistics/compute_core_metrics`. This is intentional: it isolates the audit from any future bug in the shared statistics module, avoids the win-rate fraction-vs-percent unit footgun across modules, and keeps the bootstrap inner loop cheap (no per-call equity-curve allocation). Documented as an intentional duplication in `docs/CODE_DUPLICATIONS.md`.

| Output | Pass criterion |
|--------|----------------|
| Sharpe 95% CI | Lower bound > 0 |
| Profit factor 95% CI | Lower bound > 1.0 |
| Win rate 95% CI | Reported, not gated |

Block size: use `arch.bootstrap.optimal_block_length` (Politis-White) on the
return series, take the `stationary` column. 10,000 bootstrap reps.

### 4. Deflated Sharpe Ratio — `deflated_sharpe.py`

Bailey & López de Prado (2014). Adjusts the observed Sharpe for the number
of trials in parameter selection.

Inputs:
- Observed Sharpe of the chosen run
- Sharpes of all sibling runs from the same parameter sweep (if any)
- Trade returns of the chosen run (for skew/kurtosis adjustment)
- Number of trials `N` (count of distinct parameter sets evaluated)

If the run is not part of a parameter sweep, `N=1` and the trials correction
collapses; report DSR but flag that no correction was applied.

| Output | Pass criterion |
|--------|----------------|
| DSR | `> DSR_PASS_THRESHOLD` (0.95 default) |

Reference: `references/`. Cross-check the formula against the paper before
running.

### 5. Probability of Backtest Overfitting — `pbo.py`

Bailey, Borwein, López de Prado, Zhu (2014). CSCV.

Required input: a `(T, N)` returns matrix, one column per parameter
set tested. Sibling runs are discovered by joining
`runs.grid_search_parent_id = X`.

**v1 simplification:** returns are per-trade `Trade.pnl` values aligned
positionally and zero-padded to the longest column length. Bar-level
returns (decompressed from `run_timeseries.equity_curve`) are deferred
to v2. The simplification is documented in the module docstring.

Algorithm: split the row index into S=16 blocks. For every C(S, S/2)=12,870
ways to split into IS and OOS halves, find the best parameter on IS by
Sharpe and record its OOS rank. Logit-transform the OOS rank percentile
and count splits with logit < 0. PBO is that fraction.

| Output | Pass criterion |
|--------|----------------|
| PBO | `< PBO_FAIL_THRESHOLD` (0.20 default) |

If no parameter sweep exists for the run, returns
`PBOResult(available=False, reason="no sibling runs from grid search", …)` —
this test is skipped, not failed. PBO requires multiple param combinations.

Public API:

```python
PBOResult(
    available: bool,
    pbo: float | None,
    n_strategies: int,
    n_blocks: int,
    n_combinations: int,
    passed: bool,
    threshold: float,
    reason: str | None,
)

run_pbo_analysis(
    run_id: int,
    *,
    n_blocks: int = PBO_BLOCK_COUNT,
    threshold: float = PBO_FAIL_THRESHOLD,
    session: Session | None = None,
) -> PBOResult
```

## Constants — `constants.py`

All numeric thresholds live here per the CLAUDE.md no-magic-numbers rule:

```python
IC_MIN_ABS = 0.02
IC_MAX_PVALUE = 0.01
IC_HORIZONS = [1, 4, 16, 96]
IC_DIRECTION_MISMATCH_HORIZON = 4   # horizon used for direction-vs-IC sign check
IC_AGGREGATE_POLICY = "majority"    # multi-symbol IC verdict (v1)
BOOTSTRAP_REPS = 10_000
BOOTSTRAP_CI_PCT = 95
DSR_PASS_THRESHOLD = 0.95
PBO_FAIL_THRESHOLD = 0.20
PBO_BLOCK_COUNT = 16
SANITY_TOP_TRADE_SHARE_MAX = 0.50
SANITY_COST_STRESS_FEE_MULTIPLIER = 2

# Strategy direction maps (keyed by strategy slug as stored in `strategies.name`)
STRATEGY_DIRECTION_FLAG = {...}     # bool — used by API route to set single_direction
STRATEGY_DIRECTION_SIDE = {...}     # "long"|"short"|"both" — used by report.py for direction-vs-IC mismatch
```

## Aggregator — `report.py`

`run_audit(run_id)` builds the trade log once, orchestrates every
sub-test, and returns a frozen `AuditResult` dataclass:

```python
@dataclass(frozen=True)
class AuditResult:
    run_id: int
    overall_passed: bool
    n_tests_run: int
    n_tests_passed: int

    sanity: dict | None
    bootstrap: dict | None
    ic: dict[str, Any] | None       # symbol -> ICResult (per-symbol, batch mode)
    dsr: Any | None
    pbo: PBOResult | None

    n_trades: int
    symbols: list[str]
    is_batch: bool
    duration_seconds: float

    direction_mismatch: dict[str, bool] | None
    reason: str | None              # set when no closed trades / run not found

def run_audit(
    run_id: int,
    *,
    single_direction: bool = False,
    timeframe: str = "15m",
    session: Session | None = None,
) -> AuditResult
```

Verdict logic:

- `overall_passed = True` iff **every sub-test that actually ran**
  returned `passed=True`. A sub-test that returns `None` (module not yet
  implemented, or panel CSV missing) is excluded from the count.
- PBO is excluded from the count when it returns `available=False`.
- IC verdict for multi-symbol runs is **majority rule** (v1): more than
  half the symbols clear the |IC| threshold at ≥ one horizon. If any
  symbol is direction-mismatched (strategy is long-only and IC at h=4
  is negative, or short-only and IC at h=4 is positive) the IC test
  fails outright. The aggregation policy is recorded in
  `IC_AGGREGATE_POLICY`.
- Strategy direction comes from `STRATEGY_DIRECTION_SIDE[strategy_name]`
  when present, otherwise inferred from realized trade sides
  (long-only / short-only / mixed).

Resilience: each sub-test is wrapped so a crash or import error in one
module degrades that slot to `None` rather than failing the whole audit.
Failures are logged via `structlog`.

## Conventions

Per CLAUDE.md and `docs/agent-workflow.md`:

- All audit functions return dicts or DataFrames. Never print, never log to
  stdout. Use `structlog.get_logger()` for diagnostic logging.
- Use the `arch` library for bootstrap and `scipy.stats` for IC. These are
  the only new dependencies; add to `requirements.txt` when the first test
  is implemented, not before.
- One logic class per file. Files stay under 400 lines.
- All numeric thresholds in `constants.py`.
- This module imports from `app.repository.backtest`, `app.data.indicators`,
  and standard scientific libraries. It must NOT import from
  `app.trading`, `app.api`, or `app.notification`.

## API integration (deferred)

`POST /api/backtest/audit/run` with body `{"run_id": int}` returns the
`AuditResult` JSON synchronously. Audit takes 30s-3min depending on whether
PBO runs. No SSE needed for v1; if it becomes a problem, add streaming
later. Route lives at `app/api/routes/audit.py`. Register in
`app/api/main.py`.

This integration is intentionally out of scope for the initial
implementation — get the five tests producing correct numbers in isolation
first, wire the API last.

## References

In `references/`:

- Bailey & López de Prado (2014), *The Deflated Sharpe Ratio*. SSRN 2460551.
- Bailey, Borwein, López de Prado, Zhu (2014), *The Probability of Backtest
  Overfitting*. SSRN 2326253.
- Carr & López de Prado (2014), *Determining Optimal Trading Rules Without
  Backtesting*. Adjacent methodology, useful for context.

## Out of scope (Phase 2+)

- Meta-labeling and triple-barrier (Phase 2 — strategy improvement)
- Microstructure features, VPIN, regime detection (Phase 3 — new alpha)
- Walk-forward integration (your existing `/api/walk-forward` already covers
  this; PBO is the harsher overfitting test)