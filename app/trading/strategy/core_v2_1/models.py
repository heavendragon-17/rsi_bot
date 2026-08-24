"""Immutable domain models for the pure Core V2.1 evaluator."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from .config import VENUE_BY_SYMBOL, Venue


def _normalize_utc_timestamp(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _validate_closed_flag(value: bool, field_name: str) -> None:
    if type(value) is not bool:
        raise TypeError(f"{field_name} must be bool")


def _validate_decimal(value: Decimal, field_name: str, *, positive: bool = False) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if positive and value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _validate_rsi(value: Decimal, field_name: str) -> None:
    _validate_decimal(value, field_name)
    if value < 0 or value > 100:
        raise ValueError(f"{field_name} must be between 0 and 100")


def _floor_utc_boundary(value: datetime, seconds: int) -> datetime:
    epoch_seconds = int(value.timestamp())
    return datetime.fromtimestamp((epoch_seconds // seconds) * seconds, tz=UTC)


@dataclass(frozen=True, slots=True)
class M15Snapshot:
    """One fully featured altcoin M15 candle, timestamped by close time."""

    closed_at: datetime
    is_closed: bool
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    ema21: Decimal
    ema200: Decimal
    atr14: Decimal
    rsi21: Decimal
    rsi_ema9: Decimal
    rsi_wma45: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "closed_at",
            _normalize_utc_timestamp(self.closed_at, "M15Snapshot.closed_at"),
        )
        _validate_closed_flag(self.is_closed, "M15Snapshot.is_closed")
        for name in ("open", "high", "low", "close", "ema21", "ema200"):
            _validate_decimal(getattr(self, name), f"M15Snapshot.{name}", positive=True)
        _validate_decimal(self.atr14, "M15Snapshot.atr14", positive=True)
        for name in ("rsi21", "rsi_ema9", "rsi_wma45"):
            _validate_rsi(getattr(self, name), f"M15Snapshot.{name}")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("M15Snapshot.high must be at least open, close, and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("M15Snapshot.low must be at most open, close, and high")


@dataclass(frozen=True, slots=True)
class M15TrendSnapshot:
    """Timestamped EMA21 source exactly three M15 candles before evaluation."""

    closed_at: datetime
    is_closed: bool
    ema21: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "closed_at",
            _normalize_utc_timestamp(self.closed_at, "M15TrendSnapshot.closed_at"),
        )
        _validate_closed_flag(self.is_closed, "M15TrendSnapshot.is_closed")
        _validate_decimal(self.ema21, "M15TrendSnapshot.ema21", positive=True)


@dataclass(frozen=True, slots=True)
class AltH1Snapshot:
    """Latest point-in-time altcoin H1 RSI confirmation."""

    closed_at: datetime
    is_closed: bool
    rsi21: Decimal
    rsi_ema9: Decimal
    rsi_wma45: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "closed_at",
            _normalize_utc_timestamp(self.closed_at, "AltH1Snapshot.closed_at"),
        )
        _validate_closed_flag(self.is_closed, "AltH1Snapshot.is_closed")
        for name in ("rsi21", "rsi_ema9", "rsi_wma45"):
            _validate_rsi(getattr(self, name), f"AltH1Snapshot.{name}")


@dataclass(frozen=True, slots=True)
class BtcH1Snapshot:
    """Latest point-in-time BTC H1 market-regime values."""

    closed_at: datetime
    is_closed: bool
    close: Decimal
    ema21: Decimal
    rsi21: Decimal
    rsi_ema9: Decimal
    rsi_wma45: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "closed_at",
            _normalize_utc_timestamp(self.closed_at, "BtcH1Snapshot.closed_at"),
        )
        _validate_closed_flag(self.is_closed, "BtcH1Snapshot.is_closed")
        _validate_decimal(self.close, "BtcH1Snapshot.close", positive=True)
        _validate_decimal(self.ema21, "BtcH1Snapshot.ema21", positive=True)
        for name in ("rsi21", "rsi_ema9", "rsi_wma45"):
            _validate_rsi(getattr(self, name), f"BtcH1Snapshot.{name}")


@dataclass(frozen=True, slots=True)
class BtcH4Snapshot:
    """Latest point-in-time BTC H4 strict RSI alignment values."""

    closed_at: datetime
    is_closed: bool
    rsi21: Decimal
    rsi_ema9: Decimal
    rsi_wma45: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "closed_at",
            _normalize_utc_timestamp(self.closed_at, "BtcH4Snapshot.closed_at"),
        )
        _validate_closed_flag(self.is_closed, "BtcH4Snapshot.is_closed")
        for name in ("rsi21", "rsi_ema9", "rsi_wma45"):
            _validate_rsi(getattr(self, name), f"BtcH4Snapshot.{name}")


@dataclass(frozen=True, slots=True)
class EvaluationInput:
    """Complete immutable point-in-time bundle for one M15 evaluation."""

    symbol: str
    venue: Venue
    current_m15: M15Snapshot
    previous_m15: M15Snapshot
    m15_three_bars_ago: M15TrendSnapshot
    alt_h1: AltH1Snapshot
    btc_h1: BtcH1Snapshot
    btc_h4: BtcH4Snapshot

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str):
            raise TypeError("EvaluationInput.symbol must be str")
        if not isinstance(self.venue, Venue):
            raise TypeError("EvaluationInput.venue must be Venue")
        expected_types = (
            ("current_m15", self.current_m15, M15Snapshot),
            ("previous_m15", self.previous_m15, M15Snapshot),
            ("m15_three_bars_ago", self.m15_three_bars_ago, M15TrendSnapshot),
            ("alt_h1", self.alt_h1, AltH1Snapshot),
            ("btc_h1", self.btc_h1, BtcH1Snapshot),
            ("btc_h4", self.btc_h4, BtcH4Snapshot),
        )
        for name, value, expected_type in expected_types:
            if not isinstance(value, expected_type):
                raise TypeError(f"EvaluationInput.{name} must be {expected_type.__name__}")
        expected_venue = VENUE_BY_SYMBOL.get(self.symbol)
        if expected_venue is None:
            raise ValueError(f"{self.symbol!r} is not a Core V2.1 trade candidate")
        if self.venue is not expected_venue:
            raise ValueError(
                f"{self.symbol} belongs to {expected_venue.value}, not {self.venue.value}"
            )
        snapshots = (
            ("current_m15", self.current_m15),
            ("previous_m15", self.previous_m15),
            ("m15_three_bars_ago", self.m15_three_bars_ago),
            ("alt_h1", self.alt_h1),
            ("btc_h1", self.btc_h1),
            ("btc_h4", self.btc_h4),
        )
        unclosed = [name for name, snapshot in snapshots if not snapshot.is_closed]
        if unclosed:
            raise ValueError(f"Core V2.1 accepts fully closed candles only: {', '.join(unclosed)}")
        if self.previous_m15.closed_at != self.current_m15.closed_at - timedelta(minutes=15):
            raise ValueError("previous_m15 must close exactly 15 minutes before current_m15")
        if self.m15_three_bars_ago.closed_at != self.current_m15.closed_at - timedelta(minutes=45):
            raise ValueError(
                "m15_three_bars_ago must close exactly 45 minutes before current_m15"
            )
        future_contexts = [
            name
            for name, snapshot in snapshots[3:]
            if snapshot.closed_at > self.current_m15.closed_at
        ]
        if future_contexts:
            raise ValueError(
                "point-in-time context cannot close after current_m15: "
                + ", ".join(future_contexts)
            )
        if (
            self.current_m15.closed_at.microsecond != 0
            or int(self.current_m15.closed_at.timestamp()) % (15 * 60) != 0
        ):
            raise ValueError("current_m15 must close on the UTC 15-minute grid")
        expected_h1 = _floor_utc_boundary(self.current_m15.closed_at, 60 * 60)
        expected_h4 = _floor_utc_boundary(self.current_m15.closed_at, 4 * 60 * 60)
        if self.alt_h1.closed_at != expected_h1:
            raise ValueError("alt_h1 must be the exact expected fully closed UTC H1 candle")
        if self.btc_h1.closed_at != expected_h1:
            raise ValueError("btc_h1 must be the exact expected fully closed UTC H1 candle")
        if self.btc_h4.closed_at != expected_h4:
            raise ValueError("btc_h4 must be the exact expected fully closed UTC H4 candle")


class CyclePhase(StrEnum):
    ARMED = "ARMED"
    DISARMED = "DISARMED"
    WAITING = "WAITING"


@dataclass(frozen=True, slots=True)
class CoreState:
    """Serializable per-symbol state owned by the coordinator or replay."""

    phase: CyclePhase = CyclePhase.ARMED
    wait_bars_elapsed: int = 0
    cycle_started_at: datetime | None = None
    last_processed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.phase, CyclePhase):
            raise TypeError("CoreState.phase must be CyclePhase")
        if type(self.wait_bars_elapsed) is not int:
            raise TypeError("CoreState.wait_bars_elapsed must be int")
        if self.cycle_started_at is not None:
            object.__setattr__(
                self,
                "cycle_started_at",
                _normalize_utc_timestamp(self.cycle_started_at, "CoreState.cycle_started_at"),
            )
        if self.last_processed_at is not None:
            object.__setattr__(
                self,
                "last_processed_at",
                _normalize_utc_timestamp(self.last_processed_at, "CoreState.last_processed_at"),
            )
        if self.phase is CyclePhase.WAITING:
            if self.cycle_started_at is None:
                raise ValueError("WAITING state requires cycle_started_at")
            if not 0 <= self.wait_bars_elapsed <= 3:
                raise ValueError("WAITING wait_bars_elapsed must be between 0 and 3")
        elif self.wait_bars_elapsed != 0 or self.cycle_started_at is not None:
            raise ValueError("non-WAITING state cannot retain WAIT cycle fields")
        if (
            self.cycle_started_at is not None
            and self.last_processed_at is not None
            and self.cycle_started_at > self.last_processed_at
        ):
            raise ValueError("cycle_started_at cannot follow last_processed_at")

    @classmethod
    def initial(cls) -> CoreState:
        return cls()

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "phase": self.phase.value,
            "wait_bars_elapsed": self.wait_bars_elapsed,
            "cycle_started_at": (
                self.cycle_started_at.isoformat() if self.cycle_started_at is not None else None
            ),
            "last_processed_at": (
                self.last_processed_at.isoformat() if self.last_processed_at is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CoreState:
        required = {
            "phase",
            "wait_bars_elapsed",
            "cycle_started_at",
            "last_processed_at",
        }
        missing = required.difference(payload)
        unknown = set(payload).difference(required)
        if missing or unknown:
            details = []
            if missing:
                details.append(f"missing={sorted(missing)}")
            if unknown:
                details.append(f"unknown={sorted(unknown)}")
            raise ValueError("invalid CoreState payload: " + ", ".join(details))

        def _parse_timestamp(value: object, name: str) -> datetime | None:
            if value is None:
                return None
            if not isinstance(value, str):
                raise TypeError(f"{name} must be an ISO-8601 string or null")
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"{name} is not a valid ISO-8601 timestamp") from exc
            return _normalize_utc_timestamp(parsed, name)

        wait_bars_elapsed = payload["wait_bars_elapsed"]
        if not isinstance(wait_bars_elapsed, int) or isinstance(wait_bars_elapsed, bool):
            raise TypeError("wait_bars_elapsed must be an integer")
        try:
            phase = CyclePhase(payload["phase"])
        except (ValueError, TypeError) as exc:
            raise ValueError(f"unknown CoreState phase: {payload['phase']!r}") from exc
        return cls(
            phase=phase,
            wait_bars_elapsed=wait_bars_elapsed,
            cycle_started_at=_parse_timestamp(payload["cycle_started_at"], "cycle_started_at"),
            last_processed_at=_parse_timestamp(payload["last_processed_at"], "last_processed_at"),
        )


class EventType(StrEnum):
    A_PLUS_LONG = "A_PLUS_LONG"
    WAIT_FOR_PULLBACK = "WAIT_FOR_PULLBACK"
    PULLBACK_LONG = "PULLBACK_LONG"
    WAIT_CANCELLED = "WAIT_CANCELLED"
    WAIT_EXPIRED = "WAIT_EXPIRED"


class DecisionKind(StrEnum):
    QUIET = "QUIET"
    REJECTED = "REJECTED"
    REARMED = "REARMED"
    A_PLUS_LONG = "A_PLUS_LONG"
    WAIT_FOR_PULLBACK = "WAIT_FOR_PULLBACK"
    WAIT_CONTINUES = "WAIT_CONTINUES"
    PULLBACK_LONG = "PULLBACK_LONG"
    WAIT_CANCELLED = "WAIT_CANCELLED"
    WAIT_EXPIRED = "WAIT_EXPIRED"


class ReasonCode(StrEnum):
    M15_CLOSE_NOT_ABOVE_EMA21 = "M15_CLOSE_NOT_ABOVE_EMA21"
    M15_EMA21_NOT_ABOVE_EMA200 = "M15_EMA21_NOT_ABOVE_EMA200"
    M15_EMA21_NOT_RISING = "M15_EMA21_NOT_RISING"
    M15_RSI_NOT_ABOVE_50 = "M15_RSI_NOT_ABOVE_50"
    M15_RSI_NOT_ABOVE_EMA9 = "M15_RSI_NOT_ABOVE_EMA9"
    M15_RSI_NOT_ABOVE_WMA45 = "M15_RSI_NOT_ABOVE_WMA45"
    ALT_H1_RSI_NOT_ABOVE_50 = "ALT_H1_RSI_NOT_ABOVE_50"
    ALT_H1_EMA9_BELOW_WMA45 = "ALT_H1_EMA9_BELOW_WMA45"
    BTC_H1_CLOSE_NOT_ABOVE_EMA21 = "BTC_H1_CLOSE_NOT_ABOVE_EMA21"
    BTC_H1_RSI_NOT_ABOVE_50 = "BTC_H1_RSI_NOT_ABOVE_50"
    BTC_H1_EMA9_BELOW_WMA45 = "BTC_H1_EMA9_BELOW_WMA45"
    BTC_H4_RSI_NOT_ABOVE_EMA9 = "BTC_H4_RSI_NOT_ABOVE_EMA9"
    BTC_H4_EMA9_NOT_ABOVE_WMA45 = "BTC_H4_EMA9_NOT_ABOVE_WMA45"
    PRICE_EXTENDED_FROM_EMA21 = "PRICE_EXTENDED_FROM_EMA21"
    SIGNAL_CANDLE_TOO_LARGE = "SIGNAL_CANDLE_TOO_LARGE"
    CANCEL_M15_CLOSE_BELOW_EMA21 = "CANCEL_M15_CLOSE_BELOW_EMA21"
    CANCEL_M15_RSI_BELOW_50 = "CANCEL_M15_RSI_BELOW_50"
    CANCEL_M15_EMA9_NOT_ABOVE_WMA45 = "CANCEL_M15_EMA9_NOT_ABOVE_WMA45"
    CANCEL_BTC_H1_CLOSE_NOT_ABOVE_EMA21 = "CANCEL_BTC_H1_CLOSE_NOT_ABOVE_EMA21"
    CANCEL_BTC_H1_RSI_NOT_ABOVE_50 = "CANCEL_BTC_H1_RSI_NOT_ABOVE_50"
    CANCEL_BTC_H1_EMA9_BELOW_WMA45 = "CANCEL_BTC_H1_EMA9_BELOW_WMA45"
    CANCEL_BTC_H4_RSI_NOT_ABOVE_EMA9 = "CANCEL_BTC_H4_RSI_NOT_ABOVE_EMA9"
    CANCEL_BTC_H4_EMA9_NOT_ABOVE_WMA45 = "CANCEL_BTC_H4_EMA9_NOT_ABOVE_WMA45"


def _validate_reasons(value: tuple[ReasonCode, ...], field_name: str) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    if not all(isinstance(reason, ReasonCode) for reason in value):
        raise TypeError(f"{field_name} must contain only ReasonCode values")


@dataclass(frozen=True, slots=True)
class SignalMetrics:
    distance_atr: Decimal
    signal_range_atr: Decimal

    def __post_init__(self) -> None:
        _validate_decimal(self.distance_atr, "SignalMetrics.distance_atr")
        _validate_decimal(self.signal_range_atr, "SignalMetrics.signal_range_atr")
        if self.signal_range_atr < 0:
            raise ValueError("SignalMetrics.signal_range_atr cannot be negative")


@dataclass(frozen=True, slots=True)
class PreferredEntryZone:
    lower: Decimal
    upper: Decimal

    def __post_init__(self) -> None:
        _validate_decimal(self.lower, "PreferredEntryZone.lower", positive=True)
        _validate_decimal(self.upper, "PreferredEntryZone.upper", positive=True)
        if self.upper < self.lower:
            raise ValueError("PreferredEntryZone.upper cannot be below lower")


@dataclass(frozen=True, slots=True)
class TradeLevels:
    reference_entry: Decimal
    reference_stop: Decimal
    risk_1r: Decimal
    tp1: Decimal
    tp2: Decimal
    tp3: Decimal

    def __post_init__(self) -> None:
        for name in ("reference_entry", "risk_1r", "tp1", "tp2", "tp3"):
            _validate_decimal(getattr(self, name), f"TradeLevels.{name}", positive=True)
        # The reviewer-approved formula is exact: low - 0.25 * ATR14.  On an
        # extreme candle that advisory reference can be zero or negative.
        # Do not silently floor it or crash an otherwise valid setup.
        _validate_decimal(self.reference_stop, "TradeLevels.reference_stop")
        if self.reference_stop >= self.reference_entry:
            raise ValueError("long reference_stop must be below reference_entry")
        if not self.reference_entry < self.tp1 < self.tp2 < self.tp3:
            raise ValueError("long take-profit levels must be strictly increasing")


@dataclass(frozen=True, slots=True)
class CoreEvent:
    event_type: EventType
    symbol: str
    venue: Venue
    closed_at: datetime
    reasons: tuple[ReasonCode, ...] = ()
    trade_levels: TradeLevels | None = None
    preferred_entry_zone: PreferredEntryZone | None = None
    wait_bars_elapsed: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, EventType):
            raise TypeError("CoreEvent.event_type must be EventType")
        if not isinstance(self.symbol, str):
            raise TypeError("CoreEvent.symbol must be str")
        if not isinstance(self.venue, Venue):
            raise TypeError("CoreEvent.venue must be Venue")
        _validate_reasons(self.reasons, "CoreEvent.reasons")
        if self.trade_levels is not None and not isinstance(self.trade_levels, TradeLevels):
            raise TypeError("CoreEvent.trade_levels must be TradeLevels or None")
        if self.preferred_entry_zone is not None and not isinstance(
            self.preferred_entry_zone,
            PreferredEntryZone,
        ):
            raise TypeError(
                "CoreEvent.preferred_entry_zone must be PreferredEntryZone or None"
            )
        if self.wait_bars_elapsed is not None and type(self.wait_bars_elapsed) is not int:
            raise TypeError("CoreEvent.wait_bars_elapsed must be int or None")
        object.__setattr__(
            self,
            "closed_at",
            _normalize_utc_timestamp(self.closed_at, "CoreEvent.closed_at"),
        )
        if self.symbol not in VENUE_BY_SYMBOL:
            raise ValueError(f"{self.symbol!r} is not a Core V2.1 trade candidate")
        if VENUE_BY_SYMBOL[self.symbol] is not self.venue:
            raise ValueError("CoreEvent venue does not match symbol")
        if self.wait_bars_elapsed is not None and not 0 <= self.wait_bars_elapsed <= 4:
            raise ValueError("CoreEvent.wait_bars_elapsed must be between 0 and 4")
        if self.event_type is EventType.A_PLUS_LONG:
            if self.trade_levels is None:
                raise ValueError("A_PLUS_LONG requires trade_levels")
            if self.preferred_entry_zone is not None or self.wait_bars_elapsed is not None:
                raise ValueError("A_PLUS_LONG cannot contain WAIT-only fields")
        elif self.event_type is EventType.PULLBACK_LONG:
            if self.trade_levels is None:
                raise ValueError("PULLBACK_LONG requires trade_levels")
            if self.preferred_entry_zone is not None:
                raise ValueError("PULLBACK_LONG cannot contain a preferred entry zone")
            if self.wait_bars_elapsed is None or not 1 <= self.wait_bars_elapsed <= 4:
                raise ValueError("PULLBACK_LONG requires the confirming WAIT candle number")
        elif self.event_type is EventType.WAIT_FOR_PULLBACK:
            if self.trade_levels is not None or self.preferred_entry_zone is None:
                raise ValueError("WAIT_FOR_PULLBACK requires a zone and cannot contain trade levels")
            if self.wait_bars_elapsed != 0:
                raise ValueError("WAIT_FOR_PULLBACK must start with wait_bars_elapsed=0")
            if not self.reasons:
                raise ValueError("WAIT_FOR_PULLBACK requires at least one anti-chase reason")
        elif self.event_type is EventType.WAIT_CANCELLED:
            if self.trade_levels is not None or self.preferred_entry_zone is not None:
                raise ValueError("WAIT_CANCELLED cannot contain trade or zone fields")
            if self.wait_bars_elapsed is None or self.wait_bars_elapsed < 1:
                raise ValueError("WAIT_CANCELLED requires a positive wait_bars_elapsed")
            if not self.reasons:
                raise ValueError("WAIT_CANCELLED requires at least one reason")
        elif self.event_type is EventType.WAIT_EXPIRED:
            if self.trade_levels is not None or self.preferred_entry_zone is not None:
                raise ValueError("WAIT_EXPIRED cannot contain trade or zone fields")
            if self.wait_bars_elapsed != 4:
                raise ValueError("WAIT_EXPIRED must occur on WAIT candle 4")


@dataclass(frozen=True, slots=True)
class CoreDecision:
    kind: DecisionKind
    reasons: tuple[ReasonCode, ...] = ()
    event: CoreEvent | None = None
    metrics: SignalMetrics | None = None
    preferred_entry_zone: PreferredEntryZone | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DecisionKind):
            raise TypeError("CoreDecision.kind must be DecisionKind")
        _validate_reasons(self.reasons, "CoreDecision.reasons")
        if self.event is not None and not isinstance(self.event, CoreEvent):
            raise TypeError("CoreDecision.event must be CoreEvent or None")
        if self.metrics is not None and not isinstance(self.metrics, SignalMetrics):
            raise TypeError("CoreDecision.metrics must be SignalMetrics or None")
        if self.preferred_entry_zone is not None and not isinstance(
            self.preferred_entry_zone,
            PreferredEntryZone,
        ):
            raise TypeError(
                "CoreDecision.preferred_entry_zone must be PreferredEntryZone or None"
            )
        event_kinds = {
            DecisionKind.A_PLUS_LONG,
            DecisionKind.WAIT_FOR_PULLBACK,
            DecisionKind.PULLBACK_LONG,
            DecisionKind.WAIT_CANCELLED,
            DecisionKind.WAIT_EXPIRED,
        }
        if (self.kind in event_kinds) != (self.event is not None):
            raise ValueError("event presence must match the event-producing decision kind")
        if self.event is not None and self.event.event_type.value != self.kind.value:
            raise ValueError("decision kind must match event type")
        if self.event is not None and self.reasons != self.event.reasons:
            raise ValueError("decision and event reasons must match")
        if self.kind is DecisionKind.WAIT_CONTINUES:
            if self.preferred_entry_zone is None:
                raise ValueError("WAIT_CONTINUES requires a current preferred entry zone")
        elif self.kind is not DecisionKind.WAIT_FOR_PULLBACK and self.preferred_entry_zone is not None:
            raise ValueError("preferred entry zone is only valid for WAIT decisions")


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    decision: CoreDecision
    next_state: CoreState

    def __post_init__(self) -> None:
        if not isinstance(self.decision, CoreDecision):
            raise TypeError("EvaluationResult.decision must be CoreDecision")
        if not isinstance(self.next_state, CoreState):
            raise TypeError("EvaluationResult.next_state must be CoreState")
