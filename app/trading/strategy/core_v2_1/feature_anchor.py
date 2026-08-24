"""Locked source-history anchor for deterministic Core V2.1 indicators.

Both replay and live evaluation must build recursive indicators from this
same absolute source window.  Changing this contract requires a new strategy
version and an explicit state/data migration; it must never happen implicitly
because an exchange's retention window moved.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from types import MappingProxyType

FEATURE_ANCHOR_VERSION = "core-v2.1-anchor-2026-06-29T11:15Z-v1"
FEATURE_ANCHOR_M15_OPEN = datetime(2026, 6, 29, 11, 15, tzinfo=UTC)

_TIMEFRAME_DURATION = MappingProxyType(
    {
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
    }
)


def _first_fully_covered_close(timeframe: str) -> datetime:
    try:
        duration = _TIMEFRAME_DURATION[timeframe]
    except KeyError as exc:
        raise ValueError(f"Unsupported Core V2.1 timeframe: {timeframe!r}") from exc
    seconds = int(duration.total_seconds())
    anchor_seconds = int(FEATURE_ANCHOR_M15_OPEN.timestamp())
    quotient, remainder = divmod(anchor_seconds, seconds)
    if remainder:
        quotient += 1
    bucket_open = datetime.fromtimestamp(quotient * seconds, tz=UTC)
    return bucket_open + duration


FEATURE_FIRST_CLOSE_BY_TIMEFRAME: Mapping[str, datetime] = MappingProxyType(
    {
        timeframe: _first_fully_covered_close(timeframe)
        for timeframe in _TIMEFRAME_DURATION
    }
)


def first_fully_covered_close(timeframe: str) -> datetime:
    """Return the first complete native bucket after the source anchor."""

    try:
        return FEATURE_FIRST_CLOSE_BY_TIMEFRAME[timeframe]
    except KeyError as exc:
        raise ValueError(f"Unsupported Core V2.1 timeframe: {timeframe!r}") from exc


def assert_feature_anchor_available(through: datetime) -> None:
    """Reject a requested runtime/replay boundary before the locked window."""

    if through.tzinfo is None or through.utcoffset() is None:
        raise ValueError("through must be timezone-aware")
    boundary = through.astimezone(UTC)
    if boundary < first_fully_covered_close("15m"):
        raise ValueError(
            f"Core V2.1 feature anchor begins at "
            f"{FEATURE_ANCHOR_M15_OPEN.isoformat()}, after requested boundary "
            f"{boundary.isoformat()}"
        )
