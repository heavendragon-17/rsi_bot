"""The offline comparison freezes choices and never constructs model providers."""

import json

import pytest
from test_btc_ai_pipeline_studies import build_study_packet

from app.research_pipeline import benchmark
from app.research_pipeline.study_tools import execute_study_tool
from app.research_pipeline.tools import ToolContext, ToolVerificationError


@pytest.fixture
def benchmark_case(tmp_path, monkeypatch):
    params, context = build_study_packet(tmp_path)
    summary = execute_study_tool("summarize_m5_horizons", params, context)
    horizon = max(summary["tables"], key=lambda row: (abs(row["signal_minus_baseline_pp"]), -row["horizon_minutes"]))["horizon_minutes"]
    ai = {"mode": "fixture", "horizon_minutes": horizon, "grouping": "volatility"}
    selected = execute_study_tool("compare_m5_cohorts", {**params, **ai},
                                  ToolContext(context.repo_root, context.workspace / "cohort", context.frozen_inputs))
    source = {"source_hash": "synthetic-snapshot", "artifacts": [], "campaign_id": "synthetic",
              "context": {"evidence_hashes": dict(context.frozen_inputs),
                          "verification_mode": "fixture", "baseline_packet": params["baseline_packet"],
                          "horizon_packet": params["horizon_packet"]},
              "summary_evidence": summary, "selected_evidence": selected,
              "ai_parameters": ai, "scripted_parameters": {**ai, "grouping": "calendar_year"},
              "summary": {"attempts": [], "results": [], "decisions": [], "failures": [],
                          "campaign": {"status": "STOPPED"}}}
    source["context"]["evidence_hashes"].update(source_path=params["source_csv"], h1_source_path=params["h1_source_csv"])
    monkeypatch.setattr(benchmark, "load_benchmark_source", lambda *args: source)
    monkeypatch.setattr(benchmark, "verify_benchmark_source", lambda *args: None)
    output = context.repo_root / "research/results/quality"
    return source, context.repo_root, output


def run(case):
    source, root, output = case
    return benchmark.run_selection_benchmark(root, root / "unused.sqlite", source["campaign_id"], output, replications=20)


def test_choices_are_frozen_before_catalog_and_model_calls_remain_zero(benchmark_case, monkeypatch):
    source, _, output = benchmark_case
    original = benchmark.load_benchmark_data

    def observe(params, context):
        protocol = json.loads((output / "protocol.json").read_text())
        assert protocol["policies"]["ai"] == source["ai_parameters"]
        assert protocol["policies"]["scripted"] == source["scripted_parameters"]
        assert len(protocol["candidate_space"]) == 9
        return original(params, context)

    monkeypatch.setattr(benchmark, "load_benchmark_data", observe)
    result = run(benchmark_case)
    assert result["status"] == "COMPLETED"
    assert result["verdict"] == "BENEFIT_NOT_ESTABLISHED"
    assert result["new_provider_calls"] == 0
    assert result["resources"]["scripted"]["provider_calls"] == 0
    assert len(json.loads((output / "diagnostics.json").read_text())["candidates"]) == 9
    assert result["comparison"]["ai"]["parameters"]["grouping"] == "volatility"
    assert result["comparison"]["scripted"]["parameters"]["grouping"] == "calendar_year"
    assert (output / "report.md").is_file()
    assert "post-selection" in (output / "report.md").read_text()
    assert "NaN" not in (output / "diagnostics.json").read_text()


def test_changed_source_after_evaluation_cannot_publish_completed_report(benchmark_case, monkeypatch):
    original = benchmark.evaluate_diagnostics
    changed = False

    def change_after_evaluation(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        changed = True
        return result

    def verify(source):
        if changed:
            raise ToolVerificationError("source changed")

    monkeypatch.setattr(benchmark, "evaluate_diagnostics", change_after_evaluation)
    monkeypatch.setattr(benchmark, "verify_benchmark_source", verify)
    with pytest.raises(ToolVerificationError, match="source changed"):
        run(benchmark_case)
    report = json.loads((benchmark_case[2] / "report.json").read_text())
    assert report["status"] == "FAILED"
    assert "verdict" not in report


def test_existing_output_is_never_overwritten(benchmark_case):
    output = benchmark_case[2]
    output.mkdir()
    marker = output / "marker.txt"
    marker.write_text("preserve")
    with pytest.raises(FileExistsError):
        run(benchmark_case)
    assert marker.read_text() == "preserve"


def test_changed_saved_ai_tables_fail_before_statistics(benchmark_case, monkeypatch):
    source, _, output = benchmark_case
    source["selected_evidence"]["tables"][0]["signal_n"] += 1
    monkeypatch.setattr(benchmark, "evaluate_diagnostics", lambda *args, **kwargs: pytest.fail("statistics must not run"))
    with pytest.raises(ToolVerificationError, match="recorded AI"):
        run(benchmark_case)
    assert json.loads((output / "report.json").read_text())["status"] == "FAILED"


def test_benchmark_cli_bypasses_controller(tmp_path, monkeypatch, capsys):
    import btc_ai_pipeline

    monkeypatch.setattr(btc_ai_pipeline, "PipelineController", lambda *args: pytest.fail("no controller or providers"))
    captured = []
    monkeypatch.setattr(benchmark, "run_selection_benchmark", lambda *args: captured.append(args) or {"new_provider_calls": 0})
    assert btc_ai_pipeline.main(["benchmark", "campaign_test", "--db", "saved.sqlite", "--repo-root", str(tmp_path),
                                 "--workspace", "research/results/new"]) == 0
    assert captured == [(tmp_path.resolve(), tmp_path / "saved.sqlite", "campaign_test", tmp_path / "research/results/new")]
    assert json.loads(capsys.readouterr().out)["new_provider_calls"] == 0


def test_full_synthetic_chain_remains_unchanged_after_benchmark(tmp_path):
    from pathlib import Path

    from test_btc_ai_pipeline_adaptive import adaptive_config
    from test_btc_ai_pipeline_benchmark_source import SyntheticLiveLabels

    from app.research_pipeline.controller import PipelineController
    from app.research_pipeline.inputs import file_hash

    cfg = adaptive_config(tmp_path, thinker_provider="codex", executor_provider="opencode", live_opt_in=True)
    controller = PipelineController(cfg, thinkers={"codex": SyntheticLiveLabels("thinker")},
                                    executors={"opencode": SyntheticLiveLabels("executor")})
    campaign = controller.create_campaign(name="synthetic comparison; no live calls")
    assert controller.run(campaign)["status"] == "STOPPED"
    db = Path(cfg.db_path)
    before = file_hash(db)
    root = Path(cfg.repo_root)
    result = benchmark.run_selection_benchmark(root, db, campaign, root / "research/results/benchmark", replications=20)
    assert result["status"] == "COMPLETED"
    assert file_hash(db) == before
    assert result["resources"]["historical_ai"]["model_provider_attempts"] == 5
    assert result["comparison"]["ai"]["parameters"]["grouping"] == "volatility"


def test_changed_protocol_is_rejected(benchmark_case, monkeypatch):
    original = benchmark.evaluate_diagnostics

    def corrupt_protocol(*args, **kwargs):
        result = original(*args, **kwargs)
        (benchmark_case[2] / "protocol.json").write_text("{}")
        return result

    monkeypatch.setattr(benchmark, "evaluate_diagnostics", corrupt_protocol)
    with pytest.raises(ToolVerificationError, match="frozen protocol"):
        run(benchmark_case)
