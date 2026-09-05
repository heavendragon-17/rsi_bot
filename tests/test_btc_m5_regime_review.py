"""Causal calendar/regime boundaries for the fixed BTC research diagnostic."""

import numpy as np
import pandas as pd
import pytest

from research.btc_m5_regime_review import attach_labels, daily_context


def test_daily_context_waits_for_closed_day_and_is_future_invariant():
    index = pd.date_range("2022-05-01", periods=24 * 125, freq="h", tz="UTC")
    frame = pd.DataFrame({"close": np.exp(np.arange(len(index)) * 0.0001) * 100}, index=index)
    cutoff = pd.Timestamp("2022-08-28T12:30:00Z")
    altered = frame.copy()
    altered.loc[altered.index >= cutoff, "close"] *= 10
    original = daily_context(frame)
    changed = daily_context(altered)
    pd.testing.assert_frame_equal(original.loc[original.available_at <= cutoff], changed.loc[changed.available_at <= cutoff])
    signals = pd.DataFrame({"trigger_close_at": ["2022-08-28T12:30:00Z", "2022-08-29T00:00:00Z"]})
    labels = attach_labels(signals, original)
    assert labels.available_at.tolist() == [pd.Timestamp("2022-08-28T00:00:00Z"), pd.Timestamp("2022-08-29T00:00:00Z")]
    assert labels.trend.tolist() == ["UP", "UP"]
    assert labels.volatility.tolist() == ["LOW", "LOW"]


def test_missing_hour_does_not_form_a_complete_daily_regime():
    frame = pd.DataFrame({"close": [100, 101, 102]}, index=pd.to_datetime(["2022-05-01T00:00Z", "2022-05-01T01:00Z", "2022-05-01T03:00Z"]))
    with pytest.raises(ValueError, match="cadence gap"):
        daily_context(frame)


def test_study_end_is_exclusive_and_regime_warmup_is_explicit():
    frame = pd.DataFrame({"close": np.repeat(100.0, 48)}, index=pd.date_range("2022-08-27", periods=48, freq="h", tz="UTC"))
    labels = attach_labels(pd.DataFrame({"trigger_close_at": ["2022-08-28T12:00:00Z"]}), daily_context(frame))
    assert labels.trend.iloc[0] == "UNAVAILABLE"
    with pytest.raises(ValueError, match="outside"):
        attach_labels(pd.DataFrame({"trigger_close_at": ["2026-08-28T00:00:00Z"]}), daily_context(frame))
