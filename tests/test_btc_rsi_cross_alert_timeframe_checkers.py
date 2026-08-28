"""Tests for the separate M5 and M15 BTC RSI cross checker entry points."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import pytest

from app.signal.btc_rsi_cross_alert import worker_support
from app.trading.strategy.btc_rsi_cross_alert import m5_checker, m15_checker
from app.trading.strategy.btc_rsi_cross_alert.evaluator import evaluate_btc_rsi_cross
from app.trading.strategy.btc_rsi_cross_alert.models import (
    DECISION_ALERT_FRESH_BULLISH_CROSS_H4_BULLISH,
    DECISION_ALERT_M5_BULLISH_ALIGNMENT_H4_BULLISH,
    DECISION_H1_CLOSE_NOT_ABOVE_EMA21,
    DECISION_H4_CLOSE_NOT_ABOVE_EMA21,
    DECISION_M5_CLOSE_NOT_ABOVE_EMA21,
    DECISION_M5_EMA_WMA_SPREAD_NOT_ABOVE_2,
    DECISION_M5_RSI21_NOT_BELOW_60,
    DECISION_M5_RSI_ALIGNMENT_NOT_BULLISH,
    DECISION_M5_WMA45_NOT_ABOVE_45,
    DECISION_M15_CLOSE_NOT_ABOVE_EMA21,
    PREPARATION_READY,
    BtcRsiCrossInput,
    BtcRsiCrossPreparation,
    RsiBundlePoint,
)

TRIGGER_OPEN = datetime(2026, 8, 27, 10, 0, tzinfo=UTC)
HISTORY_READY_AT = datetime(2026, 8, 27, 9, 0, tzinfo=UTC)


def _input(timeframe: str) -> BtcRsiCrossInput:
    return BtcRsiCrossInput(
        symbol="BTC/USDT",
        trigger_timeframe=timeframe,
        trigger_close_time=datetime(2026, 8, 27, 10, 15, tzinfo=UTC),
        trigger_close_price=Decimal("64000"),
        trigger_price_ema21=Decimal("63000"),
        previous_trigger=RsiBundlePoint(
            rsi21=45.0,
            rsi_ema9=40.0,
            rsi_wma45=40.0,
        ),
        current_trigger=RsiBundlePoint(
            rsi21=55.0,
            rsi_ema9=50.0,
            rsi_wma45=47.0,
        ),
        h1_close_price=Decimal("65000"),
        h1_price_ema21=Decimal("64000"),
        h1_close_time=datetime(2026, 8, 27, 10, tzinfo=UTC),
        h4_close_price=Decimal("65000"),
        h4_price_ema21=Decimal("64000"),
        h4_close_time=datetime(2026, 8, 27, 8, 0, tzinfo=UTC),
    )


def test_m15_checker_matches_shared_fresh_cross_decision():
    data = _input("15m")
    assert m15_checker.evaluate_m15_cross(data) == evaluate_btc_rsi_cross(data)


@pytest.mark.parametrize(
    ("checker", "wrong_timeframe", "message"),
    [
        (m5_checker.evaluate_m5_cross, "15m", "M5 checker requires"),
        (m15_checker.evaluate_m15_cross, "5m", "M15 checker requires"),
    ],
)
def test_timeframe_checker_rejects_other_timeframe(
    checker,
    wrong_timeframe,
    message,
):
    with pytest.raises(ValueError, match=message):
        checker(_input(wrong_timeframe))


class TestM5MandatoryFilters:
    def test_all_m5_filters_pass(self):
        decision = m5_checker.evaluate_m5_cross(_input("5m"))
        assert decision.should_alert is True
        assert decision.reason == DECISION_ALERT_M5_BULLISH_ALIGNMENT_H4_BULLISH

    def test_m5_alerts_without_a_fresh_cross(self):
        data = replace(
            _input("5m"),
            previous_trigger=RsiBundlePoint(
                rsi21=58.0,
                rsi_ema9=51.0,
                rsi_wma45=47.0,
            ),
        )

        decision = m5_checker.evaluate_m5_cross(data)

        assert decision.should_alert is True
        assert decision.reason == DECISION_ALERT_M5_BULLISH_ALIGNMENT_H4_BULLISH

    @pytest.mark.parametrize("h4_close", [Decimal("64000"), Decimal("63999.99")])
    def test_h4_close_must_be_strictly_above_h4_price_ema21(self, h4_close):
        decision = m5_checker.evaluate_m5_cross(
            replace(_input("5m"), h4_close_price=h4_close)
        )

        assert decision.should_alert is False
        assert decision.reason == DECISION_H4_CLOSE_NOT_ABOVE_EMA21

    @pytest.mark.parametrize("h1_close", [Decimal("64000"), Decimal("63999.99")])
    def test_h1_close_must_be_strictly_above_h1_price_ema21(self, h1_close):
        decision = m5_checker.evaluate_m5_cross(
            replace(_input("5m"), h1_close_price=h1_close)
        )

        assert decision.should_alert is False
        assert decision.reason == DECISION_H1_CLOSE_NOT_ABOVE_EMA21

    @pytest.mark.parametrize(
        "current",
        [
            RsiBundlePoint(rsi21=50.0, rsi_ema9=50.0, rsi_wma45=47.0),
            RsiBundlePoint(rsi21=55.0, rsi_ema9=47.0, rsi_wma45=47.0),
            RsiBundlePoint(rsi21=49.0, rsi_ema9=50.0, rsi_wma45=47.0),
        ],
    )
    def test_m5_alignment_requires_strict_rsi_above_ema_above_wma(self, current):
        decision = m5_checker.evaluate_m5_cross(
            replace(_input("5m"), current_trigger=current)
        )

        assert decision.should_alert is False
        assert decision.reason == DECISION_M5_RSI_ALIGNMENT_NOT_BULLISH

    @pytest.mark.parametrize("spread", [1.99])
    def test_rsi_ema_wma_spread_must_be_at_least_two(self, spread):
        data = _input("5m")
        current = replace(
            data.current_trigger,
            rsi_ema9=data.current_trigger.rsi_wma45 + spread,
        )

        decision = m5_checker.evaluate_m5_cross(
            replace(data, current_trigger=current)
        )

        assert decision.should_alert is False
        assert decision.reason == DECISION_M5_EMA_WMA_SPREAD_NOT_ABOVE_2

    @pytest.mark.parametrize("spread", [2.0, 2.01])
    def test_rsi_ema_wma_spread_equal_to_two_is_allowed(self, spread):
        data = _input("5m")
        current = replace(
            data.current_trigger,
            rsi_ema9=data.current_trigger.rsi_wma45 + spread,
        )

        decision = m5_checker.evaluate_m5_cross(
            replace(data, current_trigger=current)
        )

        assert decision.should_alert is True
        assert decision.reason == DECISION_ALERT_M5_BULLISH_ALIGNMENT_H4_BULLISH

    @pytest.mark.parametrize("wma45", [45.0, 44.99])
    def test_rsi_wma45_must_be_strictly_above_45(self, wma45):
        data = _input("5m")
        current = replace(
            data.current_trigger,
            rsi_ema9=wma45 + 3.0,
            rsi_wma45=wma45,
        )

        decision = m5_checker.evaluate_m5_cross(
            replace(data, current_trigger=current)
        )

        assert decision.should_alert is False
        assert decision.reason == DECISION_M5_WMA45_NOT_ABOVE_45

    @pytest.mark.parametrize("rsi21", [60.0, 60.01])
    def test_m5_rsi21_must_stay_strictly_below_60(self, rsi21):
        data = _input("5m")
        current = replace(data.current_trigger, rsi21=rsi21)

        decision = m5_checker.evaluate_m5_cross(
            replace(data, current_trigger=current)
        )

        assert decision.should_alert is False
        assert decision.reason == DECISION_M5_RSI21_NOT_BELOW_60

    def test_m5_rsi21_below_60_is_allowed(self):
        data = _input("5m")
        current = replace(data.current_trigger, rsi21=59.99)

        decision = m5_checker.evaluate_m5_cross(
            replace(data, current_trigger=current)
        )

        assert decision.should_alert is True

    @pytest.mark.parametrize("close_price", [Decimal("63000"), Decimal("62999.99")])
    def test_close_must_be_strictly_above_price_ema21(self, close_price):
        data = replace(_input("5m"), trigger_close_price=close_price)

        decision = m5_checker.evaluate_m5_cross(data)

        assert decision.should_alert is False
        assert decision.reason == DECISION_M5_CLOSE_NOT_ABOVE_EMA21

    def test_m15_does_not_apply_m5_filters(self):
        data = _input("15m")
        current = replace(
            data.current_trigger,
            rsi_ema9=10.1,
            rsi_wma45=10.0,
        )
        data = replace(
            data,
            current_trigger=current,
        )

        decision = m15_checker.evaluate_m15_cross(data)

        assert decision.should_alert is True
        assert decision.reason == DECISION_ALERT_FRESH_BULLISH_CROSS_H4_BULLISH

    @pytest.mark.parametrize("close_price", [Decimal("63000"), Decimal("62999.99")])
    def test_m15_close_must_be_strictly_above_price_ema21(self, close_price):
        data = replace(_input("15m"), trigger_close_price=close_price)

        decision = m15_checker.evaluate_m15_cross(data)

        assert decision.should_alert is False
        assert decision.reason == DECISION_M15_CLOSE_NOT_ABOVE_EMA21


@pytest.mark.parametrize(
    ("module", "prepare_name", "timeframe"),
    [
        (m5_checker, "prepare_m5_cross_input", "5m"),
        (m15_checker, "prepare_m15_cross_input", "15m"),
    ],
)
def test_prepare_entry_point_locks_its_timeframe(
    monkeypatch,
    module,
    prepare_name,
    timeframe,
):
    captured = {}
    expected = BtcRsiCrossPreparation(input=_input(timeframe), reason=PREPARATION_READY)

    def fake_prepare(trigger_df, h4_df, **kwargs):
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(module, "prepare_btc_rsi_cross_input", fake_prepare)
    result = getattr(module, prepare_name)(
        pd.DataFrame(),
        pd.DataFrame(),
        h1_df=pd.DataFrame(),
        symbol="BTC/USDT",
        trigger_open_time=TRIGGER_OPEN,
        history_ready_at=HISTORY_READY_AT,
        observed_live_h1_closes=frozenset(),
        observed_live_h4_closes=frozenset(),
    )

    assert result is expected
    assert captured["trigger_timeframe"] == timeframe


@pytest.mark.parametrize(
    ("timeframe", "selected_name", "other_name"),
    [
        ("5m", "prepare_m5_cross_input", "prepare_m15_cross_input"),
        ("15m", "prepare_m15_cross_input", "prepare_m5_cross_input"),
    ],
)
def test_worker_support_dispatches_to_matching_checker(
    monkeypatch,
    timeframe,
    selected_name,
    other_name,
):
    frame = pd.DataFrame({"close": [1.0], "closed": [True]})

    class MultiplexerStub:
        def get_dataframe(self, symbol, requested_timeframe):
            return frame

    expected = BtcRsiCrossPreparation(input=_input(timeframe), reason=PREPARATION_READY)
    calls = []

    def selected(*args, **kwargs):
        calls.append((args, kwargs))
        return expected

    def unexpected(*args, **kwargs):
        raise AssertionError("worker dispatched to the wrong timeframe checker")

    monkeypatch.setattr(worker_support, selected_name, selected)
    monkeypatch.setattr(worker_support, other_name, unexpected)
    config = SimpleNamespace(
        symbol="BTC/USDT",
        confirmation_timeframe="1h",
        trend_timeframe="4h",
    )

    result = worker_support.prepare_from_multiplexer(
        MultiplexerStub(),
        config,
        timeframe,
        TRIGGER_OPEN,
        HISTORY_READY_AT,
        frozenset(),
        frozenset(),
    )

    assert result is expected
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("timeframe", "selected_name", "other_name"),
    [
        ("5m", "evaluate_m5_cross", "evaluate_m15_cross"),
        ("15m", "evaluate_m15_cross", "evaluate_m5_cross"),
    ],
)
def test_worker_support_dispatches_decision_to_matching_checker(
    monkeypatch,
    timeframe,
    selected_name,
    other_name,
):
    data = _input(timeframe)
    expected = evaluate_btc_rsi_cross(data)

    monkeypatch.setattr(worker_support, selected_name, lambda value: expected)

    def unexpected(value):
        raise AssertionError("worker dispatched to the wrong timeframe checker")

    monkeypatch.setattr(worker_support, other_name, unexpected)

    assert worker_support.evaluate_prepared_input(timeframe, data) == expected
