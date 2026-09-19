"""Frozen M5 reference contracts: state rule, independent price-only policy."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.backtest import btc_research_phase1 as phase1
from research import btc_m15_reference_backtest as shared


def inputs_with_prices(counts=None):
    counts = counts or {"5m": 1100, "15m": 400, "1h": 120, "4h": 30}
    frames = {}
    for timeframe, count in counts.items():
        minutes = {"5m": 5, "15m": 15, "1h": 60, "4h": 240}[timeframe]
        index = pd.date_range("2025-01-01", periods=count, freq=f"{minutes}min", tz="UTC")
        values = np.arange(count, dtype=float) + 100.0
        frames[timeframe] = pd.DataFrame({"open": values, "close": values, "closed": True, "timeframe": timeframe}, index=index)
    return phase1.ValidatedInputs(data_dir=Path("."), paths={}, frames=frames, source_report={})


def test_price_only_policy_needs_no_rsi_history_or_conditions():
    from research import btc_m5_reference_backtest as m5

    inputs = inputs_with_prices()
    # Only 21 M5 rows: EMA21 is ready, whereas RSI/WMA preparation is not.
    inputs.frames["5m"] = inputs.frames["5m"].iloc[-21:]
    close = inputs.frames["5m"].index[-1].to_pydatetime() + timedelta(minutes=5)
    gates, audit = m5.price_gate_times(inputs, close, close)
    assert gates == [close]
    assert audit["price_ready_bars"] == 1
    assert audit["price_gated_bars"] == 1


def test_policy_a_uses_existing_m5_state_not_a_fresh_cross(monkeypatch):
    from dataclasses import replace
    from types import SimpleNamespace

    from app.trading.strategy.btc_rsi_cross_alert.models import RsiBundlePoint
    from research import btc_m5_reference_backtest as m5
    from tests.test_btc_rsi_cross_alert_timeframe_checkers import _input

    data = replace(_input("5m"), previous_trigger=RsiBundlePoint(rsi21=58, rsi_ema9=51, rsi_wma45=47))
    inputs = inputs_with_prices()
    event = SimpleNamespace(close_time=data.trigger_close_time)
    monkeypatch.setattr(m5, "events_for_frame", lambda *args: [event])
    monkeypatch.setattr(phase1, "_cache_for", lambda *args: SimpleNamespace(
        prepare=lambda *args, **kwargs: SimpleNamespace(input=data, reason="READY")))
    signals, audit = m5.reconstruct_alerts(inputs, data.trigger_close_time, data.trigger_close_time)
    assert signals == [data.trigger_close_time]
    assert audit["state_alert_bars_before_cooldown"] == 1


@pytest.mark.parametrize("timeframe", ["5m", "1h", "4h"])
def test_price_gate_equality_rejects_and_missing_context_never_substitutes(timeframe):
    from research import btc_m5_reference_backtest as m5

    inputs = inputs_with_prices()
    close = inputs.frames["5m"].index[-1].to_pydatetime() + timedelta(minutes=5)
    inputs.frames[timeframe]["close"] = 100.0
    assert m5.price_gate_times(inputs, close, close)[0] == []
    inputs = inputs_with_prices()
    duration = timedelta(minutes={"5m": 5, "1h": 60, "4h": 240}[timeframe])
    expected_open = pd.Timestamp(close).floor("5min" if timeframe == "5m" else timeframe) - duration
    inputs.frames[timeframe] = inputs.frames[timeframe].drop(expected_open)
    gates, audit = m5.price_gate_times(inputs, close, close)
    assert gates == []
    assert audit["price_ready_bars"] == 0


def test_future_prices_cannot_change_price_gate_decision():
    from research import btc_m5_reference_backtest as m5

    inputs = inputs_with_prices()
    close = inputs.frames["5m"].index[-10].to_pydatetime() + timedelta(minutes=5)
    before = m5.price_gate_times(inputs, close, close)
    for tf, frame in inputs.frames.items():
        duration = timedelta(minutes={"5m": 5, "15m": 15, "1h": 60, "4h": 240}[tf])
        frame.loc[frame.index + duration > close, "close"] = 0.01
    assert m5.price_gate_times(inputs, close, close) == before


def test_frozen_protocol_matches_m15_execution_and_costs_without_cross_rule():
    from research import btc_m5_reference_backtest as m5

    protocol = m5.frozen_protocol()
    for section in ("accounting", "costs", "funding", "comparison", "missing_data"):
        assert protocol[section] == shared.PROTOCOL[section]
    assert protocol["execution"]["entry"] == shared.PROTOCOL["execution"]["entry"]
    assert protocol["execution"]["exit"] == shared.PROTOCOL["execution"]["exit"]
    assert protocol["signal_timeframe"] == "5m"
    assert protocol["policies"]["B_gate_cooldown"]["rsi_conditions"] is False
    assert protocol["policies"]["A_emitted_alerts"]["evaluator"] == "evaluate_m5_cross"
    assert shared.TIMEFRAME == "15m"  # No monkeypatching shared module globals.


def test_signal_parity_is_ordered_and_fail_closed():
    from research import btc_m5_reference_backtest as m5

    start = datetime(2025, 1, 5, tzinfo=UTC)
    expected = [start, start + timedelta(hours=1)]
    assert m5.verify_parity(expected, expected)["matches"]
    with pytest.raises(ValueError, match="parity"):
        m5.verify_parity(expected, expected[:-1])
    with pytest.raises(ValueError, match="parity"):
        m5.verify_parity(expected, list(reversed(expected)))


def test_b_cooldown_is_independent_and_accepts_exact_hour():
    start = datetime(2025, 1, 5, tzinfo=UTC)
    a = shared.apply_cooldown([start + timedelta(minutes=5)], shared.SIGNAL_COOLDOWN)
    b = shared.apply_cooldown([start, start + timedelta(minutes=55), start + timedelta(minutes=60)], shared.SIGNAL_COOLDOWN)
    assert a == [start + timedelta(minutes=5)]
    assert b == [start, start + timedelta(hours=1)]


def test_price_only_path_does_not_even_compute_rsi(monkeypatch):
    from app.backtest import signal_replay_indicators
    from research import btc_m5_reference_backtest as m5

    def forbidden(*args, **kwargs):
        raise AssertionError("B must not calculate RSI")

    monkeypatch.setattr(signal_replay_indicators, "rsi_wilder", forbidden)
    inputs = inputs_with_prices()
    close = inputs.frames["5m"].index[-1].to_pydatetime() + timedelta(minutes=5)
    assert m5.price_gate_times(inputs, close, close)[0] == [close]


def test_price_only_restarts_warmup_after_gap():
    from research import btc_m5_reference_backtest as m5

    inputs = inputs_with_prices()
    frame = inputs.frames["5m"]
    gap_at = frame.index[-22]
    inputs.frames["5m"] = frame.drop(gap_at)
    first_ready = frame.index[-1].to_pydatetime() + timedelta(minutes=5)
    gates, audit = m5.price_gate_times(inputs, first_ready - timedelta(minutes=5), first_ready)
    assert gates == [first_ready]
    assert audit["exclusion_reasons"] == {"5m_INSUFFICIENT_PRICE_HISTORY": 1}
