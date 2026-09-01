"""Deterministic HTML-safe Telegram card for the BTC RSI cross alert.

Pure formatting only: no clocks, I/O, or notifier access. Every ``<``
character in the card — dynamic values *and* static comparison glyphs such as
``< 60.00`` and ``<=`` — is entity-escaped, because the underlying
``TelegramBot`` sends with ``parse_mode="HTML"`` and Telegram rejects the
whole message with HTTP 400 "can't parse entities" on any raw ``<``,
silently dropping the alert. Send-safety is enforced by
``tests/test_btc_rsi_cross_alert_formatter.py::TestHtmlEscaping``.
No entry / SL / TP / leverage / position / expected-profit fields are ever
rendered (spec §13).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
_CHART_TIMEZONE = timezone(timedelta(hours=7), name="UTC+7")


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


def _status(condition: bool) -> str:
    return "✅" if condition else "❌"


def _chart_time(value: datetime) -> str:
    return value.astimezone(_CHART_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")


def format_btc_rsi_cross_alert(data: BtcRsiCrossInput, event_id: str) -> str:
    """Render the alert card with a chart-locatable check snapshot."""

    tf_label = _label(data.trigger_timeframe)
    candle_close = _chart_time(data.trigger_close_time)
    current = data.current_trigger
    previous = data.previous_trigger
    trigger_above_ema21 = data.trigger_close_price > data.trigger_price_ema21
    h1_above_ema21 = data.h1_close_price > data.h1_price_ema21
    h4_above_ema21 = data.h4_close_price > data.h4_price_ema21
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
        f"{tf_label} EMA21(price): {_fmt_price(data.trigger_price_ema21)}",
        f"{tf_label} close > EMA21(price): "
        f"{_fmt_price(data.trigger_close_price)} > "
        f"{_fmt_price(data.trigger_price_ema21)} "
        f"{_status(trigger_above_ema21)}",
        "",
    ]

    if data.trigger_timeframe == "5m":
        alignment = (
            current.rsi21 > current.rsi_ema9
            and current.rsi_ema9 > current.rsi_wma45
        )
        spread = current.rsi_ema9 - current.rsi_wma45
        lines.extend(
            [
                f"Current M5 RSI21: {_fmt_indicator(current.rsi21)}",
                f"Current M5 EMA9(RSI21): {_fmt_indicator(current.rsi_ema9)}",
                f"Current M5 WMA45(RSI21): "
                f"{_fmt_indicator(current.rsi_wma45)}",
                f"M5 RSI alignment: {_fmt_indicator(current.rsi21)} > "
                f"{_fmt_indicator(current.rsi_ema9)} > "
                f"{_fmt_indicator(current.rsi_wma45)} {_status(alignment)}",
                f"M5 EMA9(RSI21) - WMA45(RSI21): {_fmt_indicator(spread)} "
                f">= 2.00 {_status(spread >= 2.0)}",
                f"M5 WMA45(RSI21) > 45.00: "
                f"{_fmt_indicator(current.rsi_wma45)} > 45.00 "
                f"{_status(current.rsi_wma45 > 45.0)}",
                f"M5 RSI21 &lt; 60.00: {_fmt_indicator(current.rsi21)} &lt; 60.00 "
                f"{_status(current.rsi21 < 60.0)}",
            ]
        )
    else:
        fresh_cross = (
            previous.rsi_ema9 <= previous.rsi_wma45
            and current.rsi_ema9 > current.rsi_wma45
        )
        lines.extend(
            [
                f"Previous {tf_label} EMA9(RSI21): "
                f"{_fmt_indicator(previous.rsi_ema9)}",
                f"Previous {tf_label} WMA45(RSI21): "
                f"{_fmt_indicator(previous.rsi_wma45)}",
                "",
                f"Current {tf_label} RSI21: {_fmt_indicator(current.rsi21)}",
                f"Current {tf_label} EMA9(RSI21): "
                f"{_fmt_indicator(current.rsi_ema9)}",
                f"Current {tf_label} WMA45(RSI21): "
                f"{_fmt_indicator(current.rsi_wma45)}",
                f"Fresh bullish cross: "
                f"{_fmt_indicator(previous.rsi_ema9)} &lt;= "
                f"{_fmt_indicator(previous.rsi_wma45)} and "
                f"{_fmt_indicator(current.rsi_ema9)} > "
                f"{_fmt_indicator(current.rsi_wma45)} "
                f"{_status(fresh_cross)}",
            ]
        )

    lines.extend(
        [
            "",
            f"H1 close: {_fmt_price(data.h1_close_price)}",
            f"H1 EMA21(price): {_fmt_price(data.h1_price_ema21)}",
            f"H1 close > EMA21(price): "
            f"{_fmt_price(data.h1_close_price)} > "
            f"{_fmt_price(data.h1_price_ema21)} {_status(h1_above_ema21)}",
            "",
            f"H4 close: {_fmt_price(data.h4_close_price)}",
            f"H4 EMA21(price): {_fmt_price(data.h4_price_ema21)}",
            f"H4 close > EMA21(price): "
            f"{_fmt_price(data.h4_close_price)} > "
            f"{_fmt_price(data.h4_price_ema21)} {_status(h4_above_ema21)}",
            "",
            "Duplicate check: NEW event ✅",
            f"Event: {escape(event_id_suffix(event_id))}",
        ]
    )
    return "\n".join(lines)
