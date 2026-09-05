"""Exact short-horizon profiling, fixed populations, and paired uncertainty."""

from datetime import timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from research import btc_m5_horizon_diagnostic as diagnostic


def frame(periods=60):
    index = pd.date_range("2026-01-01", periods=periods, freq="5min", tz="UTC")
    return pd.DataFrame({"close": 100.0, "high": 100.0, "low": 100.0}, index=index)


@pytest.mark.parametrize("minutes", (60, 120, 180, 240))
def test_exact_horizon_excludes_trigger_and_post_target_candles(minutes):
    source = frame()
    target_position = minutes // 5
    source.iloc[0, source.columns.get_loc("high")] = 10000
    source.iloc[0, source.columns.get_loc("low")] = 1
    source.iloc[target_position, :] = [103, 105, 98]
    source.iloc[target_position + 1, :] = [109, 200, 10]
    trigger = source.index[0].to_pydatetime() + timedelta(minutes=5)
    rows = diagnostic.profile(source, [trigger], ["fixed-id"])
    outcome = rows.loc[rows.horizon_minutes.eq(minutes)].iloc[0]
    assert outcome.return_pct == pytest.approx(3)
    assert outcome.mfe_pct == pytest.approx(5)
    assert outcome.mae_pct == pytest.approx(-2)
    assert outcome.target_close_at == diagnostic.phase1._utc_iso(trigger + timedelta(minutes=minutes))


def test_excursions_include_zero_reference_when_entire_future_is_one_sided():
    source = frame()
    source.iloc[1:, :] = [102, 103, 101]
    trigger = source.index[0].to_pydatetime() + timedelta(minutes=5)
    positive = diagnostic.profile(source, [trigger], ["positive"])
    assert positive.mae_pct.eq(0).all()
    source.iloc[1:, :] = [98, 99, 97]
    negative = diagnostic.profile(source, [trigger], ["negative"])
    assert negative.mfe_pct.eq(0).all()


def test_gap_missing_exact_target_and_tail_remain_distinct_without_substitution():
    source = frame(40)
    trigger = source.index[0].to_pydatetime() + timedelta(minutes=5)
    source = source.drop(source.index[[20, 36]])
    rows = diagnostic.profile(source, [trigger], ["incomplete-id"])
    assert rows.outcome_status.tolist() == ["COMPLETE", "GAP", "MISSING_TARGET", "INCOMPLETE_TAIL"]
    assert rows.included_all_horizons.eq(False).all()
    invalid = rows.loc[rows.outcome_status.ne("COMPLETE")]
    assert invalid[["return_pct", "mfe_pct", "mae_pct"]].isna().all().all()
    stats = diagnostic.metrics(rows.loc[rows.horizon_minutes.eq(60)])
    assert stats["n_complete"] == 1
    assert stats["n_matched"] == 0
    assert stats["mean_return_pct"] is None


def test_baseline_checks_every_event_readiness_without_signal_gates(monkeypatch):
    source = frame(4)
    checked = []

    def prepare(event, *, symbol):
        checked.append((event.position, symbol))
        return SimpleNamespace(reason="MISSING_H4" if event.position == 1 else diagnostic.PREPARATION_READY)

    monkeypatch.setattr(diagnostic.phase1, "_cache_for", lambda _: SimpleNamespace(prepare=prepare))
    times = source.index.to_pydatetime() + timedelta(minutes=5)
    eligible, audit = diagnostic.eligible_baseline(SimpleNamespace(frames={"5m": source}), times[0], times[-1])
    assert eligible == [times[0], times[2], times[3]]
    assert checked == [(position, "BTC/USDT") for position in range(4)]
    assert audit["candidate_bar_count"] == 4
    assert audit["eligible_bar_count"] == 3
    assert audit["preparation_exclusion_reasons"] == {"MISSING_H4": 1}


def test_paired_calendar_bootstrap_is_reproducible_and_preserves_common_shocks():
    days = pd.date_range("2026-01-01", periods=21, freq="D", tz="UTC")
    # Two observations on day zero exercise observation weighting; days without
    # observations must still remain on the calendar, including baseline-only days.
    data = pd.DataFrame({"trigger_close_at": [value.isoformat() for value in days[[0, 0, 7, 20]]],
                         "return_pct": [-3.0, 1.0, 5.0, 9.0], "included_all_horizons": True})
    baseline = data.assign(return_pct=data.return_pct + 2)
    first = diagnostic.paired_bootstrap(data, baseline)
    assert first == diagnostic.paired_bootstrap(data, baseline)
    assert first["calendar_days"] == 21
    assert first["replicates"] == 2000
    assert first["valid_replicates"] > 1900
    assert first["signal_minus_baseline_ci_pp"] == pytest.approx([-2, -2])
    assert first["signal_mean_ci_pct"][1] > first["signal_mean_ci_pct"][0]


def test_calendar_bootstrap_keeps_baseline_only_days_and_can_omit_short_windows():
    data = pd.DataFrame({"trigger_close_at": ["2026-01-01T00:00:00Z", "2026-01-21T00:00:00Z"],
                         "return_pct": [1.0, 3.0], "included_all_horizons": True})
    result = diagnostic.paired_bootstrap(data.iloc[[0]], data)
    assert result["calendar_days"] == 21
    assert result["valid_replicates"] < 2000
    assert result["status"] == "INCOMPLETE"
    assert result["undefined_replicates"] == 2000 - result["valid_replicates"]
    assert result["signal_mean_ci_pct"] == [1.0, 1.0]
    assert diagnostic.paired_bootstrap(data.iloc[[0]], data.iloc[[0]])["status"] == "OMITTED"


def test_parent_return_parity_rejects_changed_trigger_price():
    source = frame()
    trigger = source.index[0].to_pydatetime() + timedelta(minutes=5)
    current = diagnostic.profile(source, [trigger], ["fixed-id"])
    parent = current.loc[current.horizon_minutes.isin([60, 240])].copy()
    diagnostic.verify_parent_returns(parent, current)
    parent.loc[:, "trigger_close_price"] = 101.0
    with pytest.raises(ValueError, match="trigger_close_price"):
        diagnostic.verify_parent_returns(parent, current)


def test_monthly_and_horizon_summaries_share_complete_population():
    source = frame(80)
    times = [source.index[position].to_pydatetime() + timedelta(minutes=5) for position in (0, 40)]
    rows = diagnostic.profile(source, times, ["complete", "tail"])
    summary = diagnostic.summarize(rows, rows, bootstrap=False)
    assert summary["excluded_signal_ids"] == ["tail"]
    assert all(item["signal"]["n_matched"] == 1 for item in summary["horizon_summaries"])
    assert all(item["n_matched"] == 1 for item in summary["monthly_summaries"])
    assert all(np.isclose(item["signal_minus_baseline_mean_pp"], 0) for item in summary["horizon_summaries"])
