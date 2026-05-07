"""Stationary block bootstrap confidence intervals on per-trade metrics.

Computes CIs for three metrics from `TradeLog.df['ret_pct']`:

    sharpe         per-trade mean / std (NOT annualized)
    profit_factor  sum(positives) / abs(sum(negatives))
    win_rate       fraction of trades with ret_pct > 0   (in [0, 1])

The block size is chosen automatically by `arch.bootstrap.optimal_block_length`
(Politis-White, 2009) — we take the column labelled `'stationary'` and floor at
1. The bootstrap itself is `arch.bootstrap.StationaryBootstrap`, which resamples
contiguous blocks of geometric length `block_size` (mean), preserving any
residual autocorrelation in the trade-return series. CIs are the empirical
percentile bounds of `n_reps` resampled metric values.

Pass criteria
-------------
sharpe         CI lower bound > 0   (positive risk-adjusted edge)
profit_factor  CI lower bound > 1   (gross winners > gross losers)
win_rate       report-only          (a strategy can be profitable with <50%)

Overall `passed` requires Sharpe AND profit factor both pass.

Why this module deliberately reimplements its three metrics
-----------------------------------------------------------
This is a knowing DRY violation, NOT laziness. `app/backtest/statistics/`
already has `compute_core_metrics` which computes the same names. We do not
call it here, and the three private helpers below (`_sharpe`,
`_profit_factor`, `_win_rate`) are the canonical implementations for the
audit pipeline. Three reasons:

1. Unit footgun. `compute_core_metrics`'s `win_rate` is a percentage in
   [0, 100]; the audit's pass-criteria thresholds are written in fraction
   space ([0, 1]). Sharing the function would force every caller to
   remember which space the value lives in. A 1-line `_win_rate` that
   *only* speaks fractions is safer than a shared helper that speaks both.

2. Hot loop allocation. `arch.bootstrap.StationaryBootstrap.apply` calls
   the metric callable `n_reps` times (default 10,000) per metric — 30k
   calls for the three metrics. `compute_core_metrics` builds an equity
   curve list internally, which is dead work when all we need from the
   resampled vector is mean/std (Sharpe), pos-sum/neg-sum (PF), or a
   boolean mean (win rate). Inline numpy ops keep the inner loop cheap.

3. Independence. The audit is a *check on* the rest of the system. If a
   subtle bug ever slips into `compute_core_metrics` (e.g. annualization
   constant changes, win-rate flips to fraction), the audit must catch it
   instead of inheriting it. Two implementations that disagree are a
   feature, not a bug.

The corresponding TODO/cross-reference is recorded in
`docs/CODE_DUPLICATIONS.md` (audit metric reimplementation, intentional).

Why per-trade, unscaled Sharpe
------------------------------
Per-trade Sharpe = mean(ret_pct) / std(ret_pct) is the right object for
significance testing the trade-return *series*. Annualizing would require
multiplying by `sqrt(trades_per_year)`, which (a) is symbol- and
strategy-dependent, (b) inflates the value without adding statistical
information — the t-statistic is identical up to a constant. The CI lower
bound > 0 test is invariant to that constant, so we keep the unscaled form.
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

_THRESHOLD_SHARPE = "ci_low_above_zero"
_THRESHOLD_PROFIT_FACTOR = "ci_low_above_one"
_THRESHOLD_REPORT_ONLY = "report_only"

_SMALL_SAMPLE_WARN_THRESHOLD = 50


@dataclass(frozen=True)
class BootstrapResult:
    """Bootstrap CI summary for one metric."""

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
    """Per-trade Sharpe: mean / std. Unscaled (no annualization)."""
    std = returns.std()
    return float("nan") if std == 0.0 else float(returns.mean() / std)


def _profit_factor(returns: np.ndarray) -> float:
    """Sum of winners / abs(sum of losers). +inf when there are no losers."""
    losers = returns[returns < 0.0]
    if losers.size == 0:
        return float("inf")
    return float(returns[returns > 0.0].sum() / -losers.sum())


def _win_rate(returns: np.ndarray) -> float:
    """Fraction of strictly positive returns. In [0, 1], NOT a percentage."""
    return float((returns > 0.0).mean())


def _resolve_block_size(returns: np.ndarray, block_size: int | None) -> int:
    """Politis-White optimal stationary block length, floored at 1."""
    if block_size is not None:
        return max(1, int(block_size))
    opt = optimal_block_length(returns)
    return max(1, int(opt.iloc[0]["stationary"]))


def _bootstrap_metric(
    returns: np.ndarray,
    metric_fn: Callable[[np.ndarray], float],
    *,
    n_reps: int,
    ci_pct: int,
    block_size: int | None,
) -> tuple[float, float, float, int]:
    """Resample `returns` with stationary bootstrap and return CI bounds.

    Returns `(point_estimate, ci_low, ci_high, block_size_used)`.
    `point_estimate` is the metric on the original series, NOT the
    bootstrap mean — the bootstrap quantifies sampling uncertainty around
    the point estimate, it does not replace it.
    """
    block = _resolve_block_size(returns, block_size)
    bs = StationaryBootstrap(block, returns)
    samples = bs.apply(metric_fn, n_reps).reshape(-1)
    alpha = (100 - ci_pct) / 2.0
    ci_low = float(np.percentile(samples, alpha))
    ci_high = float(np.percentile(samples, 100 - alpha))
    point = float(metric_fn(returns))
    return point, ci_low, ci_high, block


def run_bootstrap_ci(
    tl: TradeLog,
    *,
    n_reps: int = BOOTSTRAP_REPS,
    ci_pct: int = BOOTSTRAP_CI_PCT,
) -> dict:
    """Run bootstrap CIs for Sharpe, profit factor, and win rate.

    Wide CIs on small samples are correct behavior — there is no
    `min_trades` guard. When `n_trades < 50` we log a warning and proceed.
    """
    df = tl.df
    n_trades = int(len(df))
    if df.empty:
        return {
            "passed": False,
            "n_trades": 0,
            "reason": "no closed trades",
            "metrics": {},
        }
    if n_trades < _SMALL_SAMPLE_WARN_THRESHOLD:
        logger.warning(
            "audit_bootstrap_small_sample",
            run_id=tl.run_id,
            n_trades=n_trades,
            warn_threshold=_SMALL_SAMPLE_WARN_THRESHOLD,
        )

    returns = np.ascontiguousarray(df["ret_pct"].to_numpy(dtype=np.float64))

    sharpe_pt, sharpe_lo, sharpe_hi, sharpe_block = _bootstrap_metric(
        returns, _sharpe, n_reps=n_reps, ci_pct=ci_pct, block_size=None
    )
    pf_pt, pf_lo, pf_hi, pf_block = _bootstrap_metric(
        returns, _profit_factor, n_reps=n_reps, ci_pct=ci_pct, block_size=None
    )
    wr_pt, wr_lo, wr_hi, wr_block = _bootstrap_metric(
        returns, _win_rate, n_reps=n_reps, ci_pct=ci_pct, block_size=None
    )

    sharpe_passed = sharpe_lo > BOOTSTRAP_SHARPE_LB_MIN
    pf_passed = pf_lo > BOOTSTRAP_PROFIT_FACTOR_LB_MIN

    metrics = {
        "sharpe": BootstrapResult(
            metric_name="sharpe",
            point_estimate=sharpe_pt,
            ci_low=sharpe_lo,
            ci_high=sharpe_hi,
            ci_pct=ci_pct,
            n_reps=n_reps,
            block_size=sharpe_block,
            passed=sharpe_passed,
            threshold_type=_THRESHOLD_SHARPE,
            threshold_value=BOOTSTRAP_SHARPE_LB_MIN,
        ),
        "profit_factor": BootstrapResult(
            metric_name="profit_factor",
            point_estimate=pf_pt,
            ci_low=pf_lo,
            ci_high=pf_hi,
            ci_pct=ci_pct,
            n_reps=n_reps,
            block_size=pf_block,
            passed=pf_passed,
            threshold_type=_THRESHOLD_PROFIT_FACTOR,
            threshold_value=BOOTSTRAP_PROFIT_FACTOR_LB_MIN,
        ),
        "win_rate": BootstrapResult(
            metric_name="win_rate",
            point_estimate=wr_pt,
            ci_low=wr_lo,
            ci_high=wr_hi,
            ci_pct=ci_pct,
            n_reps=n_reps,
            block_size=wr_block,
            passed=True,
            threshold_type=_THRESHOLD_REPORT_ONLY,
            threshold_value=None,
        ),
    }

    return {
        "passed": bool(sharpe_passed and pf_passed),
        "n_trades": n_trades,
        "metrics": metrics,
    }
