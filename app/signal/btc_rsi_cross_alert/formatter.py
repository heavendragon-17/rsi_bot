"""Deterministic HTML-safe Telegram card for the BTC RSI cross alert.

Pure formatting only: no clocks, I/O, or notifier access. All dynamic text is
escaped because the underlying ``TelegramBot`` sends with
``parse_mode="HTML"``. No entry / SL / TP / leverage / position / expected-
profit fields are ever rendered (spec §13).
"""

from __future__ import annotations

from datetime import UTC
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


def _status(condition: bool) -> str:
    return "✅" if condition else "❌"


def format_btc_rsi_cross_alert(data: BtcRsiCrossInput, event_id: str) -> str:
    """Render the alert card with the complete point-in-time check snapshot."""

    tf_label = _label(data.trigger_timeframe)
    candle_close = data.trigger_close_time.astimezone(UTC).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )
    h4_candle_close = data.h4_close_time.astimezone(UTC).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )
    current = data.current_trigger
    previous = data.previous_trigger
    trigger_above_ema21 = data.trigger_close_price > data.trigger_price_ema21
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
        f"Chart candle: {escape(data.symbol)} {tf_label} (close below)",
        f"Candle close: {escape(candle_close)}",
        f"BTC close: {_fmt_price(data.trigger_close_price)}",
        f"{tf_label} EMA21(price): {_fmt_price(data.trigger_price_ema21)}",
        "",
        f"{tf_label} indicators at candle close:",
        f"{tf_label} RSI21: {_fmt_indicator(current.rsi21)}",
        f"{tf_label} EMA9(RSI21): {_fmt_indicator(current.rsi_ema9)}",
        f"{tf_label} WMA45(RSI21): {_fmt_indicator(current.rsi_wma45)}",
        "",
        "Signal checks:",
    ]

    if data.trigger_timeframe == "5m":
        alignment = (
            current.rsi21 > current.rsi_ema9
            and current.rsi_ema9 > current.rsi_wma45
        )
        spread = current.rsi_ema9 - current.rsi_wma45
        lines.extend(
            [
                f"M5 RSI alignment: {_fmt_indicator(current.rsi21)} > "
                f"{_fmt_indicator(current.rsi_ema9)} > "
                f"{_fmt_indicator(current.rsi_wma45)} {_status(alignment)}",
                f"M5 RSI spread (EMA9 − WMA45): {_fmt_indicator(spread)} "
                f"(required > 2.00) {_status(spread > 2.0)}",
                f"M5 WMA45(RSI21) > 45.00: "
                f"{_fmt_indicator(current.rsi_wma45)} > 45.00 "
                f"{_status(current.rsi_wma45 > 45.0)}",
            ]
        )
    else:
        fresh_cross = (
            previous.rsi_ema9 <= previous.rsi_wma45
            and current.rsi_ema9 > current.rsi_wma45
        )
        lines.extend(
            [
                f"Previous {tf_label} RSI21: {_fmt_indicator(previous.rsi21)}",
                f"Previous {tf_label} EMA9(RSI21): "
                f"{_fmt_indicator(previous.rsi_ema9)}",
                f"Previous {tf_label} WMA45(RSI21): "
                f"{_fmt_indicator(previous.rsi_wma45)}",
                f"Fresh bullish cross: {_status(fresh_cross)}",
                f"  Previous EMA9(RSI21) <= WMA45(RSI21): "
                f"{_fmt_indicator(previous.rsi_ema9)} <= "
                f"{_fmt_indicator(previous.rsi_wma45)} "
                f"{_status(previous.rsi_ema9 <= previous.rsi_wma45)}",
                f"  Current EMA9(RSI21) > WMA45(RSI21): "
                f"{_fmt_indicator(current.rsi_ema9)} > "
                f"{_fmt_indicator(current.rsi_wma45)} "
                f"{_status(current.rsi_ema9 > current.rsi_wma45)}",
            ]
        )

    lines.extend(
        [
            f"{tf_label} close > {tf_label} EMA21(price): "
            f"{_fmt_price(data.trigger_close_price)} > "
            f"{_fmt_price(data.trigger_price_ema21)} "
            f"{_status(trigger_above_ema21)}",
            "",
            "H4 price filter:",
            f"H4 candle close: {escape(h4_candle_close)}",
            f"H4 close: {_fmt_price(data.h4_close_price)}",
            f"H4 EMA21(price): {_fmt_price(data.h4_price_ema21)}",
            f"H4 close > H4 EMA21(price): "
            f"{_fmt_price(data.h4_close_price)} > "
            f"{_fmt_price(data.h4_price_ema21)} {_status(h4_above_ema21)}",
            f"H4 price trend: BULLISH {_status(h4_above_ema21)}",
            "",
            "Duplicate check: NEW event ✅",
            f"Event: {escape(event_id_suffix(event_id))}",
        ]
    )
    return "\n".join(lines)
