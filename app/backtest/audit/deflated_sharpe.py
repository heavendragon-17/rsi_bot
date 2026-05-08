"""Deflated Sharpe Ratio (DSR) per Bailey & Lopez de Prado (2014).

DSR adjusts the observed Sharpe ratio for two distortions that inflate raw
Sharpe values relative to what a single-trial t-test would suggest:

1. Higher-moment effects of the return distribution. Negative skew and fat
   tails (excess kurtosis > 0) make extreme losses more likely than a normal
   approximation predicts; the standard error of the Sharpe estimator is
   wider in that regime, so the same observed Sharpe carries less evidence.
2. Multiple-testing inflation. When a researcher tries N parameter
   configurations and reports the best, the maximum Sharpe across N trials
   has a non-zero expectation under the null even when no real edge exists.

DSR converts the observed Sharpe + higher moments + n_trials into a single
probability: "what is the probability that this strategy's TRUE Sharpe
exceeds the benchmark Sharpe (typically 0)?"

For v1 we focus on the higher-moment correction. With ``n_trials=1`` the
multi-trial term collapses out and DSR reduces algebraically to the
Probabilistic Sharpe Ratio (PSR) from the same paper. Multi-trial DSR
requires knowing how many parameter combinations were tested, which we do
not currently track in the backtest persistence layer — wire that through
before relying on ``n_trials > 1``.

Relationship to bootstrap_ci.py
-------------------------------
DSR/PSR is a frequentist probability that the strategy's TRUE Sharpe
exceeds the benchmark, given the observed sample's higher moments. It
complements the bootstrap CI: bootstrap shows the range of plausible Sharpe
values; DSR converts that into a single "probability of being real edge"
number. They should agree directionally — if bootstrap CI straddles zero,
DSR should be far from 1.0.

References
----------
Bailey, D. H., & Lopez de Prado, M. (2014). The Deflated Sharpe Ratio:
Correcting for Selection Bias, Backtest Overfitting, and Non-Normality.
Journal of Portfolio Management, 40(5), 94-107.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import structlog
from scipy import stats

from app.backtest.audit.constants import DSR_PASS_THRESHOLD
from app.backtest.audit.trade_log import TradeLog

logger = structlog.get_logger()

_EULER_MASCHERONI = 0.5772156649015329


@dataclass(frozen=True)
class DSRResult:
    """Deflated Sharpe Ratio summary for one trade log."""

    n_trades: int
    sharpe_observed: float
    skew: float
    kurtosis: float
    psr: float
    dsr: float
    n_trials: int
    benchmark_sharpe: float
    passed: bool
    threshold: float


def _sharpe(returns: np.ndarray) -> float:
    """Per-trade Sharpe: mean / std. Unscaled (no annualization).

    Matches the bootstrap_ci.py convention so the two audits speak the same
    Sharpe — see that module's docstring for the rationale.
    """
    std = returns.std()
    return float("nan") if std == 0.0 else float(returns.mean() / std)


def _sample_skew(returns: np.ndarray) -> float:
    """Sample-bias-corrected skewness (G_1 / Fisher-Pearson)."""
    return float(stats.skew(returns, bias=False))


def _sample_kurtosis(returns: np.ndarray) -> float:
    """Sample-bias-corrected EXCESS kurtosis (kurt - 3).

    The PSR formula expects excess kurtosis: a normal distribution has
    excess kurtosis 0, fat tails are positive, thin tails negative.
    """
    return float(stats.kurtosis(returns, bias=False, fisher=True))


def _psr(
    sharpe: float,
    skew: float,
    kurtosis: float,
    n: int,
    benchmark_sharpe: float = 0.0,
) -> float:
    """Probabilistic Sharpe Ratio per Bailey & Lopez de Prado (2014) eq. (1).

    PSR = Phi( (sharpe - benchmark) * sqrt(n - 1) /
               sqrt(1 - skew*sharpe + (kurtosis/4)*sharpe^2) )

    where Phi is the standard normal CDF and ``kurtosis`` is excess kurtosis.

    The denominator inside the sqrt can go non-positive when skew is large
    and kurtosis is small (or vice versa); in that pathological case the
    formula has no real-valued answer, so we return NaN and log a warning.
    """
    if n < 2:
        return float("nan")
    denom_sq = 1.0 - skew * sharpe + (kurtosis / 4.0) * sharpe * sharpe
    if denom_sq <= 0.0:
        logger.warning(
            "audit_psr_denominator_nonpositive",
            sharpe=sharpe,
            skew=skew,
            kurtosis=kurtosis,
            denom_sq=denom_sq,
        )
        return float("nan")
    z = (sharpe - benchmark_sharpe) * math.sqrt(n - 1) / math.sqrt(denom_sq)
    return float(stats.norm.cdf(z))


def _dsr(
    sharpe: float,
    skew: float,
    kurtosis: float,
    n: int,
    n_trials: int,
    benchmark_sharpe: float = 0.0,
) -> float:
    """Deflated Sharpe Ratio per Bailey & Lopez de Prado (2014) eq. (9).

    DSR adjusts the benchmark Sharpe by the expected maximum of n_trials
    independent trial Sharpes under the null hypothesis. With ``n_trials=1``
    this expected-max term is zero and DSR collapses exactly to PSR.

    For ``n_trials > 1`` the adjusted benchmark is::

        benchmark_adj = benchmark
                      + sqrt(V[Sharpe]) * (
                          (1 - gamma) * Phi^-1(1 - 1/n_trials)
                          + gamma     * Phi^-1(1 - 1/(n_trials*e))
                        )

    where ``gamma`` is the Euler-Mascheroni constant (~0.5772) and
    ``V[Sharpe]`` is the sampling variance of the Sharpe estimator. We do
    not currently track ``n_trials`` end-to-end in the persistence layer,
    so callers should leave it at 1 until that wiring exists.

    TODO(audit): wire ``n_trials`` through the run/batch metadata so the
    multi-trial branch is reachable and testable end-to-end. Until then,
    raise on the unimplemented path so a stale caller cannot get a
    silently-wrong number back.
    """
    if n_trials <= 1:
        return _psr(sharpe, skew, kurtosis, n, benchmark_sharpe=benchmark_sharpe)
    raise NotImplementedError(
        "DSR with n_trials > 1 is not implemented yet — n_trials is not "
        "tracked in the backtest persistence layer. Use n_trials=1 (== PSR) "
        "until the multi-trial path is wired in."
    )


def run_dsr_analysis(
    tl: TradeLog,
    *,
    n_trials: int = 1,
    benchmark_sharpe: float = 0.0,
    threshold: float = DSR_PASS_THRESHOLD,
) -> DSRResult:
    """Compute DSR (== PSR for ``n_trials=1``) for the given trade log.

    Reads ``tl.df['ret_pct']`` as the per-trade return series and produces a
    ``DSRResult`` with the observed Sharpe, sample higher moments, the PSR,
    the DSR, and a pass/fail flag against ``threshold``.

    Empty/degenerate trade logs short-circuit to a NaN result with
    ``passed=False`` so callers always get a structured return value.
    """
    df = tl.df
    n_trades = int(len(df))
    if df.empty or n_trades < 2:
        return DSRResult(
            n_trades=n_trades,
            sharpe_observed=float("nan"),
            skew=float("nan"),
            kurtosis=float("nan"),
            psr=float("nan"),
            dsr=float("nan"),
            n_trials=n_trials,
            benchmark_sharpe=benchmark_sharpe,
            passed=False,
            threshold=threshold,
        )

    returns = np.ascontiguousarray(df["ret_pct"].to_numpy(dtype=np.float64))
    sharpe = _sharpe(returns)
    skew = _sample_skew(returns)
    kurt = _sample_kurtosis(returns)

    psr = _psr(sharpe, skew, kurt, n_trades, benchmark_sharpe=benchmark_sharpe)
    dsr = _dsr(
        sharpe,
        skew,
        kurt,
        n_trades,
        n_trials=n_trials,
        benchmark_sharpe=benchmark_sharpe,
    )
    passed = (not math.isnan(dsr)) and dsr >= threshold

    return DSRResult(
        n_trades=n_trades,
        sharpe_observed=sharpe,
        skew=skew,
        kurtosis=kurt,
        psr=psr,
        dsr=dsr,
        n_trials=n_trials,
        benchmark_sharpe=benchmark_sharpe,
        passed=passed,
        threshold=threshold,
    )


__all__ = ["DSRResult", "run_dsr_analysis"]
