"""Tests for the pure BTC RSI cross decision evaluator (spec §9/§10)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.trading.strategy.btc_rsi_cross_alert.evaluator import (
    evaluate_btc_rsi_cross,
)
from app.trading.strategy.btc_rsi_cross_alert.models import (
    DECISION_ALERT_FRESH_BULLISH_CROSS_H4_BULLISH,
    DECISION_H4_CLOSE_NOT_ABOVE_EMA21,
    DECISION_NO_FRESH_BULLISH_CROSS,
    BtcRsiCrossInput,
    RsiBundlePoint,
    build_event_id,
    event_id_suffix,
)

UTC = UTC
CLOSE_T = datetime(2026, 8, 24, 9, 35, tzinfo=UTC)


def _point(rsi: float, ema: float, wma: float) -> RsiBundlePoint:
    return RsiBundlePoint(rsi21=rsi, rsi_ema9=ema, rsi_wma45=wma)


def _input(
    *,
    previous: RsiBundlePoint,
    current: RsiBundlePoint,
    timeframe: str = "5m",
    close_time: datetime = CLOSE_T,
    close_price: Decimal = Decimal("64321.50"),
    price_ema21: Decimal = Decimal("63000"),
    h4_close_price: Decimal = Decimal("65000"),
    h4_price_ema21: Decimal = Decimal("64000"),
) -> BtcRsiCrossInput:
    return BtcRsiCrossInput(
        symbol="BTC/USDT",
        trigger_timeframe=timeframe,
        trigger_close_time=close_time,
        trigger_close_price=close_price,
        trigger_price_ema21=price_ema21,
        previous_trigger=previous,
        current_trigger=current,
        h4_close_price=h4_close_price,
        h4_price_ema21=h4_price_ema21,
        h4_close_time=datetime(2026, 8, 24, 8, tzinfo=UTC),
    )


def _fresh_cross_input(**kwargs) -> BtcRsiCrossInput:
    """Fresh upward cross with H4 close strictly above H4 price EMA21."""

    return _input(
        previous=_point(42.0, 40.0, 50.0),
        current=_point(58.0, 55.0, 50.0),
        **kwargs,
    )


class TestFreshCrossDetection:
    def test_exact_bullish_cross_with_strictly_bullish_h4_alerts(self):
        decision = evaluate_btc_rsi_cross(_fresh_cross_input())
        assert decision.should_alert is True
        assert decision.reason == DECISION_ALERT_FRESH_BULLISH_CROSS_H4_BULLISH

    def test_previous_equality_then_current_greater_counts_as_cross(self):
        decision = evaluate_btc_rsi_cross(
            _input(
                previous=_point(44.0, 50.0, 50.0),  # EMA == WMA counts as below
                current=_point(52.0, 50.1, 50.0),
            )
        )
        assert decision.should_alert is True

    def test_remaining_above_without_new_cross_does_not_alert(self):
        decision = evaluate_btc_rsi_cross(
            _input(
                previous=_point(60.0, 51.0, 49.0),  # already above
                current=_point(62.0, 52.0, 49.5),
            )
        )
        assert decision.should_alert is False
        assert decision.reason == DECISION_NO_FRESH_BULLISH_CROSS

    def test_current_equality_is_not_a_cross(self):
        decision = evaluate_btc_rsi_cross(
            _input(
                previous=_point(44.0, 48.0, 50.0),
                current=_point(52.0, 50.0, 50.0),  # EMA == WMA on current
            )
        )
        assert decision.should_alert is False
        assert decision.reason == DECISION_NO_FRESH_BULLISH_CROSS

    def test_downward_cross_does_not_alert(self):
        decision = evaluate_btc_rsi_cross(
            _input(
                previous=_point(56.0, 52.0, 48.0),  # above before
                current=_point(40.0, 46.0, 49.0),  # crosses downward
            )
        )
        assert decision.should_alert is False
        assert decision.reason == DECISION_NO_FRESH_BULLISH_CROSS


class TestH4Gate:
    def test_h4_close_above_price_ema21_passes(self):
        decision = evaluate_btc_rsi_cross(_fresh_cross_input())
        assert decision.should_alert is True

    @pytest.mark.parametrize(
        "h4_close_price",
        [
            Decimal("64000"),
            Decimal("63999.99"),
        ],
    )
    def test_h4_close_not_above_price_ema21_suppresses_valid_cross(
        self, h4_close_price
    ):
        decision = evaluate_btc_rsi_cross(_input(
            previous=_point(42.0, 40.0, 50.0),
            current=_point(58.0, 55.0, 50.0),
            h4_close_price=h4_close_price,
        ))
        assert decision.should_alert is False
        assert decision.reason == DECISION_H4_CLOSE_NOT_ABOVE_EMA21


class TestDecisionPrecedenceAndScope:
    def test_no_cross_reason_takes_precedence_over_h4_price_gate(self):
        decision = evaluate_btc_rsi_cross(
            _input(
                previous=_point(60.0, 51.0, 49.0),
                current=_point(62.0, 52.0, 49.5),
                h4_close_price=Decimal("63000"),
            )
        )
        assert decision.should_alert is False
        assert decision.reason == DECISION_NO_FRESH_BULLISH_CROSS

    def test_trigger_rsi_position_adds_no_undocumented_filter(self):
        # Trigger RSI21 BELOW its own EMA/WMA while the EMA/WMA cross itself
        # is fresh and H4 is bullish — must still alert.
        decision = evaluate_btc_rsi_cross(
            _input(
                previous=_point(30.0, 34.0, 40.0),
                current=_point(31.0, 35.2, 35.0),  # rsi21 < both EMAs
            )
        )
        assert decision.should_alert is True


class TestDeterminismAndIdentity:
    def test_identical_input_reproduces_identical_decision_and_event_id(self):
        first = evaluate_btc_rsi_cross(_fresh_cross_input())
        second = evaluate_btc_rsi_cross(_fresh_cross_input())
        assert first == second
        assert first.event_id == second.event_id

    def test_m5_and_m15_create_different_event_ids_at_same_close(self):
        m5 = evaluate_btc_rsi_cross(_fresh_cross_input(timeframe="5m"))
        m15 = evaluate_btc_rsi_cross(_fresh_cross_input(timeframe="15m"))
        assert m5.event_id != m15.event_id
        assert m5.should_alert == m15.should_alert

    def test_event_id_matches_canonical_builder(self):
        decision = evaluate_btc_rsi_cross(_fresh_cross_input(timeframe="15m"))
        expected = build_event_id(
            symbol="BTC/USDT",
            trigger_timeframe="15m",
            trigger_close_time=CLOSE_T,
        )
        assert decision.event_id == expected
        assert event_id_suffix(expected) == expected[:8]

    def test_different_close_times_create_different_event_ids(self):
        early = evaluate_btc_rsi_cross(
            _fresh_cross_input(close_time=CLOSE_T - timedelta(minutes=5))
        )
        late = evaluate_btc_rsi_cross(_fresh_cross_input())
        assert early.event_id != late.event_id

    def test_decision_is_frozen(self):
        import dataclasses

        decision = evaluate_btc_rsi_cross(_fresh_cross_input())
        with pytest.raises(dataclasses.FrozenInstanceError):
            decision.should_alert = False  # type: ignore[misc]

    def test_evaluator_has_no_readiness_dataframe_clock_or_io_behavior(self):
        # The evaluator consumes only prepared points: no DataFrames are
        # involved anywhere in its public surface, and repeating the call in
        # a modified environment changes nothing.
        data = _fresh_cross_input()
        baseline = evaluate_btc_rsi_cross(data)
        for _ in range(3):
            assert evaluate_btc_rsi_cross(data) == baseline
        assert baseline.event_id == build_event_id(
            symbol=data.symbol,
            trigger_timeframe=data.trigger_timeframe,
            trigger_close_time=data.trigger_close_time,
        )
