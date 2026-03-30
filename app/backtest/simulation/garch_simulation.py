"""
GARCH(1,1) Simulation with Skewed Student-t (Method 3)
=======================================================
Fits a GARCH(1,1) model to real returns, then generates synthetic price
paths where volatility evolves dynamically — just like real crypto markets.

Plain English:
  Normal price models assume volatility is constant. GARCH says "no —
  after a big move, the NEXT few days will be volatile too." It learns
  this pattern from your real data and reproduces it in simulation.

  The skewed Student-t distribution adds two crypto-specific fixes:
  1. Fat tails: extreme moves happen far more often than a bell curve
     predicts (BTC has ~5 sigma days every few months).
  2. Negative skew: crashes are sharper than rallies (the left tail
     is fatter than the right).

  Together, GARCH + skewed-t produces the most statistically realistic
  synthetic paths for estimating drawdown distributions.

The GARCH(1,1) volatility equation:
  sigma²_t = omega + alpha * epsilon²_(t-1) + beta * sigma²_(t-1)

  omega: baseline variance floor (volatility can never reach zero)
  alpha: reaction — how much yesterday's surprise affects today's vol
  beta:  persistence — how slowly volatility decays back to normal
  alpha + beta < 1 required (otherwise vol explodes to infinity)

Dependencies:
  pip install arch  (Kevin Sheppard's ARCH package)

Usage:
  garch = GarchSimulation(returns)
  garch.fit()  # estimate parameters from real data
  paths = garch.simulate(num_paths=1000, path_length=252)
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.core.constants import SIM_DEFAULT_NUM_PATHS, SIM_DEFAULT_PATH_LENGTH, SIM_GARCH_DIST


@dataclass(frozen=True)
class GarchFitResult:
    """Summary of fitted GARCH parameters for inspection.

    Attributes:
        omega:      Baseline variance constant.
        alpha:      Reaction coefficient (weight on yesterday's squared shock).
        beta:       Persistence coefficient (weight on yesterday's variance).
        persistence: alpha + beta — how close to unit root (>0.95 = very persistent).
        nu:         Degrees of freedom for Student-t (lower = fatter tails).
        skew:       Skewness parameter (< 0 means crashes are more extreme).
        mean:       Estimated mean return (mu).
        dist:       Distribution used for fitting.
        log_likelihood: Model fit quality (higher = better fit).
    """

    omega: float
    alpha: float
    beta: float
    persistence: float
    nu: float | None
    skew: float | None
    mean: float
    dist: str
    log_likelihood: float


class GarchSimulation:
    """Fit GARCH(1,1) to real returns and simulate synthetic paths.

    Parameters:
        returns: pandas Series of daily log-returns.
        dist:    Error distribution — "skewt" (recommended for crypto),
                 "t" (symmetric fat tails), or "normal" (thin tails, not
                 recommended for crypto).
    """

    def __init__(self, returns: pd.Series, dist: str = SIM_GARCH_DIST) -> None:
        self._returns = returns.values.astype(np.float64)
        self._dist = dist
        self._model = None
        self._fit_result: GarchFitResult | None = None

        # Scale returns to percentage for better numerical conditioning.
        # The `arch` library works best with returns in percent (e.g. 2.5
        # instead of 0.025). We scale up for fitting, then scale back down
        # when simulating.
        self._scale = 100.0
        self._scaled_returns = self._returns * self._scale

    def fit(self) -> GarchFitResult:
        """Fit GARCH(1,1) model to the return series.

        What happens during fitting:
          1. The `arch` library estimates omega, alpha, beta (and nu, skew
             for Student-t) using maximum likelihood estimation (MLE).
          2. MLE finds the parameters that make the observed data most
             probable under the model.
          3. We check alpha + beta < 1 (stability condition).

        Returns:
            GarchFitResult with all estimated parameters.

        Raises:
            ImportError: if the `arch` package is not installed.
            RuntimeError: if the model fails to converge.
        """
        try:
            from arch import arch_model
        except ImportError:
            raise ImportError(
                "The 'arch' package is required for GARCH simulation. "
                "Install it with: pip install arch"
            )

        # Build GARCH(1,1) with specified error distribution.
        # mean='Constant' adds a mu term (drift).
        # vol='GARCH', p=1, q=1 → GARCH(1,1).
        self._model = arch_model(
            self._scaled_returns,
            mean="Constant",
            vol="GARCH",
            p=1,
            q=1,
            dist=self._dist,
        )

        # Fit with warnings suppressed (convergence warnings are noisy
        # but usually the result is still usable).
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = self._model.fit(disp="off")

        # Extract parameters.
        params = res.params
        omega = float(params.get("omega", 0))
        alpha = float(params.get("alpha[1]", 0))
        beta = float(params.get("beta[1]", 0))
        mu = float(params.get("mu", 0))

        # Distribution parameters (only present for t / skewt).
        nu = float(params.get("nu", 0)) if "nu" in params else None
        skew_param = float(params.get("lambda", 0)) if "lambda" in params else None

        self._fit_result = GarchFitResult(
            omega=omega,
            alpha=alpha,
            beta=beta,
            persistence=alpha + beta,
            nu=nu,
            skew=skew_param,
            mean=mu,
            dist=self._dist,
            log_likelihood=float(res.loglikelihood),
        )

        self._res = res
        return self._fit_result

    def simulate(
        self,
        num_paths: int = SIM_DEFAULT_NUM_PATHS,
        path_length: int = SIM_DEFAULT_PATH_LENGTH,
        seed: int | None = None,
    ) -> np.ndarray:
        """Generate synthetic price paths from the fitted GARCH model.

        Algorithm:
          1. Use the `arch` library's built-in simulation which:
             a. Draws random shocks from the fitted distribution
                (skewed Student-t with estimated nu and skew).
             b. Evolves volatility according to the GARCH equation.
             c. Produces a series of returns for each path.
          2. Scale returns back from percentage to decimal.
          3. Convert returns to price paths: P(t) = exp(cumsum(r)).

        Args:
            num_paths:   Number of simulated paths (default 1000).
            path_length: Days per path (default 252).
            seed:        Random seed for reproducibility.

        Returns:
            numpy array of shape (path_length, num_paths).
            Each column is a price path starting at 1.0.

        Raises:
            RuntimeError: if fit() has not been called yet.
        """
        if self._fit_result is None:
            raise RuntimeError("Must call fit() before simulate().")

        rng = np.random.default_rng(seed)

        # The arch library's simulate() generates one path at a time.
        # We call it num_paths times with different random seeds.
        price_paths = np.empty((path_length, num_paths), dtype=np.float64)

        for j in range(num_paths):
            # Generate a unique seed for each path from the master rng.
            path_seed = int(rng.integers(0, 2**31))
            sim = self._res.model.simulate(
                self._res.params,
                nobs=path_length,
                initial_value_vol=np.sqrt(float(np.asarray(self._res.conditional_volatility)[-1])),
            )

            # sim.data contains simulated returns in percentage scale.
            sim_returns = sim["data"].values.flatten() / self._scale

            # Convert to price path.
            cum_returns = np.cumsum(sim_returns)
            price_paths[:, j] = np.exp(cum_returns)

        return price_paths

    @property
    def fit_result(self) -> GarchFitResult | None:
        """Access the fitted parameters (None if fit() not called)."""
        return self._fit_result

    def summary(self) -> str:
        """Human-readable summary of the fitted model.

        Explains each parameter in plain English so a beginner can
        understand what the model learned from the data.
        """
        if self._fit_result is None:
            return "Model not fitted yet. Call fit() first."

        r = self._fit_result
        lines = [
            "GARCH(1,1) Fit Summary",
            "=" * 40,
            f"Distribution: {r.dist}",
            f"Mean daily return (mu): {r.mean / self._scale:.6f} ({r.mean / self._scale * 100:.4f}%)",
            "",
            "Volatility equation: sigma²_t = omega + alpha * e²_(t-1) + beta * sigma²_(t-1)",
            f"  omega (floor):       {r.omega:.6f}",
            f"  alpha (reaction):    {r.alpha:.4f}",
            f"  beta  (persistence): {r.beta:.4f}",
            f"  alpha + beta:        {r.persistence:.4f}",
        ]

        if r.persistence > 0.99:
            lines.append("  ⚠ Very high persistence — volatility shocks decay extremely slowly.")
        elif r.persistence > 0.95:
            lines.append("  Typical for crypto — volatility shocks are quite persistent.")

        if r.nu is not None:
            lines.append(f"\nFat tails (nu / degrees of freedom): {r.nu:.2f}")
            if r.nu < 5:
                lines.append("  Very fat tails — extreme daily moves are common.")
            elif r.nu < 10:
                lines.append("  Moderately fat tails — typical for crypto.")
            else:
                lines.append("  Relatively thin tails — closer to normal distribution.")

        if r.skew is not None:
            lines.append(f"Skewness (lambda): {r.skew:.4f}")
            if r.skew < -0.05:
                lines.append("  Negative skew — crashes are sharper than rallies (typical for crypto).")
            elif r.skew > 0.05:
                lines.append("  Positive skew — rallies are sharper (unusual for crypto).")
            else:
                lines.append("  Near-symmetric — crashes and rallies similar in magnitude.")

        lines.append(f"\nLog-likelihood: {r.log_likelihood:.2f}")
        return "\n".join(lines)
