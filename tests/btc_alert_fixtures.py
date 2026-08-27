"""Shared deterministic synthetic-candle builders for BTC RSI cross alert
tests. Not collected by pytest (module name does not match ``test_*``)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd

from app.core.events import Candle
from app.trading.strategy.core_v2_1.indicators import ema, rsi_wilder, wma

UTC = UTC
STORAGE_SHIFT = timedelta(hours=7)
SYMBOL = "BTC/USDT"

BASE = datetime(2026, 8, 24, tzinfo=UTC)
READY_AT = BASE.replace(hour=9)


def storage_open(close_time: datetime, step: timedelta) -> datetime:
    """Naive UTC+07 wall-clock representation of the candle open."""
    return (close_time - step + STORAGE_SHIFT).replace(tzinfo=None)


def make_candle(
    close_time: datetime, step: timedelta, close: float, *, closed: bool = True
) -> Candle:
    return Candle(
        symbol="BTC",
        timestamp=storage_open(close_time, step),
        open=Decimal(str(close)),
        high=Decimal(str(close)),
        low=Decimal(str(close)),
        close=Decimal(str(close)),
        volume=Decimal("1"),
        closed=closed,
    )


def cross_closes(rise_rows: int = 70) -> list[float]:
    """Alternating ±1 head (RSI ~50) then sustained +3 rise — the RSI climb
    produces a fresh EMA9/WMA45-of-RSI upward cross early in the rise."""
    head = [100.0 + (1.0 if i % 2 == 0 else -1.0) for i in range(80)]
    rise = [head[-1] + 3.0 * (i + 1) for i in range(rise_rows)]
    return head + rise


def last_cross_index(closes: list[float], min_index: int = 67) -> int | None:
    series = pd.Series(closes, dtype="float64")
    rsi21 = rsi_wilder(series, 21)
    ema9 = ema(rsi21, 9)
    wma45 = wma(rsi21, 45)
    cross = None
    for i in range(min_index, len(closes)):
        if (
            float(ema9.iloc[i - 1]) <= float(wma45.iloc[i - 1])
            and float(ema9.iloc[i]) > float(wma45.iloc[i])
        ):
            cross = i
    return cross


def qualifying_trigger(step: timedelta, end: datetime, rise_rows: int = 70):
    """Close times + closes trimmed so the FINAL row is the fresh-cross row."""
    closes = cross_closes(rise_rows=rise_rows)
    cross = last_cross_index(closes)
    assert cross is not None, "fixture produced no qualifying cross"
    closes = closes[: cross + 1]
    count = len(closes)
    close_times = [end - step * (count - 1 - i) for i in range(count)]
    return close_times, closes


def qualifying_m5_trigger(step: timedelta, end: datetime):
    """M5 bullish alignment that passes every mandatory M5 filter."""

    head = [100.0 + (1.0 if i % 2 == 0 else -1.0) for i in range(80)]
    closes = head + [head[-1] + 30.0, head[-1] + 40.0]
    series = pd.Series(closes, dtype="float64")
    rsi21 = rsi_wilder(series, 21)
    ema9 = ema(rsi21, 9)
    wma45 = wma(rsi21, 45)
    price_ema21 = ema(series, 21)

    assert float(ema9.iloc[-2]) > float(wma45.iloc[-2])
    assert float(rsi21.iloc[-1]) > float(ema9.iloc[-1])
    assert float(ema9.iloc[-1]) - float(wma45.iloc[-1]) > 2.0
    assert float(wma45.iloc[-1]) > 45.0
    assert closes[-1] > float(price_ema21.iloc[-1])

    count = len(closes)
    close_times = [end - step * (count - 1 - i) for i in range(count)]
    return close_times, closes


def h4_price_above_ema21_closes(count: int = 70) -> list[float]:
    """H4 closes whose final close is strictly above EMA21(price)."""
    decline = [90.0 - 0.4 * i for i in range(25)]
    rise = [decline[-1] + 2.0 * (i + 1) for i in range(count - 25)]
    return decline + rise


def assert_h4_close_above_ema21(closes: list[float]) -> None:
    series = pd.Series(closes, dtype="float64")
    price_ema21 = float(ema(series, 21).iloc[-1])
    assert closes[-1] > price_ema21


def h4_close_times(end: datetime, count: int = 70) -> list[datetime]:
    return [end - timedelta(hours=4) * (count - 1 - i) for i in range(count)]
