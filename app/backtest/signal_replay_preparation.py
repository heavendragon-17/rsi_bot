"""Fast, point-in-time preparation for the historical BTC alert replay."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pandas as pd

from app.backtest.signal_replay_indicators import (
    _build_context,
    _bundle_point,
    _IndicatorContext,
)
from app.backtest.signal_replay_indicators import (
    _fast_wma as _indicator_fast_wma,
)
from app.backtest.signal_replay_models import ReplayTriggerEvent
from app.trading.strategy.btc_rsi_cross_alert.evaluator import (
    H1_DURATION,
    H1_PRICE_EMA_MINIMUM_ROWS,
    H4_DURATION,
    H4_PRICE_EMA_MINIMUM_ROWS,
    TRIGGER_DURATION_BY_TIMEFRAME,
    TRIGGER_MINIMUM_ROWS,
    expected_h1_close_for,
    expected_h4_close_for,
)
from app.trading.strategy.btc_rsi_cross_alert.m5_checker import (
    M5_MAX_RSI21_EXCLUSIVE,
    M5_MIN_RSI_EMA_WMA_SPREAD,
    M5_MIN_RSI_WMA45,
    M5_TIMEFRAME,
    evaluate_m5_cross,
)
from app.trading.strategy.btc_rsi_cross_alert.m15_checker import (
    M15_TIMEFRAME,
    evaluate_m15_cross,
)
from app.trading.strategy.btc_rsi_cross_alert.models import (
    H1_EXPECTED_CLOSE_MISSING,
    H1_INSUFFICIENT_CONTIGUOUS_HISTORY,
    H1_LIVE_CLOSE_UNCONFIRMED,
    H1_NON_FINITE_DATA,
    H4_EXPECTED_CLOSE_MISSING,
    H4_INSUFFICIENT_CONTIGUOUS_HISTORY,
    H4_LIVE_CLOSE_UNCONFIRMED,
    H4_NON_FINITE_DATA,
    PREPARATION_READY,
    TRIGGER_CURRENT_ROW_MISSING,
    TRIGGER_INSUFFICIENT_CONTIGUOUS_HISTORY,
    TRIGGER_NON_FINITE_DATA,
    BtcRsiCrossDecision,
    BtcRsiCrossInput,
    BtcRsiCrossPreparation,
)

PREFILTER_TOLERANCE = 1e-10


def _fast_wma(values: np.ndarray, period: int) -> np.ndarray:
    """Keep the vectorized WMA helper available to replay-focused tests."""

    return _indicator_fast_wma(values, period)


def _not_ready(reason: str) -> BtcRsiCrossPreparation:
    return BtcRsiCrossPreparation(input=None, reason=reason)


class ReplayPreparationCache:
    """Precompute replay indicators while preserving evaluator seed rules."""

    def __init__(
        self,
        m5_frame: pd.DataFrame,
        m15_frame: pd.DataFrame,
        h4_frame: pd.DataFrame,
        h1_frame: pd.DataFrame,
        *,
        history_ready_at: datetime,
        observed_h1_closes: frozenset[datetime],
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
        self._h1 = _build_context(h1_frame, H1_DURATION, include_rsi=False)
        self._h4 = _build_context(h4_frame, H4_DURATION, include_rsi=False)
        self._history_ready_at = history_ready_at.astimezone(UTC)
        self._observed_h1_closes = observed_h1_closes
        self._observed_h4_closes = observed_h4_closes
        self._h1_positions_by_timeframe = {
            timeframe: self._h1.close_index.get_indexer(context.close_index.floor("1h"))
            for timeframe, context in (
                (M5_TIMEFRAME, self._m5),
                (M15_TIMEFRAME, self._m15),
            )
        }
        self._h4_positions_by_timeframe = {
            timeframe: self._h4.close_index.get_indexer(context.close_index.floor("4h"))
            for timeframe, context in (
                (M5_TIMEFRAME, self._m5),
                (M15_TIMEFRAME, self._m15),
            )
        }
        self._h4_confirmed = np.fromiter(
            (
                close_time <= self._history_ready_at
                or close_time in self._observed_h4_closes
                for close_time in self._h4.close_times
            ),
            dtype=np.bool_,
            count=len(self._h4.close_times),
        )
        self._h1_confirmed = np.fromiter(
            (
                close_time <= self._history_ready_at
                or close_time in self._observed_h1_closes
                for close_time in self._h1.close_times
            ),
            dtype=np.bool_,
            count=len(self._h1.close_times),
        )

    @property
    def warmup_ready_at_by_timeframe(self) -> dict[str, datetime | None]:
        h4_ready = self._h4.earliest_ready_close(H4_PRICE_EMA_MINIMUM_ROWS)
        h1_ready = self._h1.earliest_ready_close(H1_PRICE_EMA_MINIMUM_ROWS)
        readiness: dict[str, datetime | None] = {}
        for timeframe, context in (
            (M5_TIMEFRAME, self._m5),
            (M15_TIMEFRAME, self._m15),
        ):
            trigger_ready = context.earliest_ready_close(TRIGGER_MINIMUM_ROWS)
            readiness[timeframe] = (
                max(trigger_ready, h1_ready, h4_ready)
                if (
                    trigger_ready is not None
                    and h1_ready is not None
                    and h4_ready is not None
                )
                else None
            )
        return readiness

    def _trigger_context(self, timeframe: str) -> _IndicatorContext:
        return self._m5 if timeframe == M5_TIMEFRAME else self._m15

    def _event_position(
        self,
        event: ReplayTriggerEvent,
        context: _IndicatorContext,
    ) -> tuple[int | None, bool]:
        position = event.position
        if (
            position is not None
            and 0 <= position < len(context.close_times)
            and context.close_times[position] == event.close_time
        ):
            return position, True
        return context.index_by_close_time.get(event.close_time), False

    def _positions_for_event(
        self,
        event: ReplayTriggerEvent,
    ) -> tuple[int | None, int | None, int | None, str]:
        trigger_context = self._trigger_context(event.timeframe)
        position, direct_position = self._event_position(event, trigger_context)
        if position is None:
            return None, None, None, TRIGGER_CURRENT_ROW_MISSING

        if not trigger_context.has_contiguous_history(position, TRIGGER_MINIMUM_ROWS):
            return None, None, None, TRIGGER_INSUFFICIENT_CONTIGUOUS_HISTORY

        previous_position = position - 1
        if previous_position < 0 or (
            trigger_context.close_times[position]
            - trigger_context.close_times[previous_position]
            != TRIGGER_DURATION_BY_TIMEFRAME[event.timeframe]
        ):
            return None, None, None, TRIGGER_INSUFFICIENT_CONTIGUOUS_HISTORY

        assert trigger_context.rsi21 is not None
        assert trigger_context.rsi_ema9 is not None
        assert trigger_context.rsi_wma45 is not None
        trigger_values = (
            trigger_context.rsi21[position],
            trigger_context.rsi_ema9[position],
            trigger_context.rsi_wma45[position],
            trigger_context.rsi21[previous_position],
            trigger_context.rsi_ema9[previous_position],
            trigger_context.rsi_wma45[previous_position],
            trigger_context.price_ema21[position],
        )
        trigger_start = int(trigger_context.segment_starts[position])
        if not np.isfinite(
            trigger_context.close_values[trigger_start : position + 1]
        ).all() or not all(math.isfinite(float(value)) for value in trigger_values):
            return None, None, None, TRIGGER_NON_FINITE_DATA

        if direct_position:
            h1_position = int(
                self._h1_positions_by_timeframe[event.timeframe][position]
            )
        else:
            expected_h1_close = expected_h1_close_for(event.close_time)
            h1_position = self._h1.index_by_close_time.get(expected_h1_close, -1)
        if h1_position < 0:
            return None, None, None, H1_EXPECTED_CLOSE_MISSING
        if not self._h1_confirmed[h1_position]:
            return None, None, None, H1_LIVE_CLOSE_UNCONFIRMED
        if not self._h1.has_contiguous_history(
            h1_position, H1_PRICE_EMA_MINIMUM_ROWS
        ):
            return None, None, None, H1_INSUFFICIENT_CONTIGUOUS_HISTORY
        h1_start = int(self._h1.segment_starts[h1_position])
        if not np.isfinite(self._h1.close_values[h1_start : h1_position + 1]).all():
            return None, None, None, H1_NON_FINITE_DATA
        if not math.isfinite(float(self._h1.price_ema21[h1_position])):
            return None, None, None, H1_NON_FINITE_DATA

        if direct_position:
            h4_position = int(
                self._h4_positions_by_timeframe[event.timeframe][position]
            )
        else:
            expected_h4_close = expected_h4_close_for(event.close_time)
            h4_position = self._h4.index_by_close_time.get(expected_h4_close, -1)
        if h4_position < 0:
            return None, None, None, H4_EXPECTED_CLOSE_MISSING
        if not self._h4_confirmed[h4_position]:
            return None, None, None, H4_LIVE_CLOSE_UNCONFIRMED
        if not self._h4.has_contiguous_history(
            h4_position, H4_PRICE_EMA_MINIMUM_ROWS
        ):
            return None, None, None, H4_INSUFFICIENT_CONTIGUOUS_HISTORY
        h4_start = int(self._h4.segment_starts[h4_position])
        if not np.isfinite(self._h4.close_values[h4_start : h4_position + 1]).all():
            return None, None, None, H4_NON_FINITE_DATA
        if not math.isfinite(float(self._h4.price_ema21[h4_position])):
            return None, None, None, H4_NON_FINITE_DATA
        return position, h1_position, h4_position, PREPARATION_READY

    def scan(self, event: ReplayTriggerEvent) -> tuple[bool | None, str]:
        """Return a safe signal-candidate superset without domain allocations."""

        position, h1_position, h4_position, reason = self._positions_for_event(event)
        if position is None or h1_position is None or h4_position is None:
            return None, reason

        context = self._trigger_context(event.timeframe)
        assert context.rsi21 is not None
        assert context.rsi_ema9 is not None
        assert context.rsi_wma45 is not None
        previous_position = position - 1
        current_rsi = context.rsi21[position]
        current_ema = context.rsi_ema9[position]
        current_wma = context.rsi_wma45[position]
        h4_bullish = (
            self._h4.close_values[h4_position]
            > self._h4.price_ema21[h4_position]
        )
        h1_bullish = (
            self._h1.close_values[h1_position]
            > self._h1.price_ema21[h1_position]
        )
        price_bullish = context.close_values[position] > context.price_ema21[position]

        if event.timeframe == M5_TIMEFRAME:
            candidate = (
                current_rsi > current_ema
                and current_ema > current_wma - PREFILTER_TOLERANCE
                and h4_bullish
                and h1_bullish
                and current_rsi
                < M5_MAX_RSI21_EXCLUSIVE + PREFILTER_TOLERANCE
                and current_ema - current_wma
                >= M5_MIN_RSI_EMA_WMA_SPREAD - PREFILTER_TOLERANCE
                and current_wma > M5_MIN_RSI_WMA45 - PREFILTER_TOLERANCE
                and price_bullish
            )
        else:
            previous_ema = context.rsi_ema9[previous_position]
            previous_wma = context.rsi_wma45[previous_position]
            candidate = (
                previous_ema <= previous_wma + PREFILTER_TOLERANCE
                and current_ema > current_wma - PREFILTER_TOLERANCE
                and h4_bullish
                and h1_bullish
                and price_bullish
            )
        return bool(candidate), PREPARATION_READY

    def prepare(self, event: ReplayTriggerEvent, *, symbol: str) -> BtcRsiCrossPreparation:
        trigger_context = self._trigger_context(event.timeframe)
        position, h1_position, h4_position, reason = self._positions_for_event(event)
        if position is None or h1_position is None or h4_position is None:
            return _not_ready(reason)

        previous_position = position - 1
        current_trigger = _bundle_point(trigger_context, position)
        previous_trigger = _bundle_point(trigger_context, previous_position)
        trigger_price_ema21 = trigger_context.price_ema21[position]
        if current_trigger is None or previous_trigger is None or not math.isfinite(trigger_price_ema21):
            return _not_ready(TRIGGER_NON_FINITE_DATA)

        h4_price_ema21 = self._h4.price_ema21[h4_position]

        prepared_input = BtcRsiCrossInput(
            symbol=symbol,
            trigger_timeframe=event.timeframe,
            trigger_close_time=event.close_time,
            trigger_close_price=Decimal(str(trigger_context.close_values[position])),
            trigger_price_ema21=Decimal(str(trigger_price_ema21)),
            previous_trigger=previous_trigger,
            current_trigger=current_trigger,
            h1_close_price=Decimal(str(self._h1.close_values[h1_position])),
            h1_price_ema21=Decimal(str(self._h1.price_ema21[h1_position])),
            h1_close_time=self._h1.close_times[h1_position],
            h4_close_price=Decimal(str(self._h4.close_values[h4_position])),
            h4_price_ema21=Decimal(str(h4_price_ema21)),
            h4_close_time=self._h4.close_times[h4_position],
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
