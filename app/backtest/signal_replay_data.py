"""Validated, vectorized CSV and event loading for BTC alert replay."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

from app.backtest.signal_replay_models import (
    ReplayTriggerEvent,
    SignalReplayInputError,
)
from app.trading.strategy.btc_rsi_cross_alert.evaluator import (
    H1_DURATION,
    H4_DURATION,
    TRIGGER_DURATION_BY_TIMEFRAME,
    normalize_candle_open,
)

STORAGE_TZ: Final[timezone] = timezone(timedelta(hours=7), name="UTC+7")
REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
)


def _format_utc7(value: datetime) -> str:
    return value.astimezone(STORAGE_TZ).strftime("%Y-%m-%d %H:%M:%S UTC+7")


def _normalize_timestamp_index(
    values: pd.Series,
    csv_path: Path,
) -> pd.DatetimeIndex:
    """Use pandas' vectorized path, with exact row diagnostics as fallback."""

    try:
        parsed = pd.to_datetime(values, format="mixed", errors="raise")
        index = pd.DatetimeIndex(parsed)
        if index.hasnans:
            raise ValueError("timestamp is NaT")
        if index.tz is None:
            return index.tz_localize(STORAGE_TZ).tz_convert(UTC)
        return index.tz_convert(UTC)
    except (TypeError, ValueError, OverflowError):
        normalized: list[datetime] = []
        for position, raw_timestamp in enumerate(values):
            try:
                parsed_value = pd.Timestamp(raw_timestamp)
                if pd.isna(parsed_value):
                    raise ValueError("timestamp is NaT")
                normalized.append(normalize_candle_open(parsed_value))
            except (TypeError, ValueError, OverflowError) as exc:
                raise SignalReplayInputError(
                    f"Invalid timestamp at row {position} in {csv_path}: "
                    f"{raw_timestamp!r}"
                ) from exc
        return pd.DatetimeIndex(normalized)


def load_ohlcv_csv(path: str | Path, timeframe: str) -> pd.DataFrame:
    """Load, normalize, and validate one historical OHLCV frame."""

    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Historical {timeframe} CSV not found: {csv_path}")
    if not csv_path.is_file():
        raise SignalReplayInputError(
            f"Historical {timeframe} path is not a file: {csv_path}"
        )

    try:
        raw = pd.read_csv(csv_path)
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise SignalReplayInputError(
            f"Could not read historical {timeframe} CSV {csv_path}: {exc}"
        ) from exc

    missing = [column for column in REQUIRED_COLUMNS if column not in raw.columns]
    if missing:
        raise SignalReplayInputError(
            f"Historical {timeframe} CSV {csv_path} is missing columns: "
            f"{', '.join(missing)}"
        )
    if raw.empty:
        raise SignalReplayInputError(f"Historical {timeframe} CSV is empty: {csv_path}")

    frame = raw.loc[:, list(REQUIRED_COLUMNS)].copy()
    frame["timestamp"] = _normalize_timestamp_index(raw["timestamp"], csv_path)
    for column in REQUIRED_COLUMNS[1:]:
        numeric = pd.to_numeric(frame[column], errors="coerce")
        values = numeric.to_numpy(dtype="float64", na_value=np.nan)
        if not np.isfinite(values).all():
            bad_position = int(np.flatnonzero(~np.isfinite(values))[0])
            raise SignalReplayInputError(
                f"Invalid {column} at row {bad_position} in {csv_path}; "
                "OHLCV values must be finite numbers"
            )
        frame[column] = values

    frame = frame.set_index("timestamp").sort_index()
    if not frame.index.is_unique:
        duplicate = frame.index[frame.index.duplicated(keep=False)][0]
        duplicate_time = duplicate.to_pydatetime()
        raise SignalReplayInputError(
            f"Historical {timeframe} CSV contains duplicate candle opens: "
            f"{_format_utc7(duplicate_time)}"
        )

    frame["closed"] = True
    frame["timeframe"] = timeframe
    return frame


def _utc_open_times(frame: pd.DataFrame) -> tuple[datetime, ...]:
    index = pd.DatetimeIndex(frame.index)
    if index.tz is None:
        return tuple(normalize_candle_open(raw_open) for raw_open in frame.index)
    return tuple(value.to_pydatetime() for value in index.tz_convert(UTC))


def events_for_frame(
    frame: pd.DataFrame,
    timeframe: str,
    start_utc: datetime | None,
    end_utc: datetime | None,
) -> list[ReplayTriggerEvent]:
    """Build in-window events while retaining their source-array positions."""

    duration = TRIGGER_DURATION_BY_TIMEFRAME[timeframe]
    events: list[ReplayTriggerEvent] = []
    for position, open_time in enumerate(_utc_open_times(frame)):
        close_time = open_time + duration
        if start_utc is not None and close_time < start_utc:
            continue
        if end_utc is not None and close_time > end_utc:
            continue
        events.append(
            ReplayTriggerEvent(
                timeframe=timeframe,
                open_time=open_time,
                close_time=close_time,
                position=position,
            )
        )
    return events


def all_h4_close_times(frame: pd.DataFrame) -> frozenset[datetime]:
    """Return every historical H4 close as a confirmed UTC instant."""

    return frozenset(open_time + H4_DURATION for open_time in _utc_open_times(frame))


def all_h1_close_times(frame: pd.DataFrame) -> frozenset[datetime]:
    """Return every historical H1 close as a confirmed UTC instant."""

    return frozenset(open_time + H1_DURATION for open_time in _utc_open_times(frame))
