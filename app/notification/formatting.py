"""Shared Telegram message formatting helpers."""

from __future__ import annotations

from decimal import Decimal


def mono(text: str) -> str:
    """Wrap text in HTML <pre> tags for monospace rendering."""
    return f"<pre>{text}</pre>"


def row(label: str, value: str, width: int = 14) -> str:
    """Format a label-value row with fixed-width label."""
    return f"{label:<{width}} {value}"


def fmt_price(p: Decimal) -> str:
    return f"${float(p):,.2f}"


def fmt_pct(p: Decimal) -> str:
    sign = "+" if p >= 0 else ""
    return f"{sign}{float(p):.2f}%"


def fmt_pnl(p: Decimal) -> str:
    sign = "+" if p >= 0 else ""
    return f"{sign}{float(p):,.2f}"
