"""
OHLCV Builder — Convert Simulated Price Paths to Candle Data
=============================================================
Your backtest engine needs full OHLCV candles (open, high, low, close,
volume), but our simulation methods only produce closing prices.

This module bridges that gap by learning the "shape" of candles from your
real data and applying that shape to synthetic price paths.

How it works:
  1. Analyze your real candles to measure "intracandle ratios":
     - Upper wick ratio = (high - max(open, close)) / close
     - Lower wick ratio = (min(open, close) - low) / close
     - Body ratio = abs(close - open) / close
  2. Store the distribution of these ratios (not just averages — we
     keep the full distribution so we can sample from it).
  3. For each synthetic close price, sample ratios from the real
     distribution and build open, high, low values.

Why this is good enough:
  - The strategy uses OHLCV primarily for indicator computation (which
    mostly uses close) and SL/TP wick-fill checking.
  - By preserving the wick distribution, the frequency of SL/TP hits
    in simulation matches reality reasonably well.
  - It's NOT pixel-perfect — but for Monte Carlo stress testing, it's
    the right tradeoff between accuracy and simplicity.

Usage:
  builder = OHLCVBuilder.from_real_data(real_df)
  candle_df = builder.build(price_path, start_date="2024-01-01", timeframe="5m")
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd


class OHLCVBuilder:
    """Build synthetic OHLCV DataFrames from price paths.

    Learns intracandle shape from real data, then applies it to
    simulated closing prices to produce full candles.
    """

    def __init__(
        self,
        upper_wick_ratios: np.ndarray,
        lower_wick_ratios: np.ndarray,
        body_ratios: np.ndarray,
        body_directions: np.ndarray,
        volume_values: np.ndarray,
    ) -> None:
        self._upper = upper_wick_ratios
        self._lower = lower_wick_ratios
        self._body = body_ratios
        self._directions = body_directions  # fraction of bullish candles
        self._volumes = volume_values

    @classmethod
    def from_real_data(cls, df: pd.DataFrame) -> OHLCVBuilder:
        """Learn candle shape from a real OHLCV DataFrame.

        Measures the distribution of:
          - Upper wick: how far high extends above the candle body.
          - Lower wick: how far low extends below the candle body.
          - Body size: how far open and close are apart.
          - Body direction: what fraction of candles are bullish (close > open).
          - Volume: raw volume values to sample from.

        Args:
            df: DataFrame with columns 'open', 'high', 'low', 'close', 'volume'.
                Must have at least 50 rows for meaningful statistics.

        Returns:
            OHLCVBuilder instance ready to generate synthetic candles.
        """
        o = df["open"].values.astype(np.float64)
        h = df["high"].values.astype(np.float64)
        low = df["low"].values.astype(np.float64)
        c = df["close"].values.astype(np.float64)

        # Body top and bottom (regardless of candle direction).
        body_top = np.maximum(o, c)
        body_bot = np.minimum(o, c)

        # Ratios relative to close price (avoid division by zero).
        safe_close = np.where(c > 0, c, 1.0)

        upper_wick = (h - body_top) / safe_close
        lower_wick = (body_bot - low) / safe_close
        body = np.abs(c - o) / safe_close

        # Clamp to reasonable range (0 to 15% of price).
        upper_wick = np.clip(upper_wick, 0, 0.15)
        lower_wick = np.clip(lower_wick, 0, 0.15)
        body = np.clip(body, 0, 0.15)

        bullish_frac = np.mean(c > o)

        vol = df["volume"].values.astype(np.float64) if "volume" in df.columns else np.ones(len(df))

        return cls(
            upper_wick_ratios=upper_wick,
            lower_wick_ratios=lower_wick,
            body_ratios=body,
            body_directions=np.array([bullish_frac]),
            volume_values=vol,
        )

    def build(
        self,
        price_path: np.ndarray,
        start_date: str | datetime = "2024-01-01",
        timeframe: str = "5m",
        seed: int | None = None,
    ) -> pd.DataFrame:
        """Convert a simulated price path to a full OHLCV DataFrame.

        Algorithm for each candle:
          1. close = price_path[i] (this is given by the simulation).
          2. Sample an upper wick ratio from the real distribution.
          3. Sample a lower wick ratio from the real distribution.
          4. Sample a body ratio from the real distribution.
          5. Decide if candle is bullish or bearish (random, weighted
             by the real bullish fraction).
          6. Compute open = close ± body_ratio * close.
          7. Compute high = max(open, close) + upper_wick_ratio * close.
          8. Compute low = min(open, close) - lower_wick_ratio * close.
          9. Sample volume from the real volume distribution.

        Args:
            price_path: 1D numpy array of simulated closing prices.
            start_date: Starting timestamp for the candle series.
            timeframe:  Candle interval (e.g. "5m", "15m", "1h", "1d").
            seed:       Random seed for reproducibility.

        Returns:
            pandas DataFrame with columns: timestamp, open, high, low,
            close, volume — in the same format your BacktestEngine expects.
        """
        rng = np.random.default_rng(seed)
        n = len(price_path)

        closes = price_path.astype(np.float64)

        # Sample ratios by randomly picking from real data distribution.
        idx_upper = rng.integers(0, len(self._upper), size=n)
        idx_lower = rng.integers(0, len(self._lower), size=n)
        idx_body = rng.integers(0, len(self._body), size=n)
        idx_vol = rng.integers(0, len(self._volumes), size=n)

        upper_r = self._upper[idx_upper]
        lower_r = self._lower[idx_lower]
        body_r = self._body[idx_body]
        volumes = self._volumes[idx_vol]

        # Decide candle direction (bullish/bearish).
        bullish_frac = float(self._directions[0])
        is_bullish = rng.random(size=n) < bullish_frac

        # Compute open prices.
        opens = np.where(
            is_bullish,
            closes * (1 - body_r),  # bullish: open < close
            closes * (1 + body_r),  # bearish: open > close
        )

        # Compute high and low.
        body_top = np.maximum(opens, closes)
        body_bot = np.minimum(opens, closes)
        highs = body_top + upper_r * closes
        lows = body_bot - lower_r * closes

        # Ensure high >= max(open, close) and low <= min(open, close).
        highs = np.maximum(highs, body_top)
        lows = np.minimum(lows, body_bot)
        lows = np.maximum(lows, 0)  # prices can't go negative

        # Build timestamp index.
        timestamps = _build_timestamps(start_date, n, timeframe)

        return pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": volumes,
            }
        )


def _build_timestamps(
    start: str | datetime,
    n: int,
    timeframe: str,
) -> pd.DatetimeIndex:
    """Generate a DatetimeIndex for n candles at the given timeframe."""
    if isinstance(start, str):
        start = pd.Timestamp(start)

    freq_map = {
        "1m": "1min",
        "3m": "3min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "1d": "1D",
    }
    freq = freq_map.get(timeframe, "5min")
    return pd.date_range(start=start, periods=n, freq=freq)
