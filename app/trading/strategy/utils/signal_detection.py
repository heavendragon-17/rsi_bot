"""Thin wrappers over Indicators crossover methods for strategy use."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from app.data.indicators import Indicators


def detect_crossover_signal(indicators: Indicators, df: pd.DataFrame, direction: str) -> bool:
    """Detect EMA9/WMA45 crossover. Delegates to Indicators.detect_crossover."""
    return indicators.detect_crossover(df, direction=direction)


def check_rsi_alignment(indicators: Indicators, df: pd.DataFrame, direction: str) -> bool:
    """Check RSI < EMA9 < WMA45 (bearish) or inverse. Delegates to Indicators.check_alignment."""
    return indicators.check_alignment(df, direction=direction)


def check_rsi_spread(df: pd.DataFrame, min_spread: float) -> bool:
    """Check if WMA45-EMA9 spread exceeds threshold on the last candle."""
    if df is None or df.empty:
        return False

    last = df.iloc[-1]
    ema = last.get("rsi_ema9")
    wma = last.get("rsi_wma45")

    if ema is None or wma is None or pd.isna(ema) or pd.isna(wma):
        return False

    return abs(float(wma) - float(ema)) > min_spread
