"""Shared validation primitives for Core V2.1 immutable models."""

from datetime import UTC, datetime
from decimal import Decimal


def normalize_utc_timestamp(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def validate_closed_flag(value: bool, field_name: str) -> None:
    if type(value) is not bool:
        raise TypeError(f"{field_name} must be bool")


def validate_decimal(value: Decimal, field_name: str, *, positive: bool = False) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if positive and value <= 0:
        raise ValueError(f"{field_name} must be positive")


def validate_rsi(value: Decimal, field_name: str) -> None:
    validate_decimal(value, field_name)
    if value < 0 or value > 100:
        raise ValueError(f"{field_name} must be between 0 and 100")


def floor_utc_boundary(value: datetime, seconds: int) -> datetime:
    epoch_seconds = int(value.timestamp())
    return datetime.fromtimestamp((epoch_seconds // seconds) * seconds, tz=UTC)
