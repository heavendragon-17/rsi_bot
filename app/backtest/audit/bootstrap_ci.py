"""Stationary block bootstrap confidence intervals on Sharpe, profit factor, and win rate.

Resamples the trade-return stream with `arch.bootstrap.StationaryBootstrap`,
sized by the Politis-White `optimal_block_length` (the `stationary`
column of its DataFrame output). Returns 95% percentile-bound CIs and a
pass/fail per-metric verdict against the thresholds declared in
`audit/constants.py`.

DRY violation, by design
========================
The three metric helpers below — `_sharpe`, `_profit_factor`,
`_win_rate` — are *deliberate* reimplementations of formulas that also
live inside
`app.backtest.statistics.metrics_core.compute_core_metrics`. Reasons,
in priority order:

1. **Unit safety.** `compute_core_metrics` reports `win_rate` as a
   percentage (0–100). The bootstrap input/output for win_rate is a
   *fraction* in [0, 1]. Routing through the shared helper would mean
   dividing by 100 every rep — inviting the percent-vs-fraction unit
   footgun on every future edit.

2. **Performance.** Each metric function is invoked `n_reps` times
   (default 10 000) per metric per audit run.
   `compute_core_metrics` allocates intermediate equity lists and
   computes statistics this module does not need; that overhead would
   dominate the inner loop. The inline one-liners stay vectorized and
   allocation-free.

3. **Correctness over reuse.** The shared helper's contract is "give
   me the canonical run summary" — a different problem from
   "evaluate this resampled return vector for one statistic." Coupling
   them would force one to bend to the other.

Treat this duplication as load-bearing. Do not unify it with
`compute_core_metrics` later "for DRY"; the divergence is the point.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import structlog
from arch.bootstrap import StationaryBootstrap, optimal_block_length

from app.backtest.audit.constants import (
    BOOTSTRAP_CI_PCT,
    BOOTSTRAP_PROFIT_FACTOR_LB_MIN,
    BOOTSTRAP_REPS,
    BOOTSTRAP_SHARPE_LB_MIN,
)
from app.backtest.audit.trade_log import TradeLog

logger = structlog.get_logger()

_SMALL_SAMPLE_WARN_THRESHOLD = 50

# Threshold-type tags. Recorded on each `BootstrapResult` so the report
# layer can render the rule that produced `passed` without re-deriving it.
_THRESHOLD_CI_LOW_ABOVE_ZERO = "ci_low_above_zero"
_THRESHOLD_CI_LOW_ABOVE_ONE = "ci_low_above_one"
_THRESHOLD_REPORT_ONLY = "report_only"


@dataclass(frozen=True)
class BootstrapResult:
    """Per-metric bootstrap output with the rule that produced `passed`."""

    metric_name: str
    point_estimate: float
    ci_low: float
    ci_high: float
    ci_pct: int
    n_reps: int
    block_size: int
    passed: bool
    threshold_type: str
    threshold_value: float | None


def _sharpe(returns: np.ndarray) -> float:
    """Per-trade Sharpe = mean / std, **unscaled** (no annualization).

    The audit consumes a per-trade return stream whose holding period
    varies trade-to-trade; there is no constant `sqrt(T)` factor that
    would honestly annualize it. Annualizing would require either a
    uniform-holding-period assumption (false here) or time-weighting
    each return (a different statistic). Unscaled mean/std is the
    correct per-trade signal-to-noise ratio; the `> 0` threshold is
    calibrated against that quantity.
    """
    sd = returns.std()
    return float(returns.mean() / sd) if sd > 0 else 0.0


def _profit_factor(returns: np.ndarray) -> float:
    """Sum of winning returns / |sum of losing returns|. ∞ if no losers."""
    neg = returns[returns < 0].sum()
    return float(returns[returns > 0].sum() / -neg) if neg < 0 else float("inf")


def _win_rate(returns: np.ndarray) -> float:
    """Fraction of strictly positive returns. In [0, 1] — NOT a percentage."""
    return float((returns > 0).mean())


def _bootstrap_metric(
    returns: np.ndarray,
    metric_fn: Callable[[np.ndarray], float],
    *,
    n_reps: int,
    ci_pct: int,
    block_size: int | None,
) -> tuple[float, float, float, int]:
    """Bootstrap one metric. Returns `(point, ci_low, ci_high, block_size_used)`.

    When `block_size` is None it is computed once from `returns` via
    Politis-White `optimal_block_length` (stationary column, floored
    at 1). The caller can pass a precomputed block size to skip that
    work when bootstrapping multiple metrics on the same series.
    """
    if block_size is None:
        opt = optimal_block_length(returns)
        block_size = max(1, int(opt.iloc[0]["stationary"]))
    bs = StationaryBootstrap(block_size, returns)
    samples = np.asarray(bs.apply(metric_fn, n_reps)).ravel()
    point = float(metric_fn(returns))
    alpha = (100.0 - ci_pct) / 2.0
    ci_low = float(np.percentile(samples, alpha))
    ci_high = float(np.percentile(samples, 100.0 - alpha))
    return point, ci_low, ci_high, block_size


def _evaluate_threshold(threshold_type: str, ci_low: float) -> bool:
    if threshold_type == _THRESHOLD_CI_LOW_ABOVE_ZERO:
        return ci_low > 0.0
    if threshold_type == _THRESHOLD_CI_LOW_ABOVE_ONE:
        return ci_low > 1.0
    if threshold_type == _THRESHOLD_REPORT_ONLY:
        return True
    raise ValueError(f"unknown threshold_type: {threshold_type}")


def _build_result(
    name: str,
    *,
    point: float,
    ci_low: float,
    ci_high: float,
    ci_pct: int,
    n_reps: int,
    block_size: int,
    threshold_type: str,
    threshold_value: float | None,
) -> BootstrapResult:
    return BootstrapResult(
        metric_name=name,
        point_estimate=point,
        ci_low=ci_low,
        ci_high=ci_high,
        ci_pct=ci_pct,
        n_reps=n_reps,
        block_size=block_size,
        passed=_evaluate_threshold(threshold_type, ci_low),
        threshold_type=threshold_type,
        threshold_value=threshold_value,
    )


def run_bootstrap_ci(
    tl: TradeLog,
    *,
    n_reps: int = BOOTSTRAP_REPS,
    ci_pct: int = BOOTSTRAP_CI_PCT,
) -> dict:
    """Bootstrap Sharpe / profit factor / win rate from `tl`'s `ret_pct` stream.

    Overall `passed` is the AND of the Sharpe and profit-factor verdicts
    only — win rate is reported but never gates. Wide CIs on small
    samples are an honest signal, not an error: when `n_trades < 50`
    a warning is logged and the bootstrap proceeds anyway.
    """
    df = tl.df
    n_trades = int(len(df))
    if df.empty:
        return {"passed": False, "n_trades": 0, "reason": "no closed trades"}
    if n_trades < _SMALL_SAMPLE_WARN_THRESHOLD:
        logger.warning(
            "bootstrap_ci_small_sample",
            n_trades=n_trades,
            min_for_stable_ci=_SMALL_SAMPLE_WARN_THRESHOLD,
        )

    returns = np.ascontiguousarray(df["ret_pct"].to_numpy(dtype=np.float64))

    sharpe_pt, sharpe_lo, sharpe_hi, block_size = _bootstrap_metric(
        returns, _sharpe, n_reps=n_reps, ci_pct=ci_pct, block_size=None,
    )
    pf_pt, pf_lo, pf_hi, _ = _bootstrap_metric(
        returns, _profit_factor, n_reps=n_reps, ci_pct=ci_pct, block_size=block_size,
    )
    wr_pt, wr_lo, wr_hi, _ = _bootstrap_metric(
        returns, _win_rate, n_reps=n_reps, ci_pct=ci_pct, block_size=block_size,
    )

    common = {"ci_pct": ci_pct, "n_reps": n_reps, "block_size": block_size}
    sharpe_res = _build_result(
        "sharpe", point=sharpe_pt, ci_low=sharpe_lo, ci_high=sharpe_hi,
        threshold_type=_THRESHOLD_CI_LOW_ABOVE_ZERO,
        threshold_value=BOOTSTRAP_SHARPE_LB_MIN,
        **common,
    )
    pf_res = _build_result(
        "profit_factor", point=pf_pt, ci_low=pf_lo, ci_high=pf_hi,
        threshold_type=_THRESHOLD_CI_LOW_ABOVE_ONE,
        threshold_value=BOOTSTRAP_PROFIT_FACTOR_LB_MIN,
        **common,
    )
    wr_res = _build_result(
        "win_rate", point=wr_pt, ci_low=wr_lo, ci_high=wr_hi,
        threshold_type=_THRESHOLD_REPORT_ONLY,
        threshold_value=None,
        **common,
    )

    return {
        "passed": bool(sharpe_res.passed and pf_res.passed),
        "n_trades": n_trades,
        "metrics": {
            "sharpe": sharpe_res,
            "profit_factor": pf_res,
            "win_rate": wr_res,
        },
    }
