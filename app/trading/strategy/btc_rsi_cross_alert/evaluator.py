"""Pure indicator preparation and signal decision for the BTC RSI cross alert.

Two pure functions (spec §10):

* :func:`prepare_btc_rsi_cross_input` — timestamp normalization, point-in-time
  slicing, bootstrap eligibility, continuity, finite-value checks, recursive
  indicator preparation over the maximal contiguous suffix, exact current
  trigger selection, and exact H1/H4 context selection.
* :func:`evaluate_btc_rsi_cross` — only the fresh-cross / H1/H4 price decision.

Both are deterministic: identical inputs produce identical outputs with no
clock, network, filesystem, database, logging, Telegram, sleep, thread, or
mutable-global access. The worker obtains wall-clock times and the live H4
confirmation set, then passes immutable values in.

Indicator primitives are imported unchanged from Core V2.1
(``rsi_wilder``, ``ema``, ``wma``); this module never re-implements them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Final, cast

import pandas as pd

from app.trading.strategy.btc_rsi_cross_alert.models import (
    DECISION_ALERT_FRESH_BULLISH_CROSS_H4_BULLISH,
    DECISION_H1_CLOSE_NOT_ABOVE_EMA21,
    DECISION_H4_CLOSE_NOT_ABOVE_EMA21,
    DECISION_NO_FRESH_BULLISH_CROSS,
    H1_DUPLICATE_OR_NON_INCREASING_TIME,
    H1_EXPECTED_CLOSE_MISSING,
    H1_INSUFFICIENT_CONTIGUOUS_HISTORY,
    H1_LIVE_CLOSE_UNCONFIRMED,
    H1_NON_FINITE_DATA,
    H4_DUPLICATE_OR_NON_INCREASING_TIME,
    H4_EXPECTED_CLOSE_MISSING,
    H4_INSUFFICIENT_CONTIGUOUS_HISTORY,
    H4_LIVE_CLOSE_UNCONFIRMED,
    H4_NON_FINITE_DATA,
    PREPARATION_READY,
    TRIGGER_CURRENT_ROW_MISSING,
    TRIGGER_DUPLICATE_OR_NON_INCREASING_TIME,
    TRIGGER_INSUFFICIENT_CONTIGUOUS_HISTORY,
    TRIGGER_NON_FINITE_DATA,
    TRIGGER_UNSUPPORTED_TIMEFRAME,
    BtcRsiCrossDecision,
    BtcRsiCrossInput,
    BtcRsiCrossPreparation,
    RsiBundlePoint,
    build_event_id,
)
from app.trading.strategy.core_v2_1.indicators import ema, rsi_wilder, wma

UTC: Final[timezone] = UTC

#: DataNormalizer stores candle opens as timezone-naive fixed UTC+07:00.
STORAGE_TZ: Final[timezone] = timezone(timedelta(hours=7))

TRIGGER_DURATION_BY_TIMEFRAME: Final[dict[str, timedelta]] = {
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
}
H4_DURATION: Final[timedelta] = timedelta(hours=4)
H1_DURATION: Final[timedelta] = timedelta(hours=1)

RSI_PERIOD: Final[int] = 21
RSI_EMA_PERIOD: Final[int] = 9
RSI_WMA_PERIOD: Final[int] = 45
PRICE_EMA_PERIOD: Final[int] = 21
H4_PRICE_EMA_MINIMUM_ROWS: Final[int] = PRICE_EMA_PERIOD
H1_PRICE_EMA_MINIMUM_ROWS: Final[int] = PRICE_EMA_PERIOD

#: RSI21 first becomes finite at row 21; WMA45 needs 45 consecutive finite RSI
#: values, so the complete bundle is finite at row 65 (0-based) — 66 rows.
RSI_BUNDLE_MINIMUM_ROWS: Final[int] = 66
#: Trigger evaluation also needs the immediately previous complete bundle.
TRIGGER_MINIMUM_ROWS: Final[int] = RSI_BUNDLE_MINIMUM_ROWS + 1

#: Preparation reasons that mean "the exact H1/H4 context for this shared
#: boundary may still arrive" and therefore justify the single settle retry.
RETRYABLE_PREPARATION_REASONS: Final[frozenset[str]] = frozenset(
    {
        H4_EXPECTED_CLOSE_MISSING,
        H4_LIVE_CLOSE_UNCONFIRMED,
        H1_EXPECTED_CLOSE_MISSING,
        H1_LIVE_CLOSE_UNCONFIRMED,
    }
)


# ---------------------------------------------------------------------------
# Timestamp normalization (spec §7 exact algorithm)
# ---------------------------------------------------------------------------
def normalize_candle_open(index_value: object) -> datetime:
    """Normalize one stored candle-open index value to an aware UTC instant.

    1. Parse as a pandas/Python datetime.
    2. Timezone-naive → interpreted as fixed UTC+07:00 (DataNormalizer's
       storage convention).
    3. Already timezone-aware → its represented instant is preserved.
    4. Convert to UTC.

    The close time is obtained by adding the exact timeframe duration to this
    result (never by shifting hours twice).
    """

    ts = pd.Timestamp(index_value)
    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
        ts = ts.tz_localize(STORAGE_TZ)
    else:
        ts = ts.tz_convert(UTC)
    return ts.to_pydatetime().astimezone(UTC)


def candle_close_time(index_value: object, duration: timedelta) -> datetime:
    """Aware UTC close time of the candle whose open ``index_value`` is stored."""

    return normalize_candle_open(index_value) + duration


def _require_aware(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def expected_h4_close_for(trigger_close_time: datetime) -> datetime:
    """Latest native Binance UTC four-hour boundary close at or before ``T``."""

    return _expected_context_close_for(trigger_close_time, H4_DURATION)


def expected_h1_close_for(trigger_close_time: datetime) -> datetime:
    """Latest native Binance UTC one-hour boundary close at or before ``T``."""

    return _expected_context_close_for(trigger_close_time, H1_DURATION)


def _expected_context_close_for(
    trigger_close_time: datetime, duration: timedelta
) -> datetime:
    t = _require_aware(trigger_close_time, "trigger_close_time")
    seconds = int(duration.total_seconds())
    floored = (int(t.timestamp()) // seconds) * seconds
    return datetime.fromtimestamp(floored, tz=UTC)


def timeframe_duration(timeframe: str) -> timedelta | None:
    """Exact duration for a supported trigger timeframe, else ``None``."""

    return TRIGGER_DURATION_BY_TIMEFRAME.get(timeframe)


# ---------------------------------------------------------------------------
# Frame scanning helpers (pure list math — no pandas version pitfalls)
# ---------------------------------------------------------------------------
def _frame_columns(frame: pd.DataFrame) -> tuple[list[datetime], list[bool], list[object]]:
    opens: list[datetime] = []
    closed_flags: list[bool] = []
    closes: list[object] = []
    if "closed" not in frame.columns:
        raise ValueError("candle frame is missing the 'closed' column")
    if "close" not in frame.columns:
        raise ValueError("candle frame is missing the 'close' column")
    closed_series = frame["closed"]
    close_series = frame["close"]
    for position, index_value in enumerate(frame.index):
        opens.append(normalize_candle_open(index_value))
        closed_flags.append(bool(closed_series.iloc[position]))
        closes.append(close_series.iloc[position])
    return opens, closed_flags, closes


def _strictly_increasing(values: list[datetime]) -> bool:
    return all(b > a for a, b in zip(values, values[1:], strict=False))


def _suffix_start(close_times: list[datetime], step: timedelta) -> int:
    """Start index of the maximal contiguous cadence suffix (spec §8.3)."""

    start = 0
    for i in range(1, len(close_times)):
        if close_times[i] - close_times[i - 1] != step:
            start = i
    return start


def _finite_closes(raw_closes: list[object]) -> list[float] | None:
    values: list[float] = []
    for raw in raw_closes:
        try:
            value = float(cast(Any, raw))
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value):
            return None
        values.append(value)
    return values


def _bundle_points(
    closes: list[float],
) -> tuple[RsiBundlePoint | None, RsiBundlePoint | None]:
    """Current (last row) and previous (second-to-last row) RSI bundle points."""

    series = pd.Series(tuple(closes), dtype="float64")
    rsi21 = rsi_wilder(series, RSI_PERIOD)
    rsi_ema9 = ema(rsi21, RSI_EMA_PERIOD)
    rsi_wma45 = wma(rsi21, RSI_WMA_PERIOD)

    def point_at(position: int) -> RsiBundlePoint | None:
        if position < 0 or position >= len(series):
            return None
        rsi_value = float(rsi21.iloc[position])
        ema_value = float(rsi_ema9.iloc[position])
        wma_value = float(rsi_wma45.iloc[position])
        if not all(math.isfinite(v) for v in (rsi_value, ema_value, wma_value)):
            return None
        return RsiBundlePoint(rsi21=rsi_value, rsi_ema9=ema_value, rsi_wma45=wma_value)

    return point_at(len(closes) - 1), point_at(len(closes) - 2)


def _close_price_decimal(closes_column: list[object], close_dec_column: list[object] | None, position: int) -> Decimal:
    source: object = (
        close_dec_column[position] if close_dec_column is not None else closes_column[position]
    )
    if isinstance(source, Decimal):
        return source
    return Decimal(str(source))


def _not_ready(reason: str) -> BtcRsiCrossPreparation:
    return BtcRsiCrossPreparation(input=None, reason=reason)


@dataclass(frozen=True)
class _PriceContext:
    close_price: Decimal
    price_ema21: Decimal
    close_time: datetime


def _prepare_price_context(
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
) -> _PriceContext | str:
    """Prepare one native price-EMA context frame at a trigger close."""

    opens, closed_flags, closes = _frame_columns(frame)
    all_times = [o + duration for o in opens]
    if not _strictly_increasing(all_times):
        return duplicate_reason

    kept = [
        pos
        for pos in range(len(all_times))
        if closed_flags[pos] and all_times[pos] <= as_of
    ]
    kept_times = [all_times[pos] for pos in kept]
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

    suffix_start = _suffix_start(kept_times, duration)
    if len(kept_times) - suffix_start < minimum_rows:
        return insufficient_reason

    suffix_closes = _finite_closes(
        [closes[pos] for pos in kept[suffix_start:]]
    )
    if suffix_closes is None:
        return non_finite_reason

    price_ema21_series = ema(
        pd.Series(tuple(suffix_closes), dtype="float64"),
        PRICE_EMA_PERIOD,
    )
    price_ema21_value = float(price_ema21_series.iloc[-1])
    if not math.isfinite(price_ema21_value):
        return non_finite_reason

    close_dec_series = list(frame["close_dec"]) if "close_dec" in frame.columns else None
    return _PriceContext(
        close_price=_close_price_decimal(closes, close_dec_series, kept[selected_offset]),
        price_ema21=Decimal(str(price_ema21_value)),
        close_time=expected_close,
    )


# ---------------------------------------------------------------------------
# Preparation (spec §8 window locking + §7 selection rules)
# ---------------------------------------------------------------------------
def prepare_btc_rsi_cross_input(
    trigger_df: pd.DataFrame,
    h4_df: pd.DataFrame,
    *,
    h1_df: pd.DataFrame,
    symbol: str,
    trigger_timeframe: str,
    trigger_open_time: datetime,
    history_ready_at: datetime,
    observed_live_h1_closes: frozenset[datetime],
    observed_live_h4_closes: frozenset[datetime],
) -> BtcRsiCrossPreparation:
    """Build the exact point-in-time evaluation input, failing closed.

    ``history_ready_at`` and every observed context close must be aware
    datetimes; comparisons happen exclusively between aware UTC instants.
    """

    if not all(isinstance(frame, pd.DataFrame) for frame in (trigger_df, h1_df, h4_df)):
        raise TypeError("trigger_df, h1_df, and h4_df must be pandas DataFrames")
    ready_at = _require_aware(history_ready_at, "history_ready_at")
    for observed in observed_live_h1_closes:
        _require_aware(observed, "observed_live_h1_closes element")
    for observed in observed_live_h4_closes:
        _require_aware(observed, "observed_live_h4_closes element")

    duration = TRIGGER_DURATION_BY_TIMEFRAME.get(trigger_timeframe)
    if duration is None:
        return _not_ready(TRIGGER_UNSUPPORTED_TIMEFRAME)

    trigger_open = normalize_candle_open(trigger_open_time)
    trigger_close = trigger_open + duration

    # ---------------- trigger frame ----------------
    trig_opens, trig_closed_flags, trig_closes = _frame_columns(trigger_df)
    trig_all_times = [o + duration for o in trig_opens]
    if not _strictly_increasing(trig_all_times):
        return _not_ready(TRIGGER_DUPLICATE_OR_NON_INCREASING_TIME)

    kept = [
        pos
        for pos in range(len(trig_all_times))
        if trig_closed_flags[pos] and trig_all_times[pos] <= trigger_close
    ]
    kept_times = [trig_all_times[pos] for pos in kept]
    kept_closes = [trig_closes[pos] for pos in kept]

    current_position = None
    for offset, close_time in enumerate(kept_times):
        if close_time == trigger_close:
            current_position = offset
            break
    if current_position is None:
        return _not_ready(TRIGGER_CURRENT_ROW_MISSING)

    # The current row is the maximum allowed close, so it ends the filtered
    # sequence; the contiguous suffix must end exactly there (spec §8.3-8.4).
    if kept_times[-1] != trigger_close:
        return _not_ready(TRIGGER_CURRENT_ROW_MISSING)

    suffix_start = _suffix_start(kept_times, duration)
    suffix_len = len(kept_times) - suffix_start
    if suffix_len < TRIGGER_MINIMUM_ROWS:
        return _not_ready(TRIGGER_INSUFFICIENT_CONTIGUOUS_HISTORY)

    suffix_closes = _finite_closes(kept_closes[suffix_start:])
    if suffix_closes is None:
        return _not_ready(TRIGGER_NON_FINITE_DATA)

    current_trigger, previous_trigger = _bundle_points(suffix_closes)
    if current_trigger is None or previous_trigger is None:
        return _not_ready(TRIGGER_NON_FINITE_DATA)

    close_dec_series = (
        list(trigger_df["close_dec"]) if "close_dec" in trigger_df.columns else None
    )
    trigger_close_price = _close_price_decimal(
        trig_closes, close_dec_series, kept[current_position]
    )
    price_ema21_series = ema(
        pd.Series(tuple(suffix_closes), dtype="float64"),
        PRICE_EMA_PERIOD,
    )
    price_ema21_value = float(price_ema21_series.iloc[-1])
    if not math.isfinite(price_ema21_value):
        return _not_ready(TRIGGER_NON_FINITE_DATA)
    trigger_price_ema21 = Decimal(str(price_ema21_value))

    # ---------------- native H4 and H1 price contexts ----------------
    h4_context = _prepare_price_context(
        h4_df,
        duration=H4_DURATION,
        expected_close=expected_h4_close_for(trigger_close),
        as_of=trigger_close,
        history_ready_at=ready_at,
        observed_live_closes=observed_live_h4_closes,
        minimum_rows=H4_PRICE_EMA_MINIMUM_ROWS,
        duplicate_reason=H4_DUPLICATE_OR_NON_INCREASING_TIME,
        expected_missing_reason=H4_EXPECTED_CLOSE_MISSING,
        live_unconfirmed_reason=H4_LIVE_CLOSE_UNCONFIRMED,
        insufficient_reason=H4_INSUFFICIENT_CONTIGUOUS_HISTORY,
        non_finite_reason=H4_NON_FINITE_DATA,
    )
    if isinstance(h4_context, str):
        return _not_ready(h4_context)

    h1_context = _prepare_price_context(
        h1_df,
        duration=H1_DURATION,
        expected_close=expected_h1_close_for(trigger_close),
        as_of=trigger_close,
        history_ready_at=ready_at,
        observed_live_closes=observed_live_h1_closes,
        minimum_rows=H1_PRICE_EMA_MINIMUM_ROWS,
        duplicate_reason=H1_DUPLICATE_OR_NON_INCREASING_TIME,
        expected_missing_reason=H1_EXPECTED_CLOSE_MISSING,
        live_unconfirmed_reason=H1_LIVE_CLOSE_UNCONFIRMED,
        insufficient_reason=H1_INSUFFICIENT_CONTIGUOUS_HISTORY,
        non_finite_reason=H1_NON_FINITE_DATA,
    )
    if isinstance(h1_context, str):
        return _not_ready(h1_context)

    prepared_input = BtcRsiCrossInput(
        symbol=symbol,
        trigger_timeframe=trigger_timeframe,
        trigger_close_time=trigger_close,
        trigger_close_price=trigger_close_price,
        trigger_price_ema21=trigger_price_ema21,
        previous_trigger=previous_trigger,
        current_trigger=current_trigger,
        h1_close_price=h1_context.close_price,
        h1_price_ema21=h1_context.price_ema21,
        h1_close_time=h1_context.close_time,
        h4_close_price=h4_context.close_price,
        h4_price_ema21=h4_context.price_ema21,
        h4_close_time=h4_context.close_time,
    )
    return BtcRsiCrossPreparation(input=prepared_input, reason=PREPARATION_READY)


# ---------------------------------------------------------------------------
# Decision (spec §9 locked precedence)
# ---------------------------------------------------------------------------
def evaluate_btc_rsi_cross(data: BtcRsiCrossInput) -> BtcRsiCrossDecision:
    """Pure fresh-cross + H1/H4 price-gate decision for one input."""

    event_id = build_event_id(
        symbol=data.symbol,
        trigger_timeframe=data.trigger_timeframe,
        trigger_close_time=data.trigger_close_time,
    )

    # Equality on the previous candle counts as below; equality on the
    # current candle is not a cross.
    fresh_bullish_cross = (
        data.previous_trigger.rsi_ema9 <= data.previous_trigger.rsi_wma45
        and data.current_trigger.rsi_ema9 > data.current_trigger.rsi_wma45
    )
    if not fresh_bullish_cross:
        return BtcRsiCrossDecision(
            should_alert=False,
            event_id=event_id,
            reason=DECISION_NO_FRESH_BULLISH_CROSS,
        )

    if data.h4_close_price <= data.h4_price_ema21:
        return BtcRsiCrossDecision(
            should_alert=False,
            event_id=event_id,
            reason=DECISION_H4_CLOSE_NOT_ABOVE_EMA21,
        )

    if data.h1_close_price <= data.h1_price_ema21:
        return BtcRsiCrossDecision(
            should_alert=False,
            event_id=event_id,
            reason=DECISION_H1_CLOSE_NOT_ABOVE_EMA21,
        )

    return BtcRsiCrossDecision(
        should_alert=True,
        event_id=event_id,
        reason=DECISION_ALERT_FRESH_BULLISH_CROSS_H4_BULLISH,
    )
