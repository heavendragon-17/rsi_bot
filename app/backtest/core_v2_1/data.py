"""Strict candle normalization and point-in-time context selection.

The historical files in ``app/backtest/data`` store a timezone-naive UTC+7
*open* timestamp.  Internally Core V2.1 uses timezone-aware UTC *close*
timestamps.  Converting at this boundary prevents both timezone drift and the
common error of making a candle visible before it has closed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np
import pandas as pd

UTC = "UTC"
STORED_UTC_OFFSET = pd.Timedelta(hours=7)
OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")
SUPPORTED_TIMEFRAMES: Mapping[str, pd.Timedelta] = MappingProxyType(
    {
        "15m": pd.Timedelta(minutes=15),
        "1h": pd.Timedelta(hours=1),
        "4h": pd.Timedelta(hours=4),
    }
)
SYNTHETIC_BTC_FIXTURE = "BTC_USDT_15m.csv"


class CandleDataError(ValueError):
    """Raised when candle data would make a replay ambiguous or unsafe."""


@dataclass(frozen=True)
class CandleValidationReport:
    """Data-quality facts recorded when a candle frame is normalized."""

    timeframe: str
    input_rows: int
    output_rows: int
    dropped_forming_rows: int
    duplicate_timestamps: int
    gap_count: int
    missing_candles: int
    first_open_at: pd.Timestamp | None
    last_closed_at: pd.Timestamp | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeframe": self.timeframe,
            "input_rows": self.input_rows,
            "output_rows": self.output_rows,
            "dropped_forming_rows": self.dropped_forming_rows,
            "duplicate_timestamps": self.duplicate_timestamps,
            "gap_count": self.gap_count,
            "missing_candles": self.missing_candles,
            "first_open_at": _iso_or_none(self.first_open_at),
            "last_closed_at": _iso_or_none(self.last_closed_at),
        }


@dataclass(frozen=True)
class LoadedCandles:
    """A canonical closed-candle frame and the validation evidence for it."""

    frame: pd.DataFrame
    report: CandleValidationReport
    path: Path | None = None


@dataclass(frozen=True)
class AsOfRow:
    """One immutable row together with the close time that made it visible."""

    closed_at: pd.Timestamp
    values: Mapping[str, Any]

    @classmethod
    def from_series(cls, closed_at: pd.Timestamp, row: pd.Series) -> AsOfRow:
        values = {key: _python_scalar(value) for key, value in row.items()}
        return cls(closed_at=closed_at, values=MappingProxyType(values))


@dataclass(frozen=True)
class PointInTimeContext:
    """All information Core V2.1 may observe at one M15 close."""

    symbol: str
    as_of: pd.Timestamp
    current_m15: AsOfRow
    previous_m15: AsOfRow
    m15_three_bars_ago: AsOfRow
    alt_h1: AsOfRow
    btc_h1: AsOfRow
    btc_h4: AsOfRow

    @property
    def context_closed_at(self) -> Mapping[str, str]:
        return MappingProxyType(
            {
                "current_m15": self.current_m15.closed_at.isoformat(),
                "previous_m15": self.previous_m15.closed_at.isoformat(),
                "m15_three_bars_ago": self.m15_three_bars_ago.closed_at.isoformat(),
                "alt_h1": self.alt_h1.closed_at.isoformat(),
                "btc_h1": self.btc_h1.closed_at.isoformat(),
                "btc_h4": self.btc_h4.closed_at.isoformat(),
            }
        )


def timeframe_delta(timeframe: str) -> pd.Timedelta:
    """Return the exact duration for a supported Core V2.1 timeframe."""

    try:
        return SUPPORTED_TIMEFRAMES[timeframe.lower()]
    except KeyError as exc:
        supported = ", ".join(SUPPORTED_TIMEFRAMES)
        raise CandleDataError(f"Unsupported timeframe {timeframe!r}; expected one of {supported}") from exc


def load_stored_candles(
    path: str | Path,
    *,
    timeframe: str = "15m",
    now: pd.Timestamp | str | None = None,
    strict: bool = True,
) -> LoadedCandles:
    """Load a repository CSV and convert it to canonical closed-candle time.

    ``timestamp`` must be timezone-naive and is interpreted as UTC+7 candle
    open time.  Rows whose close is later than ``now`` are removed.  In strict
    mode, duplicates, gaps, non-chronological rows, invalid OHLC relationships,
    and non-finite values fail closed.
    """

    source_path = Path(path)
    if source_path.name.upper() == SYNTHETIC_BTC_FIXTURE.upper():
        raise CandleDataError(
            f"{source_path.name} is a synthetic test fixture and cannot be used as the BTC benchmark"
        )
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    raw = pd.read_csv(source_path)
    loaded = normalize_stored_candles(raw, timeframe=timeframe, now=now, strict=strict)
    return LoadedCandles(frame=loaded.frame, report=loaded.report, path=source_path.resolve())


def normalize_stored_candles(
    raw: pd.DataFrame,
    *,
    timeframe: str = "15m",
    now: pd.Timestamp | str | None = None,
    strict: bool = True,
) -> LoadedCandles:
    """Normalize an in-memory stored-format frame.

    This is the testable implementation behind :func:`load_stored_candles` and
    is also used by the downloader before committing reconciled files.
    """

    delta = timeframe_delta(timeframe)
    required = {"timestamp", *OHLCV_COLUMNS}
    missing_columns = sorted(required.difference(raw.columns))
    if missing_columns:
        raise CandleDataError(f"Missing required candle columns: {', '.join(missing_columns)}")

    frame = raw.loc[:, ["timestamp", *OHLCV_COLUMNS]].copy()
    input_rows = len(frame)
    if frame.empty:
        return LoadedCandles(
            frame=_empty_canonical_frame(),
            report=CandleValidationReport(
                timeframe=timeframe,
                input_rows=0,
                output_rows=0,
                dropped_forming_rows=0,
                duplicate_timestamps=0,
                gap_count=0,
                missing_candles=0,
                first_open_at=None,
                last_closed_at=None,
            ),
        )

    parsed = pd.to_datetime(frame["timestamp"], errors="coerce")
    invalid_ts = int(parsed.isna().sum())
    if invalid_ts:
        raise CandleDataError(f"Found {invalid_ts} invalid timestamp value(s)")
    if isinstance(parsed.dtype, pd.DatetimeTZDtype):
        raise CandleDataError("Stored timestamps must be timezone-naive UTC+7 candle-open times")
    if not parsed.is_monotonic_increasing:
        if strict:
            raise CandleDataError("Candle timestamps are not chronological")
        order = parsed.sort_values(kind="stable").index
        frame = frame.loc[order].reset_index(drop=True)
        parsed = parsed.loc[order].reset_index(drop=True)

    duplicate_count = int(parsed.duplicated(keep=False).sum())
    if duplicate_count and strict:
        raise CandleDataError(f"Found {duplicate_count} row(s) with duplicate candle timestamps")
    if duplicate_count:
        keep = ~parsed.duplicated(keep="last")
        frame = frame.loc[keep].reset_index(drop=True)
        parsed = parsed.loc[keep].reset_index(drop=True)

    for column in OHLCV_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    numeric_values = frame.loc[:, OHLCV_COLUMNS].to_numpy(dtype=float)
    invalid_numeric = int((~np.isfinite(numeric_values)).any(axis=1).sum())
    if invalid_numeric:
        raise CandleDataError(f"Found {invalid_numeric} candle row(s) with non-finite OHLCV values")

    invalid_ohlc = (
        (frame["open"] <= 0)
        | (frame["high"] <= 0)
        | (frame["low"] <= 0)
        | (frame["close"] <= 0)
        | (frame["volume"] < 0)
        | (frame["high"] < frame[["open", "close"]].max(axis=1))
        | (frame["low"] > frame[["open", "close"]].min(axis=1))
        | (frame["high"] < frame["low"])
    )
    if invalid_ohlc.any():
        raise CandleDataError(f"Found {int(invalid_ohlc.sum())} candle row(s) with invalid OHLCV relationships")

    # Stored local wall time -> UTC open time.  No host-local timezone is ever
    # consulted, making the conversion deterministic on every machine.
    open_at = (pd.DatetimeIndex(parsed) - STORED_UTC_OFFSET).tz_localize(UTC)
    closed_at = open_at + delta
    cutoff = _as_utc(now) if now is not None else pd.Timestamp.now(tz=UTC)
    closed_mask = closed_at <= cutoff
    dropped_forming = int((~closed_mask).sum())
    frame = frame.loc[closed_mask].copy()
    open_at = open_at[closed_mask]
    closed_at = closed_at[closed_mask]

    if len(open_at) and not open_at.equals(open_at.floor(_pandas_rule(timeframe))):
        raise CandleDataError(f"{timeframe} candle opens must lie on the UTC {timeframe} grid")

    gap_count, missing_candles = _cadence_gaps(open_at, delta)
    if gap_count and strict:
        raise CandleDataError(
            f"Candle cadence contains {gap_count} gap(s) totaling {missing_candles} missing {timeframe} candle(s)"
        )

    frame.drop(columns=["timestamp"], inplace=True)
    frame.insert(0, "open_at", open_at)
    frame.index = pd.DatetimeIndex(closed_at, name="closed_at")
    frame = frame.astype({column: "float64" for column in OHLCV_COLUMNS})

    report = CandleValidationReport(
        timeframe=timeframe,
        input_rows=input_rows,
        output_rows=len(frame),
        dropped_forming_rows=dropped_forming,
        duplicate_timestamps=duplicate_count,
        gap_count=gap_count,
        missing_candles=missing_candles,
        first_open_at=open_at[0] if len(open_at) else None,
        last_closed_at=closed_at[-1] if len(closed_at) else None,
    )
    return LoadedCandles(frame=frame, report=report)


def resample_closed_candles(frame: pd.DataFrame, target_timeframe: str) -> pd.DataFrame:
    """Derive complete UTC-anchored H1/H4 candles from canonical M15 data.

    Partial leading/trailing buckets are discarded.  Every emitted row is
    indexed by its close time, so an as-of lookup cannot observe it early.
    """

    target_delta = timeframe_delta(target_timeframe)
    base_delta = timeframe_delta("15m")
    if target_delta <= base_delta or target_delta % base_delta != pd.Timedelta(0):
        raise CandleDataError("Core V2.1 resampling requires a whole-number multiple of 15m")
    _validate_canonical_index(frame)
    required = set(OHLCV_COLUMNS)
    missing_columns = sorted(required.difference(frame.columns))
    if missing_columns:
        raise CandleDataError(f"Missing OHLCV columns for resampling: {', '.join(missing_columns)}")
    if frame.empty:
        return _empty_canonical_frame()

    # Reconstruct UTC opens from the canonical close index.  This also avoids
    # trusting a mutable/open_at helper column supplied by a caller.
    source = frame.loc[:, OHLCV_COLUMNS].copy()
    source.index = frame.index - base_delta
    source.index.name = "open_at"
    _validate_m15_source_grid(source.index, base_delta)
    source["_open_at"] = source.index
    rule = _pandas_rule(target_timeframe)
    grouped = source.resample(rule, origin="epoch", label="left", closed="left")
    result = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    bucket_shape = grouped["_open_at"].agg(["count", "min", "max"])
    expected_count = int(target_delta / base_delta)
    expected_last_open = bucket_shape.index + target_delta - base_delta
    valid_bucket = (
        (bucket_shape["count"] == expected_count)
        & (bucket_shape["min"] == bucket_shape.index)
        & (bucket_shape["max"] == expected_last_open)
    )
    result = result.loc[valid_bucket].copy()
    if result.empty:
        return _empty_canonical_frame()

    result.insert(0, "open_at", result.index)
    result.index = pd.DatetimeIndex(result.index + target_delta, name="closed_at")
    return result


def row_at_or_before(frame: pd.DataFrame, as_of: pd.Timestamp | str) -> AsOfRow | None:
    """Return the latest row that was fully closed at ``as_of``."""

    _validate_canonical_index(frame)
    at = _as_utc(as_of)
    position = int(frame.index.searchsorted(at, side="right")) - 1
    if position < 0:
        return None
    closed_at = frame.index[position]
    if closed_at > at:  # defensive guard around future pandas behavior
        raise CandleDataError("Point-in-time lookup selected a future candle")
    return AsOfRow.from_series(closed_at, frame.iloc[position])


def build_point_in_time_context(
    *,
    symbol: str,
    as_of: pd.Timestamp | str,
    m15: pd.DataFrame,
    alt_h1: pd.DataFrame,
    btc_h1: pd.DataFrame,
    btc_h4: pd.DataFrame,
) -> PointInTimeContext | None:
    """Build the exact data bundle observable at one alt M15 close.

    ``None`` means warm-up/readiness is incomplete.  A mismatched M15 trigger
    is an error rather than an implicit as-of lookup because replay events must
    correspond one-to-one with an actual trigger candle.
    """

    for candidate in (m15, alt_h1, btc_h1, btc_h4):
        _validate_canonical_index(candidate)
    at = _as_utc(as_of)
    position = int(m15.index.searchsorted(at, side="left"))
    if position >= len(m15) or m15.index[position] != at:
        raise CandleDataError(f"No {symbol} M15 candle closes exactly at {at.isoformat()}")
    if position < 3:
        return None

    expected_h1_close = at.floor("1h")
    expected_h4_close = at.floor("4h")
    context_rows = {
        "alt_h1": row_at_or_before(alt_h1, at),
        "btc_h1": row_at_or_before(btc_h1, at),
        "btc_h4": row_at_or_before(btc_h4, at),
    }
    if any(value is None for value in context_rows.values()):
        return None
    if (
        context_rows["alt_h1"].closed_at != expected_h1_close  # type: ignore[union-attr]
        or context_rows["btc_h1"].closed_at != expected_h1_close  # type: ignore[union-attr]
        or context_rows["btc_h4"].closed_at != expected_h4_close  # type: ignore[union-attr]
    ):
        # A stale context is not a substitute for the bar that should have
        # closed by this event time.  Fail readiness closed on data gaps.
        return None

    context = PointInTimeContext(
        symbol=symbol,
        as_of=at,
        current_m15=AsOfRow.from_series(m15.index[position], m15.iloc[position]),
        previous_m15=AsOfRow.from_series(m15.index[position - 1], m15.iloc[position - 1]),
        m15_three_bars_ago=AsOfRow.from_series(m15.index[position - 3], m15.iloc[position - 3]),
        alt_h1=context_rows["alt_h1"],  # type: ignore[arg-type]
        btc_h1=context_rows["btc_h1"],  # type: ignore[arg-type]
        btc_h4=context_rows["btc_h4"],  # type: ignore[arg-type]
    )
    assert_no_lookahead(context)
    return context


def assert_no_lookahead(context: PointInTimeContext) -> None:
    """Fail if any row in a context closes after its trigger time."""

    timestamps = (
        context.current_m15.closed_at,
        context.previous_m15.closed_at,
        context.m15_three_bars_ago.closed_at,
        context.alt_h1.closed_at,
        context.btc_h1.closed_at,
        context.btc_h4.closed_at,
    )
    future = [timestamp for timestamp in timestamps if timestamp > context.as_of]
    if future:
        rendered = ", ".join(timestamp.isoformat() for timestamp in future)
        raise CandleDataError(f"Point-in-time context contains future close(s): {rendered}")


def canonical_to_stored(frame: pd.DataFrame, *, timeframe: str = "15m") -> pd.DataFrame:
    """Convert a canonical frame back to the repository CSV representation."""

    _validate_canonical_index(frame)
    delta = timeframe_delta(timeframe)
    stored = frame.loc[:, OHLCV_COLUMNS].copy()
    utc_open = frame.index - delta
    local_naive_open = (utc_open + STORED_UTC_OFFSET).tz_localize(None)
    stored.insert(0, "timestamp", local_naive_open)
    return stored.reset_index(drop=True)


def _validate_canonical_index(frame: pd.DataFrame) -> None:
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise CandleDataError("Canonical candle frame must use a DatetimeIndex of close times")
    if frame.index.tz is None:
        raise CandleDataError("Canonical candle close index must be timezone-aware UTC")
    if str(frame.index.tz) not in {"UTC", "UTC+00:00"}:
        raise CandleDataError("Canonical candle close index must be normalized to UTC")
    if not frame.index.is_monotonic_increasing:
        raise CandleDataError("Canonical candle close index must be chronological")
    if not frame.index.is_unique:
        raise CandleDataError("Canonical candle close index must be unique")


def _cadence_gaps(index: pd.DatetimeIndex, delta: pd.Timedelta) -> tuple[int, int]:
    if len(index) < 2:
        return 0, 0
    differences = index[1:] - index[:-1]
    gap_differences = differences[differences != delta]
    if len(gap_differences) == 0:
        return 0, 0
    missing = 0
    for difference in gap_differences:
        if difference > delta and difference % delta == pd.Timedelta(0):
            missing += int(difference / delta) - 1
        else:
            # A non-grid timestamp is one integrity failure even when no exact
            # integer number of missing bars can be inferred.
            missing += 1
    return len(gap_differences), missing


def _validate_m15_source_grid(index: pd.DatetimeIndex, delta: pd.Timedelta) -> None:
    """Reject off-grid or discontinuous source rows before any aggregation."""

    if len(index) == 0:
        return
    off_grid = (
        (index.minute % 15 != 0)
        | (index.second != 0)
        | (index.microsecond != 0)
        | (index.nanosecond != 0)
    )
    if bool(off_grid.any()):
        raise CandleDataError("M15 source contains a timestamp that is not on the UTC 15-minute grid")
    if len(index) > 1 and bool(((index[1:] - index[:-1]) != delta).any()):
        raise CandleDataError("M15 source must be contiguous before higher-timeframe aggregation")


def _as_utc(value: pd.Timestamp | str | None) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise CandleDataError(f"Timestamp {timestamp!s} must be timezone-aware")
    return timestamp.tz_convert(UTC)


def _pandas_rule(timeframe: str) -> str:
    normalized = timeframe.lower()
    if normalized.endswith("h"):
        return f"{int(normalized[:-1])}h"
    if normalized.endswith("m"):
        return f"{int(normalized[:-1])}min"
    raise CandleDataError(f"Unsupported pandas timeframe rule: {timeframe}")


def _empty_canonical_frame() -> pd.DataFrame:
    empty = pd.DataFrame(columns=["open_at", *OHLCV_COLUMNS])
    empty.index = pd.DatetimeIndex([], tz=UTC, name="closed_at")
    return empty


def _python_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value
    if pd.isna(value):
        return None
    return value


def _iso_or_none(value: pd.Timestamp | None) -> str | None:
    return value.isoformat() if value is not None else None
