from __future__ import annotations
from typing import Optional, Tuple
import pandas as pd


class Indicators:
    """
    Compute indicators needed for strategy:
      - rsi
      - rsi_ema9
      - rsi_wma45
      - ema21  (price)
      - ema200 (price)
    """

    def __init__(
        self,
        rsi_length: int = 14,
        rsi_ema_length: int = 9,
        rsi_wma_length: int = 45,
        price_ema_fast: int = 21,
        price_ema_slow: int = 200,
        enable_cache: bool = True,
    ):
        # Store RSI calculation parameters
        self.rsi_length = int(rsi_length)
        self.rsi_ema_length = int(rsi_ema_length)
        self.rsi_wma_length = int(rsi_wma_length)
        
        # Store price EMA calculation parameters
        self.price_ema_fast = int(price_ema_fast)
        self.price_ema_slow = int(price_ema_slow)
        
        # Cache settings
        self.enable_cache = bool(enable_cache)
        self._cache_key: Optional[Tuple[str, str, int, int]] = None
        self._cache_df: Optional[pd.DataFrame] = None

    def compute(self, df: pd.DataFrame, *, symbol: str = "", timeframe: str = "") -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()

        # Create cache key based on symbol, timeframe, last timestamp, and data length
        last_timestamp = int(df.iloc[-1]["ts"]) if "ts" in df.columns else len(df)
        key = (symbol, timeframe, last_timestamp, len(df))

        # Return cached result if available and cache is enabled
        if self.enable_cache and self._cache_key == key and self._cache_df is not None:
            return self._cache_df

        out = df.copy()

        try:
            import pandas_ta as ta

            # Calculate RSI and its moving averages
            out["rsi"] = ta.rsi(out["close"], length=self.rsi_length)
            out["rsi_ema9"] = ta.ema(out["rsi"], length=self.rsi_ema_length)
            out["rsi_wma45"] = ta.wma(out["rsi"], length=self.rsi_wma_length)

            # Calculate price EMAs
            out["ema21"] = ta.ema(out["close"], length=self.price_ema_fast)
            out["ema200"] = ta.ema(out["close"], length=self.price_ema_slow)

        except Exception:
            # Fallback: Manually compute indicators if pandas_ta is not available
            # Calculate RSI manually
            delta = out["close"].diff()
            gain = delta.clip(lower=0).rolling(self.rsi_length).mean()
            loss = (-delta.clip(upper=0)).rolling(self.rsi_length).mean()
            rs = gain / loss.replace(0, pd.NA)
            out["rsi"] = 100 - (100 / (1 + rs))

            # Calculate RSI EMA
            out["rsi_ema9"] = out["rsi"].ewm(span=self.rsi_ema_length, adjust=False).mean()

            # Calculate RSI WMA
            w = pd.Series(range(1, self.rsi_wma_length + 1))
            out["rsi_wma45"] = out["rsi"].rolling(self.rsi_wma_length).apply(
                lambda x: (x * w[-len(x):].values).sum() / w[-len(x):].sum(),
                raw=False,
            )

            # Calculate price EMAs
            out["ema21"] = out["close"].ewm(span=self.price_ema_fast, adjust=False).mean()
            out["ema200"] = out["close"].ewm(span=self.price_ema_slow, adjust=False).mean()

        # Store result in cache if enabled
        if self.enable_cache:
            self._cache_key = key
            self._cache_df = out

        return out

    @staticmethod
    def last(df: pd.DataFrame) -> dict:
        """Extract the last row as a dictionary, converting numpy types to Python types."""
        if df is None or df.empty:
            return {}
        
        row = df.iloc[-1].to_dict()
        
        # Convert numpy scalar types to Python native types
        for k, v in list(row.items()):
            if hasattr(v, "item"):
                row[k] = v.item()
        
        return row
