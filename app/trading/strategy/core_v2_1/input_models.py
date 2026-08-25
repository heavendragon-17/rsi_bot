"""Immutable point-in-time inputs for the pure Core V2.1 evaluator."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from .config import VENUE_BY_SYMBOL, Venue
from .model_validation import (
    floor_utc_boundary,
    normalize_utc_timestamp,
    validate_closed_flag,
    validate_decimal,
    validate_rsi,
)


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
            normalize_utc_timestamp(self.closed_at, "M15Snapshot.closed_at"),
        )
        validate_closed_flag(self.is_closed, "M15Snapshot.is_closed")
        for name in ("open", "high", "low", "close", "ema21", "ema200"):
            validate_decimal(getattr(self, name), f"M15Snapshot.{name}", positive=True)
        validate_decimal(self.atr14, "M15Snapshot.atr14", positive=True)
        for name in ("rsi21", "rsi_ema9", "rsi_wma45"):
            validate_rsi(getattr(self, name), f"M15Snapshot.{name}")
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
            normalize_utc_timestamp(self.closed_at, "M15TrendSnapshot.closed_at"),
        )
        validate_closed_flag(self.is_closed, "M15TrendSnapshot.is_closed")
        validate_decimal(self.ema21, "M15TrendSnapshot.ema21", positive=True)


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
            normalize_utc_timestamp(self.closed_at, "AltH1Snapshot.closed_at"),
        )
        validate_closed_flag(self.is_closed, "AltH1Snapshot.is_closed")
        for name in ("rsi21", "rsi_ema9", "rsi_wma45"):
            validate_rsi(getattr(self, name), f"AltH1Snapshot.{name}")


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
            normalize_utc_timestamp(self.closed_at, "BtcH1Snapshot.closed_at"),
        )
        validate_closed_flag(self.is_closed, "BtcH1Snapshot.is_closed")
        validate_decimal(self.close, "BtcH1Snapshot.close", positive=True)
        validate_decimal(self.ema21, "BtcH1Snapshot.ema21", positive=True)
        for name in ("rsi21", "rsi_ema9", "rsi_wma45"):
            validate_rsi(getattr(self, name), f"BtcH1Snapshot.{name}")


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
            normalize_utc_timestamp(self.closed_at, "BtcH4Snapshot.closed_at"),
        )
        validate_closed_flag(self.is_closed, "BtcH4Snapshot.is_closed")
        for name in ("rsi21", "rsi_ema9", "rsi_wma45"):
            validate_rsi(getattr(self, name), f"BtcH4Snapshot.{name}")


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
            raise ValueError(f"{self.symbol} belongs to {expected_venue.value}, not {self.venue.value}")
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
            raise ValueError("m15_three_bars_ago must close exactly 45 minutes before current_m15")
        future_contexts = [
            name
            for name, snapshot in snapshots[3:]
            if snapshot.closed_at > self.current_m15.closed_at
        ]
        if future_contexts:
            raise ValueError(
                "point-in-time context cannot close after current_m15: " + ", ".join(future_contexts)
            )
        if (
            self.current_m15.closed_at.microsecond != 0
            or int(self.current_m15.closed_at.timestamp()) % (15 * 60) != 0
        ):
            raise ValueError("current_m15 must close on the UTC 15-minute grid")
        expected_h1 = floor_utc_boundary(self.current_m15.closed_at, 60 * 60)
        expected_h4 = floor_utc_boundary(self.current_m15.closed_at, 4 * 60 * 60)
        if self.alt_h1.closed_at != expected_h1:
            raise ValueError("alt_h1 must be the exact expected fully closed UTC H1 candle")
        if self.btc_h1.closed_at != expected_h1:
            raise ValueError("btc_h1 must be the exact expected fully closed UTC H1 candle")
        if self.btc_h4.closed_at != expected_h4:
            raise ValueError("btc_h4 must be the exact expected fully closed UTC H4 candle")
