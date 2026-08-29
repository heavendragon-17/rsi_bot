"""Typed public models for the historical BTC signal replay."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.trading.strategy.btc_rsi_cross_alert.models import (
    BtcRsiCrossDecision,
    BtcRsiCrossInput,
)


class SignalReplayInputError(ValueError):
    """Raised when a historical replay CSV cannot be safely consumed."""


@dataclass(frozen=True)
class ReplayTriggerEvent:
    """One M5 or M15 candle-close event in chronological replay order."""

    timeframe: str
    open_time: datetime
    close_time: datetime
    position: int | None = None


@dataclass(frozen=True)
class ReplaySignal:
    """One confirmed replay signal and its exact Telegram card snapshot."""

    sequence: int
    timeframe: str
    data: BtcRsiCrossInput
    decision: BtcRsiCrossDecision
    telegram_card: str


@dataclass(frozen=True)
class ReplayCounts:
    """Counters that explain how the replay reached its confirmed signals."""

    m5_candidates: int
    m15_candidates: int
    m5_not_ready: int
    m15_not_ready: int
    m5_rejected: int
    m15_rejected: int
    m5_cooldown_suppressed: int
    duplicate_suppressed: int
    m5_warmup_skipped: int = 0
    m15_warmup_skipped: int = 0
    m15_cooldown_suppressed: int = 0

    @property
    def candidates(self) -> int:
        """Total M5 and M15 trigger candles in the requested window."""

        return self.m5_candidates + self.m15_candidates

    @property
    def not_ready(self) -> int:
        """Total trigger candles without enough valid point-in-time data."""

        return self.m5_not_ready + self.m15_not_ready

    @property
    def rejected(self) -> int:
        """Total prepared candles that did not satisfy their signal rules."""

        return self.m5_rejected + self.m15_rejected

    @property
    def warmup_skipped(self) -> int:
        """Total initial candles skipped before all indicators were ready."""

        return self.m5_warmup_skipped + self.m15_warmup_skipped


@dataclass(frozen=True)
class ReplayResult:
    """Result of one historical BTC alert replay."""

    signals: tuple[ReplaySignal, ...]
    counts: ReplayCounts
    start_utc7: datetime | None
    end_utc7: datetime | None
    generated_at_utc7: datetime
    output_path: Path | None = None
    output_m5_path: Path | None = None
    output_m15_path: Path | None = None

    @property
    def output_paths(self) -> tuple[Path, ...]:
        """Paths written by the replay, in deterministic display order."""

        return tuple(
            path
            for path in (self.output_path, self.output_m5_path, self.output_m15_path)
            if path is not None
        )
