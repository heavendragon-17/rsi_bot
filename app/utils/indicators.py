"""
Layer 2: Core Logic - Indicators
=================================
Technical indicator calculations for RSI+WMA+EMA strategy.
"""
from __future__ import annotations
from typing import Optional, Tuple
from decimal import Decimal
from collections import OrderedDict
import pandas as pd


# Market mode constants
MODE_BULLISH = "BULLISH"
MODE_NEUTRAL = "NEUTRAL"


class Indicators:
    """
    Compute indicators needed for RSI WMA Retest strategy:
      - RSI (14 period)
      - RSI EMA9
      - RSI WMA45
      - EMA21 (price)
      - EMA200 (price)
      - Mode detection
      - Price ladder (R40, R60, R70, R80)
      - WMA retest detection
    """

    def __init__(
        self,
        rsi_length: int = 21,
        rsi_ema_length: int = 9,
        rsi_wma_length: int = 45,
        price_ema_fast: int = 21,
        price_ema_slow: int = 200,
        enable_cache: bool = True,
    ):
        self.rsi_length = int(rsi_length)
        self.rsi_ema_length = int(rsi_ema_length)
        self.rsi_wma_length = int(rsi_wma_length)
        self.price_ema_fast = int(price_ema_fast)
        self.price_ema_slow = int(price_ema_slow)
        
        self.enable_cache = bool(enable_cache)
        # LRU Cache: Key -> DataFrame
        self._cache: OrderedDict = OrderedDict()
        self._cache_size = 32

    def compute(self, df: pd.DataFrame, *, symbol: str = "", timeframe: str = "") -> pd.DataFrame:
        """
        Compute all indicators and add as new columns.
        Returns DataFrame with: rsi, rsi_ema9, rsi_wma45, ema21, ema200
        """
        if df is None or df.empty:
            return pd.DataFrame()

        # Skip if indicators already computed (for backtest optimization)
        if "rsi" in df.columns and "rsi_wma45" in df.columns:
            return df

        # Cache key based on symbol, timeframe, last timestamp, length
        last_timestamp = int(df.iloc[-1]["ts"]) if "ts" in df.columns else len(df)
        key = (symbol, timeframe, last_timestamp, len(df))

        if self.enable_cache:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]

        out = df.copy()

        try:
            import pandas_ta as ta

            out["rsi"] = ta.rsi(out["close"], length=self.rsi_length)
            out["rsi_ema9"] = ta.ema(out["rsi"], length=self.rsi_ema_length)
            out["rsi_wma45"] = ta.wma(out["rsi"], length=self.rsi_wma_length)
            out["ema21"] = ta.ema(out["close"], length=self.price_ema_fast)
            out["ema200"] = ta.ema(out["close"], length=self.price_ema_slow)

        except Exception:
            # Fallback: Manual computation
            delta = out["close"].diff()
            gain = delta.clip(lower=0).rolling(self.rsi_length).mean()
            loss = (-delta.clip(upper=0)).rolling(self.rsi_length).mean()
            rs = gain / loss.replace(0, pd.NA)
            out["rsi"] = 100 - (100 / (1 + rs))

            out["rsi_ema9"] = out["rsi"].ewm(span=self.rsi_ema_length, adjust=False).mean()
            
            # WMA calculation
            w = pd.Series(range(1, self.rsi_wma_length + 1))
            out["rsi_wma45"] = out["rsi"].rolling(self.rsi_wma_length).apply(
                lambda x: (x * w[-len(x):].values).sum() / w[-len(x):].sum(),
                raw=False,
            )

            out["ema21"] = out["close"].ewm(span=self.price_ema_fast, adjust=False).mean()
            out["ema200"] = out["close"].ewm(span=self.price_ema_slow, adjust=False).mean()

        # Store RSI components for price ladder calculation
        out["_delta"] = out["close"].diff()
        out["_gain"] = out["_delta"].clip(lower=0)
        out["_loss"] = (-out["_delta"].clip(upper=0))
        out["_avg_gain"] = out["_gain"].ewm(alpha=1/self.rsi_length, adjust=False).mean()
        out["_avg_loss"] = out["_loss"].ewm(alpha=1/self.rsi_length, adjust=False).mean()

        if self.enable_cache:
            self._cache[key] = out
            if len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)

        return out

    def get_mode(self, df: pd.DataFrame) -> str:
        """
        Detect market mode: BULLISH or NEUTRAL.
        Based on indicator_code.txt lines 62-74.
        
        LONG ONLY strategy - we only care about BULLISH and NEUTRAL.
        """
        if df is None or len(df) < 10:
            return MODE_NEUTRAL
        
        last = df.iloc[-1]
        rsi_ema9 = last.get("rsi_ema9")
        rsi_wma45 = last.get("rsi_wma45")
        
        if rsi_ema9 is None or rsi_wma45 is None:
            return MODE_NEUTRAL
        
        # Get WMA45 values for momentum check
        if len(df) < 10:
            return MODE_NEUTRAL
            
        wma45_now = rsi_wma45
        wma45_3 = df.iloc[-4].get("rsi_wma45") if len(df) > 3 else None
        wma45_9 = df.iloc[-10].get("rsi_wma45") if len(df) > 9 else None
        
        if wma45_3 is None or wma45_9 is None:
            return MODE_NEUTRAL
        
        # Mode detection logic from indicator_code.txt
        if (wma45_now - wma45_3 > 0) and rsi_ema9 > wma45_now and (wma45_now > 55 or wma45_now < 45):
            return MODE_BULLISH
        
        if (wma45_now - wma45_9 > 3):
            return MODE_BULLISH
        
        return MODE_NEUTRAL

    def calculate_price_at_rsi(self, df: pd.DataFrame, target_rsi: float) -> Optional[Decimal]:
        """
        Calculate the price level for a target RSI value.
        Based on indicator_code.txt lines 102-111 (f_calc_target_price).
        
        Used for:
        - R40 (SL level)
        - R60, R70, R80 (TP levels)
        
        Returns None if calculation not possible.
        """
        if df is None or df.empty:
            return None
        
        last = df.iloc[-1]
        close = last.get("close")
        avg_gain = last.get("_avg_gain")
        avg_loss = last.get("_avg_loss")
        
        if close is None or avg_gain is None or avg_loss is None:
            return None
        
        if avg_gain is None or pd.isna(avg_gain) or avg_loss is None or pd.isna(avg_loss):
            return None
        
        try:
            # Target RS = 100 / (100 - targetRSI) - 1
            target_rs = 100 / (100 - target_rsi) - 1
            
            if target_rsi >= 50:
                # Price needs to go UP
                required_gain = target_rs * avg_loss - avg_gain
                required_change = required_gain * self.rsi_length
                target_price = close + required_change
            else:
                # Price needs to go DOWN
                required_loss = avg_gain / target_rs - avg_loss if target_rs > 0 else 0
                required_change = required_loss * self.rsi_length
                target_price = close - required_change
            
            return Decimal(str(round(target_price, 8)))
        except (ZeroDivisionError, ValueError):
            return None

    def check_wma_retest(self, df: pd.DataFrame, distance: float = 1.0) -> bool:
        """
        Check if RSI is retesting WMA45 within specified distance.
        Based on indicator_code.txt lines 224-226.
        
        Args:
            df: DataFrame with indicators computed
            distance: Maximum distance from WMA45 (default ≤1 unit)
        
        Returns:
            True if RSI is within distance of WMA45 (valid retest)
        """
        if df is None or len(df) < 4:
            return False
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        rsi = last.get("rsi")
        rsi_wma45 = last.get("rsi_wma45")
        prev_rsi = prev.get("rsi")
        
        if rsi is None or rsi_wma45 is None or prev_rsi is None:
            return False
        
        # Check if RSI is within distance of WMA45
        touched = abs(rsi - rsi_wma45) <= distance
        
        # Additional check: RSI should be coming from above (retest from above)
        came_from_above = prev_rsi > rsi_wma45
        
        return touched and came_from_above

    def check_r40_floor(self, df: pd.DataFrame, lookback: int = 5) -> bool:
        """
        Verify no candle in lookback period closed below R40 price level.
        Wicks are allowed, only closes are checked.
        
        Args:
            df: DataFrame with indicators and R40 prices computed
            lookback: Number of candles to check (default 5)
        
        Returns:
            True if floor is intact (no close below R40) - valid for entry
            False if any candle closed below R40 - invalid for entry
        """
        if df is None or len(df) < lookback:
            return False
        
        # Get the lookback period
        check_period = df.tail(lookback)
        
        for i in range(len(check_period)):
            row = check_period.iloc[i]
            close = row.get("close")
            
            # Calculate R40 price for this candle
            r40_price = self.calculate_price_at_rsi(df.iloc[:len(df) - lookback + i + 1], 40)
            
            if r40_price is None:
                continue
            
            # Check if close is below R40
            if close is not None and Decimal(str(close)) < r40_price:
                return False
        
        return True

    @staticmethod
    def last(df: pd.DataFrame) -> dict:
        """Extract the last row as a dictionary, converting numpy types."""
        if df is None or df.empty:
            return {}
        
        row = df.iloc[-1].to_dict()
        
        for k, v in list(row.items()):
            if hasattr(v, "item"):
                row[k] = v.item()
        
        return row
