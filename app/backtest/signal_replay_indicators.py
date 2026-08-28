"""Indicator contexts used by the historical BTC alert replay."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from app.trading.strategy.btc_rsi_cross_alert.evaluator import candle_close_time
from app.trading.strategy.btc_rsi_cross_alert.models import RsiBundlePoint
from app.trading.strategy.core_v2_1.indicators import ema, rsi_wilder

RSI_PERIOD = 21
RSI_EMA_PERIOD = 9
RSI_WMA_PERIOD = 45
PRICE_EMA_PERIOD = 21


@dataclass(frozen=True)
class _IndicatorContext:
    close_index: pd.DatetimeIndex
    close_times: tuple[datetime, ...]
    close_values: np.ndarray
    segment_starts: np.ndarray
    index_by_close_time: dict[datetime, int]
    price_ema21: np.ndarray
    rsi21: np.ndarray | None = None
    rsi_ema9: np.ndarray | None = None
    rsi_wma45: np.ndarray | None = None

    def earliest_ready_close(self, minimum_rows: int) -> datetime | None:
        for position, segment_start in enumerate(self.segment_starts):
            if position - int(segment_start) + 1 >= minimum_rows:
                return self.close_times[position]
        return None

    def has_contiguous_history(self, position: int, minimum_rows: int) -> bool:
        return position - int(self.segment_starts[position]) + 1 >= minimum_rows


def _segment_starts(
    close_times: tuple[datetime, ...],
    duration: timedelta,
) -> np.ndarray:
    starts = np.zeros(len(close_times), dtype=np.int64)
    current_start = 0
    for position in range(1, len(close_times)):
        if close_times[position] - close_times[position - 1] != duration:
            current_start = position
        starts[position] = current_start
    return starts


def _finite_array(series: pd.Series) -> np.ndarray:
    return series.to_numpy(dtype="float64", na_value=np.nan)


def _close_index(frame: pd.DataFrame, duration: timedelta) -> pd.DatetimeIndex:
    index = pd.DatetimeIndex(frame.index)
    if index.tz is None:
        return pd.DatetimeIndex(
            candle_close_time(raw_open, duration) for raw_open in frame.index
        )
    return index.tz_convert(UTC) + duration


def _fast_wma(values: np.ndarray, period: int) -> np.ndarray:
    """Vectorized WMA used only to find a safe superset of signal candidates."""

    result = np.full(len(values), np.nan, dtype="float64")
    if len(values) < period:
        return result
    weights = np.arange(1.0, period + 1.0, dtype="float64")
    denominator = period * (period + 1) / 2.0
    result[period - 1 :] = np.correlate(values, weights, mode="valid") / denominator
    return result


def _build_context(
    frame: pd.DataFrame,
    duration: timedelta,
    *,
    include_rsi: bool,
) -> _IndicatorContext:
    close_index = _close_index(frame, duration)
    close_times = tuple(value.to_pydatetime() for value in close_index)
    close_values = frame["close"].to_numpy(dtype="float64")
    segment_starts = _segment_starts(close_times, duration)
    price_ema21 = np.full(len(frame), np.nan, dtype="float64")
    rsi21 = np.full(len(frame), np.nan, dtype="float64") if include_rsi else None
    rsi_ema9 = np.full(len(frame), np.nan, dtype="float64") if include_rsi else None
    rsi_wma45 = np.full(len(frame), np.nan, dtype="float64") if include_rsi else None

    segment_start = 0
    for position in range(1, len(close_times) + 1):
        at_end = position == len(close_times)
        has_gap = not at_end and segment_starts[position] != segment_start
        if not at_end and not has_gap:
            continue

        closes = pd.Series(close_values[segment_start:position], dtype="float64")
        price_ema21[segment_start:position] = _finite_array(ema(closes, PRICE_EMA_PERIOD))
        if include_rsi:
            assert rsi21 is not None
            assert rsi_ema9 is not None
            assert rsi_wma45 is not None
            rsi_series = rsi_wilder(closes, RSI_PERIOD)
            rsi21[segment_start:position] = _finite_array(rsi_series)
            rsi_ema9[segment_start:position] = _finite_array(
                ema(rsi_series, RSI_EMA_PERIOD)
            )
            rsi_wma45[segment_start:position] = _fast_wma(
                _finite_array(rsi_series), RSI_WMA_PERIOD
            )
        if not at_end:
            segment_start = position

    return _IndicatorContext(
        close_index=close_index,
        close_times=close_times,
        close_values=close_values,
        segment_starts=segment_starts,
        index_by_close_time={close_time: position for position, close_time in enumerate(close_times)},
        price_ema21=price_ema21,
        rsi21=rsi21,
        rsi_ema9=rsi_ema9,
        rsi_wma45=rsi_wma45,
    )


def _bundle_point(context: _IndicatorContext, position: int) -> RsiBundlePoint | None:
    if context.rsi21 is None or context.rsi_ema9 is None or context.rsi_wma45 is None:
        return None
    start = position - RSI_WMA_PERIOD + 1
    if start < int(context.segment_starts[position]):
        return None
    rsi_window = context.rsi21[start : position + 1]
    if len(rsi_window) != RSI_WMA_PERIOD or not np.isfinite(rsi_window).all():
        return None
    denominator = RSI_WMA_PERIOD * (RSI_WMA_PERIOD + 1) / 2.0
    exact_wma = sum(
        float(value) * weight for weight, value in enumerate(rsi_window, start=1)
    ) / denominator
    values = (context.rsi21[position], context.rsi_ema9[position], exact_wma)
    if not all(math.isfinite(float(value)) for value in values):
        return None
    return RsiBundlePoint(
        rsi21=float(values[0]),
        rsi_ema9=float(values[1]),
        rsi_wma45=float(values[2]),
    )
