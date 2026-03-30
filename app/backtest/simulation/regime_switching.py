"""
Regime-Switching Simulation (Method 4)
=======================================
Models the market as switching between 3 distinct states (bull, neutral,
bear), each with its own return and volatility profile. A Markov transition
matrix controls how the market jumps between states.

Plain English:
  GARCH treats all market conditions as one continuous process. But crypto
  clearly has distinct "modes":
    - Bull:    +0.3%/day drift, low-ish volatility, everyone's euphoric
    - Neutral: ~0% drift, moderate vol, choppy consolidation
    - Bear:    -0.4%/day drift, HIGH volatility, capitulation and fear

  Regime switching explicitly models these modes. On any given day, the
  market is in one state, and there's a probability of switching to another
  state tomorrow. These probabilities form a "transition matrix."

  Example transition matrix (crypto-calibrated):
    From/To    Bull   Neutral  Bear
    Bull       0.97   0.02     0.01    (bull tends to persist)
    Neutral    0.04   0.92     0.04    (neutral is less stable)
    Bear       0.01   0.04     0.95    (bear markets are sticky)

  The key insight: bear markets in crypto are STICKY (0.95 persistence).
  Once you enter a bear, you stay there for weeks/months. GARCH can't
  reproduce this because it has no concept of discrete states.

Why 3 regimes (not 2)?
  With only 2 (bull/bear), you miss the long choppy consolidation phases
  that are very common in crypto. The neutral regime captures this — low
  drift, moderate vol, lots of false signals.

Usage:
  rs = RegimeSwitching(returns)
  rs.fit()  # estimates regimes from real data
  paths = rs.simulate(num_paths=1000, path_length=252)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.core.constants import SIM_DEFAULT_NUM_PATHS, SIM_DEFAULT_PATH_LENGTH, SIM_REGIME_COUNT

# ── Default crypto regime parameters ─────────────────────────────────
# These are sensible starting values for crypto markets.
# If you have enough data, fit() will estimate better ones.

_DEFAULT_REGIME_MU = np.array([0.003, 0.0002, -0.004])  # daily drift
_DEFAULT_REGIME_SIGMA = np.array([0.035, 0.025, 0.055])  # daily volatility

# Transition matrix: rows = from-state, cols = to-state.
# Each row sums to 1.0.
_DEFAULT_TRANSITION = np.array(
    [
        [0.97, 0.02, 0.01],  # bull  → bull/neutral/bear
        [0.04, 0.92, 0.04],  # neutral → ...
        [0.01, 0.04, 0.95],  # bear  → ...
    ]
)

_REGIME_NAMES = ["BULL", "NEUTRAL", "BEAR"]


@dataclass(frozen=True)
class RegimeFitResult:
    """Summary of estimated regime parameters.

    Attributes:
        regime_names: Labels for each regime.
        mu:           Mean daily return per regime.
        sigma:        Daily volatility per regime.
        transition:   Transition probability matrix (n_regimes x n_regimes).
        stationary:   Long-run probability of being in each regime.
        n_regimes:    Number of regimes (always 3 for crypto).
        fitted:       True if estimated from data, False if using defaults.
    """

    regime_names: list[str]
    mu: np.ndarray
    sigma: np.ndarray
    transition: np.ndarray
    stationary: np.ndarray
    n_regimes: int
    fitted: bool


class RegimeSwitching:
    """3-regime Markov switching model for crypto simulation.

    Parameters:
        returns:    pandas Series of daily log-returns.
        n_regimes:  Number of market regimes (default 3: bull/neutral/bear).
    """

    def __init__(
        self,
        returns: pd.Series,
        n_regimes: int = SIM_REGIME_COUNT,
    ) -> None:
        self._returns = returns.values.astype(np.float64)
        self._n_regimes = n_regimes
        self._fit_result: RegimeFitResult | None = None

    def fit(self, use_defaults: bool = False) -> RegimeFitResult:
        """Estimate regime parameters from the return series.

        Two approaches:
          1. use_defaults=False (default): Use a Gaussian Mixture Model (GMM)
             to cluster returns into regimes, then estimate transition
             probabilities from the state sequence. This is simpler and more
             robust than a full Hidden Markov Model for our purposes.
          2. use_defaults=True: Skip fitting and use the hard-coded crypto
             defaults. Useful when you have limited data.

        Why GMM instead of full HMM?
          Full HMM (e.g. hmmlearn) can be unstable with few data points and
          requires careful initialization. GMM + transition counting is more
          robust and gives nearly identical results for simulation purposes.
          The key thing we need is reasonable mu/sigma per regime and a
          transition matrix — GMM gives us that reliably.

        Returns:
            RegimeFitResult with estimated parameters.
        """
        if use_defaults or len(self._returns) < 100:
            self._fit_result = RegimeFitResult(
                regime_names=_REGIME_NAMES[: self._n_regimes],
                mu=_DEFAULT_REGIME_MU[: self._n_regimes].copy(),
                sigma=_DEFAULT_REGIME_SIGMA[: self._n_regimes].copy(),
                transition=_DEFAULT_TRANSITION[: self._n_regimes, : self._n_regimes].copy(),
                stationary=_compute_stationary(
                    _DEFAULT_TRANSITION[: self._n_regimes, : self._n_regimes]
                ),
                n_regimes=self._n_regimes,
                fitted=False,
            )
            return self._fit_result

        # Step 1: Cluster returns into regimes using GMM.
        from sklearn.mixture import GaussianMixture

        X = self._returns.reshape(-1, 1)
        gmm = GaussianMixture(
            n_components=self._n_regimes,
            covariance_type="full",
            n_init=10,
            random_state=42,
        )
        gmm.fit(X)
        labels = gmm.predict(X)

        # Step 2: Extract mu and sigma per regime.
        means = gmm.means_.flatten()
        stds = np.sqrt(gmm.covariances_.flatten())

        # Step 3: Sort regimes by mean return (bear=lowest, bull=highest).
        order = np.argsort(means)
        means = means[order]
        stds = stds[order]
        # Remap labels to sorted order.
        remap = {old: new for new, old in enumerate(order)}
        labels = np.array([remap[l] for l in labels])

        # Step 4: Estimate transition matrix from the label sequence.
        # Count how many times state i is followed by state j.
        transition = np.zeros((self._n_regimes, self._n_regimes))
        for i in range(len(labels) - 1):
            transition[labels[i], labels[i + 1]] += 1

        # Normalize rows to get probabilities.
        row_sums = transition.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1  # avoid division by zero
        transition = transition / row_sums

        # Assign regime names: bear (lowest mu) → neutral → bull (highest mu).
        names = list(reversed(_REGIME_NAMES[: self._n_regimes]))
        # Actually: index 0 = bear (lowest mean), index 2 = bull (highest)
        names = ["BEAR", "NEUTRAL", "BULL"][: self._n_regimes]

        self._fit_result = RegimeFitResult(
            regime_names=names,
            mu=means,
            sigma=stds,
            transition=transition,
            stationary=_compute_stationary(transition),
            n_regimes=self._n_regimes,
            fitted=True,
        )
        return self._fit_result

    def simulate(
        self,
        num_paths: int = SIM_DEFAULT_NUM_PATHS,
        path_length: int = SIM_DEFAULT_PATH_LENGTH,
        seed: int | None = None,
    ) -> np.ndarray:
        """Generate synthetic price paths with regime switching.

        Algorithm for each path:
          1. Start in a random regime (weighted by stationary distribution).
          2. For each day:
             a. Draw today's return from N(mu[regime], sigma[regime]).
             b. Decide tomorrow's regime: draw from the transition matrix
                row for the current regime.
          3. Convert returns to prices: P(t) = exp(cumsum(r)).

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
        r = self._fit_result

        price_paths = np.empty((path_length, num_paths), dtype=np.float64)

        for j in range(num_paths):
            # Pick starting regime from stationary distribution.
            regime = rng.choice(r.n_regimes, p=r.stationary)
            returns = np.empty(path_length, dtype=np.float64)

            for t in range(path_length):
                # Draw today's return from current regime.
                returns[t] = rng.normal(r.mu[regime], r.sigma[regime])

                # Transition to next regime.
                regime = rng.choice(r.n_regimes, p=r.transition[regime])

            cum_returns = np.cumsum(returns)
            price_paths[:, j] = np.exp(cum_returns)

        return price_paths

    @property
    def fit_result(self) -> RegimeFitResult | None:
        """Access fitted parameters (None if not fitted)."""
        return self._fit_result

    def summary(self) -> str:
        """Human-readable summary of regime parameters."""
        if self._fit_result is None:
            return "Model not fitted yet. Call fit() first."

        r = self._fit_result
        lines = [
            f"Regime-Switching Model ({r.n_regimes} regimes)",
            "=" * 50,
            f"Estimated from data: {'Yes' if r.fitted else 'No (using defaults)'}",
            "",
            "Regime Parameters:",
            f"  {'Regime':<10} {'Daily Drift':>12} {'Daily Vol':>10} {'Stationary %':>14}",
            f"  {'-' * 48}",
        ]
        for i in range(r.n_regimes):
            lines.append(
                f"  {r.regime_names[i]:<10} "
                f"{r.mu[i] * 100:>+11.3f}% "
                f"{r.sigma[i] * 100:>9.2f}% "
                f"{r.stationary[i] * 100:>13.1f}%"
            )

        lines.append("\nTransition Matrix (row=from, col=to):")
        header = "  " + " " * 10 + "".join(f"{n:>10}" for n in r.regime_names)
        lines.append(header)
        for i in range(r.n_regimes):
            row = f"  {r.regime_names[i]:<10}" + "".join(
                f"{r.transition[i, j]:>10.3f}" for j in range(r.n_regimes)
            )
            lines.append(row)

        lines.append(
            f"\nInterpretation: Once in BEAR, expected duration = "
            f"{1 / (1 - r.transition[-1, -1]):.0f} days before switching."
        )
        return "\n".join(lines)


def _compute_stationary(transition: np.ndarray) -> np.ndarray:
    """Compute the stationary distribution of a Markov transition matrix.

    The stationary distribution pi satisfies: pi @ T = pi and sum(pi) = 1.
    This tells you the long-run fraction of time spent in each regime.

    Method: find the left eigenvector corresponding to eigenvalue 1.
    """
    n = transition.shape[0]
    # Solve (T' - I) @ pi = 0 with constraint sum(pi) = 1.
    A = transition.T - np.eye(n)
    A[-1, :] = 1  # replace last equation with sum constraint
    b = np.zeros(n)
    b[-1] = 1
    try:
        pi = np.linalg.solve(A, b)
        pi = np.maximum(pi, 0)  # numerical safety
        pi /= pi.sum()
    except np.linalg.LinAlgError:
        pi = np.ones(n) / n  # fallback to uniform
    return pi
