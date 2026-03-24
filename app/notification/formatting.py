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
