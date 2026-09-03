"""Chart enrichment and objective forward observations for signal review.

This module intentionally does not model orders or PnL.  It answers two
different questions for a bullish alert:

* what did price do after the trigger close at named horizons; and
* what candles/indicators should be displayed in the review chart.

The source CSV remains authoritative for both operations.  The caller stores
the source metadata alongside the signal so a missing or shortened file is
visible to the reviewer instead of being silently treated as a complete
observation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.backtest.signal_replay_models import ReplaySignal
from app.trading.strategy.btc_rsi_cross_alert.evaluator import (
    H1_DURATION,
    H4_DURATION,
    TRIGGER_DURATION_BY_TIMEFRAME,
)
from app.trading.strategy.core_v2_1.indicators import ema, rsi_wilder, wma

FORWARD_HORIZONS_MINUTES: tuple[int, ...] = (60, 240, 720, 1440)
CHART_CONTEXT_CANDLES = 120
CHART_INITIAL_FORWARD_CANDLES = 0
CHART_CHUNK_CANDLES = 2_000
CHART_INDICATOR_WARMUP_CANDLES = 1_000

TRADE_EXIT_TAKE_PROFIT = "TAKE_PROFIT"
TRADE_EXIT_STOP_LOSS = "STOP_LOSS"
TRADE_EXIT_BOTH_SAME_CANDLE = "BOTH_SAME_CANDLE"
TRADE_EXIT_OPEN = "OPEN"
TRADE_EXIT_NO_DATA = "NO_DATA"


@dataclass(frozen=True, slots=True)
class TradeExitEvaluation:
    """Candle-level result for a reviewer-configured long TP/SL plan."""

    exit_reason: str
    exit_at: datetime | None
    duration_minutes: int | None
    warning: str | None = None


@dataclass(frozen=True, slots=True)
class ForwardMetricSource:
    """Pre-indexed OHLCV arrays shared by every signal in one timeframe."""

    close_times: pd.DatetimeIndex
    closes: np.ndarray
    highs: np.ndarray
    lows: np.ndarray


def _duration_for_timeframe(timeframe: str) -> timedelta:
    return TRIGGER_DURATION_BY_TIMEFRAME.get(
        timeframe,
        H1_DURATION if timeframe == "1h" else H4_DURATION,
    )


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()


def source_metadata(path: str | Path, frame: pd.DataFrame, timeframe: str) -> dict[str, Any]:
    """Return persisted source facts without claiming content hashing."""

    csv_path = Path(path).resolve()
    index = pd.DatetimeIndex(frame.index).tz_convert(UTC)
    duration = _duration_for_timeframe(timeframe)
    stat = csv_path.stat()
    modified_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
    return {
        "path": str(csv_path),
        "timeframe": timeframe,
        "row_count": int(len(frame)),
        "available_start": _utc_iso(index[0].to_pydatetime()) if len(index) else None,
        "available_end": _utc_iso((index[-1] + duration).to_pydatetime()) if len(index) else None,
        "source_modified_at": modified_at.isoformat(),
        "observed_at": datetime.now(UTC).isoformat(),
        "downloaded_at": None,
    }


def _close_times(frame: pd.DataFrame, timeframe: str) -> pd.DatetimeIndex:
    index = pd.DatetimeIndex(frame.index).tz_convert(UTC)
    duration = _duration_for_timeframe(timeframe)
    return index + duration


def _decimal_text(value: Any) -> str:
    return str(Decimal(str(float(value))))


def _finite_float(value: Any) -> float | None:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


def prepare_forward_metric_source(
    frame: pd.DataFrame,
    timeframe: str,
) -> ForwardMetricSource:
    """Prepare one immutable lookup source for all replay signals in a timeframe."""

    return ForwardMetricSource(
        close_times=_close_times(frame, timeframe),
        closes=frame["close"].to_numpy(dtype=float, copy=False),
        highs=frame["high"].to_numpy(dtype=float, copy=False),
        lows=frame["low"].to_numpy(dtype=float, copy=False),
    )


def calculate_forward_metrics(
    signal: ReplaySignal,
    frame: pd.DataFrame | ForwardMetricSource,
) -> list[dict[str, Any]]:
    """Calculate close-return, MFE, and MAE observations after a signal.

    The trigger candle is excluded from the observation window.  Every alert
    emitted by this replay is bullish, so favorable movement is measured by a
    higher high and adverse movement by a lower low relative to the trigger
    close.  If a requested horizon extends past the CSV, the available suffix
    is returned with ``complete=False`` and a warning.
    """

    source = (
        frame
        if isinstance(frame, ForwardMetricSource)
        else prepare_forward_metric_source(frame, signal.timeframe)
    )
    trigger_close = signal.data.trigger_close_time.astimezone(UTC)
    baseline = float(signal.data.trigger_close_price)
    future_start = int(
        source.close_times.searchsorted(pd.Timestamp(trigger_close), side="right")
    )
    rows: list[dict[str, Any]] = []
    for horizon_minutes in FORWARD_HORIZONS_MINUTES:
        target = trigger_close + timedelta(minutes=horizon_minutes)
        if future_start >= len(source.close_times):
            rows.append(
                {
                    "horizon_minutes": horizon_minutes,
                    "price_at_observation": None,
                    "return_pct": None,
                    "mfe_pct": None,
                    "mae_pct": None,
                    "observed_at": None,
                    "complete": False,
                    "warning": "No candles exist after the trigger close.",
                }
            )
            continue

        target_position = int(
            source.close_times.searchsorted(pd.Timestamp(target), side="left")
        )
        complete = target_position < len(source.close_times)
        end_position = target_position if complete else len(source.close_times) - 1
        observation = slice(future_start, end_position + 1)
        observed_at = source.close_times[end_position].to_pydatetime()
        last_close = float(source.closes[end_position])
        rows.append(
            {
                "horizon_minutes": horizon_minutes,
                "price_at_observation": _decimal_text(last_close),
                "return_pct": (last_close / baseline - 1.0) * 100.0,
                "mfe_pct": (
                    float(np.max(source.highs[observation])) / baseline - 1.0
                )
                * 100.0,
                "mae_pct": min(
                    0.0,
                    (
                        float(np.min(source.lows[observation])) / baseline - 1.0
                    )
                    * 100.0,
                ),
                "observed_at": observed_at,
                "complete": complete,
                "warning": None
                if complete
                else "CSV ends before this horizon; metric uses the available suffix.",
            }
        )
    return rows


def evaluate_long_trade(
    frame: pd.DataFrame | ForwardMetricSource,
    timeframe: str,
    *,
    trigger_close: datetime,
    take_profit_price: Decimal,
    stop_loss_price: Decimal,
) -> TradeExitEvaluation:
    """Find the first TP/SL touch after the signal candle.

    This is an observation of native OHLC candles, not an execution or PnL
    simulation. The signal candle is excluded because entry is at its close.
    If both levels appear inside one candle, OHLC data cannot establish their
    intrabar order, so the result is explicitly marked indeterminate.
    """

    source = (
        frame
        if isinstance(frame, ForwardMetricSource)
        else prepare_forward_metric_source(frame, timeframe)
    )
    trigger_close_utc = trigger_close.astimezone(UTC)
    future_start = int(
        source.close_times.searchsorted(
            pd.Timestamp(trigger_close_utc),
            side="right",
        )
    )
    if future_start >= len(source.close_times):
        return TradeExitEvaluation(
            exit_reason=TRADE_EXIT_NO_DATA,
            exit_at=None,
            duration_minutes=None,
            warning="No candles exist after the signal candle.",
        )

    for position in range(future_start, len(source.close_times)):
        take_profit_hit = Decimal(str(float(source.highs[position]))) >= take_profit_price
        stop_loss_hit = Decimal(str(float(source.lows[position]))) <= stop_loss_price
        if not take_profit_hit and not stop_loss_hit:
            continue

        exit_at = source.close_times[position].to_pydatetime()
        duration_minutes = max(
            0,
            int((exit_at - trigger_close_utc).total_seconds() // 60),
        )
        if take_profit_hit and stop_loss_hit:
            return TradeExitEvaluation(
                exit_reason=TRADE_EXIT_BOTH_SAME_CANDLE,
                exit_at=exit_at,
                duration_minutes=duration_minutes,
                warning=(
                    "Both TP and SL were touched in the same candle; "
                    "intrabar order is unavailable from OHLC data."
                ),
            )
        return TradeExitEvaluation(
            exit_reason=(
                TRADE_EXIT_TAKE_PROFIT
                if take_profit_hit
                else TRADE_EXIT_STOP_LOSS
            ),
            exit_at=exit_at,
            duration_minutes=duration_minutes,
        )

    return TradeExitEvaluation(
        exit_reason=TRADE_EXIT_OPEN,
        exit_at=None,
        duration_minutes=None,
        warning="Neither TP nor SL was touched before the source data ended.",
    )


def _indicator_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute the exact locked RSI/EMA/WMA semantics for a chart frame."""

    output = frame.copy()
    output["ema21"] = ema(output["close"], 21)
    output["ema200"] = ema(output["close"], 200)
    output["rsi21"] = rsi_wilder(output["close"], 21)
    output["rsi_ema9"] = ema(output["rsi21"], 9)
    output["rsi_wma45"] = wma(output["rsi21"], 45)
    return output


def chart_anchor_position(
    close_times: pd.DatetimeIndex,
    signal_time: datetime,
) -> int:
    """Return the latest native candle closed at or before the signal time."""

    signal_utc = pd.Timestamp(signal_time.astimezone(UTC))
    position = int(close_times.searchsorted(signal_utc, side="right")) - 1
    if position < 0:
        raise LookupError(
            "No fully closed candle is available at or before the signal time"
        )
    return position


def chart_candles(
    frame: pd.DataFrame,
    timeframe: str,
    *,
    trigger_close: datetime,
    before: int = CHART_CONTEXT_CANDLES,
    after: int = CHART_INITIAL_FORWARD_CANDLES,
    allow_future: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return a bounded indicator-enriched chart window and range metadata."""

    if before < 0 or after < 0:
        raise ValueError("before and after must be non-negative")
    close_times = _close_times(frame, timeframe)
    signal_time = trigger_close.astimezone(UTC)
    trigger_position = chart_anchor_position(close_times, signal_time)
    anchor_time = close_times[trigger_position].to_pydatetime()
    future_allowed = allow_future
    end_position = (
        min(len(frame) - 1, trigger_position + after)
        if future_allowed
        else trigger_position
    )
    start_position = max(0, trigger_position - before)
    # Keep enough prefix history for the recursive EMA and RSI/WMA seed rules;
    # only the requested display rows are returned to the browser.
    compute_start = max(0, start_position - CHART_INDICATOR_WARMUP_CANDLES)
    computed = _indicator_frame(frame.iloc[compute_start : end_position + 1].copy())
    enriched = computed.iloc[start_position - compute_start :].reset_index(drop=True)
    sliced_close_times = close_times[start_position : end_position + 1]
    candles: list[dict[str, Any]] = []
    for offset, (_, row) in enumerate(enriched.iterrows()):
        close_time = sliced_close_times[offset].to_pydatetime()
        values = {
            "time": close_time.isoformat(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row.get("volume", 0.0)),
            "rsi21": _finite_float(row.get("rsi21")),
            "rsi_ema9": _finite_float(row.get("rsi_ema9")),
            "rsi_wma45": _finite_float(row.get("rsi_wma45")),
            "ema21": _finite_float(row.get("ema21")),
            "ema200": _finite_float(row.get("ema200")),
            "is_trigger": close_time == anchor_time,
        }
        candles.append(values)

    available_start = close_times[0].to_pydatetime() if len(close_times) else None
    available_end = close_times[-1].to_pydatetime() if len(close_times) else None
    has_before = start_position > 0
    has_after = end_position < len(frame) - 1 and future_allowed
    warning: str | None = None
    if available_start is None or available_end is None:
        warning = "CSV contains no candles."
    elif signal_time < available_start:
        warning = "Signal time is before the current CSV range."
    elif signal_time > available_end:
        warning = "Signal time is after the current CSV range."
    elif not future_allowed:
        warning = "Future candles are locked until a quality label is saved."
    elif end_position == len(frame) - 1:
        warning = "CSV ends at the currently loaded chart range."

    return candles, {
        "available_start": _utc_iso(available_start),
        "available_end": _utc_iso(available_end),
        "requested_start": _utc_iso(sliced_close_times[0].to_pydatetime()) if len(sliced_close_times) else None,
        "requested_end": _utc_iso(sliced_close_times[-1].to_pydatetime()) if len(sliced_close_times) else None,
        "has_before": has_before,
        "has_after": has_after,
        "future_allowed": future_allowed,
        "signal_time": _utc_iso(signal_time),
        "anchor_time": _utc_iso(anchor_time),
        "warning": warning,
    }


def chart_window_from_frame(
    frame: pd.DataFrame,
    timeframe: str,
    *,
    trigger_close: datetime,
    start_at: datetime | None,
    end_at: datetime | None,
    allow_future: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return an explicit timestamp window, applying the review gate."""

    close_times = _close_times(frame, timeframe)
    signal_time = trigger_close.astimezone(UTC)
    anchor_position = chart_anchor_position(close_times, signal_time)
    anchor_time = close_times[anchor_position].to_pydatetime()
    requested_start = start_at.astimezone(UTC) if start_at else None
    requested_end = end_at.astimezone(UTC) if end_at else None
    original_requested_end = requested_end
    if not allow_future:
        requested_end = anchor_time
    elif requested_end is None:
        duration = _duration_for_timeframe(timeframe)
        requested_end = anchor_time + duration * CHART_CHUNK_CANDLES
    if requested_start is None:
        requested_start = anchor_time - timedelta(
            minutes=CHART_CONTEXT_CANDLES
            * int(_duration_for_timeframe(timeframe).total_seconds() // 60)
        )
    positions = [
        position
        for position, close_time in enumerate(close_times)
        if close_time.to_pydatetime() >= requested_start
        and (requested_end is None or close_time.to_pydatetime() <= requested_end)
        and (allow_future or close_time.to_pydatetime() <= anchor_time)
    ]
    if not positions:
        return [], {
            "available_start": _utc_iso(close_times[0].to_pydatetime()) if len(close_times) else None,
            "available_end": _utc_iso(close_times[-1].to_pydatetime()) if len(close_times) else None,
            "requested_start": _utc_iso(requested_start),
            "requested_end": _utc_iso(requested_end),
            "has_before": False,
            "has_after": False,
            "future_allowed": allow_future,
            "signal_time": _utc_iso(signal_time),
            "anchor_time": _utc_iso(anchor_time),
            "warning": "Requested chart range is unavailable in the current CSV.",
        }
    start_position, end_position = positions[0], positions[-1]
    candles, metadata = chart_candles(
        frame,
        timeframe,
        trigger_close=signal_time,
        before=max(0, anchor_position - start_position),
        after=max(0, end_position - anchor_position),
        allow_future=allow_future,
    )
    metadata["requested_start"] = _utc_iso(requested_start)
    metadata["requested_end"] = _utc_iso(requested_end)
    metadata["has_before"] = start_position > 0
    metadata["has_after"] = end_position < len(frame) - 1 and allow_future
    range_warnings: list[str] = []
    available_start = close_times[0].to_pydatetime()
    available_end = close_times[-1].to_pydatetime()
    if requested_start < available_start:
        range_warnings.append("CSV starts after the requested historical chart range.")
    if allow_future and original_requested_end is not None and original_requested_end > available_end:
        range_warnings.append("CSV ends before the requested forward chart range.")
    if range_warnings:
        warnings = [warning for warning in (metadata.get("warning"), *range_warnings) if warning]
        metadata["warning"] = " ".join(dict.fromkeys(warnings))
    return candles, metadata
