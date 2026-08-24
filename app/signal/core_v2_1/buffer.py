"""Point-in-time candle buffer and fail-closed bundle construction."""

from __future__ import annotations

import bisect
import threading
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from app.signal.core_v2_1.models import (
    AsOfBundle,
    ClosedCandle,
    MarketKey,
    MarketSeries,
    TriggerPlan,
    ensure_utc,
    timeframe_delta,
)


class BundleNotReady(RuntimeError):
    """Required history has not arrived yet and evaluation must not run."""


class MarketDataIntegrityError(RuntimeError):
    """Market history is stale, conflicting, or contains a time gap."""


class ClosedCandleBuffer:
    """Thread-safe venue-aware store containing only fully closed candles.

    Writes are idempotent when a source repeats the exact same candle.  A
    conflicting candle for an existing close timestamp is rejected rather
    than silently rewriting point-in-time history.
    """

    def __init__(self, *, max_candles_per_market: int | None = None) -> None:
        if max_candles_per_market is not None and max_candles_per_market < 2:
            raise ValueError("max_candles_per_market must be at least 2")
        self._cap = max_candles_per_market
        self._candles: dict[MarketKey, list[ClosedCandle]] = defaultdict(list)
        self._locks: dict[MarketKey, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    def add(self, candle: ClosedCandle) -> bool:
        """Add a closed candle, returning ``False`` for an exact duplicate."""

        with self._lock_for(candle.key):
            values = self._candles[candle.key]
            close_times = [item.close_time for item in values]
            index = bisect.bisect_left(close_times, candle.close_time)
            if index < len(values) and values[index].close_time == candle.close_time:
                if values[index] == candle:
                    return False
                raise MarketDataIntegrityError(
                    f"Conflicting candle for {candle.key.storage_id} "
                    f"at {candle.close_time.isoformat()}"
                )
            values.insert(index, candle)
            if self._cap is not None and len(values) > self._cap:
                del values[: len(values) - self._cap]
            return True

    def add_many(self, candles: list[ClosedCandle] | tuple[ClosedCandle, ...]) -> int:
        added = 0
        for candle in sorted(candles, key=lambda item: (item.key, item.close_time)):
            added += int(self.add(candle))
        return added

    def close_times_after(
        self,
        key: MarketKey,
        after: datetime | None,
        *,
        through: datetime | None = None,
    ) -> tuple[datetime, ...]:
        """Return trigger close times in strict chronological order."""

        after_utc = ensure_utc(after, field_name="after") if after is not None else None
        through_utc = ensure_utc(through, field_name="through") if through is not None else None
        with self._lock_for(key):
            return tuple(
                candle.close_time
                for candle in self._candles.get(key, ())
                if (after_utc is None or candle.close_time > after_utc)
                and (through_utc is None or candle.close_time <= through_utc)
            )

    def series_as_of(
        self,
        key: MarketKey,
        as_of: datetime,
        *,
        minimum_candles: int,
    ) -> MarketSeries:
        as_of_utc = ensure_utc(as_of, field_name="as_of")
        with self._lock_for(key):
            eligible = [
                candle
                for candle in self._candles.get(key, ())
                if candle.close_time <= as_of_utc
            ]
        if len(eligible) < minimum_candles:
            raise BundleNotReady(
                f"{key.storage_id} has {len(eligible)} closed candles as of "
                f"{as_of_utc.isoformat()}, needs {minimum_candles}"
            )
        # Retain the complete available prefix.  Recursive EMA/RSI/ATR values
        # depend on their seed, so re-seeding from a moving minimum-length
        # window would make live values drift from chronological replay.
        return MarketSeries(key=key, candles=tuple(eligible))

    def latest_close(self, key: MarketKey) -> datetime | None:
        with self._lock_for(key):
            values = self._candles.get(key)
            return values[-1].close_time if values else None

    def _lock_for(self, key: MarketKey) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(key, threading.RLock())


class PointInTimeBundleBuilder:
    """Build evaluator input frames while enforcing readiness and integrity."""

    def __init__(self, buffer: ClosedCandleBuffer) -> None:
        self._buffer = buffer

    def build(self, plan: TriggerPlan, as_of: datetime) -> AsOfBundle:
        as_of_utc = ensure_utc(as_of, field_name="as_of")
        built: list[MarketSeries] = []

        for requirement in plan.requirements:
            series = self._buffer.series_as_of(
                requirement.key,
                as_of_utc,
                minimum_candles=requirement.minimum_candles,
            )
            latest = series.latest.close_time

            if requirement.key == plan.trigger and latest != as_of_utc:
                raise BundleNotReady(
                    f"Trigger {plan.trigger.storage_id} has no close at "
                    f"{as_of_utc.isoformat()}"
                )

            age = as_of_utc - latest
            if age < timedelta(0):
                # Defensive assertion: series_as_of must never return future data.
                raise MarketDataIntegrityError(
                    f"{requirement.key.storage_id} contains future data"
                )
            if age > requirement.max_staleness:
                raise MarketDataIntegrityError(
                    f"{requirement.key.storage_id} is stale by {age}; "
                    f"maximum is {requirement.max_staleness}"
                )

            if requirement.require_boundary_close:
                expected_close = _floor_utc_boundary(
                    as_of_utc,
                    requirement.key.timeframe,
                )
                if latest != expected_close:
                    raise MarketDataIntegrityError(
                        f"{requirement.key.storage_id} boundary is incomplete: "
                        f"expected {expected_close.isoformat()}, got {latest.isoformat()}"
                    )

            if requirement.require_contiguous:
                self._assert_contiguous(series)
            built.append(series)

        return AsOfBundle(
            trigger_key=plan.trigger,
            as_of=as_of_utc,
            series=tuple(built),
        )

    @staticmethod
    def _assert_contiguous(series: MarketSeries) -> None:
        expected = timeframe_delta(series.key.timeframe)
        for previous, current in zip(series.candles, series.candles[1:], strict=False):
            actual = current.close_time - previous.close_time
            if actual != expected:
                raise MarketDataIntegrityError(
                    f"Gap in {series.key.storage_id}: {previous.close_time.isoformat()} "
                    f"to {current.close_time.isoformat()} ({actual}, expected {expected})"
                )


def _floor_utc_boundary(value: datetime, timeframe: str) -> datetime:
    """Floor an aware timestamp to a UTC-anchored candle-close boundary."""

    utc_value = ensure_utc(value, field_name="boundary")
    seconds = int(timeframe_delta(timeframe).total_seconds())
    epoch_seconds = int(utc_value.timestamp())
    return datetime.fromtimestamp((epoch_seconds // seconds) * seconds, tz=UTC)
