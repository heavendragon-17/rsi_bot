"""Pure Telegram card formatting for Core V2.1 advisory events."""

from __future__ import annotations

from decimal import Decimal
from html import escape

from app.signal.core_v2_1.models import AdvisoryEvent, AdvisoryEventType, Venue

_HEADERS: dict[AdvisoryEventType, tuple[str, str]] = {
    AdvisoryEventType.A_PLUS_LONG: ("🟢", "A+ LONG"),
    AdvisoryEventType.WAIT_FOR_PULLBACK: ("🟡", "WAIT FOR PULLBACK"),
    AdvisoryEventType.PULLBACK_LONG: ("🟢", "PULLBACK LONG"),
    AdvisoryEventType.WAIT_CANCELLED: ("⚪", "WAIT CANCELLED"),
    AdvisoryEventType.WAIT_EXPIRED: ("⌛", "WAIT EXPIRED"),
}


def format_core_v2_1_event(event: AdvisoryEvent) -> str:
    """Render a deterministic HTML-safe Telegram advisory.

    Signal levels always use the evaluator's reference values.  The formatter
    never implies that the signal-only runtime placed or filled an order.
    """

    emoji, title = _HEADERS[event.event_type]
    venue = (
        "Binance Futures"
        if event.venue is Venue.BINANCE_FUTURES
        else "Hyperliquid Perp"
    )
    lines = [
        f"{emoji} <b>CORE V2.1 · {title}</b>",
        f"Symbol: <code>{escape(event.symbol)}</code>",
        f"Venue: {venue}",
        f"M15 close: <code>{event.closed_at:%Y-%m-%d %H:%M} UTC</code>",
    ]

    if event.event_type in (
        AdvisoryEventType.A_PLUS_LONG,
        AdvisoryEventType.PULLBACK_LONG,
    ):
        lines.extend(_format_reference_levels(event))
        lines.append("Advisory only — no order was placed.")
    elif event.event_type is AdvisoryEventType.WAIT_FOR_PULLBACK:
        if event.zone_low is not None and event.zone_high is not None:
            lines.append(
                "Pullback zone: "
                f"<code>{_price(event.zone_low)} – {_price(event.zone_high)}</code>"
            )
        elapsed = event.wait_elapsed if event.wait_elapsed is not None else 0
        lines.append(f"WAIT candle: {elapsed}/4")
        lines.append("Monitoring fully closed M15 candles; no entry yet.")
    elif event.event_type is AdvisoryEventType.WAIT_CANCELLED:
        lines.append("The pending setup is cancelled; no entry was issued.")
    else:
        lines.append("The four-candle pullback window expired; no entry was issued.")

    if event.reasons:
        lines.append("Reason: " + escape(", ".join(event.reasons)))
    return "\n".join(lines)


def _format_reference_levels(event: AdvisoryEvent) -> list[str]:
    labels = (
        ("Reference entry", event.reference_entry),
        ("Reference SL", event.reference_stop),
        ("TP1 (1R)", event.reference_tp1),
        ("TP2 (2R)", event.reference_tp2),
        ("TP3 (3R)", event.reference_tp3),
    )
    return [
        f"{label}: <code>{_price(value)}</code>"
        for label, value in labels
        if value is not None
    ]


def _price(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
