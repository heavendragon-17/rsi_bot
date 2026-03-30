"""
Block Bootstrap Simulation (Method 2)
======================================
Resample chunks of consecutive real returns with replacement to create
new synthetic price paths. This preserves short-term volatility clustering
without any model assumptions.

Plain English:
  Imagine your daily returns written on cards. A simple bootstrap would
  shuffle every card individually — but that destroys the fact that
  volatile days tend to cluster together. Block bootstrap instead cuts the
  cards into hands of ~20 consecutive cards, then shuffles the hands.
  Within each hand, the original order is preserved.

  By reassembling 1000 different shuffles, you get 1000 "what if"
  histories that are statistically similar to the real one — but each
  has a different sequence of booms and crashes.

Key concepts:
  - Block size: how many consecutive days per block.
    Too small (1-3) → destroys autocorrelation (no better than iid shuffle).
    Too large (100+) → too few blocks to resample, paths look like history.
    Sweet spot for crypto: ~20 days (captures one volatility regime).
  - Circular bootstrap: treats the return series as a ring so blocks that
    start near the end can wrap around. Avoids edge bias.

Usage:
  bs = BlockBootstrap(returns, block_size=20)
  paths = bs.simulate(num_paths=1000, path_length=252)
  # paths.shape == (252, 1000) — each column is one simulated price path
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.constants import SIM_BLOCK_BOOTSTRAP_SIZE, SIM_DEFAULT_NUM_PATHS, SIM_DEFAULT_PATH_LENGTH


class BlockBootstrap:
    """Generate synthetic return paths by block-resampling real returns.

    Parameters:
        returns:    pandas Series of daily log-returns.
        block_size: number of consecutive days per block.
                    Default 20 — roughly one volatility cluster in crypto.
    """

    def __init__(
        self,
        returns: pd.Series,
        block_size: int = SIM_BLOCK_BOOTSTRAP_SIZE,
    ) -> None:
        self._returns = returns.values.astype(np.float64)
        self._n = len(self._returns)
        self._block_size = block_size

        if self._n < block_size:
            raise ValueError(
                f"Return series ({self._n} points) is shorter than block_size "
                f"({block_size}). Need at least one full block of data."
            )

    def simulate(
        self,
        num_paths: int = SIM_DEFAULT_NUM_PATHS,
        path_length: int = SIM_DEFAULT_PATH_LENGTH,
        seed: int | None = None,
    ) -> np.ndarray:
        """Generate simulated price paths via block bootstrap.

        Algorithm:
          1. Decide how many blocks we need: ceil(path_length / block_size).
          2. For each simulated path:
             a. Randomly pick that many starting positions in the real data.
             b. Extract a block of `block_size` consecutive returns starting
                at each position (wrapping around circularly if needed).
             c. Concatenate all blocks and trim to exactly `path_length` days.
          3. Convert the resampled returns to price paths: P(t) = exp(cumsum(r)).

        Why circular? If we only allow blocks that fit entirely within the
        data, blocks near the end are underrepresented. Circular wrapping
        treats the series as a ring, giving every starting point equal
        probability.

        Args:
            num_paths:   Number of simulated paths to generate (default 1000).
            path_length: Length of each path in days (default 252 ≈ 1 year).
            seed:        Random seed for reproducibility. None = random.

        Returns:
            numpy array of shape (path_length, num_paths).
            Each column is a price path starting at 1.0.
        """
        rng = np.random.default_rng(seed)

        # How many blocks do we need to fill one path?
        blocks_needed = int(np.ceil(path_length / self._block_size))

        # Pre-allocate output: returns first, then convert to prices.
        sim_returns = np.empty((path_length, num_paths), dtype=np.float64)

        for j in range(num_paths):
            # Pick random starting indices for each block.
            starts = rng.integers(0, self._n, size=blocks_needed)

            # Extract and concatenate blocks.
            blocks = []
            for s in starts:
                # Circular extraction: if the block extends past the end,
                # wrap around to the beginning.
                if s + self._block_size <= self._n:
                    blocks.append(self._returns[s : s + self._block_size])
                else:
                    # Wrap: take from s to end, then from beginning.
                    tail = self._returns[s:]
                    head = self._returns[: self._block_size - len(tail)]
                    blocks.append(np.concatenate([tail, head]))

            # Concatenate all blocks and trim to exact path length.
            all_returns = np.concatenate(blocks)[:path_length]
            sim_returns[:, j] = all_returns

        # Convert log-returns to price paths starting at 1.0.
        # price[t] = exp(cumulative_sum_of_returns[0..t])
        cum_returns = np.cumsum(sim_returns, axis=0)
        price_paths = np.exp(cum_returns)

        return price_paths

    @property
    def block_size(self) -> int:
        """Current block size."""
        return self._block_size

    @property
    def num_blocks_available(self) -> int:
        """How many non-overlapping blocks fit in the data (informational)."""
        return self._n // self._block_size
