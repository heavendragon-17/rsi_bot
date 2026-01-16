from decimal import Decimal

def to_decimal(val) -> Decimal:
    """Convert any numeric to Decimal."""
    if val is None:
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))
