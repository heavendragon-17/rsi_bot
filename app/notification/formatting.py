"""Shared Telegram message formatting helpers.

Two knobs control how precise displayed prices and sizes are. Each is a
relative-precision %: the last visible digit should represent at most that
fraction of the value.

* ``PRICE_PRECISION_PCT`` — for entry / exit / SL / TP / fill prices.
  Finer (0.01%) so you can read the exact level. At this setting BTC shows
  2 dp, SOL 4 dp, API3 5 dp, ZIL 7 dp.
* ``SIZE_PRECISION_PCT`` — for size / amount / closed quantities. Looser
  (1%) so cards don't drown in amount-digit noise; notional USD figures
  always stay at 2 dp regardless.
"""

from __future__ import annotations

import math
from decimal import Decimal

PRICE_PRECISION_PCT: float = 0.01   # last price digit ≈ 0.01% of value → "exact"
SIZE_PRECISION_PCT: float = 1.0     # last size digit ≈ 1% of amount → readable
_MIN_DECIMALS = 2
_MAX_DECIMALS = 10


def mono(text: str) -> str:
    """Wrap text in HTML <pre> tags for monospace rendering."""
    return f"<pre>{text}</pre>"


def row(label: str, value: str, width: int = 14) -> str:
    """Format a label-value row with fixed-width label."""
    return f"{label:<{width}} {value}"


def fmt_price(p: Decimal) -> str:
    return f"${float(p):,.2f}"


def fmt_price_precise(p: Decimal) -> str:
    """Format price preserving full Decimal precision, for copy-trade values."""
    d = Decimal(str(p))
    exp = d.as_tuple().exponent
    decimals = max(2, -exp) if isinstance(exp, int) and exp < 0 else 2
    return f"${float(d):,.{decimals}f}"


def fmt_amount_precise(a: Decimal) -> str:
    """Format size/amount preserving full Decimal precision, for copy-trade values."""
    d = Decimal(str(a))
    exp = d.as_tuple().exponent
    decimals = max(2, -exp) if isinstance(exp, int) and exp < 0 else 2
    return f"{float(d):,.{decimals}f}"


def _decimals_for(value: float, precision_pct: float, min_decimals: int = _MIN_DECIMALS) -> int:
    """Decimals such that the last digit ≈ ``precision_pct`` % of ``value``.

    ``decimals = ceil(-log10(value × precision_pct/100))``, clamped to
    ``[min_decimals, _MAX_DECIMALS]``.
    """
    if value <= 0 or precision_pct <= 0:
        return min_decimals
    raw = math.ceil(-math.log10(value * precision_pct / 100.0))
    return max(min_decimals, min(_MAX_DECIMALS, raw))


def fmt_price_auto(price: Decimal) -> str:
    """Format a token *unit price* with dynamic decimals.

    Use for entry, SL, TP, and fill prices — not for USD notional or balance
    (those stay at 2 dp via ``fmt_price``). Precision is controlled by
    ``PRICE_PRECISION_PCT``.
    """
    try:
        p = float(price)
    except (TypeError, ValueError):
        return f"${float(price or 0):,.2f}"
    decimals = _decimals_for(p, PRICE_PRECISION_PCT)
    return f"${p:,.{decimals}f}"


def fmt_amount_auto(amount: Decimal, price: Decimal | None = None) -> str:
    """Format a size/amount with dynamic decimals.

    Decimals are picked so the last visible digit represents at most
    ``SIZE_PRECISION_PCT`` % of the amount. For amounts ≥ 100 the min-decimals
    floor is lifted (no need to pad ``3,333,333.00``). ``price`` is kept in
    the signature for call-site backwards compat but ignored.
    """
    try:
        a = float(amount)
    except (TypeError, ValueError):
        return "0"
    abs_a = abs(a) if a else 1.0
    min_dp = 0 if abs_a >= 100 else _MIN_DECIMALS
    decimals = _decimals_for(abs_a, SIZE_PRECISION_PCT, min_decimals=min_dp)
    return f"{a:,.{decimals}f}"


def fmt_pct(p: Decimal) -> str:
    sign = "+" if p >= 0 else ""
    return f"{sign}{float(p):.2f}%"


def fmt_pnl(p: Decimal) -> str:
    sign = "+" if p >= 0 else ""
    return f"{sign}{float(p):,.2f}"


def fmt_duration(seconds: float) -> str:
    """Format seconds as human-readable duration like '2h 15m' or '3d 1h'."""
    if seconds < 0:
        return "0m"
    total_minutes = int(seconds // 60)
    if total_minutes < 60:
        return f"{total_minutes}m"
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if hours < 24:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    days = hours // 24
    rem_hours = hours % 24
    return f"{days}d {rem_hours}h" if rem_hours else f"{days}d"
