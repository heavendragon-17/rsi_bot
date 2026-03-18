# app/utils/crossover_indicators.py
"""
CrossoverIndicators — RSI with EMA9 and WMA45 applied to the RSI series.

Used by RsiMomentumStrategy for SHORT/LONG signals based on EMA9/WMA45
crossovers, alignment detection, and bearish RSI divergence.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

import pandas as pd

from app.core.interfaces import IIndicators


class CrossoverIndicators(IIndicators):
    """
    Compute RSI14, EMA9-of-RSI, and WMA45-of-RSI indicators.

    Also provides:
    - detect_bearish_divergence() — price HH + RSI LH in lookback window
    - detect_crossover()          — EMA9 crossed below/above WMA45
    - check_alignment()           — RSI < EMA9 < WMA45 (bearish) or >
    """

    def __init__(
        self,
        rsi_period: int = 14,
        rsi_ema_period: int = 9,
        rsi_wma_period: int = 45,
    ):
        self.rsi_period = int(rsi_period)
        self.rsi_ema_period = int(rsi_ema_period)
        self.rsi_wma_period = int(rsi_wma_period)

    # ------------------------------------------------------------------
    # IIndicators interface
    # ------------------------------------------------------------------

    def compute(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        Adds columns: rsi_14, rsi_ema9, rsi_wma45.

        EMA and WMA are applied to the RSI series (NOT to price).
        If columns already exist they are not recomputed.
        """
        if df is None or df.empty:
            return pd.DataFrame()

        # Skip if already computed
        if "rsi_14" in df.columns and "rsi_wma45" in df.columns:
            return df

        out = df.copy()

        try:
            import pandas_ta as ta  # type: ignore[import]

            out["rsi_14"] = ta.rsi(out["close"], length=self.rsi_period)
            out["rsi_ema9"] = ta.ema(out["rsi_14"], length=self.rsi_ema_period)
            out["rsi_wma45"] = ta.wma(out["rsi_14"], length=self.rsi_wma_period)

        except Exception:
            # Fallback: manual computation
            delta = out["close"].diff()
            gain = delta.clip(lower=0)
            loss = (-delta.clip(upper=0))
            avg_gain = gain.ewm(alpha=1 / self.rsi_period, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1 / self.rsi_period, adjust=False).mean()
            rs = avg_gain / avg_loss.replace(0, float("nan"))
            out["rsi_14"] = 100 - (100 / (1 + rs))

            out["rsi_ema9"] = out["rsi_14"].ewm(
                span=self.rsi_ema_period, adjust=False
            ).mean()

            weights = pd.Series(range(1, self.rsi_wma_period + 1))
            out["rsi_wma45"] = out["rsi_14"].rolling(self.rsi_wma_period).apply(
                lambda x: (x * weights[-len(x):].values).sum()
                / weights[-len(x):].sum(),
                raw=False,
            )

        return out

    def get_mode(self, df: pd.DataFrame) -> str:
        """Returns 'BEARISH' if RSI < EMA9 < WMA45, else 'NEUTRAL'."""
        if self.check_alignment(df, direction="bearish"):
            return "BEARISH"
        return "NEUTRAL"

    def check_wma_retest(self, df: pd.DataFrame, distance: float = 1.0) -> bool:
        """IIndicators stub — not used by this strategy."""
        return False

    def calculate_price_at_rsi(
        self, df: pd.DataFrame, target_rsi: float
    ) -> Optional[Decimal]:
        """IIndicators stub — not used by this strategy."""
        return None

    # ------------------------------------------------------------------
    # Strategy-specific helpers
    # ------------------------------------------------------------------

    def detect_bearish_divergence(
        self,
        df: pd.DataFrame,
        lookback: int = 30,
        pivot_strength: int = 5,
    ) -> bool:
        """
        Detect bearish RSI divergence in the last `lookback` candles.

        A bearish divergence exists when:
        - Price makes a Higher High (uses candle wicks — 'high' column)
        - RSI makes a Lower High at the same swing-high candles

        Swing high pivot: index i is a swing high if high[i] > high[j]
        for all j in [i-N, i+N] (strict, N = pivot_strength).

        Returns True if any valid divergence pair exists in the window.
        """
        required_cols = {"high", "rsi_14"}
        if df is None or len(df) < lookback or not required_cols.issubset(df.columns):
            return False

        window = df.iloc[-lookback:].copy().reset_index(drop=True)
        n = pivot_strength

        # Identify swing-high indices within the window (excluding edges)
        swing_high_idxs = []
        for i in range(n, len(window) - n):
            center_high = window["high"].iloc[i]
            left = window["high"].iloc[i - n : i]
            right = window["high"].iloc[i + 1 : i + n + 1]
            if (center_high > left).all() and (center_high > right).all():
                swing_high_idxs.append(i)

        if len(swing_high_idxs) < 2:
            return False

        # Check every pair (earlier=A, later=B) for divergence
        for a_pos in range(len(swing_high_idxs) - 1):
            for b_pos in range(a_pos + 1, len(swing_high_idxs)):
                a_idx = swing_high_idxs[a_pos]
                b_idx = swing_high_idxs[b_pos]

                price_a = window["high"].iloc[a_idx]
                price_b = window["high"].iloc[b_idx]
                rsi_a = window["rsi_14"].iloc[a_idx]
                rsi_b = window["rsi_14"].iloc[b_idx]

                if pd.isna(rsi_a) or pd.isna(rsi_b):
                    continue

                # Price HH + RSI LH → bearish divergence
                if price_b > price_a and rsi_b < rsi_a:
                    return True

        return False

    def detect_crossover(
        self,
        df: pd.DataFrame,
        direction: str = "bearish",
    ) -> bool:
        """
        Detect EMA9/WMA45 crossover on the most recent closed candle.

        Bearish: EMA9[prev] >= WMA45[prev] AND EMA9[current] < WMA45[current]
        Bullish: EMA9[prev] <= WMA45[prev] AND EMA9[current] > WMA45[current]

        Uses strict inequality to avoid floating-point edge cases.
        """
        required = {"rsi_ema9", "rsi_wma45"}
        if df is None or len(df) < 2 or not required.issubset(df.columns):
            return False

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        curr_ema = curr.get("rsi_ema9")
        curr_wma = curr.get("rsi_wma45")
        prev_ema = prev.get("rsi_ema9")
        prev_wma = prev.get("rsi_wma45")

        if any(pd.isna(v) for v in [curr_ema, curr_wma, prev_ema, prev_wma]):
            return False

        if direction == "bearish":
            return prev_ema >= prev_wma and curr_ema < curr_wma
        else:  # bullish
            return prev_ema <= prev_wma and curr_ema > curr_wma

    def check_alignment(
        self,
        df: pd.DataFrame,
        direction: str = "bearish",
    ) -> bool:
        """
        Check if indicators are in the required alignment on the last candle.

        Bearish: RSI < EMA9 < WMA45
        Bullish: RSI > EMA9 > WMA45
        """
        required = {"rsi_14", "rsi_ema9", "rsi_wma45"}
        if df is None or df.empty or not required.issubset(df.columns):
            return False

        last = df.iloc[-1]
        rsi = last.get("rsi_14")
        ema = last.get("rsi_ema9")
        wma = last.get("rsi_wma45")

        if any(pd.isna(v) for v in [rsi, ema, wma]):
            return False

        if direction == "bearish":
            return rsi < ema < wma
        else:  # bullish
            return rsi > ema > wma
