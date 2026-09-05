"""Exact checker input readiness must precede paid model dispatch."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_btc_ai_pipeline import CountingFixtureProvider, real_fixture_layout
from test_btc_ai_pipeline_adaptive import adaptive_config

from app.research_pipeline.controller import PipelineController, preflight
from app.research_pipeline.inputs import resolve_inputs, validate_inputs


def test_relocated_manifest_uses_configured_data_with_same_hash(tmp_path):
    config, source, _ = real_fixture_layout(tmp_path)
    manifest_path = source.parent.parent / "results/horizon/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["inputs"]["files"]["5m"]["path"] = "C:/old-checkout/research/data/BTCUSDT_5m.csv"
    manifest_path.write_text(json.dumps(manifest))
    controller = PipelineController(config)
    campaign = controller.create_campaign()
    result = controller.run(campaign)
    assert result["status"] == "STOPPED"
    assert controller.store.context(campaign)["evidence_hashes"]["source_path"] == str(source)
    assert preflight(config)["inputs_ready"] is True


def test_changed_raw_input_fails_before_any_provider_call(tmp_path):
    config, source, _ = real_fixture_layout(tmp_path)
    thinker = CountingFixtureProvider("thinker")
    executor = CountingFixtureProvider("executor")
    controller = PipelineController(config, thinkers={"fixture": thinker}, executors={"fixture": executor})
    campaign = controller.create_campaign()
    source.write_text(source.read_text() + "\n")
    result = controller.run(campaign)
    assert result["status"] == "FAILED"
    assert result["attempt_count"] == 0
    assert not thinker.calls and not executor.calls
    assert preflight(config)["inputs_ready"] is False


def test_missing_packet_fails_before_provider_dispatch(tmp_path):
    config, source, signals = real_fixture_layout(tmp_path)
    controller = PipelineController(config)
    campaign = controller.create_campaign()
    signals.unlink()
    result = controller.run(campaign)
    assert result["status"] in {"FAILED", "PAUSED"}
    assert result["attempt_count"] == 0
    assert preflight(config)["inputs_ready"] is False


@pytest.mark.parametrize("mode", ["real", "fixture"])
def test_wrong_baseline_ancestry_fails_preflight_and_dispatch(tmp_path, mode):
    config, _, _ = real_fixture_layout(tmp_path)
    config = replace(config, verification_mode=mode)
    baseline_path = Path(config.baseline_packet) / "manifest.json"
    baseline = json.loads(baseline_path.read_text())
    baseline["run_id"] = "unrelated-parent"
    baseline_path.write_text(json.dumps(baseline))
    thinker = CountingFixtureProvider("thinker")
    executor = CountingFixtureProvider("executor")
    controller = PipelineController(config, thinkers={"fixture": thinker}, executors={"fixture": executor})

    readiness = preflight(config)
    state = controller.run(controller.create_campaign())

    assert readiness["inputs_ready"] is False
    assert "descended" in readiness["input_error"]["message"]
    assert state["status"] == "FAILED"
    assert state["attempt_count"] == 0
    assert not thinker.calls and not executor.calls
    assert state["budget"]["thinker_calls"] == state["budget"]["executor_calls"] == 0


@pytest.mark.parametrize("phase,completed_phases", [
    ("proposal", []), ("execution", ["proposal"]), ("review", ["proposal", "execution"]),
])
def test_frozen_source_checked_at_every_model_dispatch(tmp_path, monkeypatch, phase, completed_phases):
    config, source, _ = real_fixture_layout(tmp_path)
    thinker = CountingFixtureProvider("thinker")
    executor = CountingFixtureProvider("executor")
    controller = PipelineController(config, thinkers={"fixture": thinker}, executors={"fixture": executor})
    original_call = controller._provider_call

    def change_source_before_dispatch(*args, **kwargs):
        if kwargs["phase"] == phase:
            source.write_bytes(source.read_bytes() + b"\n")
        return original_call(*args, **kwargs)

    monkeypatch.setattr(controller, "_provider_call", change_source_before_dispatch)
    state = controller.run(controller.create_campaign())

    assert state["status"] == "FAILED"
    assert [request.phase for request in thinker.calls + executor.calls] == completed_phases
    assert state["attempt_count"] == len(completed_phases)
    assert state["budget"]["thinker_calls"] == completed_phases.count("proposal")
    assert state["budget"]["executor_calls"] == completed_phases.count("execution")
    assert state["decisions"] == []


@pytest.mark.parametrize("changed_input", ["5m", "1h", "comparator", "parent_signals"])
def test_adaptive_resume_rejects_changed_inputs_before_pending_review(tmp_path, monkeypatch, changed_input):
    config = adaptive_config(tmp_path)
    controller = PipelineController(config)
    campaign = controller.create_campaign()

    def crash_before_review(*args, **kwargs):
        raise KeyboardInterrupt("simulated process interruption before review")

    monkeypatch.setattr(controller, "_review", crash_before_review)
    with pytest.raises(KeyboardInterrupt):
        controller.run(campaign)
    before = controller.status(campaign)
    assert before["attempt_count"] == 2 and before["result_count"] == 1
    changed_path = {
        "5m": Path(config.data_dir) / "BTCUSDT_5m.csv",
        "1h": Path(config.data_dir) / "BTCUSDT_1h.csv",
        "comparator": Path(config.horizon_packet) / "baseline.csv",
        "parent_signals": Path(config.baseline_packet) / "signals.csv",
    }[changed_input]
    changed_path.write_bytes(changed_path.read_bytes() + b"\n")
    resumed = PipelineController(config)
    provider_lookups = []
    original_provider = resumed._provider

    def track_provider_lookup(role):
        provider_lookups.append(role)
        return original_provider(role)

    monkeypatch.setattr(resumed, "_provider", track_provider_lookup)
    state = resumed.resume(campaign)

    assert state["status"] == "FAILED"
    assert state["attempt_count"] == before["attempt_count"]
    assert state["budget"] == before["budget"]
    assert state["decisions"] == []
    assert provider_lookups == []


def test_adaptive_dispatch_validation_hashes_inputs_without_population_parsing(tmp_path, monkeypatch):
    config = adaptive_config(tmp_path)
    context = resolve_inputs(config)

    def unexpected_population_read(*args, **kwargs):
        raise AssertionError("dispatch readiness must not parse population rows or candle frames")

    monkeypatch.setattr("app.research_pipeline.study_tools._read_rows", unexpected_population_read)
    monkeypatch.setattr("app.research_pipeline.study_tools.load_ohlcv_csv", unexpected_population_read)
    identity = validate_inputs(context, Path(config.repo_root), Path(config.output_dir), adaptive=True)

    assert identity["mismatches"] == []
    assert identity["h1_source_sha256"] == context["evidence_hashes"]["h1_source_sha256"]
