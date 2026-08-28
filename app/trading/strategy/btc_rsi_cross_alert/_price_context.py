"""Point-in-time native H1/H4 price-context preparation helpers."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd

from app.trading.strategy.core_v2_1.indicators import ema


@dataclass(frozen=True)
class PriceContext:
    """One fully prepared native price-EMA context row."""

    close_price: Decimal
    price_ema21: Decimal
    close_time: datetime


def prepare_price_context(
    frame: pd.DataFrame,
    *,
    duration: timedelta,
    expected_close: datetime,
    as_of: datetime,
    history_ready_at: datetime,
    observed_live_closes: frozenset[datetime],
    minimum_rows: int,
    duplicate_reason: str,
    expected_missing_reason: str,
    live_unconfirmed_reason: str,
    insufficient_reason: str,
    non_finite_reason: str,
    frame_columns: Callable[[pd.DataFrame], tuple[list[datetime], list[bool], list[Any]]],
    strictly_increasing: Callable[[list[datetime]], bool],
    suffix_start: Callable[[list[datetime], timedelta], int],
    finite_closes: Callable[[list[Any]], list[float] | None],
    close_price_decimal: Callable[[list[Any], list[Any] | None, int], Decimal],
) -> PriceContext | str:
    """Prepare one native price-EMA context frame at a trigger close."""

    opens, closed_flags, closes = frame_columns(frame)
    all_times = [open_time + duration for open_time in opens]
    if not strictly_increasing(all_times):
        return duplicate_reason

    kept = [
        position
        for position, close_time in enumerate(all_times)
        if closed_flags[position] and close_time <= as_of
    ]
    kept_times = [all_times[position] for position in kept]
    if not kept_times or kept_times[-1] != expected_close:
        return expected_missing_reason

    selected_offset = next(
        (offset for offset, close_time in enumerate(kept_times) if close_time == expected_close),
        None,
    )
    if selected_offset is None:
        return expected_missing_reason
    if expected_close > history_ready_at and expected_close not in observed_live_closes:
        return live_unconfirmed_reason

    contiguous_start = suffix_start(kept_times, duration)
    if len(kept_times) - contiguous_start < minimum_rows:
        return insufficient_reason

    suffix_closes = finite_closes(
        [closes[position] for position in kept[contiguous_start:]]
    )
    if suffix_closes is None:
        return non_finite_reason

    price_ema21_series = ema(pd.Series(tuple(suffix_closes), dtype="float64"), 21)
    price_ema21_value = float(price_ema21_series.iloc[-1])
    if not math.isfinite(price_ema21_value):
        return non_finite_reason

    close_dec_series = list(frame["close_dec"]) if "close_dec" in frame.columns else None
    return PriceContext(
        close_price=close_price_decimal(closes, close_dec_series, kept[selected_offset]),
        price_ema21=Decimal(str(price_ema21_value)),
        close_time=expected_close,
    )
