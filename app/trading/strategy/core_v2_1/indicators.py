"""Deterministic indicator implementation dedicated to Core V2.1.

No optional TA library is used, so live and replay calculations share the
same seed conventions.  Output warm-up values remain NaN and each enriched
frame exposes an explicit ``core_v2_1_ready`` column.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Final

import pandas as pd

from .config import LOCKED_CONFIG

INDICATOR_VERSION: Final[str] = "core-v2.1-indicators-v1"
INDICATOR_SEED_CONVENTION: Final[str] = (
    "RSI21: SMA of first 21 gains/losses then Wilder recursion; "
    "ATR14: SMA of first 14 true ranges (first TR=high-low) then Wilder recursion; "
    "EMA: alpha=2/(n+1), seeded from first finite input; "
    "WMA45: rolling weights 1..45"
)
READINESS_COLUMN: Final[str] = "core_v2_1_ready"
# RSI21 first becomes finite at row 21 and WMA45 needs 45 consecutive
# finite RSI values, so the complete RSI bundle is ready at row 65.
RSI_BUNDLE_MINIMUM_CANDLES: Final[int] = 66
# M15 evaluation also needs the immediately previous complete RSI bundle.
M15_EVALUATION_MINIMUM_CANDLES: Final[int] = RSI_BUNDLE_MINIMUM_CANDLES + 1
M15_INDICATOR_COLUMNS: Final[tuple[str, ...]] = (
    "ema21",
    "ema200",
    "atr14",
    "rsi21",
    "rsi_ema9",
    "rsi_wma45",
)
RSI_INDICATOR_COLUMNS: Final[tuple[str, ...]] = (
    "rsi21",
    "rsi_ema9",
    "rsi_wma45",
)
BTC_H1_INDICATOR_COLUMNS: Final[tuple[str, ...]] = (
    "ema21",
    "rsi21",
    "rsi_ema9",
    "rsi_wma45",
)


def _positive_period(period: int) -> int:
    if not isinstance(period, int) or isinstance(period, bool) or period <= 0:
        raise ValueError("period must be a positive integer")
    return period


def _float_values(series: pd.Series) -> list[float]:
    if not isinstance(series, pd.Series):
        raise TypeError("indicator input must be a pandas Series")
    values: list[float] = []
    for value in series:
        try:
            values.append(float(value))
        except (TypeError, ValueError) as exc:
            raise TypeError("indicator Series must contain numeric values") from exc
    return values


def _series(values: Iterable[float], source: pd.Series, name: str) -> pd.Series:
    return pd.Series(tuple(values), index=source.index, dtype="float64", name=name)


def ema(series: pd.Series, period: int) -> pd.Series:
    """Recursive EMA seeded from the first finite input value.

    A non-finite gap is retained as NaN and resets the seed for the next finite
    segment; it is never replaced by a fabricated value.
    """

    period = _positive_period(period)
    values = _float_values(series)
    alpha = 2.0 / (period + 1.0)
    result = [math.nan] * len(values)
    previous: float | None = None
    for index, value in enumerate(values):
        if not math.isfinite(value):
            previous = None
            continue
        previous = value if previous is None else alpha * value + (1.0 - alpha) * previous
        result[index] = previous
    return _series(result, series, f"ema{period}")


def wma(series: pd.Series, period: int) -> pd.Series:
    """Rolling linearly weighted moving average using weights ``1..period``."""

    period = _positive_period(period)
    values = _float_values(series)
    result = [math.nan] * len(values)
    denominator = period * (period + 1) / 2.0
    for index in range(period - 1, len(values)):
        window = values[index - period + 1 : index + 1]
        if all(math.isfinite(value) for value in window):
            result[index] = sum(
                value * weight for weight, value in enumerate(window, start=1)
            ) / denominator
    return _series(result, series, f"wma{period}")


def _rsi_from_averages(average_gain: float, average_loss: float) -> float:
    if average_gain == 0.0 and average_loss == 0.0:
        return 50.0
    if average_loss == 0.0:
        return 100.0
    if average_gain == 0.0:
        return 0.0
    relative_strength = average_gain / average_loss
    return 100.0 - 100.0 / (1.0 + relative_strength)


def rsi_wilder(series: pd.Series, period: int = 21) -> pd.Series:
    """Traditional Wilder RSI with an SMA seed after ``period`` deltas."""

    period = _positive_period(period)
    values = _float_values(series)
    result = [math.nan] * len(values)
    run_start = 0
    while run_start < len(values):
        while run_start < len(values) and not math.isfinite(values[run_start]):
            run_start += 1
        run_end = run_start
        while run_end < len(values) and math.isfinite(values[run_end]):
            run_end += 1
        if run_end - run_start >= period + 1:
            deltas = [values[index] - values[index - 1] for index in range(run_start + 1, run_end)]
            gains = [max(delta, 0.0) for delta in deltas]
            losses = [max(-delta, 0.0) for delta in deltas]
            average_gain = sum(gains[:period]) / period
            average_loss = sum(losses[:period]) / period
            seed_index = run_start + period
            result[seed_index] = _rsi_from_averages(average_gain, average_loss)
            for index in range(seed_index + 1, run_end):
                delta_index = index - run_start - 1
                average_gain = (
                    average_gain * (period - 1) + gains[delta_index]
                ) / period
                average_loss = (
                    average_loss * (period - 1) + losses[delta_index]
                ) / period
                result[index] = _rsi_from_averages(average_gain, average_loss)
        run_start = run_end + 1
    return _series(result, series, f"rsi{period}")


def atr_wilder(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Traditional Wilder ATR seeded from the first ``period`` true ranges."""

    period = _positive_period(period)
    highs = _float_values(high)
    lows = _float_values(low)
    closes = _float_values(close)
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("high, low, and close Series must have the same length")
    if not high.index.equals(low.index) or not high.index.equals(close.index):
        raise ValueError("high, low, and close Series must have identical indexes")
    true_ranges = [math.nan] * len(highs)
    previous_close: float | None = None
    for index, (high_value, low_value, close_value) in enumerate(
        zip(highs, lows, closes, strict=True)
    ):
        if not all(math.isfinite(value) for value in (high_value, low_value, close_value)):
            previous_close = None
            continue
        if high_value < low_value:
            raise ValueError("high cannot be below low")
        if previous_close is None:
            true_ranges[index] = high_value - low_value
        else:
            true_ranges[index] = max(
                high_value - low_value,
                abs(high_value - previous_close),
                abs(low_value - previous_close),
            )
        previous_close = close_value

    result = [math.nan] * len(true_ranges)
    run_start = 0
    while run_start < len(true_ranges):
        while run_start < len(true_ranges) and not math.isfinite(true_ranges[run_start]):
            run_start += 1
        run_end = run_start
        while run_end < len(true_ranges) and math.isfinite(true_ranges[run_end]):
            run_end += 1
        if run_end - run_start >= period:
            average_true_range = sum(true_ranges[run_start : run_start + period]) / period
            seed_index = run_start + period - 1
            result[seed_index] = average_true_range
            for index in range(seed_index + 1, run_end):
                average_true_range = (
                    average_true_range * (period - 1) + true_ranges[index]
                ) / period
                result[index] = average_true_range
        run_start = run_end + 1
    return _series(result, high, f"atr{period}")


def _copy_numeric_frame(frame: pd.DataFrame, required: tuple[str, ...]) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    missing = set(required).difference(frame.columns)
    if missing:
        raise ValueError(f"missing required OHLC columns: {sorted(missing)}")
    output = frame.copy(deep=True)
    for column in required:
        try:
            output[column] = pd.to_numeric(output[column], errors="raise").astype("float64")
        except (TypeError, ValueError) as exc:
            raise TypeError(f"column {column!r} must be numeric") from exc
        if not output[column].map(math.isfinite).all():
            raise ValueError(f"column {column!r} must contain only finite values")
    return output


def _add_rsi_bundle(output: pd.DataFrame) -> None:
    config = LOCKED_CONFIG
    output["rsi21"] = rsi_wilder(output["close"], config.rsi_period)
    output["rsi_ema9"] = ema(output["rsi21"], config.rsi_fast_ema_period)
    output["rsi_wma45"] = wma(output["rsi21"], config.rsi_slow_wma_period)


def _ready_mask(output: pd.DataFrame, columns: tuple[str, ...]) -> pd.Series:
    if output.empty:
        return pd.Series(index=output.index, dtype="bool", name=READINESS_COLUMN)
    ready = pd.Series(True, index=output.index, dtype="bool")
    for column in columns:
        ready &= output[column].map(math.isfinite)
    if "atr14" in columns:
        ready &= output["atr14"] > 0.0
    ready.name = READINESS_COLUMN
    return ready


def compute_m15_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """Enrich altcoin M15 OHLC data with all locked Core V2.1 indicators."""

    output = _copy_numeric_frame(frame, ("high", "low", "close"))
    config = LOCKED_CONFIG
    output["ema21"] = ema(output["close"], config.price_ema_period)
    output["ema200"] = ema(output["close"], config.trend_ema_period)
    output["atr14"] = atr_wilder(output["high"], output["low"], output["close"], config.atr_period)
    _add_rsi_bundle(output)
    output[READINESS_COLUMN] = _ready_mask(output, M15_INDICATOR_COLUMNS)
    return output


def compute_alt_h1_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """Enrich altcoin H1 closes with the locked RSI bundle."""

    output = _copy_numeric_frame(frame, ("close",))
    _add_rsi_bundle(output)
    output[READINESS_COLUMN] = _ready_mask(output, RSI_INDICATOR_COLUMNS)
    return output


def compute_btc_h1_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """Enrich BTC H1 closes with EMA21 and the locked RSI bundle."""

    output = _copy_numeric_frame(frame, ("close",))
    output["ema21"] = ema(output["close"], LOCKED_CONFIG.price_ema_period)
    _add_rsi_bundle(output)
    output[READINESS_COLUMN] = _ready_mask(output, BTC_H1_INDICATOR_COLUMNS)
    return output


def compute_btc_h4_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """Enrich BTC H4 closes with the strict-alignment RSI bundle."""

    output = _copy_numeric_frame(frame, ("close",))
    _add_rsi_bundle(output)
    output[READINESS_COLUMN] = _ready_mask(output, RSI_INDICATOR_COLUMNS)
    return output
