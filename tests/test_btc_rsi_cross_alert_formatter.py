"""Tests for the deterministic HTML-safe BTC RSI cross alert formatter."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.signal.btc_rsi_cross_alert.formatter import format_btc_rsi_cross_alert
from app.trading.strategy.btc_rsi_cross_alert.models import (
    BtcRsiCrossInput,
    RsiBundlePoint,
    build_event_id,
)

UTC = UTC


def _input(timeframe: str = "5m") -> BtcRsiCrossInput:
    return BtcRsiCrossInput(
        symbol="BTC/USDT",
        trigger_timeframe=timeframe,
        trigger_close_time=datetime(2026, 8, 24, 9, 35, tzinfo=UTC),
        trigger_close_price=Decimal("64321.5"),
        trigger_price_ema21=Decimal("63000"),
        previous_trigger=RsiBundlePoint(42.0, 40.0, 50.0),
        current_trigger=RsiBundlePoint(53.423, 48.762, 46.551),
        h4_close_price=Decimal("65012.34"),
        h4_price_ema21=Decimal("64001.23"),
        h4_close_time=datetime(2026, 8, 24, 8, tzinfo=UTC),
    )


def _format(data=None, event_id: str | None = None) -> str:
    data = data or _input()
    event_id = event_id or build_event_id(
        symbol=data.symbol,
        trigger_timeframe=data.trigger_timeframe,
        trigger_close_time=data.trigger_close_time,
    )
    return format_btc_rsi_cross_alert(data, event_id)


class TestLabelsAndValues:
    def test_m5_labels(self):
        body = _format()
        assert "🟢 BTC RSI BULLISH ALIGNMENT" in body
        assert "Timeframe: 5m" in body
        assert "Current M5 RSI21: 53.42" in body
        assert "Current M5 EMA9(RSI21): 48.76" in body
        assert "Current M5 WMA45(RSI21): 46.55" in body

    def test_m15_labels(self):
        body = _format(_input("15m"))
        assert "🟢 BTC RSI BULLISH CROSS" in body
        assert "Timeframe: 15m" in body
        assert "Current M15 RSI21: 53.42" in body
        assert "Current M15 EMA9(RSI21): 48.76" in body
        assert "Current M15 WMA45(RSI21): 46.55" in body

    def test_all_required_values_present(self):
        body = _format()
        assert "🟢 BTC RSI BULLISH ALIGNMENT" in body
        assert "Candle close: 2026-08-24 16:35:00 UTC+7" in body
        assert "BTC close: 64,321.50" in body
        assert "M5 EMA21(price): 63,000.00" in body
        assert "M5 close > EMA21(price): 64,321.50 > 63,000.00 ✅" in body
        assert "H4 close: 65,012.34" in body
        assert "H4 EMA21(price): 64,001.23" in body
        assert "H4 close > EMA21(price): 65,012.34 > 64,001.23 ✅" in body

    def test_m5_check_snapshot_is_explicit(self):
        body = _format()
        assert "M5 RSI alignment: 53.42 > 48.76 > 46.55 ✅" in body
        assert "M5 EMA9(RSI21) - WMA45(RSI21): 2.21 > 2.00 ✅" in body
        assert "M5 WMA45(RSI21) > 45.00: 46.55 > 45.00 ✅" in body
        assert "Duplicate check: NEW event ✅" in body

    def test_m15_cross_snapshot_is_explicit(self):
        body = _format(_input("15m"))
        assert "Previous M15 EMA9(RSI21): 40.00" in body
        assert "Previous M15 WMA45(RSI21): 50.00" in body
        assert "Current M15 RSI21: 53.42" in body
        assert "Fresh bullish cross: 40.00 <= 50.00 and 48.76 > 46.55 ✅" in body
        assert "M15 close > EMA21(price): 64,321.50 > 63,000.00 ✅" in body

    def test_short_event_suffix_displayed(self):
        event_id = build_event_id(
            symbol="BTC/USDT",
            trigger_timeframe="5m",
            trigger_close_time=datetime(2026, 8, 24, 9, 35, tzinfo=UTC),
        )
        body = _format(event_id=event_id)
        assert f"Event: {event_id[:8]}" in body
        assert event_id not in body.replace(f"Event: {event_id[:8]}", "")

    def test_no_trade_lifecycle_fields(self):
        body = _format()
        for banned in ("Entry", "SL", "TP", "Leverage", "Position", "Profit", "PnL"):
            assert f"{banned}:" not in body


class TestStability:
    def test_timestamp_is_utc_plus_7_and_stable(self):
        assert "2026-08-24 16:35:00 UTC+7" in _format()

    def test_chart_timestamp_converts_to_utc(self):
        local_time = datetime(
            2026,
            8,
            24,
            16,
            35,
            tzinfo=timezone(timedelta(hours=7)),
        )
        body = _format(replace(_input(), trigger_close_time=local_time))
        assert "Candle close: 2026-08-24 16:35:00 UTC+7" in body

    def test_numeric_formatting_is_stable(self):
        first = _format()
        second = _format()
        assert first == second
        # Two-decimal indicator rendering regardless of extra precision.
        assert "53.42" in first and "53.423" not in first

    def test_price_thousands_separator(self):
        assert "BTC close: 64,321.50" in _format()


class TestHtmlEscaping:
    def test_dynamic_text_is_escaped(self):
        body = _format(event_id="<b>dead</b>&beef")
        assert "<b>dead</b>" not in body
        # Suffix = first 8 chars: "<b>dead<" -> escaped.
        assert "Event: &lt;b&gt;dead&lt;" in body

    def test_unsupported_timeframe_rejected(self):
        data = BtcRsiCrossInput(
            symbol="BTC/USDT",
            trigger_timeframe="1h",
            trigger_close_time=datetime(2026, 8, 24, 9, 35, tzinfo=UTC),
            trigger_close_price=Decimal("64321.5"),
            trigger_price_ema21=Decimal("63000"),
            previous_trigger=RsiBundlePoint(42.0, 40.0, 50.0),
            current_trigger=RsiBundlePoint(53.4, 48.7, 48.5),
            h4_close_price=Decimal("65000"),
            h4_price_ema21=Decimal("64000"),
            h4_close_time=datetime(2026, 8, 24, 8, tzinfo=UTC),
        )
        event_id = build_event_id(
            symbol="BTC/USDT",
            trigger_timeframe="1h",
            trigger_close_time=data.trigger_close_time,
        )
        with pytest.raises(ValueError, match="unsupported trigger timeframe"):
            format_btc_rsi_cross_alert(data, event_id)
