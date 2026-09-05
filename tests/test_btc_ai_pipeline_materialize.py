"""Reconstruct a missing frozen comparator without modifying historical packets."""

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from app.backtest.signal_replay_data import load_ohlcv_csv
from app.research_pipeline.study_materialize import materialize_study_packet
from app.research_pipeline.study_tools import execute_study_tool
from app.research_pipeline.tools import ToolContext
from research import btc_m5_horizon_diagnostic as diagnostic
from tests.test_btc_ai_pipeline_studies import build_study_packet, digest, save_json


@pytest.fixture
def materialization(tmp_path):
    params, context = build_study_packet(tmp_path)
    horizon, parent = Path(params["horizon_packet"]), Path(params["baseline_packet"])
    frame = load_ohlcv_csv(params["source_csv"], "5m")
    times = (frame.index[:25] + pd.Timedelta(minutes=5)).to_pydatetime().tolist()
    baseline = diagnostic.profile(frame, times, ["bar_" + timestamp.strftime("%Y-%m-%dT%H:%M:%SZ") for timestamp in times])
    baseline["target_close_price"] = pd.to_numeric(baseline.target_close_price)
    (horizon / "baseline.csv").unlink()
    summary = {"alpha_assessment": "NOT_ASSESSED", "excluded_baseline_count": 0,
               "horizon_summaries": [{"horizon_minutes": minutes,
                                      "baseline": diagnostic.metrics(baseline.loc[baseline.horizon_minutes.eq(minutes)])}
                                     for minutes in diagnostic.HORIZONS]}
    save_json(horizon / "summary.json", summary)
    (horizon / "report.md").write_text("# Historical horizon report\n", encoding="utf-8")
    save_json(parent / "summary.json", {"completion_status": "SUCCESS"})
    (parent / "report.md").write_bytes(b"# Historical parent report\n")
    manifest = json.loads((horizon / "manifest.json").read_text())
    manifest["run_id"] = horizon.name
    manifest["comparator"].update(eligible_bar_count=25, preparation_excluded_count=0, preparation_exclusion_reasons={})
    manifest["parent"]["files_sha256"] = {name: digest(parent / name)
                                              for name in ("manifest.json", "signals.csv", "summary.json", "report.md")}
    save_json(horizon / "manifest.json", manifest)
    kwargs = {"repo_root": context.repo_root, "horizon_packet": horizon, "baseline_packet": parent,
              "data_dir": Path(params["source_csv"]).parent,
              "workspace": context.repo_root / "research/results/prepared"}
    return kwargs, baseline


def historical_hashes(kwargs):
    return {str(path): digest(path) for directory in (kwargs["horizon_packet"], kwargs["baseline_packet"], kwargs["data_dir"])
            for path in directory.iterdir() if path.is_file()}


def test_materializes_exact_small_comparator_and_checks_return_evidence(materialization):
    kwargs, expected = materialization
    before = historical_hashes(kwargs)
    result = materialize_study_packet(**kwargs)
    horizon, parent = Path(result["horizon_packet"]), Path(result["baseline_packet"])
    assert horizon.name == kwargs["horizon_packet"].name
    assert parent.name == kwargs["baseline_packet"].name
    assert Path(result["data_dir"]) == kwargs["data_dir"]
    pd.testing.assert_frame_equal(pd.read_csv(horizon / "baseline.csv"), expected, check_dtype=False, atol=1e-10)
    assert historical_hashes(kwargs) == before
    manifest = json.loads((horizon / "manifest.json").read_text())
    assert manifest["materialization"]["original_comparator"]["eligible_bar_count"] == 25
    assert manifest["materialization"]["baseline_rows"] == 100
    assert manifest["materialization"]["saved_summary_parity"] is True
    provenance = json.loads((kwargs["workspace"] / "materialization_report.json").read_text())
    assert provenance["status"] == "VERIFIED"
    assert provenance["output_sha256"][str((horizon / "baseline.csv").relative_to(kwargs["workspace"]))] == digest(horizon / "baseline.csv")
    params = {"mode": "fixture", "horizon_packet": str(horizon), "baseline_packet": str(parent),
              "source_csv": str(kwargs["data_dir"] / "BTCUSDT_5m.csv"), "h1_source_csv": str(kwargs["data_dir"] / "BTCUSDT_1h.csv")}
    hashes = {"baseline_manifest_sha256": digest(parent / "manifest.json"),
              "horizon_manifest_sha256": digest(horizon / "manifest.json"),
              "horizon_signals_sha256": digest(horizon / "signals.csv"),
              "horizon_baseline_sha256": digest(horizon / "baseline.csv"),
              "source_sha256": digest(params["source_csv"]), "h1_source_sha256": digest(params["h1_source_csv"])}
    evidence = execute_study_tool("summarize_m5_horizons", params, ToolContext(kwargs["repo_root"], kwargs["workspace"] / "job", hashes))
    assert evidence["status"] == "VERIFIED"
    assert evidence["tables"][0]["baseline_n"] == 25


def test_copied_parent_only_normalizes_when_lf_hash_matches(materialization):
    kwargs, _ = materialization
    path = kwargs["baseline_packet"] / "report.md"
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    before = historical_hashes(kwargs)
    result = materialize_study_packet(**kwargs)
    manifest = json.loads((Path(result["horizon_packet"]) / "manifest.json").read_text())
    expected = manifest["parent"]["files_sha256"]["report.md"]
    assert digest(Path(result["baseline_packet"]) / "report.md") == expected
    assert historical_hashes(kwargs) == before
    assert manifest["materialization"]["parent_copy_transformations"]["report.md"] == "CRLF_TO_LF_EXACT_EXPECTED_HASH"


@pytest.mark.parametrize("kind", ["source", "parent", "summary", "eligibility", "count", "signals"])
def test_materializer_rejects_changed_or_ambiguous_inputs(materialization, kind):
    kwargs, _ = materialization
    if kind == "source":
        path = kwargs["data_dir"] / "BTCUSDT_5m.csv"
        path.write_bytes(path.read_bytes() + b"\n")
    elif kind == "parent":
        path = kwargs["baseline_packet"] / "report.md"
        path.write_bytes(path.read_bytes() + b"tampered")
    elif kind == "summary":
        path = kwargs["horizon_packet"] / "summary.json"
        summary = json.loads(path.read_text())
        summary["horizon_summaries"][0]["baseline"]["mean_return_pct"] += 0.5
        save_json(path, summary)
    elif kind in {"eligibility", "count"}:
        path = kwargs["horizon_packet"] / "manifest.json"
        manifest = json.loads(path.read_text())
        if kind == "eligibility":
            manifest["comparator"].update(eligible_bar_count=24, preparation_excluded_count=1)
        else:
            manifest["comparator"].update(candidate_bar_count=26, eligible_bar_count=26)
        save_json(path, manifest)
    else:
        path = kwargs["horizon_packet"] / "signals.csv"
        signals = pd.read_csv(path)
        signals.loc[0, "return_pct"] = 999
        signals.to_csv(path, index=False)
    before = historical_hashes(kwargs)
    with pytest.raises(ValueError):
        materialize_study_packet(**kwargs)
    assert historical_hashes(kwargs) == before


def test_existing_output_is_never_overwritten(materialization):
    kwargs, _ = materialization
    kwargs["workspace"].mkdir()
    sentinel = kwargs["workspace"] / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises((ValueError, FileExistsError)):
        materialize_study_packet(**kwargs)
    assert sentinel.read_text() == "keep"


def test_current_raw_crlf_is_rejected_even_when_normalization_would_match(materialization):
    kwargs, _ = materialization
    path = kwargs["data_dir"] / "BTCUSDT_5m.csv"
    # The materializer may restore copied packet files; current raw data has to
    # arrive with exactly the frozen byte identity from the caller.
    authored = path.read_bytes().replace(b"\r\n", b"\n")
    manifest_path = kwargs["horizon_packet"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["inputs"]["files"]["5m"]["sha256"] = hashlib.sha256(authored).hexdigest()
    save_json(manifest_path, manifest)
    path.write_bytes(authored.replace(b"\n", b"\r\n"))
    with pytest.raises(ValueError, match="source"):
        materialize_study_packet(**kwargs)
