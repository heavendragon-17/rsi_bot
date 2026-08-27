"""Deterministic HTML-safe Telegram card for the BTC RSI cross alert.

Pure formatting only: no clocks, I/O, or notifier access. All dynamic text is
escaped because the underlying ``TelegramBot`` sends with
``parse_mode="HTML"``. No entry / SL / TP / leverage / position / expected-
profit fields are ever rendered (spec §13).
"""

from __future__ import annotations

from decimal import Decimal
from html import escape

from app.trading.strategy.btc_rsi_cross_alert.models import (
    BtcRsiCrossInput,
    event_id_suffix,
)

_TIMEFRAME_LABELS: dict[str, str] = {
    "5m": "M5",
    "15m": "M15",
}


def _label(timeframe: str) -> str:
    label = _TIMEFRAME_LABELS.get(timeframe)
    if label is None:
        raise ValueError(f"unsupported trigger timeframe for formatting: {timeframe!r}")
    return label


def _fmt_indicator(value: float) -> str:
    """Stable two-decimal indicator rendering."""

    return f"{float(value):.2f}"


def _fmt_price(value: Decimal) -> str:
    """Stable thousands-separated two-decimal price rendering."""

    return f"{Decimal(value):,.2f}"


def format_btc_rsi_cross_alert(data: BtcRsiCrossInput, event_id: str) -> str:
    """Render the alert card exactly per spec §13."""

    tf_label = _label(data.trigger_timeframe)
    candle_close = data.trigger_close_time.strftime("%Y-%m-%d %H:%M:%S UTC")
    title = (
        "🟢 BTC RSI BULLISH ALIGNMENT"
        if data.trigger_timeframe == "5m"
        else "🟢 BTC RSI BULLISH CROSS"
    )

    lines = [
        title,
        "",
        f"Timeframe: {escape(data.trigger_timeframe)}",
        f"Candle close: {escape(candle_close)}",
        f"BTC close: {_fmt_price(data.trigger_close_price)}",
        "",
        f"{tf_label} RSI21: {_fmt_indicator(data.current_trigger.rsi21)}",
        f"{tf_label} EMA9(RSI): {_fmt_indicator(data.current_trigger.rsi_ema9)}",
        f"{tf_label} WMA45(RSI): {_fmt_indicator(data.current_trigger.rsi_wma45)}",
        "",
        "H4 price trend: BULLISH ✅",
        f"H4 close: {_fmt_price(data.h4_close_price)}",
        f"H4 EMA21(price): {_fmt_price(data.h4_price_ema21)}",
        f"Event: {escape(event_id_suffix(event_id))}",
    ]
    return "\n".join(lines)
