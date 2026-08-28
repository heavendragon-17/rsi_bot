"""Frozen domain models and deterministic identities for the BTC RSI cross alert.

Pure domain layer: identical inputs produce identical outputs. No clocks,
threads, network, filesystem, database, logging, Telegram, sleep, or mutable
global state live here. Runtime orchestration belongs to
``app.signal.btc_rsi_cross_alert``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Final

COMPONENT_NAME: Final[str] = "btc_rsi_cross_alert"

EVENT_ID_PREFIX: Final[str] = "btc-rsi-cross-v1"
EVENT_ID_SEPARATOR: Final[str] = "|"
EVENT_ID_SUFFIX_LENGTH: Final[int] = 8
M5_ALERT_COOLDOWN: Final[timedelta] = timedelta(hours=1)

# ---------------------------------------------------------------------------
# Exact preparation reasons (spec §10)
# ---------------------------------------------------------------------------
PREPARATION_READY: Final[str] = "READY"
TRIGGER_UNSUPPORTED_TIMEFRAME: Final[str] = "TRIGGER_UNSUPPORTED_TIMEFRAME"
TRIGGER_CURRENT_ROW_MISSING: Final[str] = "TRIGGER_CURRENT_ROW_MISSING"
TRIGGER_INSUFFICIENT_CONTIGUOUS_HISTORY: Final[str] = (
    "TRIGGER_INSUFFICIENT_CONTIGUOUS_HISTORY"
)
TRIGGER_DUPLICATE_OR_NON_INCREASING_TIME: Final[str] = (
    "TRIGGER_DUPLICATE_OR_NON_INCREASING_TIME"
)
TRIGGER_NON_FINITE_DATA: Final[str] = "TRIGGER_NON_FINITE_DATA"
H4_EXPECTED_CLOSE_MISSING: Final[str] = "H4_EXPECTED_CLOSE_MISSING"
H4_LIVE_CLOSE_UNCONFIRMED: Final[str] = "H4_LIVE_CLOSE_UNCONFIRMED"
H4_INSUFFICIENT_CONTIGUOUS_HISTORY: Final[str] = (
    "H4_INSUFFICIENT_CONTIGUOUS_HISTORY"
)
H4_DUPLICATE_OR_NON_INCREASING_TIME: Final[str] = (
    "H4_DUPLICATE_OR_NON_INCREASING_TIME"
)
H4_NON_FINITE_DATA: Final[str] = "H4_NON_FINITE_DATA"
H1_EXPECTED_CLOSE_MISSING: Final[str] = "H1_EXPECTED_CLOSE_MISSING"
H1_LIVE_CLOSE_UNCONFIRMED: Final[str] = "H1_LIVE_CLOSE_UNCONFIRMED"
H1_INSUFFICIENT_CONTIGUOUS_HISTORY: Final[str] = (
    "H1_INSUFFICIENT_CONTIGUOUS_HISTORY"
)
H1_DUPLICATE_OR_NON_INCREASING_TIME: Final[str] = (
    "H1_DUPLICATE_OR_NON_INCREASING_TIME"
)
H1_NON_FINITE_DATA: Final[str] = "H1_NON_FINITE_DATA"

PREPARATION_REASONS: Final[frozenset[str]] = frozenset(
    {
        PREPARATION_READY,
        TRIGGER_UNSUPPORTED_TIMEFRAME,
        TRIGGER_CURRENT_ROW_MISSING,
        TRIGGER_INSUFFICIENT_CONTIGUOUS_HISTORY,
        TRIGGER_DUPLICATE_OR_NON_INCREASING_TIME,
        TRIGGER_NON_FINITE_DATA,
        H4_EXPECTED_CLOSE_MISSING,
        H4_LIVE_CLOSE_UNCONFIRMED,
        H4_INSUFFICIENT_CONTIGUOUS_HISTORY,
        H4_DUPLICATE_OR_NON_INCREASING_TIME,
        H4_NON_FINITE_DATA,
        H1_EXPECTED_CLOSE_MISSING,
        H1_LIVE_CLOSE_UNCONFIRMED,
        H1_INSUFFICIENT_CONTIGUOUS_HISTORY,
        H1_DUPLICATE_OR_NON_INCREASING_TIME,
        H1_NON_FINITE_DATA,
    }
)

# Exact decision reasons (spec §10)
DECISION_ALERT_FRESH_BULLISH_CROSS_H4_BULLISH: Final[str] = (
    "ALERT_FRESH_BULLISH_CROSS_H4_BULLISH"
)
DECISION_ALERT_M5_BULLISH_ALIGNMENT_H4_BULLISH: Final[str] = (
    "ALERT_M5_BULLISH_ALIGNMENT_H4_BULLISH"
)
DECISION_NO_FRESH_BULLISH_CROSS: Final[str] = "NO_FRESH_BULLISH_CROSS"
DECISION_H4_CLOSE_NOT_ABOVE_EMA21: Final[str] = "H4_CLOSE_NOT_ABOVE_EMA21"
DECISION_M5_RSI_ALIGNMENT_NOT_BULLISH: Final[str] = (
    "M5_RSI21_EMA9_WMA45_ALIGNMENT_NOT_BULLISH"
)
DECISION_M5_EMA_WMA_SPREAD_NOT_ABOVE_2: Final[str] = (
    "M5_EMA9_WMA45_SPREAD_NOT_ABOVE_2"
)
DECISION_M5_WMA45_NOT_ABOVE_45: Final[str] = "M5_WMA45_NOT_ABOVE_45"
DECISION_M5_CLOSE_NOT_ABOVE_EMA21: Final[str] = "M5_CLOSE_NOT_ABOVE_EMA21"
DECISION_M15_CLOSE_NOT_ABOVE_EMA21: Final[str] = "M15_CLOSE_NOT_ABOVE_EMA21"
DECISION_H1_CLOSE_NOT_ABOVE_EMA21: Final[str] = "H1_CLOSE_NOT_ABOVE_EMA21"
DECISION_M5_RSI21_NOT_BELOW_60: Final[str] = "M5_RSI21_NOT_BELOW_60"

DECISION_REASONS: Final[frozenset[str]] = frozenset(
    {
        DECISION_ALERT_FRESH_BULLISH_CROSS_H4_BULLISH,
        DECISION_ALERT_M5_BULLISH_ALIGNMENT_H4_BULLISH,
        DECISION_NO_FRESH_BULLISH_CROSS,
        DECISION_H4_CLOSE_NOT_ABOVE_EMA21,
        DECISION_M5_RSI_ALIGNMENT_NOT_BULLISH,
        DECISION_M5_EMA_WMA_SPREAD_NOT_ABOVE_2,
        DECISION_M5_WMA45_NOT_ABOVE_45,
        DECISION_M5_CLOSE_NOT_ABOVE_EMA21,
        DECISION_M15_CLOSE_NOT_ABOVE_EMA21,
        DECISION_H1_CLOSE_NOT_ABOVE_EMA21,
        DECISION_M5_RSI21_NOT_BELOW_60,
    }
)


@dataclass(frozen=True)
class RsiBundlePoint:
    """One finite RSI21 / EMA9(RSI21) / WMA45(RSI21) triple."""

    rsi21: float
    rsi_ema9: float
    rsi_wma45: float


@dataclass(frozen=True)
class BtcRsiCrossInput:
    """Fully prepared, point-in-time inputs for one trigger evaluation."""

    symbol: str
    trigger_timeframe: str
    trigger_close_time: datetime
    trigger_close_price: Decimal
    trigger_price_ema21: Decimal
    previous_trigger: RsiBundlePoint
    current_trigger: RsiBundlePoint
    h1_close_price: Decimal
    h1_price_ema21: Decimal
    h1_close_time: datetime
    h4_close_price: Decimal
    h4_price_ema21: Decimal
    h4_close_time: datetime


@dataclass(frozen=True)
class BtcRsiCrossDecision:
    """Outcome of the pure decision function for one input."""

    should_alert: bool
    event_id: str
    reason: str


@dataclass(frozen=True)
class BtcRsiCrossPreparation:
    """Result of pure preparation.

    ``input`` is non-``None`` if and only if ``reason == "READY"``.
    """

    input: BtcRsiCrossInput | None
    reason: str


def _require_aware_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _format_event_timestamp(value: datetime) -> str:
    utc = _require_aware_utc(value, "trigger_close_time")
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_event_id(
    *,
    symbol: str,
    trigger_timeframe: str,
    trigger_close_time: datetime,
) -> str:
    """Deterministic event identity (spec §10).

    Canonical string::

        btc-rsi-cross-v1 | BTC/USDT | trigger timeframe | UTC trigger close time

    The stored ID is the SHA-256 hex digest of that canonical string.
    """

    canonical = EVENT_ID_SEPARATOR.join(
        (
            EVENT_ID_PREFIX,
            symbol,
            trigger_timeframe,
            _format_event_timestamp(trigger_close_time),
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def event_id_suffix(event_id: str, length: int = EVENT_ID_SUFFIX_LENGTH) -> str:
    """Short recognizable suffix for Telegram display."""

    if not isinstance(event_id, str) or not event_id:
        raise ValueError("event_id must be a non-empty string")
    if length <= 0:
        raise ValueError("length must be positive")
    return event_id[:length]
