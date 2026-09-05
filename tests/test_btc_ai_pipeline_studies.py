"""Small synthetic packets exercise independent population evidence checks."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.research_pipeline import study_tools
from app.research_pipeline.study_tools import execute_study_tool, prepare_study_context
from app.research_pipeline.tools import ToolContext, ToolRestrictionError


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def save_source(path, frame):
    frame.rename_axis("timestamp").reset_index().to_csv(path, index=False)


def packet_rows(frame, positions, prefix):
    rows = []
    for position in positions:
        trigger = frame.index[position] + pd.Timedelta(minutes=5)
        price = float(frame.close.iloc[position])
        for horizon in (60, 120, 180, 240):
            end = position + horizon // 5
            complete = end < len(frame)
            target_price = float(frame.close.iloc[end]) if complete else None
            rows.append({"event_id": f"{prefix}{position}", "trigger_close_at": trigger.isoformat(),
                         "trigger_close_price": price, "horizon_minutes": horizon,
                         "target_close_at": (trigger + pd.Timedelta(minutes=horizon)).isoformat(),
                         "target_close_price": target_price,
                         "outcome_status": "COMPLETE" if complete else "INCOMPLETE_TAIL",
                         "return_pct": round((target_price / price - 1) * 100, 10) if complete else None,
                         "mfe_pct": 0.0 if complete else None, "mae_pct": 0.0 if complete else None,
                         "included_all_horizons": position + 48 < len(frame)})
    return pd.DataFrame(rows)


def build_study_packet(tmp_path):
    """Build a portable synthetic input set for study/controller integration tests."""
    root = tmp_path / "repo"
    packet = root / "research/results/horizon"
    parent = root / "research/results/parent"
    data = root / "research/data"
    for path in (packet, parent, data):
        path.mkdir(parents=True)
    index = pd.date_range("2022-08-28T00:00:00Z", periods=100, freq="5min")
    frame = pd.DataFrame({"open": 100.0, "high": 150.0, "low": 50.0,
                          "close": 100.0, "volume": 1.0}, index=index)
    for position, price in {0: 100, 12: 105, 24: 110, 36: 90, 48: 120, 60: 100, 72: 99}.items():
        frame.loc[index[position], "close"] = price
    source = data / "BTCUSDT_5m.csv"
    save_source(source, frame)
    h1 = data / "BTCUSDT_1h.csv"
    h1_frame = pd.DataFrame({"open": 100.0, "high": 1000.0, "low": 1.0,
                             "close": np.exp(np.arange(24 * 125) * 0.0001) * 100, "volume": 1.0},
                            index=pd.date_range("2022-05-01", periods=24 * 125, freq="h", tz="UTC"))
    save_source(h1, h1_frame)
    signals = packet_rows(frame, [0, 24], "signal_")
    baseline = packet_rows(frame, [0, 12, 24], "bar_")
    signals.to_csv(packet / "signals.csv", index=False)
    baseline.to_csv(packet / "baseline.csv", index=False)
    parent_rows = signals.assign(timeframe="5m")
    parent_rows.to_csv(parent / "signals.csv", index=False)
    save_json(parent / "manifest.json", {"run_id": "parent", "completion_status": "SUCCESS"})
    ids = signals.drop_duplicates("event_id").sort_values("trigger_close_at").event_id.tolist()
    manifest = {"definition_version": "btc-m5-horizon-diagnostic-v1", "completion_status": "SUCCESS",
                "definitions": {"horizons_minutes": [60, 120, 180, 240]},
                "inputs": {"files": {"5m": {"path": "C:/old-checkout/BTCUSDT_5m.csv", "sha256": digest(source)},
                                      "1h": {"path": "C:/old-checkout/BTCUSDT_1h.csv", "sha256": digest(h1)}}},
                "parent": {"run_id": "parent", "signal_count": 2,
                           "signal_ids_sha256": hashlib.sha256("\n".join(ids).encode()).hexdigest(),
                           "files_sha256": {name: digest(parent / name) for name in ("manifest.json", "signals.csv")}},
                "comparator": {"eligible_bar_count": 3, "candidate_bar_count": 25,
                               "preparation_excluded_count": 22,
                               "window_start_close_utc": signals.trigger_close_at.iloc[0],
                               "window_end_close_utc": signals.trigger_close_at.iloc[-1]}}
    save_json(packet / "manifest.json", manifest)
    params = {"mode": "fixture", "baseline_packet": str(parent), "horizon_packet": str(packet),
              "source_csv": str(source), "h1_source_csv": str(h1)}
    frozen = {"source_sha256": digest(source), "h1_source_sha256": digest(h1),
              "horizon_manifest_sha256": digest(packet / "manifest.json"),
              "horizon_signals_sha256": digest(packet / "signals.csv"),
              "horizon_baseline_sha256": digest(packet / "baseline.csv"),
              "baseline_manifest_sha256": digest(parent / "manifest.json")}
    return params, ToolContext(root, root / "job", frozen)


@pytest.fixture
def study(tmp_path):
    return build_study_packet(tmp_path)


def change_packet(study, filename, mutate):
    params, context = study
    path = Path(params["horizon_packet"]) / filename
    frame = pd.read_csv(path)
    mutate(frame)
    frame.to_csv(path, index=False)
    context.frozen_inputs[f"horizon_{path.stem}_sha256"] = digest(path)


def refresh_source_identity(study, key="source_csv"):
    params, context = study
    hash_key, timeframe = ("source_sha256", "5m") if key == "source_csv" else ("h1_source_sha256", "1h")
    context.frozen_inputs[hash_key] = digest(params[key])
    path = Path(params["horizon_packet"]) / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["inputs"]["files"][timeframe]["sha256"] = context.frozen_inputs[hash_key]
    save_json(path, manifest)
    context.frozen_inputs["horizon_manifest_sha256"] = digest(path)


def test_summary_uses_known_raw_arithmetic_and_writes_compact_artifact(study):
    params, context = study
    result = execute_study_tool("summarize_m5_horizons", params, context)
    assert result["status"] == "VERIFIED"
    assert result["verification_mode"] == "fixture_validation"
    assert result["alpha_assessment"] == "NOT_ASSESSED"
    assert [row["horizon_minutes"] for row in result["tables"]] == [60, 120, 180]
    first = result["tables"][0]
    signal_mean = (5 + (90 / 110 - 1) * 100) / 2
    baseline_mean = (5 + (110 / 105 - 1) * 100 + (90 / 110 - 1) * 100) / 3
    assert first["grouping"] == "all"
    assert first["group"] == "ALL"
    assert first["signal_n"] == 2
    assert first["baseline_n"] == 3
    assert first["signal_mean_return_pct"] == pytest.approx(signal_mean)
    assert first["signal_median_return_pct"] == pytest.approx(signal_mean)
    assert first["signal_positive_return_share"] == 0.5
    assert first["signal_minus_baseline_pp"] == pytest.approx(signal_mean - baseline_mean)
    assert result["input_identity"]["source_path"] == params["source_csv"]
    assert result == json.loads((context.workspace / "artifacts/evidence.json").read_text())
    assert execute_study_tool("summarize_m5_horizons", params, context) == result


def test_prepare_context_exposes_unverified_preview_and_grouping_choices(study):
    params, context = study
    result = prepare_study_context(params, context)
    assert result["status"] == "UNVERIFIED"
    assert result["available_groupings"] == ["calendar_year", "trend", "volatility"]
    assert result["horizons_minutes"] == [60, 120, 180]
    assert len(result["tables"]) == 3
    assert len(json.dumps(result)) < 14000


@pytest.mark.parametrize("field,value", [("return_pct", 999), ("trigger_close_price", 99),
                                        ("target_close_price", 999), ("target_close_at", "2022-08-28T01:06:00Z"),
                                        ("trigger_close_at", "nonsense"), ("included_all_horizons", False)])
def test_frozen_packet_with_wrong_numerical_or_population_claim_fails(study, field, value):
    change_packet(study, "signals.csv", lambda frame: frame.__setitem__(field, value))
    result = execute_study_tool("summarize_m5_horizons", *study)
    assert result["status"] == "FAILED"
    assert result["tables"] == []
    assert result["checks"]


@pytest.mark.parametrize("filename", ["signals.csv", "baseline.csv"])
def test_duplicate_or_missing_horizon_is_not_silently_dropped(study, filename):
    change_packet(study, filename, lambda frame: frame.drop(index=0, inplace=True))
    assert execute_study_tool("summarize_m5_horizons", *study)["status"] == "FAILED"


def test_frozen_source_change_and_missing_expected_hash_fail(study):
    params, context = study
    with Path(params["source_csv"]).open("a") as stream:
        stream.write("\n")
    assert execute_study_tool("summarize_m5_horizons", params, context)["status"] == "FAILED"
    context.frozen_inputs.pop("horizon_baseline_sha256")
    assert execute_study_tool("summarize_m5_horizons", params, context)["status"] == "FAILED"


@pytest.mark.parametrize("position", [12, 5])
def test_missing_target_or_intervening_bar_cannot_be_replaced(study, position):
    params, _ = study
    path = Path(params["source_csv"])
    source = pd.read_csv(path).drop(index=position)
    source.to_csv(path, index=False)
    refresh_source_identity(study)
    result = execute_study_tool("summarize_m5_horizons", *study)
    assert result["status"] == "FAILED"
    assert any("outcome_status" in str(check) for check in result["checks"])


@pytest.mark.parametrize("grouping,group", [("calendar_year", "2022"), ("trend", "UP"), ("volatility", "LOW")])
def test_cohort_grouping_uses_same_checked_observations(study, grouping, group):
    params, context = study
    result = execute_study_tool("compare_m5_cohorts", {**params, "horizon_minutes": 120, "grouping": grouping}, context)
    assert result["status"] == "VERIFIED"
    assert [row["group"] for row in result["tables"]] == [group]
    assert result["tables"][0]["signal_n"] == 2
    assert result["tables"][0]["signal_mean_return_pct"] == pytest.approx((10 + (120 / 110 - 1) * 100) / 2)


def test_future_h1_values_cannot_change_event_labels(study):
    params, context = study
    cohort = {**params, "horizon_minutes": 60, "grouping": "trend"}
    before = execute_study_tool("compare_m5_cohorts", cohort, context)
    path = Path(params["h1_source_csv"])
    h1 = pd.read_csv(path)
    future = pd.to_datetime(h1.timestamp, utc=True) >= pd.Timestamp("2022-08-28T00:00Z")
    h1.loc[future, "close"] *= 0.01
    h1.to_csv(path, index=False)
    refresh_source_identity(study, "h1_source_csv")
    after = execute_study_tool("compare_m5_cohorts", cohort, context)
    assert before["status"] == after["status"] == "VERIFIED"
    assert before["tables"] == after["tables"]


def test_h1_gap_is_rejected_and_never_bridged(study):
    params, context = study
    path = Path(params["h1_source_csv"])
    pd.read_csv(path).drop(index=100).to_csv(path, index=False)
    refresh_source_identity(study, "h1_source_csv")
    result = execute_study_tool("compare_m5_cohorts", {**params, "horizon_minutes": 60, "grouping": "trend"}, context)
    assert result["status"] == "FAILED"


def test_no_raw_source_fallback_to_historical_manifest_path(study):
    params, context = study
    params.pop("source_csv")
    with pytest.raises(ToolRestrictionError, match="source_csv"):
        execute_study_tool("summarize_m5_horizons", params, context)


@pytest.mark.parametrize("extra", [{"grouping": "choose", "horizon_minutes": 60},
                                  {"grouping": "trend", "horizon_minutes": 240},
                                  {"grouping": "trend", "horizon_minutes": True}])
def test_executor_must_select_a_registered_concrete_cohort(study, extra):
    params, context = study
    with pytest.raises(ToolRestrictionError):
        execute_study_tool("compare_m5_cohorts", {**params, **extra}, context)


def test_four_hour_incomplete_event_is_excluded_even_when_shorter_returns_exist(study):
    params, context = study
    path = Path(params["source_csv"])
    pd.read_csv(path).iloc[:65].to_csv(path, index=False)
    refresh_source_identity(study)
    for filename in ("signals.csv", "baseline.csv"):
        def set_tail(frame):
            frame.loc[frame.event_id.str.endswith("24"), "included_all_horizons"] = False
            tail = frame.event_id.str.endswith("24") & frame.horizon_minutes.eq(240)
            frame.loc[tail, "outcome_status"] = "INCOMPLETE_TAIL"
            frame.loc[tail, ["target_close_price", "return_pct", "mfe_pct", "mae_pct"]] = np.nan
        change_packet(study, filename, set_tail)
    result = execute_study_tool("summarize_m5_horizons", params, context)
    assert result["status"] == "VERIFIED"
    assert [row["signal_n"] for row in result["tables"]] == [1, 1, 1]
    assert [row["signal_complete_n"] for row in result["tables"]] == [2, 2, 2]
    assert [row["signal_mean_return_pct"] for row in result["tables"]] == [5, 10, -10]


def test_checker_detects_a_deliberately_forward_joined_regime(study, monkeypatch):
    params, context = study
    original = study_tools.regimes.attach_labels

    def future_join(rows, daily):
        attached = original(rows, daily)
        attached["available_at"] += pd.Timedelta(days=1)
        return attached

    monkeypatch.setattr(study_tools.regimes, "attach_labels", future_join)
    result = execute_study_tool("compare_m5_cohorts", {**params, "horizon_minutes": 60, "grouping": "trend"}, context)
    assert result["status"] == "FAILED"
    assert result["tables"] == []
    assert any(check["name"] == "causal_regime_alignment" and not check["passed"] for check in result["checks"])


def test_off_grid_hourly_source_cannot_supply_daily_labels(study):
    params, context = study
    path = Path(params["h1_source_csv"])
    source = pd.read_csv(path)
    source["timestamp"] = pd.to_datetime(source.timestamp, utc=True) + pd.Timedelta(minutes=5)
    source.to_csv(path, index=False)
    refresh_source_identity(study, "h1_source_csv")
    result = execute_study_tool("compare_m5_cohorts", {**params, "horizon_minutes": 60, "grouping": "trend"}, context)
    assert result["status"] == "FAILED"


def test_insufficient_regime_warmup_remains_explicit(study):
    params, context = study
    path = Path(params["h1_source_csv"])
    source = pd.read_csv(path)
    source.loc[pd.to_datetime(source.timestamp, utc=True) >= pd.Timestamp("2022-08-27T00:00Z")].to_csv(path, index=False)
    refresh_source_identity(study, "h1_source_csv")
    result = execute_study_tool("compare_m5_cohorts", {**params, "horizon_minutes": 60, "grouping": "volatility"}, context)
    assert result["status"] == "VERIFIED"
    assert result["unavailable_regime_events"] == {"signals": 2, "baseline": 3}
    assert result["tables"][0]["group"] == "UNAVAILABLE"


def test_input_changed_during_analysis_cannot_produce_verified_tables(study, monkeypatch):
    params, context = study
    summary = study_tools._summary

    def modify_after_summary(*args):
        result = summary(*args)
        with Path(params["source_csv"]).open("a") as stream:
            stream.write("\n")
        return result

    monkeypatch.setattr(study_tools, "_summary", modify_after_summary)
    result = execute_study_tool("summarize_m5_horizons", params, context)
    assert result["status"] == "FAILED"
    assert result["tables"] == []


@pytest.mark.parametrize("field", ["inputs", "definitions", "parent", "comparator"])
def test_malformed_nested_manifest_is_failed_evidence(study, field):
    params, context = study
    path = Path(params["horizon_packet"]) / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest[field] = []
    save_json(path, manifest)
    context.frozen_inputs["horizon_manifest_sha256"] = digest(path)
    assert execute_study_tool("summarize_m5_horizons", params, context)["status"] == "FAILED"


@pytest.mark.parametrize("parameter", ["source_csv", "h1_source_csv"])
def test_missing_current_raw_file_yields_no_numerical_claim(study, parameter):
    params, context = study
    Path(params[parameter]).unlink()
    result = execute_study_tool("summarize_m5_horizons", params, context)
    assert result["status"] == "FAILED"
    assert result["tables"] == []


def test_controller_path_boundary_is_preserved(study, tmp_path):
    params, context = study
    outside = tmp_path / "unregistered.csv"
    outside.write_bytes(Path(params["source_csv"]).read_bytes())
    with pytest.raises(ToolRestrictionError, match="outside"):
        execute_study_tool("summarize_m5_horizons", {**params, "source_csv": str(outside)}, context)
