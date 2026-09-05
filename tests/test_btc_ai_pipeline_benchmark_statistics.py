"""Synthetic statistical-contract tests; no market data or provider calls."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
import pytest

from app.research_pipeline.benchmark_data import _catalog
from app.research_pipeline.benchmark_statistics import evaluate_diagnostics


def _frame(events: list[tuple[int, float, str]], *, start: str = "2020-01-01") -> pd.DataFrame:
    rows = []
    for event, (day, value, trend) in enumerate(events):
        timestamp = pd.Timestamp(start, tz="UTC") + pd.Timedelta(days=day)
        for horizon in (60, 120, 180, 240):
            rows.append({"event_id": str(event), "trigger_close_at": timestamp,
                         "horizon_minutes": horizon, "return_pct": value,
                         "included_all_horizons": True, "calendar_year": str(timestamp.year),
                         "trend": trend, "volatility": "normal"})
    return pd.DataFrame(rows)


def _cohort(result: dict[str, Any], group: str = "up", grouping: str = "trend", horizon: int = 60) -> dict[str, Any]:
    candidate = next(item for item in result["candidates"] if item["parameters"] == {
        "horizon_minutes": horizon, "grouping": grouping,
    })
    return next(item for item in candidate["cohorts"] if item["group"] == group)


def test_estimand_uses_separate_population_denominators_not_average_daily_gaps() -> None:
    signals = _frame([(0, 10, "up"), (0, 10, "up"), (1, 0, "up")])
    baseline = _frame([(0, 0, "up"), (1, 6, "up"), (1, 6, "up")])

    result = evaluate_diagnostics(signals, baseline, replications=40, block_lengths=(1,))
    cohort = _cohort(result)

    assert cohort["delta_pp"] == pytest.approx(8 / 3)
    assert cohort["pooled_delta_pp"] == pytest.approx(8 / 3)
    assert cohort["contrast_pp"] == 0
    assert cohort["signal_n"] == cohort["baseline_n"] == 3
    assert len(result["candidates"]) == 9
    assert all(_cohort(result, horizon=h)["signal_n"] == 3 for h in (60, 120, 180))


def test_identical_variable_populations_have_zero_paired_intervals() -> None:
    frame = _frame([(day, float(day % 9 - 3), "up" if day % 2 else "down") for day in range(90)])

    result = evaluate_diagnostics(frame, frame.copy(), replications=60)

    for candidate in result["candidates"]:
        for cohort in candidate["cohorts"]:
            for bootstrap in cohort["bootstrap"]:
                assert bootstrap["delta_ci_pp"] == [0, 0]
                assert bootstrap["contrast_ci_pp"] == [0, 0]
                assert bootstrap["valid_replicates"] == 60
                assert bootstrap["undefined_replicates"] == 0


def test_continuous_grid_keeps_zero_signal_days_and_filters_incomplete_events() -> None:
    signals = _frame([(2, 1, "up"), (6, 3, "up"), (4, 999, "up")])
    signals.loc[signals.event_id.eq("2"), "included_all_horizons"] = False
    baseline = _frame([(0, 0, "up"), (9, 0, "up")])

    result = evaluate_diagnostics(signals, baseline, replications=40, block_lengths=(1,))

    assert result["calendar_grid"] == {"start_utc": "2020-01-01", "end_utc": "2020-01-10",
                                       "days": 10, "signal_zero_days": 8, "baseline_zero_days": 8}
    cohort = _cohort(result)
    assert cohort["signal_n"] == 2
    assert cohort["delta_pp"] == 2
    assert cohort["support"]["signal"] == {"active_utc_weeks": 2, "max_utc_week_share": 0.5}
    assert _cohort(result, "2020", "calendar_year")["support"]["partial_calendar_year"] is True


def test_cohort_missing_one_population_is_undefined_and_json_safe() -> None:
    result = evaluate_diagnostics(_frame([(0, 1, "up")]), _frame([(1, 2, "down")]),
                                  replications=20, block_lengths=(1,))

    cohort = _cohort(result)
    assert cohort["signal_n"] == 1 and cohort["baseline_n"] == 0
    assert cohort["delta_pp"] is None and cohort["contrast_pp"] is None
    assert cohort["support"]["baseline"] == {"active_utc_weeks": 0, "max_utc_week_share": None}
    assert cohort["bootstrap"][0]["valid_replicates"] == 0
    assert cohort["bootstrap"][0]["undefined_replicates"] == 20
    assert cohort["bootstrap"][0]["delta_ci_pp"] is None
    json.dumps(result, allow_nan=False)


def test_seed_reproduces_shared_draws_and_changes_sampling_intervals() -> None:
    signals = _frame([(day, float(day * day), "up") for day in range(20)])
    baseline = _frame([(day, 0, "up") for day in range(20)])
    first = evaluate_diagnostics(signals, baseline, replications=25, block_lengths=(1, 7), seed=11)
    again = evaluate_diagnostics(signals, baseline, replications=25, block_lengths=(1, 7), seed=11)
    changed = evaluate_diagnostics(signals, baseline, replications=25, block_lengths=(1, 7), seed=12)

    assert first == again
    assert _cohort(first)["bootstrap"] != _cohort(changed)["bootstrap"]
    for horizon in (120, 180):
        assert _cohort(first, horizon=horizon)["bootstrap"] == _cohort(first)["bootstrap"]
    assert _cohort(first, "normal", "volatility")["bootstrap"] == _cohort(first)["bootstrap"]


def test_leave_consecutive_28_day_blocks_recomputes_denominators_and_sign_changes() -> None:
    signals = _frame([(0, 10, "up"), (0, 10, "up"), (28, -2, "up")])
    baseline = _frame([(0, 0, "up"), (28, 0, "up"), (28, 0, "up")])

    result = evaluate_diagnostics(signals, baseline, replications=20, block_lengths=(7,))
    influence = _cohort(result)["influence"]

    assert _cohort(result)["delta_pp"] == 6
    assert influence == {"block_days": 28, "blocks": 2, "max_abs_delta_change_pp": 8,
                         "max_abs_contrast_change_pp": 0, "delta_sign_changes": 1,
                         "contrast_sign_changes": 0, "undefined_delta_cases": 0, "undefined_contrast_cases": 0}


def test_contrast_uses_pooled_same_horizon_and_empty_leave_block_is_counted() -> None:
    signals = _frame([(0, 10, "up"), (28, -2, "down")])
    baseline = _frame([(0, 0, "up"), (28, 0, "down")])

    result = evaluate_diagnostics(signals, baseline, replications=20, block_lengths=(7,))
    cohort = _cohort(result)

    assert cohort["delta_pp"] == 10
    assert cohort["pooled_delta_pp"] == 4
    assert cohort["contrast_pp"] == 6
    assert cohort["influence"]["max_abs_contrast_change_pp"] == 6
    assert cohort["influence"]["undefined_delta_cases"] == 1
    assert cohort["influence"]["undefined_contrast_cases"] == 1


def test_nonfinite_returns_are_undefined_without_nan_json() -> None:
    signals = _frame([(0, np.inf, "up"), (28, 2, "down")])
    result = evaluate_diagnostics(signals, _frame([(0, 0, "up"), (28, 0, "down")]),
                                  replications=20, block_lengths=(7,))
    assert _cohort(result)["delta_pp"] is None
    assert _cohort(result, "down")["delta_pp"] == 2
    assert _cohort(result, "down")["pooled_delta_pp"] is None
    json.dumps(result, allow_nan=False)


@pytest.mark.filterwarnings("error::RuntimeWarning")
def test_extreme_finite_returns_cannot_emit_nonfinite_interval_bounds() -> None:
    signals = _frame([(0, -1e308, "up"), (1, 1e308, "up")])
    baseline = _frame([(0, 0, "up"), (1, 0, "up")])
    result = evaluate_diagnostics(signals, baseline, replications=40, block_lengths=(1,))
    json.dumps(result, allow_nan=False)


def test_full_calendar_year_is_not_marked_partial_and_input_frames_are_unchanged() -> None:
    frame = _frame([(0, 1, "up"), (365, 2, "up")])
    original = frame.copy(deep=True)
    result = evaluate_diagnostics(frame, frame, replications=20, block_lengths=(7,))
    assert _cohort(result, "2020", "calendar_year")["support"]["partial_calendar_year"] is False
    pd.testing.assert_frame_equal(frame, original)


def test_duplicate_event_horizon_rows_are_rejected_instead_of_double_counted() -> None:
    frame = _frame([(0, 1, "up")])
    with pytest.raises(ValueError, match="duplicate"):
        evaluate_diagnostics(pd.concat([frame, frame.iloc[:1]]), frame, replications=20)


def test_excluded_only_cohorts_preserve_full_catalog_parity_without_expanding_calendar() -> None:
    frame = _frame([(0, 1, "up"), (367, 999, "excluded_only")])
    frame["outcome_status"] = "COMPLETE"
    frame.loc[frame.event_id.eq("1"), "included_all_horizons"] = False
    frame.loc[frame.event_id.eq("1"), "volatility"] = "excluded_vol"
    catalog = _catalog(frame, frame.copy(), "fixture")

    result = evaluate_diagnostics(frame, frame.copy(), replications=20)

    assert result["calendar_grid"]["days"] == 1
    for candidate, checked in zip(result["candidates"], catalog, strict=True):
        assert [row["group"] for row in candidate["cohorts"]] == [row["group"] for row in checked["tables"]]
        for row, expected in zip(candidate["cohorts"], checked["tables"], strict=True):
            assert row["signal_n"] == expected["signal_n"]
            assert row["baseline_n"] == expected["baseline_n"]
            assert row["delta_pp"] == expected["signal_minus_baseline_pp"]
    excluded = _cohort(result, "excluded_only")
    assert excluded["signal_n"] == excluded["baseline_n"] == 0
    assert excluded["delta_pp"] is None and excluded["contrast_pp"] is None
    assert excluded["support"]["signal"] == {"active_utc_weeks": 0, "max_utc_week_share": None}
    assert all(row["valid_replicates"] == 0 and row["undefined_replicates"] == 20
               and row["delta_ci_pp"] is None and row["contrast_ci_pp"] is None for row in excluded["bootstrap"])
    json.dumps(result, allow_nan=False)


def test_horizon_specific_label_universes_do_not_create_phantom_cohorts() -> None:
    frame = _frame([(0, 1, "up")])
    frame.loc[frame.horizon_minutes.eq(120), "trend"] = "middle_horizon_only"

    result = evaluate_diagnostics(frame, frame.copy(), replications=20)

    by_horizon = {candidate["parameters"]["horizon_minutes"]: [row["group"] for row in candidate["cohorts"]]
                  for candidate in result["candidates"] if candidate["parameters"]["grouping"] == "trend"}
    assert by_horizon == {60: ["up"], 120: ["middle_horizon_only"], 180: ["up"]}


@pytest.mark.parametrize("options", [
    {"replications": 0}, {"replications": True}, {"replications": 10001},
    {"block_lengths": ()}, {"block_lengths": (0,)}, {"block_lengths": (7, 7)},
    {"block_lengths": (True,)}, {"seed": -1}, {"seed": True},
])
def test_invalid_configuration_fails_before_computation(options: dict[str, Any]) -> None:
    frame = _frame([(0, 1, "up")])
    with pytest.raises(ValueError):
        evaluate_diagnostics(frame, frame, **options)


def test_empty_included_population_is_rejected() -> None:
    frame = _frame([(0, 1, "up")])
    with pytest.raises(ValueError, match="empty"):
        evaluate_diagnostics(frame.iloc[:0], frame, replications=20)
    frame["included_all_horizons"] = False
    with pytest.raises(ValueError, match="empty"):
        evaluate_diagnostics(frame, frame, replications=20)
