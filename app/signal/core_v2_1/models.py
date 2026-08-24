"""Typed, immutable models for the Core V2.1 signal runtime."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any

from app.trading.strategy.core_v2_1.config import Venue
from app.trading.strategy.core_v2_1.models import EventType as AdvisoryEventType

_TIMEFRAME_RE = re.compile(r"^(?P<count>[1-9][0-9]*)(?P<unit>[mhd])$")
_UNIFIED_INSTRUMENT_RE = re.compile(
    r"^[A-Z0-9]+/[A-Z0-9]+:[A-Z0-9]+$"
)


def timeframe_delta(timeframe: str) -> timedelta:
    """Return an exact duration for a crypto OHLCV timeframe."""

    match = _TIMEFRAME_RE.fullmatch(timeframe)
    if match is None:
        raise ValueError(f"Unsupported timeframe: {timeframe!r}")
    count = int(match.group("count"))
    unit = match.group("unit")
    if unit == "m":
        return timedelta(minutes=count)
    if unit == "h":
        return timedelta(hours=count)
    return timedelta(days=count)


def ensure_utc(value: datetime, *, field_name: str) -> datetime:
    """Validate an aware timestamp and normalize it to UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class MarketKey:
    """Unambiguous market identity.

    ``instrument`` is the structural CCXT-style perp identity (for example
    ``ETH/USDT:USDT`` or ``PUMP/USDC:USDC``), not a lossy compact alias.
    Including the venue prevents an identically named pair on two venues from
    sharing state or candle storage.
    """

    venue: Venue
    instrument: str
    timeframe: str

    def __post_init__(self) -> None:
        instrument = self.instrument.strip().upper()
        if _UNIFIED_INSTRUMENT_RE.fullmatch(instrument) is None:
            raise ValueError(f"Invalid instrument: {self.instrument!r}")
        timeframe_delta(self.timeframe)
        object.__setattr__(self, "instrument", instrument)

    @property
    def storage_id(self) -> str:
        return f"{self.venue.value}:{self.instrument}:{self.timeframe}"

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, MarketKey):
            return NotImplemented
        return self.storage_id < other.storage_id


@dataclass(frozen=True)
class ClosedCandle:
    """A canonical, fully closed OHLCV candle."""

    key: MarketKey
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        open_time = ensure_utc(self.open_time, field_name="open_time")
        close_time = ensure_utc(self.close_time, field_name="close_time")
        numeric = {
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }
        for name, value in numeric.items():
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must be Decimal")
            if not value.is_finite():
                raise ValueError(f"{name} must be finite")
        if close_time <= open_time:
            raise ValueError("close_time must be later than open_time")
        if close_time - open_time != timeframe_delta(self.key.timeframe):
            raise ValueError("candle duration does not match key timeframe")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC prices must be positive")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high is below an OHLC value")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low is above an OHLC value")
        if self.volume < 0:
            raise ValueError("volume cannot be negative")
        object.__setattr__(self, "open_time", open_time)
        object.__setattr__(self, "close_time", close_time)


@dataclass(frozen=True)
class MarketSeries:
    """One immutable point-in-time candle series."""

    key: MarketKey
    candles: tuple[ClosedCandle, ...]

    def __post_init__(self) -> None:
        previous: datetime | None = None
        for candle in self.candles:
            if candle.key != self.key:
                raise ValueError("series contains a candle for a different market")
            if previous is not None and candle.close_time <= previous:
                raise ValueError("series candles must be strictly chronological")
            previous = candle.close_time

    @property
    def latest(self) -> ClosedCandle:
        if not self.candles:
            raise LookupError(f"No candles for {self.key.storage_id}")
        return self.candles[-1]


@dataclass(frozen=True)
class AsOfBundle:
    """Immutable multi-market view with no candle after ``as_of``."""

    trigger_key: MarketKey
    as_of: datetime
    series: tuple[MarketSeries, ...]
    _by_key: Mapping[MarketKey, MarketSeries] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        as_of = ensure_utc(self.as_of, field_name="as_of")
        by_key: dict[MarketKey, MarketSeries] = {}
        for item in self.series:
            if item.key in by_key:
                raise ValueError(f"Duplicate series: {item.key.storage_id}")
            if item.candles and item.latest.close_time > as_of:
                raise ValueError("as-of bundle contains future data")
            by_key[item.key] = item
        if self.trigger_key not in by_key:
            raise ValueError("as-of bundle is missing its trigger series")
        if by_key[self.trigger_key].latest.close_time != as_of:
            raise ValueError("trigger series must end exactly at bundle as_of")
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "_by_key", MappingProxyType(by_key))

    def for_key(self, key: MarketKey) -> MarketSeries:
        try:
            return self._by_key[key]
        except KeyError as exc:
            raise KeyError(f"Bundle has no series for {key.storage_id}") from exc


@dataclass(frozen=True)
class BundleRequirement:
    """Readiness and integrity requirements for one as-of series."""

    key: MarketKey
    minimum_candles: int
    max_staleness: timedelta
    require_contiguous: bool = True
    require_boundary_close: bool = True

    def __post_init__(self) -> None:
        if self.minimum_candles < 1:
            raise ValueError("minimum_candles must be positive")
        if self.max_staleness < timedelta(0):
            raise ValueError("max_staleness cannot be negative")


@dataclass(frozen=True)
class TriggerPlan:
    """One M15 trigger and all slower-timeframe dependencies it needs."""

    strategy_symbol: str
    trigger: MarketKey
    requirements: tuple[BundleRequirement, ...]

    def __post_init__(self) -> None:
        strategy_symbol = self.strategy_symbol.strip().upper().replace("/", "")
        if not strategy_symbol or not strategy_symbol.isalnum():
            raise ValueError(f"Invalid strategy symbol: {self.strategy_symbol!r}")
        object.__setattr__(self, "strategy_symbol", strategy_symbol)
        if self.trigger.timeframe != "15m":
            raise ValueError("Core V2.1 trigger markets must use 15m")
        keys = [item.key for item in self.requirements]
        if self.trigger not in keys:
            raise ValueError("requirements must include the trigger market")
        if len(keys) != len(set(keys)):
            raise ValueError("requirements contain duplicate markets")


@dataclass(frozen=True)
class MarketPlan:
    """Subscription graph with explicit triggers and dependencies."""

    triggers: tuple[TriggerPlan, ...]
    _by_trigger: Mapping[MarketKey, TriggerPlan] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        by_trigger = {item.trigger: item for item in self.triggers}
        if len(by_trigger) != len(self.triggers):
            raise ValueError("duplicate trigger market")
        object.__setattr__(self, "_by_trigger", MappingProxyType(by_trigger))

    @property
    def trigger_keys(self) -> frozenset[MarketKey]:
        return frozenset(self._by_trigger)

    @property
    def dependency_keys(self) -> frozenset[MarketKey]:
        result: set[MarketKey] = set()
        for item in self.triggers:
            result.update(requirement.key for requirement in item.requirements)
        return frozenset(result - self.trigger_keys)

    @property
    def all_keys(self) -> frozenset[MarketKey]:
        return self.trigger_keys | self.dependency_keys

    def for_trigger(self, key: MarketKey) -> TriggerPlan:
        try:
            return self._by_trigger[key]
        except KeyError as exc:
            raise KeyError(f"Not a trigger market: {key.storage_id}") from exc


@dataclass(frozen=True)
class AdvisoryEvent:
    """Serializable user-facing event emitted by the pure evaluator."""

    event_type: AdvisoryEventType
    symbol: str
    venue: Venue
    closed_at: datetime
    reasons: tuple[str, ...] = ()
    reference_entry: Decimal | None = None
    reference_stop: Decimal | None = None
    reference_tp1: Decimal | None = None
    reference_tp2: Decimal | None = None
    reference_tp3: Decimal | None = None
    zone_low: Decimal | None = None
    zone_high: Decimal | None = None
    wait_elapsed: int | None = None
    metrics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.strip().upper().replace("/", ""))
        object.__setattr__(self, "closed_at", ensure_utc(self.closed_at, field_name="closed_at"))
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))

    def to_payload(self) -> dict[str, Any]:
        def scalar(value: Any) -> Any:
            if isinstance(value, Decimal):
                return str(value)
            if isinstance(value, datetime):
                return ensure_utc(value, field_name="timestamp").isoformat()
            if isinstance(value, Enum):
                return value.value
            return value

        return {
            "event_type": self.event_type.value,
            "symbol": self.symbol,
            "venue": self.venue.value,
            "closed_at": self.closed_at.isoformat(),
            "reasons": list(self.reasons),
            "reference_entry": scalar(self.reference_entry),
            "reference_stop": scalar(self.reference_stop),
            "reference_tp1": scalar(self.reference_tp1),
            "reference_tp2": scalar(self.reference_tp2),
            "reference_tp3": scalar(self.reference_tp3),
            "zone_low": scalar(self.zone_low),
            "zone_high": scalar(self.zone_high),
            "wait_elapsed": self.wait_elapsed,
            "metrics": {key: scalar(value) for key, value in self.metrics.items()},
        }
