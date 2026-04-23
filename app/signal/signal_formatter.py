"""Plain-text message templates for the signal bot.

Every function is pure and returns plain text (no HTML). The signal bot's
`NotificationService.send_message(..., topic_id=...)` posts these verbatim
to the strategy's Telegram topic (or the debug topic for infra messages).

Staying plain-text sidesteps Markdown/HTML-escaping concerns for values
that originate from config or exchange payloads.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.events import Candle
from app.signal.virtual_position import VirtualPosition

_TP_LABELS = ("TP1", "TP2", "TP3", "TP4", "TP5")


def _fmt_price(value: Decimal) -> str:
    """Render a price with up to 8 decimals, trailing zeros trimmed."""
    s = format(value.normalize(), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def _side_emoji(side: str) -> str:
    return "🟢" if side == "LONG" else "🔴"


def _tp_label(tp_index: int) -> str:
    if 0 <= tp_index < len(_TP_LABELS):
        return _TP_LABELS[tp_index]
    return f"TP{tp_index + 1}"


def _header(vp: VirtualPosition, emoji: str, label: str) -> str:
    """Canonical ``[strategy] EMOJI LABEL — SIDE SYMBOL  (signal_id)`` header."""
    return (
        f"[{vp.strategy_name}] {emoji} {label} — {vp.side} {vp.symbol}  "
        f"({vp.signal_id})"
    )


def format_entry(vp: VirtualPosition) -> str:
    lines = [
        f"[{vp.strategy_name}] {_side_emoji(vp.side)} {vp.side} {vp.symbol}  ({vp.signal_id})",
        f"Entry: {_fmt_price(vp.entry_price)}",
        f"SL:    {_fmt_price(vp.sl_price)}  (candle-close)",
    ]
    for i, tp in enumerate(vp.tp_levels):
        lines.append(f"{_tp_label(i)}:   {_fmt_price(tp)}")
    return "\n".join(lines)


def format_sl_hit(vp: VirtualPosition, candle: Candle) -> str:
    return (
        f"{_header(vp, '🛑', 'EXIT advice')}\n"
        f"{vp.timeframe} candle closed at {_fmt_price(candle.close)} "
        f"(beyond SL {_fmt_price(vp.sl_price)})\n"
        "If still in this trade, consider closing."
    )


def format_tp_hit(
    vp: VirtualPosition,
    tp_index: int,
    tp_price: Decimal,
    candle: Candle,
) -> str:
    label = _tp_label(tp_index)
    extremum = candle.high if vp.side == "LONG" else candle.low
    return (
        f"{_header(vp, '🎯', f'{label} hit')}\n"
        f"Price reached {_fmt_price(tp_price)} "
        f"({'high' if vp.side == 'LONG' else 'low'} {_fmt_price(extremum)})\n"
        "Consider closing per strategy plan."
    )


def format_strategy_exit(
    vp: VirtualPosition, reason: str, price: Decimal | None
) -> str:
    price_line = (
        f"Price at signal: {_fmt_price(price)}"
        if price is not None
        else "Price at signal: (not provided)"
    )
    return (
        f"{_header(vp, '🔚', 'STRATEGY EXIT')}\n"
        f"Reason: {reason}\n"
        f"{price_line}"
    )


def format_sl_moved(
    vp: VirtualPosition, old_sl: Decimal, new_sl: Decimal
) -> str:
    return (
        f"{_header(vp, '📉', 'SL MOVED')}\n"
        f"Old SL: {_fmt_price(old_sl)} → New SL: {_fmt_price(new_sl)}"
    )


def format_partial_close(
    vp: VirtualPosition, tp_level: str, price: Decimal
) -> str:
    return (
        f"{_header(vp, '⚖️', 'PARTIAL CLOSE')}\n"
        f"Close at {tp_level} @ {_fmt_price(price)}"
    )


def format_expired(vp: VirtualPosition, age_candles: int) -> str:
    return (
        f"[debug] ⏰ {vp.signal_id} ({vp.strategy_name} {vp.side} {vp.symbol}) "
        f"expired after {age_candles} candles (no SL/TP hit)"
    )


def format_strategy_failure(
    strategy_name: str, symbol: str, attempt: int, error: str
) -> str:
    return (
        f"[debug] ⚠ {strategy_name} error on {symbol}: {error} "
        f"(attempt {attempt})"
    )


def format_invariant_violation(
    strategy_name: str, symbol: str, reason: str
) -> str:
    """Invariant violations (e.g. ClosePosition with no VP) — no retry attempt."""
    return f"[debug] ⚠ {strategy_name} invalid action on {symbol}: {reason}"


def format_strategy_dead(strategy_name: str, symbol: str, error: str) -> str:
    return (
        f"[debug] ⚠ {strategy_name} disabled on {symbol} after consecutive failures. "
        f"Last error: {error}"
    )


def format_shutdown_broadcast(
    strategy_name: str, vps: list[VirtualPosition]
) -> str:
    if not vps:
        return (
            f"⚠ Signal bot shutting down.\n"
            f"[{strategy_name}] No open virtual positions."
        )
    count = len(vps)
    header = (
        f"[{strategy_name}] You have {count} open virtual position"
        + ("s" if count != 1 else "")
        + ":"
    )
    lines = ["⚠ Signal bot shutting down.", header]
    for vp in vps:
        lines.append(
            f"• {vp.signal_id} {vp.side} {vp.symbol} @ {_fmt_price(vp.entry_price)} "
            f"(SL {_fmt_price(vp.sl_price)})"
        )
    lines.append("Manage these manually.")
    return "\n".join(lines)
