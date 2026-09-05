"""Synthetic verification and registered-tool parity for the benchmark boundary."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.research_pipeline import study_tools
from app.research_pipeline.benchmark_data import load_benchmark_data, verify_benchmark_inputs
from app.research_pipeline.tools import ToolContext, ToolVerificationError
from tests.test_btc_ai_pipeline_studies import (
    build_study_packet,
    change_packet,
    digest,
    refresh_source_identity,
    save_json,
)


@pytest.fixture
def study(tmp_path):
    return build_study_packet(tmp_path)


def test_one_full_verification_and_nine_tables_match_registered_tools(study, monkeypatch):
    params, context = study
    original = study_tools.execute_study_tool
    calls = []

    def counted(task, selected, tool_context):
        calls.append((task, tool_context.workspace))
        return original(task, selected, tool_context)

    monkeypatch.setattr(study_tools, "execute_study_tool", counted)
    data = load_benchmark_data(params, context)
    assert calls == [("summarize_m5_horizons", context.workspace / "verification")]
    assert data.summary["status"] == "VERIFIED"
    assert data.summary["alpha_assessment"] == "NOT_ASSESSED"
    assert data.input_identity == data.summary["input_identity"]
    evidence = context.workspace / "verification/artifacts/evidence.json"
    assert json.loads(evidence.read_text()) == data.summary
    assert len(list(context.workspace.rglob("evidence.json"))) == 1
    assert all(check["passed"] for check in data.checks)
    label_checks = [check for check in data.checks if check["name"] == "causal_regime_alignment"]
    assert [(check["population"], check["checked_rows"]) for check in label_checks] == [
        ("signals", 2), ("baseline", 3),
    ]
    assert all(value >= 0 for value in data.timings.values())
    assert set(data.timings) == {
        "full_verification_seconds", "reload_and_catalog_seconds", "total_seconds",
    }
    assert len(data.candidates) == 9
    for candidate in data.candidates:
        selected = candidate["parameters"]
        comparison_context = ToolContext(context.repo_root, context.repo_root / "parity", context.frozen_inputs)
        expected = original(candidate["task"], {**params, **selected}, comparison_context)
        assert expected["status"] == "VERIFIED"
        assert candidate["tables"] == expected["tables"]
    assert [(item["parameters"]["horizon_minutes"], item["parameters"]["grouping"])
            for item in data.candidates] == [
        (horizon, grouping) for horizon in (60, 120, 180)
        for grouping in ("calendar_year", "trend", "volatility")
    ]
    for frame, event_n in ((data.signals, 2), (data.baseline, 3)):
        assert len(frame) == event_n * 4
        assert set(frame.horizon_minutes) == {60, 120, 180, 240}
        assert set(frame.calendar_year) == {"2022"}
        assert set(frame.trend) == {"UP"}
        assert set(frame.volatility) == {"LOW"}
        assert frame.included_all_horizons.all()
        assert (frame.available_at <= frame.trigger_close_at).all()
        assert frame.groupby("event_id")[["trend", "volatility", "calendar_year"]].nunique().eq(1).all().all()


def test_failed_raw_check_cannot_produce_benchmark_catalog(study):
    change_packet(study, "signals.csv", lambda rows: rows.__setitem__("return_pct", 999))
    with pytest.raises(ToolVerificationError, match="full study verification failed"):
        load_benchmark_data(*study)
    evidence = json.loads((study[1].workspace / "verification/artifacts/evidence.json").read_text())
    assert evidence["status"] == "FAILED"
    assert any(check["name"] == "signals.return_pct" and not check["passed"] for check in evidence["checks"])


@pytest.mark.parametrize("stage", ["after_verification", "during_catalog"])
def test_inputs_changed_during_loading_are_rejected(study, monkeypatch, stage):
    params, _ = study
    target = "execute_study_tool" if stage == "after_verification" else "_comparison"
    original = getattr(study_tools, target)

    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        with Path(params["source_csv"]).open("a") as stream:
            stream.write("\n")
        return result

    if stage == "during_catalog":
        # Install after the saved summary, whose own aggregation must stay valid.
        execute = study_tools.execute_study_tool

        def install_after_summary(*args, **kwargs):
            result = execute(*args, **kwargs)
            monkeypatch.setattr(study_tools, target, mutate)
            return result

        monkeypatch.setattr(study_tools, "execute_study_tool", install_after_summary)
    else:
        monkeypatch.setattr(study_tools, target, mutate)
    with pytest.raises(ToolVerificationError, match="input identity"):
        load_benchmark_data(*study)


@pytest.mark.parametrize("refresh_frozen", [False, True])
def test_final_input_verifier_binds_loaded_identity_even_if_expectations_change(study, refresh_frozen):
    params, context = study
    data = load_benchmark_data(params, context)
    assert verify_benchmark_inputs(params, context, data.input_identity) is None
    with Path(params["source_csv"]).open("a") as stream:
        stream.write("\n")
    if refresh_frozen:
        refresh_source_identity(study)
    with pytest.raises(ToolVerificationError, match="input identity"):
        verify_benchmark_inputs(params, context, data.input_identity)


def test_future_hourly_values_do_not_change_benchmark_labels_or_tables(study):
    params, context = study
    before = load_benchmark_data(params, context)
    path = Path(params["h1_source_csv"])
    hourly = pd.read_csv(path)
    future = pd.to_datetime(hourly.timestamp, utc=True) >= pd.Timestamp("2022-08-28T00:00Z")
    hourly.loc[future, "close"] *= 0.01
    hourly.to_csv(path, index=False)
    refresh_source_identity(study, "h1_source_csv")
    after = load_benchmark_data(params, context)
    assert before.candidates == after.candidates
    assert before.input_identity != after.input_identity
    for population in ("signals", "baseline"):
        columns = ["event_id", "available_at", "calendar_year", "trend", "volatility"]
        pd.testing.assert_frame_equal(getattr(before, population)[columns], getattr(after, population)[columns])


@pytest.mark.parametrize("corruption", ["future", "missing_event", "duplicate_event", "wrong_year"])
def test_causal_alignment_and_complete_label_mapping_are_required(study, monkeypatch, corruption):
    original = study_tools.regimes.attach_labels

    def corrupt(rows, daily):
        attached = original(rows, daily)
        if corruption == "future":
            attached["available_at"] += pd.Timedelta(days=1)
        elif corruption == "missing_event":
            attached = attached.iloc[1:]
        elif corruption == "duplicate_event":
            attached = pd.concat([attached, attached.iloc[:1]], ignore_index=True)
        else:
            attached["calendar_year"] = "2099"
        return attached

    monkeypatch.setattr(study_tools.regimes, "attach_labels", corrupt)
    with pytest.raises(ToolVerificationError, match="label|alignment|calendar"):
        load_benchmark_data(*study)


def test_incomplete_four_hour_events_remain_excluded_at_all_horizons(study):
    params, _ = study
    source = Path(params["source_csv"])
    pd.read_csv(source).iloc[:65].to_csv(source, index=False)
    refresh_source_identity(study)

    def set_tail(rows):
        excluded = rows.event_id.str.endswith("24")
        rows.loc[excluded, "included_all_horizons"] = False
        tail = excluded & rows.horizon_minutes.eq(240)
        rows.loc[tail, "outcome_status"] = "INCOMPLETE_TAIL"
        rows.loc[tail, ["target_close_price", "return_pct", "mfe_pct", "mae_pct"]] = np.nan

    for name in ("signals.csv", "baseline.csv"):
        change_packet(study, name, set_tail)
    data = load_benchmark_data(*study)
    for frame in (data.signals, data.baseline):
        excluded = frame.loc[frame.event_id.str.endswith("24")]
        assert len(excluded) == 4
        assert not excluded.included_all_horizons.any()
        assert excluded.loc[excluded.horizon_minutes.eq(240), "return_pct"].isna().all()
    for candidate in data.candidates:
        assert candidate["tables"][0]["signal_n"] == 1
        assert candidate["tables"][0]["signal_complete_n"] == 2
        assert candidate["tables"][0]["baseline_n"] == 2


def test_insufficient_regime_history_stays_explicit_in_every_catalog(study):
    params, _ = study
    source = Path(params["h1_source_csv"])
    hourly = pd.read_csv(source)
    hourly.loc[pd.to_datetime(hourly.timestamp, utc=True) >= pd.Timestamp("2022-08-27T00:00Z")].to_csv(source, index=False)
    refresh_source_identity(study, "h1_source_csv")
    data = load_benchmark_data(*study)
    for frame in (data.signals, data.baseline):
        assert frame.trend.eq("UNAVAILABLE").all()
        assert frame.volatility.eq("UNAVAILABLE").all()
    for candidate in data.candidates:
        if candidate["parameters"]["grouping"] != "calendar_year":
            assert candidate["tables"][0]["group"] == "UNAVAILABLE"


def test_year_and_regime_boundary_with_shuffled_rows_matches_every_registered_cohort(study):
    params, context = study
    shift = pd.Timedelta(days=125, hours=23)
    for key in ("source_csv", "h1_source_csv"):
        path = Path(params[key])
        source = pd.read_csv(path)
        source["timestamp"] = pd.to_datetime(source.timestamp, utc=True) + shift
        if key == "h1_source_csv":
            source.loc[source.timestamp.eq(pd.Timestamp("2022-12-31T23:00Z")), "close"] *= 0.01
        source.to_csv(path, index=False)
        refresh_source_identity(study, key)
    for packet, name in (("horizon_packet", "signals.csv"), ("horizon_packet", "baseline.csv"),
                         ("baseline_packet", "signals.csv")):
        path = Path(params[packet]) / name
        rows = pd.read_csv(path)
        for column in ("trigger_close_at", "target_close_at"):
            rows[column] = pd.to_datetime(rows[column], utc=True) + shift
        rows.sort_values(["event_id", "horizon_minutes"], ascending=False).to_csv(path, index=False)
        if packet == "horizon_packet":
            context.frozen_inputs[f"horizon_{path.stem}_sha256"] = digest(path)
    manifest_path = Path(params["horizon_packet"]) / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for key in ("window_start_close_utc", "window_end_close_utc"):
        manifest["comparator"][key] = (pd.Timestamp(manifest["comparator"][key]) + shift).isoformat()
    manifest["parent"]["files_sha256"]["signals.csv"] = digest(Path(params["baseline_packet"]) / "signals.csv")
    save_json(manifest_path, manifest)
    context.frozen_inputs["horizon_manifest_sha256"] = digest(manifest_path)
    data = load_benchmark_data(params, context)
    assert data.signals.event_id.iloc[0] == "signal_24"
    for frame in (data.signals, data.baseline):
        assert set(frame.calendar_year) == {"2022", "2023"}
        assert set(frame.trend) == {"UP", "DOWN"}
        assert set(frame.volatility) == {"LOW", "HIGH"}
    for candidate in data.candidates:
        expected = study_tools.execute_study_tool(candidate["task"], {**params, **candidate["parameters"]}, context)
        assert expected["status"] == "VERIFIED"
        assert len(candidate["tables"]) == 2
        assert candidate["tables"] == expected["tables"]


@pytest.mark.parametrize("corruption", ["gap", "off_grid"])
def test_hourly_cadence_restrictions_apply_to_all_benchmark_candidates(study, corruption):
    params, _ = study
    path = Path(params["h1_source_csv"])
    source = pd.read_csv(path)
    if corruption == "gap":
        source = source.drop(index=100)
    else:
        source["timestamp"] = pd.to_datetime(source.timestamp, utc=True) + pd.Timedelta(minutes=5)
    source.to_csv(path, index=False)
    refresh_source_identity(study, "h1_source_csv")
    with pytest.raises(ToolVerificationError, match="cadence gap|off the native grid"):
        load_benchmark_data(*study)
