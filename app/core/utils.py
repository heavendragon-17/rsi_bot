from decimal import Decimal
from typing import Optional


def to_decimal(val) -> Decimal:
    """Convert any numeric to Decimal. Returns Decimal("0") for None."""
    if val is None:
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


def to_decimal_or_none(val) -> Optional[Decimal]:
    """Convert any numeric to Decimal, preserving None.

    Use this when None carries semantic meaning (e.g. "no price available").
    """
    if val is None:
        return None
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))
