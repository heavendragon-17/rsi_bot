"""Tests for exit_monitor.check — mechanical SL/TP/age rules (slice 5)."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from app.core.events import Candle
from app.signal.exit_monitor import Expired, SLHit, TPHit, check
from app.signal.virtual_position import VirtualPosition

OPEN_TIME = datetime(2024, 1, 1, 0, 0, 0)
OPEN_TS_MS = int(OPEN_TIME.timestamp() * 1000)


def _mk_vp(
    *,
    side="LONG",
    sl="60000",
    tps=("62000", "64000"),
    timeframe="15m",
    tp_hits=frozenset(),
):
    return VirtualPosition(
        signal_id="RSIN#001",
        strategy_name="rsi_no_retest",
        symbol="BTC/USDT",
        side=side,
        entry_price=Decimal("61000"),
        sl_price=Decimal(sl),
        tp_levels=tuple(Decimal(x) for x in tps),
        tp_close_pcts=tuple(0.5 for _ in tps),
        opened_at_candle_ts=OPEN_TS_MS,
        timeframe=timeframe,
        tp_hits=tp_hits,
    )


def _mk_candle(
    *,
    close="61000",
    high="61500",
    low="60500",
    ts=None,
):
    return Candle(
        symbol="BTC",
        timestamp=ts or OPEN_TIME + timedelta(minutes=15),
        open=Decimal("61000"),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("10"),
        closed=True,
        timeframe="15m",
    )


class TestSL:
    def test_long_sl_hits_on_close_below(self):
        events = check(_mk_vp(side="LONG", sl="60000"), _mk_candle(close="59900"))
        assert len(events) == 1
        assert isinstance(events[0], SLHit)

    def test_long_sl_not_hit_when_close_above(self):
        events = check(_mk_vp(side="LONG", sl="60000"), _mk_candle(close="60100"))
        assert not any(isinstance(e, SLHit) for e in events)

    def test_short_sl_hits_on_close_above(self):
        vp = _mk_vp(side="SHORT", sl="62000", tps=("60000", "58000"))
        events = check(vp, _mk_candle(close="62100"))
        assert len(events) == 1
        assert isinstance(events[0], SLHit)

    def test_short_sl_not_hit_when_close_below(self):
        vp = _mk_vp(side="SHORT", sl="62000", tps=("60000", "58000"))
        events = check(vp, _mk_candle(close="61900"))
        assert not any(isinstance(e, SLHit) for e in events)


class TestTP:
    def test_long_tp_wick_touch_via_high(self):
        events = check(_mk_vp(tps=("62000",)), _mk_candle(high="62001", close="61500"))
        assert len(events) == 1
        tp = events[0]
        assert isinstance(tp, TPHit)
        assert tp.tp_index == 0
        assert tp.closes_vp is True

    def test_long_tp_not_hit_when_high_below(self):
        events = check(_mk_vp(tps=("62000",)), _mk_candle(high="61999", close="61500"))
        assert events == []

    def test_short_tp_wick_touch_via_low(self):
        vp = _mk_vp(side="SHORT", sl="62000", tps=("60000",))
        events = check(vp, _mk_candle(low="59999", close="61500"))
        assert len(events) == 1
        assert isinstance(events[0], TPHit)
        assert events[0].closes_vp is True

    def test_two_tps_in_single_candle(self):
        vp = _mk_vp(tps=("62000", "64000"))
        # High reaches both
        events = check(vp, _mk_candle(high="64500", close="61500"))
        tp_events = [e for e in events if isinstance(e, TPHit)]
        assert len(tp_events) == 2
        assert tp_events[0].tp_index == 0
        assert tp_events[0].closes_vp is False
        assert tp_events[1].tp_index == 1
        assert tp_events[1].closes_vp is True

    def test_already_hit_tp_not_refired(self):
        vp = _mk_vp(tps=("62000", "64000"), tp_hits=frozenset({0}))
        events = check(vp, _mk_candle(high="64500", close="61500"))
        tp_events = [e for e in events if isinstance(e, TPHit)]
        assert len(tp_events) == 1
        assert tp_events[0].tp_index == 1
        assert tp_events[0].closes_vp is True

    def test_last_tp_closes_when_prior_already_hit(self):
        vp = _mk_vp(tps=("62000", "64000", "66000"), tp_hits=frozenset({0, 1}))
        events = check(vp, _mk_candle(high="66500", close="61500"))
        assert len(events) == 1
        assert isinstance(events[0], TPHit)
        assert events[0].closes_vp is True


class TestPrecedence:
    def test_sl_wins_over_tp_in_same_candle(self):
        """Candle wicks up to TP but closes below SL — only SLHit fires."""
        vp = _mk_vp(side="LONG", sl="60000", tps=("62000",))
        events = check(vp, _mk_candle(high="62500", low="59500", close="59800"))
        assert len(events) == 1
        assert isinstance(events[0], SLHit)


class TestAgeExpiry:
    def test_expires_after_threshold(self):
        vp = _mk_vp(timeframe="15m")
        # 60 candles × 15m = 900 minutes later
        later = OPEN_TIME + timedelta(minutes=60 * 15 + 1)
        events = check(vp, _mk_candle(ts=later, close="61000"), max_age_candles=50)
        expired = [e for e in events if isinstance(e, Expired)]
        assert len(expired) == 1
        assert expired[0].age_candles >= 50

    def test_does_not_expire_before_threshold(self):
        vp = _mk_vp(timeframe="15m")
        later = OPEN_TIME + timedelta(minutes=10 * 15)
        events = check(vp, _mk_candle(ts=later, close="61000"), max_age_candles=50)
        assert not any(isinstance(e, Expired) for e in events)

    def test_unknown_timeframe_skips_expiry(self):
        vp = _mk_vp(timeframe="7m")  # not in TIMEFRAME_SECONDS
        later = OPEN_TIME + timedelta(days=365)
        events = check(vp, _mk_candle(ts=later, close="61000"), max_age_candles=1)
        assert not any(isinstance(e, Expired) for e in events)

    def test_unknown_timeframe_warning_dedupes_per_vp(self):
        """A misconfigured timeframe must not spam warnings every candle."""
        import structlog.testing

        from app.signal import exit_monitor as em
        em._warned_unknown_timeframe.clear()

        vp = _mk_vp(timeframe="7m")
        with structlog.testing.capture_logs() as captured:
            for _ in range(5):
                check(vp, _mk_candle(close="61000"), max_age_candles=1)

        warnings = [c for c in captured if c.get("log_level") == "warning"]
        assert len(warnings) == 1

    def test_closing_tp_suppresses_expiry_on_same_candle(self):
        """When the final TP closes the VP, age expiry shouldn't also fire."""
        vp = _mk_vp(timeframe="15m", tps=("62000",))
        later = OPEN_TIME + timedelta(minutes=60 * 15 + 1)
        events = check(
            vp,
            _mk_candle(ts=later, high="62500", close="61500"),
            max_age_candles=50,
        )
        assert any(isinstance(e, TPHit) and e.closes_vp for e in events)
        assert not any(isinstance(e, Expired) for e in events)

    def test_partial_tp_does_not_suppress_expiry(self):
        """A non-closing TP still lets the expiry fire on the same candle."""
        vp = _mk_vp(timeframe="15m", tps=("62000", "64000"))
        later = OPEN_TIME + timedelta(minutes=60 * 15 + 1)
        events = check(
            vp,
            _mk_candle(ts=later, high="62500", close="61500"),
            max_age_candles=50,
        )
        assert any(isinstance(e, TPHit) for e in events)
        assert any(isinstance(e, Expired) for e in events)
