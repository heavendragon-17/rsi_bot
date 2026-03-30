"""
Historical Scenario Replay (Simulation Method 1)
=================================================
Instead of generating synthetic data, this module finds the WORST periods
in your actual historical data and extracts them as standalone test scenarios.

Why this matters:
  If your strategy can't survive what already happened, it won't survive
  the next crash. This is the most trustworthy stress test because it uses
  real data with zero model assumptions.

How it works:
  1. Compute a rolling drawdown curve over the full return series.
  2. Find the top-N deepest drawdown windows (non-overlapping).
  3. Also find the top-N sharpest single-day crashes.
  4. Return each scenario as a slice of the original return series.

Usage:
  replay = HistoricalReplay(returns)
  scenarios = replay.find_scenarios(top_n=5, min_window=20)
  # scenarios is a list of dicts, each with 'returns', 'start', 'end', etc.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Scenario:
    """One historical stress scenario extracted from real data.

    Attributes:
        name:        Human-readable label (e.g. "Drawdown #1: -62.3%").
        returns:     Daily log-returns for this period.
        prices:      Reconstructed price path starting at 1.0.
        start_idx:   Index in the original series where this scenario begins.
        end_idx:     Index where it ends (inclusive).
        max_dd_pct:  Deepest peak-to-trough drawdown within this window (%).
        duration:    Number of trading days in this window.
    """

    name: str
    returns: np.ndarray
    prices: np.ndarray
    start_idx: int
    end_idx: int
    max_dd_pct: float
    duration: int


class HistoricalReplay:
    """Find and extract the worst historical periods from a return series.

    Parameters:
        returns: pandas Series of daily log-returns (e.g. np.log(close/close.shift(1))).
                 Index can be datetime or integer — only the values matter.

    The class computes a cumulative equity curve internally and identifies
    drawdown windows. It does NOT modify the input data.
    """

    def __init__(self, returns: pd.Series) -> None:
        self._returns = returns.values.astype(np.float64)
        self._index = returns.index

        # Build equity curve: start at 1.0, compound log-returns.
        # equity[i] = exp(sum of returns[0..i])
        cum_returns = np.cumsum(self._returns)
        self._equity = np.exp(cum_returns)

    def find_scenarios(
        self,
        top_n: int = 5,
        min_window: int = 20,
    ) -> list[Scenario]:
        """Extract the top-N worst drawdown periods from the data.

        How the algorithm works:
          - Walk through the equity curve tracking the running peak.
          - At each point, drawdown = (peak - current) / peak.
          - A "drawdown window" starts when equity drops below the peak
            and ends when equity recovers to a new peak (or data ends).
          - We collect all such windows, sort by depth, and keep the
            top_n deepest ones that are at least min_window days long.

        Args:
            top_n:      How many worst scenarios to extract.
            min_window: Minimum duration (days) for a scenario to count.
                        Short blips are noise, not true stress tests.

        Returns:
            List of Scenario objects, sorted from worst to least bad.
        """
        windows = self._find_drawdown_windows()

        # Filter by minimum length and sort by depth (most negative first).
        valid = [w for w in windows if w["duration"] >= min_window]
        valid.sort(key=lambda w: w["max_dd"])  # most negative first

        scenarios = []
        for i, w in enumerate(valid[:top_n]):
            start, end = w["start"], w["end"]
            ret_slice = self._returns[start : end + 1]

            # Reconstruct a price path starting at 1.0 for this slice.
            prices = np.exp(np.cumsum(ret_slice))
            prices = np.insert(prices, 0, 1.0)  # prepend starting price

            scenarios.append(
                Scenario(
                    name=f"Drawdown #{i + 1}: {w['max_dd'] * 100:.1f}%",
                    returns=ret_slice,
                    prices=prices,
                    start_idx=start,
                    end_idx=end,
                    max_dd_pct=w["max_dd"] * 100,
                    duration=w["duration"],
                )
            )

        return scenarios

    def find_sharp_crashes(self, top_n: int = 5, window: int = 5) -> list[Scenario]:
        """Find the sharpest short-term crashes (e.g. 5-day rolling return).

        Unlike find_scenarios() which looks for prolonged drawdowns, this
        finds sudden, violent moves — like March 2020 BTC (-60% in 48h)
        or LUNA collapse.

        Args:
            top_n:  How many worst crashes to extract.
            window: Rolling window size in days to measure crash severity.

        Returns:
            List of Scenario objects for the sharpest short-term drops.
        """
        n = len(self._returns)
        if n < window:
            return []

        # Compute rolling sum of returns over `window` days.
        # A very negative rolling sum = a sharp crash.
        rolling_sum = np.convolve(self._returns, np.ones(window), mode="valid")

        # Get indices sorted by worst rolling return.
        sorted_indices = np.argsort(rolling_sum)

        scenarios = []
        used_ranges: list[tuple[int, int]] = []

        for idx in sorted_indices:
            if len(scenarios) >= top_n:
                break

            start = idx
            end = idx + window - 1

            # Skip if this overlaps with an already-selected crash.
            if any(s <= end and e >= start for s, e in used_ranges):
                continue

            used_ranges.append((start, end))
            ret_slice = self._returns[start : end + 1]
            prices = np.exp(np.cumsum(ret_slice))
            prices = np.insert(prices, 0, 1.0)

            total_drop = float(np.expm1(rolling_sum[idx]))  # convert log to pct

            scenarios.append(
                Scenario(
                    name=f"Crash #{len(scenarios) + 1}: {total_drop * 100:.1f}% in {window}d",
                    returns=ret_slice,
                    prices=prices,
                    start_idx=start,
                    end_idx=end,
                    max_dd_pct=total_drop * 100,
                    duration=window,
                )
            )

        return scenarios

    # ── Internal helpers ──────────────────────────────────────────────

    def _find_drawdown_windows(self) -> list[dict]:
        """Walk the equity curve and identify every drawdown window.

        A drawdown window:
          - Starts when equity drops below its running peak.
          - Ends when equity recovers to a new peak (or the data ends).
          - Records the deepest point within that window.

        Returns:
            List of dicts with keys: start, end, duration, max_dd, trough_idx.
        """
        equity = self._equity
        n = len(equity)
        windows = []

        peak = equity[0]
        window_start = None
        max_dd = 0.0
        trough_idx = 0

        for i in range(n):
            if equity[i] >= peak:
                # New peak — close any open drawdown window.
                if window_start is not None:
                    windows.append(
                        {
                            "start": window_start,
                            "end": i - 1,
                            "duration": i - window_start,
                            "max_dd": max_dd,
                            "trough_idx": trough_idx,
                        }
                    )
                    window_start = None
                    max_dd = 0.0
                peak = equity[i]
            else:
                # In drawdown — track it.
                if window_start is None:
                    window_start = i
                dd = (equity[i] - peak) / peak  # negative number
                if dd < max_dd:
                    max_dd = dd
                    trough_idx = i

        # Close final window if data ends in drawdown.
        if window_start is not None:
            windows.append(
                {
                    "start": window_start,
                    "end": n - 1,
                    "duration": n - window_start,
                    "max_dd": max_dd,
                    "trough_idx": trough_idx,
                }
            )

        return windows
