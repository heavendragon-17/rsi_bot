"""Tests for app/signal/signal_formatter.py — plain-text message templates."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.core.events import Candle
from app.signal.signal_formatter import (
    format_entry,
    format_expired,
    format_partial_close,
    format_shutdown_broadcast,
    format_sl_hit,
    format_sl_moved,
    format_strategy_dead,
    format_strategy_exit,
    format_strategy_failure,
    format_tp_hit,
)
from app.signal.virtual_position import VirtualPosition


def _mk_vp(**overrides) -> VirtualPosition:
    defaults = dict(
        signal_id="RSIN#042",
        strategy_name="rsi_no_retest",
        symbol="BTC/USDT",
        side="LONG",
        entry_price=Decimal("62340"),
        sl_price=Decimal("61800"),
        tp_levels=(Decimal("62960"), Decimal("63500")),
        tp_close_pcts=(0.5, 0.5),
        opened_at_candle_ts=1_700_000_000_000,
        timeframe="15m",
    )
    defaults.update(overrides)
    return VirtualPosition(**defaults)


def _mk_candle(**overrides) -> Candle:
    defaults = dict(
        symbol="BTC",
        timestamp=datetime(2024, 1, 1),
        open=Decimal("62000"),
        high=Decimal("62985"),
        low=Decimal("61700"),
        close=Decimal("61720"),
        volume=Decimal("1"),
        closed=True,
        timeframe="15m",
    )
    defaults.update(overrides)
    return Candle(**defaults)


class TestEntry:
    def test_long_entry_contains_core_fields(self):
        out = format_entry(_mk_vp())
        assert "[rsi_no_retest]" in out
        assert "🟢" in out
        assert "LONG" in out
        assert "BTC/USDT" in out
        assert "RSIN#042" in out
        assert "Entry: 62340" in out
        assert "SL:" in out
        assert "61800" in out
        assert "TP1:" in out and "62960" in out
        assert "TP2:" in out and "63500" in out

    def test_short_entry_uses_red_emoji(self):
        out = format_entry(_mk_vp(side="SHORT"))
        assert "🔴" in out
        assert "SHORT" in out

    def test_single_tp_entry_only_shows_tp1(self):
        out = format_entry(_mk_vp(tp_levels=(Decimal("63000"),), tp_close_pcts=(1.0,)))
        assert "TP1" in out
        assert "TP2" not in out


class TestSLHit:
    def test_long_sl_hit_message(self):
        out = format_sl_hit(_mk_vp(), _mk_candle(close=Decimal("61720")))
        assert "🛑" in out
        assert "EXIT advice" in out
        assert "LONG" in out
        assert "BTC/USDT" in out
        assert "RSIN#042" in out
        assert "15m candle closed at 61720" in out
        assert "beyond SL 61800" in out


class TestTPHit:
    def test_long_tp1_hit_uses_high(self):
        out = format_tp_hit(
            _mk_vp(),
            tp_index=0,
            tp_price=Decimal("62960"),
            candle=_mk_candle(high=Decimal("62985")),
        )
        assert "🎯 TP1 hit" in out
        assert "Price reached 62960" in out
        assert "high 62985" in out

    def test_short_tp_uses_low(self):
        vp = _mk_vp(
            side="SHORT",
            sl_price=Decimal("62000"),
            tp_levels=(Decimal("60000"),),
            tp_close_pcts=(1.0,),
        )
        out = format_tp_hit(
            vp,
            tp_index=0,
            tp_price=Decimal("60000"),
            candle=_mk_candle(low=Decimal("59900"), high=Decimal("61500"), close=Decimal("60500")),
        )
        assert "🎯 TP1 hit" in out
        assert "low 59900" in out


class TestStrategyExit:
    def test_with_price(self):
        out = format_strategy_exit(_mk_vp(), reason="strategy signaled close", price=Decimal("62450"))
        assert "🔚 STRATEGY EXIT" in out
        assert "Reason: strategy signaled close" in out
        assert "Price at signal: 62450" in out

    def test_without_price(self):
        out = format_strategy_exit(_mk_vp(), reason="manual close", price=None)
        assert "not provided" in out


class TestSLMoved:
    def test_contents(self):
        out = format_sl_moved(_mk_vp(), Decimal("61800"), Decimal("62100"))
        assert "📉 SL MOVED" in out
        assert "Old SL: 61800" in out
        assert "New SL: 62100" in out


class TestPartialClose:
    def test_contents(self):
        out = format_partial_close(_mk_vp(), tp_level="TP1", price=Decimal("62960"))
        assert "⚖️ PARTIAL CLOSE" in out
        assert "TP1" in out
        assert "62960" in out


class TestExpired:
    def test_goes_to_debug(self):
        out = format_expired(_mk_vp(), age_candles=50)
        assert "[debug]" in out
        assert "⏰" in out
        assert "RSIN#042" in out
        assert "50 candles" in out


class TestFailureAndDead:
    def test_failure_contains_attempt(self):
        out = format_strategy_failure("rsi_no_retest", "SOL/USDT", 2, "ValueError: bad")
        assert "[debug]" in out
        assert "rsi_no_retest" in out
        assert "SOL/USDT" in out
        assert "ValueError: bad" in out
        assert "attempt 2" in out

    def test_dead_mentions_disabled(self):
        out = format_strategy_dead("rsi_no_retest", "SOL/USDT", "boom")
        assert "[debug]" in out
        assert "disabled" in out
        assert "SOL/USDT" in out
        assert "boom" in out


class TestShutdownBroadcast:
    def test_single_vp(self):
        out = format_shutdown_broadcast("rsi_no_retest", [_mk_vp()])
        assert "Signal bot shutting down" in out
        assert "1 open virtual position:" in out
        assert "RSIN#042" in out
        assert "Manage these manually" in out

    def test_multiple_vps(self):
        vp1 = _mk_vp(signal_id="RSIN#001", symbol="BTC/USDT")
        vp2 = _mk_vp(signal_id="RSIN#002", symbol="ETH/USDT")
        out = format_shutdown_broadcast("rsi_no_retest", [vp1, vp2])
        assert "2 open virtual positions:" in out
        assert "RSIN#001" in out
        assert "RSIN#002" in out

    def test_empty(self):
        out = format_shutdown_broadcast("rsi_no_retest", [])
        assert "No open virtual positions" in out
