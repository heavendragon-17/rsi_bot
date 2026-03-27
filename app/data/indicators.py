"""
Layer 2: Core Logic - Indicators
=================================
Unified technical indicator calculations for all RSI-based strategies.

Computes RSI, EMA9-of-RSI, WMA45-of-RSI (shared by all strategies),
plus optional price EMAs for long strategies.

Crossover detection:
  - direction="bearish" (down cross) -> SHORT entry signal
  - direction="bullish" (up cross)   -> LONG setup signal
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd

from app.core.interfaces import IIndicators

# Market mode constants
MODE_BULLISH = "BULLISH"
MODE_NEUTRAL = "NEUTRAL"


class Indicators(IIndicators):
    """Unified indicator computation for all RSI strategies.

    Computes RSI, EMA9-of-RSI, WMA45-of-RSI (shared by all strategies),
    plus optional price EMAs (EMA21, EMA200) for long strategies.

    Output columns: rsi_14, rsi_ema9, rsi_wma45
    Optional columns (include_price_emas=True): ema21, ema200
    Internal columns: _delta, _gain, _loss, _avg_gain, _avg_loss
    """

    def __init__(
        self,
        rsi_period: int = 14,
        rsi_ema_period: int = 9,
        rsi_wma_period: int = 45,
        price_ema_fast: int = 21,
        price_ema_slow: int = 200,
        include_price_emas: bool = False,
        enable_cache: bool = True,
    ):
        self.rsi_period = int(rsi_period)
        self.rsi_ema_period = int(rsi_ema_period)
        self.rsi_wma_period = int(rsi_wma_period)
        self.price_ema_fast = int(price_ema_fast)
        self.price_ema_slow = int(price_ema_slow)
        self.include_price_emas = bool(include_price_emas)

        self.enable_cache = bool(enable_cache)
        self._cache_key: tuple[str, str, int, int] | None = None
        self._cache_df: pd.DataFrame | None = None

    # ------------------------------------------------------------------
    # IIndicators interface
    # ------------------------------------------------------------------

    def compute(self, df: pd.DataFrame, *, symbol: str = "", timeframe: str = "") -> pd.DataFrame:  # type: ignore[override]
        """Compute all indicators. Adds: rsi_14, rsi_ema9, rsi_wma45.
        Optionally: ema21, ema200 (when include_price_emas=True)."""
        if df is None or df.empty:
            return pd.DataFrame()

        # Skip if indicators already computed (for backtest optimization)
        if "rsi_14" in df.columns and "rsi_wma45" in df.columns:
            return df

        # Cache key based on symbol, timeframe, last timestamp, length
        last_timestamp = int(df.iloc[-1]["ts"]) if "ts" in df.columns else len(df)
        key = (symbol, timeframe, last_timestamp, len(df))

        if self.enable_cache and self._cache_key == key and self._cache_df is not None:
            return self._cache_df

        out = df.copy()

        try:
            import pandas_ta as ta

            out["rsi_14"] = ta.rsi(out["close"], length=self.rsi_period)
            out["rsi_ema9"] = ta.ema(out["rsi_14"], length=self.rsi_ema_period)
            out["rsi_wma45"] = ta.wma(out["rsi_14"], length=self.rsi_wma_period)

            if self.include_price_emas:
                out["ema21"] = ta.ema(out["close"], length=self.price_ema_fast)
                out["ema200"] = ta.ema(out["close"], length=self.price_ema_slow)

        except Exception:
            # Fallback: manual computation
            delta = out["close"].diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.ewm(alpha=1 / self.rsi_period, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1 / self.rsi_period, adjust=False).mean()
            rs = avg_gain / avg_loss.replace(0, float("nan"))
            out["rsi_14"] = 100 - (100 / (1 + rs))

            out["rsi_ema9"] = out["rsi_14"].ewm(span=self.rsi_ema_period, adjust=False).mean()

            weights = pd.Series(range(1, self.rsi_wma_period + 1))
            out["rsi_wma45"] = (
                out["rsi_14"]
                .rolling(self.rsi_wma_period)
                .apply(
                    lambda x: (x * weights[-len(x) :].values).sum() / weights[-len(x) :].sum(),
                    raw=False,
                )
            )

            if self.include_price_emas:
                out["ema21"] = out["close"].ewm(span=self.price_ema_fast, adjust=False).mean()
                out["ema200"] = out["close"].ewm(span=self.price_ema_slow, adjust=False).mean()

        # Store RSI components for price ladder calculation
        out["_delta"] = out["close"].diff()
        out["_gain"] = out["_delta"].clip(lower=0)
        out["_loss"] = -out["_delta"].clip(upper=0)
        out["_avg_gain"] = out["_gain"].ewm(alpha=1 / self.rsi_period, adjust=False).mean()
        out["_avg_loss"] = out["_loss"].ewm(alpha=1 / self.rsi_period, adjust=False).mean()

        if self.enable_cache:
            self._cache_key = key
            self._cache_df = out

        return out

    def get_mode(self, df: pd.DataFrame, current_index: int | None = None) -> str:
        """Detect market mode: BULLISH or NEUTRAL.

        Based on WMA45 momentum and EMA9/WMA45 relationship.
        Used by long strategies for mode filtering.
        """
        idx = current_index if current_index is not None else (len(df) - 1 if df is not None else -1)
        eff_len = idx + 1
        if df is None or eff_len < 10:
            return MODE_NEUTRAL

        last = df.iloc[idx]
        rsi_ema9 = last.get("rsi_ema9")
        rsi_wma45 = last.get("rsi_wma45")

        if rsi_ema9 is None or rsi_wma45 is None:
            return MODE_NEUTRAL

        wma45_now = rsi_wma45
        wma45_3 = df.iloc[idx - 3].get("rsi_wma45") if eff_len > 3 else None
        wma45_9 = df.iloc[idx - 9].get("rsi_wma45") if eff_len > 9 else None

        if wma45_3 is None or wma45_9 is None:
            return MODE_NEUTRAL

        if (wma45_now - wma45_3 > 0) and rsi_ema9 > wma45_now and (wma45_now > 55 or wma45_now < 45):
            return MODE_BULLISH

        if wma45_now - wma45_9 > 3:
            return MODE_BULLISH

        return MODE_NEUTRAL

    def check_wma_retest(self, df: pd.DataFrame, distance: float = 1.0, current_index: int | None = None) -> bool:
        """Check if RSI is retesting WMA45 within specified distance.

        Returns True if RSI is within distance of WMA45 and came from above.
        """
        idx = current_index if current_index is not None else (len(df) - 1 if df is not None else -1)
        eff_len = idx + 1
        if df is None or eff_len < 4:
            return False

        last = df.iloc[idx]
        prev = df.iloc[idx - 1]

        rsi = last.get("rsi_14")
        rsi_wma45 = last.get("rsi_wma45")
        prev_rsi = prev.get("rsi_14")

        if rsi is None or rsi_wma45 is None or prev_rsi is None:
            return False

        touched = abs(rsi - rsi_wma45) <= distance
        came_from_above = prev_rsi > rsi_wma45

        return touched and came_from_above

    def calculate_price_at_rsi(self, df: pd.DataFrame, target_rsi: float, current_index: int | None = None) -> Decimal | None:  # type: ignore[override]
        """Calculate the price level for a target RSI value.

        Used for R40 (SL level), R60, R70, R80 (TP levels).
        Returns None if calculation not possible.
        """
        if df is None or df.empty:
            return None

        idx = current_index if current_index is not None else -1
        last = df.iloc[idx]
        close = last.get("close")
        avg_gain = last.get("_avg_gain")
        avg_loss = last.get("_avg_loss")

        if close is None or avg_gain is None or avg_loss is None:
            return None

        if pd.isna(avg_gain) or pd.isna(avg_loss):
            return None

        try:
            target_rs = 100 / (100 - target_rsi) - 1

            if target_rsi >= 50:
                required_gain = target_rs * avg_loss - avg_gain
                required_change = required_gain * self.rsi_period
                target_price = close + required_change
            else:
                required_loss = avg_gain / target_rs - avg_loss if target_rs > 0 else 0
                required_change = required_loss * self.rsi_period
                target_price = close - required_change

            return Decimal(str(round(target_price, 8)))
        except (ZeroDivisionError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Crossover detection (shared by SHORT and LONG strategies)
    # ------------------------------------------------------------------

    def detect_crossover(self, df: pd.DataFrame, direction: str = "bearish", current_index: int | None = None) -> bool:
        """Detect EMA9/WMA45 crossover on the most recent closed candle.

        direction='bearish' (down cross): EMA9 was >= WMA45, now < WMA45
        direction='bullish' (up cross): EMA9 was <= WMA45, now > WMA45
        """
        required = {"rsi_ema9", "rsi_wma45"}
        eff_len = (current_index + 1) if current_index is not None else len(df) if df is not None else 0
        if df is None or eff_len < 2 or not required.issubset(df.columns):
            return False

        idx = current_index if current_index is not None else len(df) - 1
        curr = df.iloc[idx]
        prev = df.iloc[idx - 1]

        curr_ema = curr["rsi_ema9"]
        curr_wma = curr["rsi_wma45"]
        prev_ema = prev["rsi_ema9"]
        prev_wma = prev["rsi_wma45"]

        if any(pd.isna(v) for v in [curr_ema, curr_wma, prev_ema, prev_wma]):
            return False

        if direction == "bearish":
            return prev_ema >= prev_wma and curr_ema < curr_wma
        else:  # bullish
            return prev_ema <= prev_wma and curr_ema > curr_wma

    def check_alignment(self, df: pd.DataFrame, direction: str = "bearish", current_index: int | None = None) -> bool:
        """Check indicator alignment on the last candle.

        Bearish: RSI < EMA9 < WMA45
        Bullish: RSI > EMA9 > WMA45
        """
        required = {"rsi_14", "rsi_ema9", "rsi_wma45"}
        if df is None or df.empty or not required.issubset(df.columns):
            return False

        idx = current_index if current_index is not None else -1
        last = df.iloc[idx]
        rsi = last["rsi_14"]
        ema = last["rsi_ema9"]
        wma = last["rsi_wma45"]

        if any(pd.isna(v) for v in [rsi, ema, wma]):
            return False

        if direction == "bearish":
            return rsi < ema < wma
        else:  # bullish
            return rsi > ema > wma

    def detect_bearish_divergence(
        self,
        df: pd.DataFrame,
        lookback: int = 30,
        pivot_strength: int = 5,
        current_index: int | None = None,
    ) -> bool:
        """Detect bearish RSI divergence in the last `lookback` candles.

        A bearish divergence exists when price makes a Higher High
        but RSI makes a Lower High at the same swing-high candles.

        Swing high pivot: index i is a swing high if high[i] > high[j]
        for all j in [i-N, i+N] (strict, N = pivot_strength).
        """
        required_cols = {"high", "rsi_14"}
        idx = current_index if current_index is not None else (len(df) - 1 if df is not None else -1)
        eff_len = idx + 1
        if df is None or eff_len < lookback or not required_cols.issubset(df.columns):
            return False

        start = eff_len - lookback
        end = idx + 1
        n = pivot_strength
        highs = df["high"].values[start:end]
        rsis = df["rsi_14"].values[start:end]
        wlen = len(highs)

        swing_high_idxs = []
        for i in range(n, wlen - n):
            center = highs[i]
            if all(center > highs[i - j] for j in range(1, n + 1)) and all(
                center > highs[i + j] for j in range(1, n + 1)
            ):
                swing_high_idxs.append(i)

        if len(swing_high_idxs) < 2:
            return False

        for a_pos in range(len(swing_high_idxs) - 1):
            for b_pos in range(a_pos + 1, len(swing_high_idxs)):
                a_idx = swing_high_idxs[a_pos]
                b_idx = swing_high_idxs[b_pos]

                rsi_a = rsis[a_idx]
                rsi_b = rsis[b_idx]

                if pd.isna(rsi_a) or pd.isna(rsi_b):
                    continue

                if highs[b_idx] > highs[a_idx] and rsi_b < rsi_a:
                    return True

        return False

    # ------------------------------------------------------------------
    # Price ladder helpers (long strategies, requires include_price_emas)
    # ------------------------------------------------------------------

    def check_r40_floor(self, df: pd.DataFrame, lookback: int = 5, current_index: int | None = None) -> bool:
        """Verify no candle in lookback period closed below R40 price level.

        Wicks are allowed, only closes are checked.
        Returns True if floor is intact (valid for entry).
        """
        idx = current_index if current_index is not None else (len(df) - 1 if df is not None else -1)
        eff_len = idx + 1
        if df is None or eff_len < lookback:
            return False

        start = idx - lookback + 1
        for i in range(lookback):
            row = df.iloc[start + i]
            close = row.get("close")

            r40_price = self.calculate_price_at_rsi(df, 40, current_index=start + i)

            if r40_price is None:
                continue

            if close is not None and Decimal(str(close)) < r40_price:
                return False

        return True

    @staticmethod
    def last(df: pd.DataFrame, current_index: int | None = None) -> dict:
        """Extract the current row as a dictionary, converting numpy types.

        Args:
            df: DataFrame with indicator columns.
            current_index: Absolute row index (backtest mode). None = last row.
        """
        if df is None or df.empty:
            return {}

        idx = current_index if current_index is not None else -1
        row = df.iloc[idx].to_dict()

        for k, v in list(row.items()):
            if hasattr(v, "item"):
                row[k] = v.item()

        return row
