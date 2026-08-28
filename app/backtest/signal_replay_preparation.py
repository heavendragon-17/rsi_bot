"""Fast, point-in-time preparation for the historical BTC alert replay."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd

from app.backtest.signal_replay_models import ReplayTriggerEvent
from app.trading.strategy.btc_rsi_cross_alert.evaluator import (
    H4_DURATION,
    H4_PRICE_EMA_MINIMUM_ROWS,
    TRIGGER_DURATION_BY_TIMEFRAME,
    TRIGGER_MINIMUM_ROWS,
    candle_close_time,
    expected_h4_close_for,
)
from app.trading.strategy.btc_rsi_cross_alert.m5_checker import (
    M5_TIMEFRAME,
    evaluate_m5_cross,
)
from app.trading.strategy.btc_rsi_cross_alert.m15_checker import (
    M15_TIMEFRAME,
    evaluate_m15_cross,
)
from app.trading.strategy.btc_rsi_cross_alert.models import (
    H4_EXPECTED_CLOSE_MISSING,
    H4_INSUFFICIENT_CONTIGUOUS_HISTORY,
    H4_LIVE_CLOSE_UNCONFIRMED,
    PREPARATION_READY,
    TRIGGER_CURRENT_ROW_MISSING,
    TRIGGER_INSUFFICIENT_CONTIGUOUS_HISTORY,
    TRIGGER_NON_FINITE_DATA,
    BtcRsiCrossDecision,
    BtcRsiCrossInput,
    BtcRsiCrossPreparation,
    RsiBundlePoint,
)
from app.trading.strategy.core_v2_1.indicators import ema, rsi_wilder, wma

RSI_PERIOD = 21
RSI_EMA_PERIOD = 9
RSI_WMA_PERIOD = 45
PRICE_EMA_PERIOD = 21


@dataclass(frozen=True)
class _IndicatorContext:
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


def _build_context(
    frame: pd.DataFrame,
    duration: timedelta,
    *,
    include_rsi: bool,
) -> _IndicatorContext:
    close_times = tuple(candle_close_time(raw_open, duration) for raw_open in frame.index)
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
            rsi_wma45[segment_start:position] = _finite_array(
                wma(rsi_series, RSI_WMA_PERIOD)
            )
        if not at_end:
            segment_start = position

    return _IndicatorContext(
        close_times=close_times,
        close_values=close_values,
        segment_starts=segment_starts,
        index_by_close_time={close_time: position for position, close_time in enumerate(close_times)},
        price_ema21=price_ema21,
        rsi21=rsi21,
        rsi_ema9=rsi_ema9,
        rsi_wma45=rsi_wma45,
    )


def _not_ready(reason: str) -> BtcRsiCrossPreparation:
    return BtcRsiCrossPreparation(input=None, reason=reason)


def _bundle_point(context: _IndicatorContext, position: int) -> RsiBundlePoint | None:
    if context.rsi21 is None or context.rsi_ema9 is None or context.rsi_wma45 is None:
        return None
    values = (
        context.rsi21[position],
        context.rsi_ema9[position],
        context.rsi_wma45[position],
    )
    if not all(math.isfinite(float(value)) for value in values):
        return None
    return RsiBundlePoint(
        rsi21=float(values[0]),
        rsi_ema9=float(values[1]),
        rsi_wma45=float(values[2]),
    )


class ReplayPreparationCache:
    """Precompute replay indicators while preserving evaluator seed rules."""

    def __init__(
        self,
        m5_frame: pd.DataFrame,
        m15_frame: pd.DataFrame,
        h4_frame: pd.DataFrame,
        *,
        history_ready_at: datetime,
        observed_h4_closes: frozenset[datetime],
    ) -> None:
        self._m5 = _build_context(
            m5_frame,
            TRIGGER_DURATION_BY_TIMEFRAME[M5_TIMEFRAME],
            include_rsi=True,
        )
        self._m15 = _build_context(
            m15_frame,
            TRIGGER_DURATION_BY_TIMEFRAME[M15_TIMEFRAME],
            include_rsi=True,
        )
        self._h4 = _build_context(h4_frame, H4_DURATION, include_rsi=False)
        self._history_ready_at = history_ready_at.astimezone(UTC)
        self._observed_h4_closes = observed_h4_closes

    @property
    def warmup_ready_at_by_timeframe(self) -> dict[str, datetime | None]:
        h4_ready = self._h4.earliest_ready_close(H4_PRICE_EMA_MINIMUM_ROWS)
        readiness: dict[str, datetime | None] = {}
        for timeframe, context in (
            (M5_TIMEFRAME, self._m5),
            (M15_TIMEFRAME, self._m15),
        ):
            trigger_ready = context.earliest_ready_close(TRIGGER_MINIMUM_ROWS)
            readiness[timeframe] = (
                max(trigger_ready, h4_ready)
                if trigger_ready is not None and h4_ready is not None
                else None
            )
        return readiness

    def _trigger_context(self, timeframe: str) -> _IndicatorContext:
        return self._m5 if timeframe == M5_TIMEFRAME else self._m15

    def prepare(self, event: ReplayTriggerEvent, *, symbol: str) -> BtcRsiCrossPreparation:
        trigger_context = self._trigger_context(event.timeframe)
        position = trigger_context.index_by_close_time.get(event.close_time)
        if position is None:
            return _not_ready(TRIGGER_CURRENT_ROW_MISSING)

        if not trigger_context.has_contiguous_history(position, TRIGGER_MINIMUM_ROWS):
            return _not_ready(TRIGGER_INSUFFICIENT_CONTIGUOUS_HISTORY)

        previous_position = position - 1
        if previous_position < 0 or (
            trigger_context.close_times[position]
            - trigger_context.close_times[previous_position]
            != TRIGGER_DURATION_BY_TIMEFRAME[event.timeframe]
        ):
            return _not_ready(TRIGGER_INSUFFICIENT_CONTIGUOUS_HISTORY)

        current_trigger = _bundle_point(trigger_context, position)
        previous_trigger = _bundle_point(trigger_context, previous_position)
        trigger_price_ema21 = trigger_context.price_ema21[position]
        if current_trigger is None or previous_trigger is None or not math.isfinite(trigger_price_ema21):
            return _not_ready(TRIGGER_NON_FINITE_DATA)

        expected_h4_close = expected_h4_close_for(event.close_time)
        h4_position = self._h4.index_by_close_time.get(expected_h4_close)
        if h4_position is None:
            return _not_ready(H4_EXPECTED_CLOSE_MISSING)
        if (
            expected_h4_close > self._history_ready_at
            and expected_h4_close not in self._observed_h4_closes
        ):
            return _not_ready(H4_LIVE_CLOSE_UNCONFIRMED)
        if not self._h4.has_contiguous_history(h4_position, H4_PRICE_EMA_MINIMUM_ROWS):
            return _not_ready(H4_INSUFFICIENT_CONTIGUOUS_HISTORY)

        h4_price_ema21 = self._h4.price_ema21[h4_position]
        if not math.isfinite(h4_price_ema21):
            return _not_ready(H4_INSUFFICIENT_CONTIGUOUS_HISTORY)

        prepared_input = BtcRsiCrossInput(
            symbol=symbol,
            trigger_timeframe=event.timeframe,
            trigger_close_time=event.close_time,
            trigger_close_price=Decimal(str(trigger_context.close_values[position])),
            trigger_price_ema21=Decimal(str(trigger_price_ema21)),
            previous_trigger=previous_trigger,
            current_trigger=current_trigger,
            h4_close_price=Decimal(str(self._h4.close_values[h4_position])),
            h4_price_ema21=Decimal(str(h4_price_ema21)),
            h4_close_time=expected_h4_close,
        )
        return BtcRsiCrossPreparation(input=prepared_input, reason=PREPARATION_READY)

    def prepare_and_evaluate(
        self,
        event: ReplayTriggerEvent,
        *,
        symbol: str,
    ) -> tuple[BtcRsiCrossInput | None, BtcRsiCrossDecision | None, str]:
        preparation = self.prepare(event, symbol=symbol)
        if preparation.input is None:
            return None, None, preparation.reason
        if event.timeframe == M5_TIMEFRAME:
            decision = evaluate_m5_cross(preparation.input)
        else:
            decision = evaluate_m15_cross(preparation.input)
        return preparation.input, decision, preparation.reason
