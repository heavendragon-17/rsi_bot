"""
Resampling Utility
==================
Utility function to resample OHLCV DataFrames to different timeframes.
"""
import pandas as pd


def resample_dataframe(df: pd.DataFrame, target_timeframe: str) -> pd.DataFrame:
    """
    Resample a DataFrame with OHLCV data to a target timeframe.

    Args:
        df: Input DataFrame. Must have a DatetimeIndex or a 'timestamp' column.
            Columns expected: 'open', 'high', 'low', 'close', 'volume'.
        target_timeframe: Target timeframe string (e.g., '1h', '1H', '15m').

    Returns:
        Resampled DataFrame with OHLCV aggregation.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    # Work on a copy
    df_res = df.copy()

    # Ensure DatetimeIndex
    if not isinstance(df_res.index, pd.DatetimeIndex):
        if "timestamp" in df_res.columns:
            df_res["timestamp"] = pd.to_datetime(df_res["timestamp"])
            df_res.set_index("timestamp", inplace=True)
        else:
            # If no timestamp column and not DatetimeIndex, assume it's already indexed properly
            # or we can't resample. Let's try to infer or fail gracefully.
            pass

    # Normalize timeframe string for pandas (e.g. '1m' -> '1T', '1h' -> '1H')
    # Simple mapping for common crypto timeframes
    tf_map = {
        'm': 'min',
        'h': 'h',
        'd': 'D',
        'w': 'W'
    }

    # Try to parse timeframe if it ends with m, h, d, w
    rule = target_timeframe
    if target_timeframe[-1].lower() in tf_map:
        unit = target_timeframe[-1].lower()
        val = target_timeframe[:-1]
        rule = f"{val}{tf_map[unit]}"

    # Define aggregation logic
    agg_dict = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }

    # Resample
    # label='left', closed='left' is standard for financial candles (start of interval)
    resampled = df_res.resample(rule, label='left', closed='left').agg(agg_dict)

    # Remove rows with NaN (empty intervals)
    resampled.dropna(inplace=True)

    return resampled
