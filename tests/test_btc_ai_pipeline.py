"""Offline contract and persistence tests for the BTC AI pipeline MVP."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

import app.research_pipeline.providers as providers_module
import btc_ai_pipeline
from app.research_pipeline.contracts import (
    EXECUTION_SCHEMA,
    PROPOSAL_SCHEMA,
    REVIEW_SCHEMA,
    ContractError,
    PipelineConfig,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    review_schema,
    validate_execution_plan,
    validate_proposal,
    validate_review,
)
from app.research_pipeline.controller import PipelineController
from app.research_pipeline.providers import CodexCLIProvider, FixtureProvider, OpenCodeProvider, _proposal
from app.research_pipeline.tools import (
    ToolContext,
    ToolRestrictionError,
    _expected_from_packet,
    _write_fixture_source,
    execute_registered_tool,
)

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "research/results/phase1_four_year_runs/run_20260904T084317586748Z_97d3c169"
HORIZON = ROOT / "research/results/m5_four_year_horizon_runs/run_20260904T084448776441Z_97d3c169"


def config(tmp_path: Path, **overrides: object) -> PipelineConfig:
    values = dict(db_path=str(tmp_path / "pipeline.sqlite"), output_dir=str(tmp_path / "artifacts"), repo_root=str(ROOT), baseline_packet=str(BASELINE), horizon_packet=str(HORIZON))
    values.update(overrides)
    return PipelineConfig(**values)


class CountingFixtureProvider(FixtureProvider):
    def __init__(self, role: str, **kwargs: object) -> None:
        super().__init__(role=role, **kwargs)
        self.calls: list[ProviderRequest] = []

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        return super().complete(request)


class ChangedExecutionProvider(FixtureProvider):
    def complete(self, request: ProviderRequest) -> ProviderResponse:
        response = super().complete(request)
        if request.phase == "execution":
            payload = dict(response.payload)
            payload["parameters"] = {"mode": "fixture", "event_index": 1}
            return replace(response, payload=payload)
        return response


class WrongReviewReferenceProvider(FixtureProvider):
    def complete(self, request: ProviderRequest) -> ProviderResponse:
        response = super().complete(request)
        if request.phase == "review":
            payload = dict(response.payload)
            payload["evidence_refs"] = ["unrelated-result"]
            return replace(response, payload=payload)
        return response


class WrongParentReviewProvider(FixtureProvider):
    def complete(self, request: ProviderRequest) -> ProviderResponse:
        response = super().complete(request)
        if request.phase == "review" and response.payload.get("action") == "PROPOSE_NEXT":
            payload = dict(response.payload)
            next_job = dict(payload["next_job"])
            next_job["parent_result_id"] = "unrelated-result"
            payload["next_job"] = next_job
            return replace(response, payload=payload)
        return response


def real_fixture_layout(tmp_path: Path) -> tuple[PipelineConfig, Path, Path]:
    mini_root = tmp_path / "mini_repo"
    horizon = mini_root / "research" / "results" / "horizon"
    baseline = mini_root / "research" / "results" / "baseline"
    source = mini_root / "research" / "data" / "BTCUSDT_5m.csv"
    horizon.mkdir(parents=True)
    baseline.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    source_event, source_rows = _expected_from_packet(HORIZON, 0)
    _write_fixture_source(source, {"trigger_close_at": source_event["trigger_close_at"], "trigger_close_price": source_event["trigger_close_price"], "rows": source_rows})
    manifest = json.loads((HORIZON / "manifest.json").read_text(encoding="utf-8"))
    baseline_manifest = json.loads((BASELINE / "manifest.json").read_text(encoding="utf-8"))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest["inputs"]["files"]["5m"]["path"] = str(source)
    manifest["inputs"]["files"]["5m"]["sha256"] = source_hash
    (horizon / "signals.csv").write_bytes((HORIZON / "signals.csv").read_bytes())
    (horizon / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (baseline / "manifest.json").write_text(json.dumps(baseline_manifest, indent=2) + "\n", encoding="utf-8")
    return config(tmp_path, repo_root=str(mini_root), baseline_packet=str(baseline), horizon_packet=str(horizon), data_dir=str(source.parent), verification_mode="real"), source, horizon / "signals.csv"


def test_strict_contracts_reject_malformed_json() -> None:
    with pytest.raises(ContractError):
        validate_proposal({"schema": PROPOSAL_SCHEMA})
    with pytest.raises(ContractError):
        validate_execution_plan({"schema": EXECUTION_SCHEMA, "task": "x", "tool": "shell", "parameters": {}, "invariants": [], "extra": 1})
    with pytest.raises(ContractError):
        validate_review({"schema": REVIEW_SCHEMA, "action": "NEXT", "reasons": ["x"], "evidence_refs": []})
    with pytest.raises(ContractError):
        validate_review({"schema": REVIEW_SCHEMA, "action": "STOP", "reasons": ["x"], "evidence_refs": []})


def test_review_schema_closes_nested_followup_tool_parameters() -> None:
    followup = review_schema()["properties"]["next_job"]["anyOf"][0]
    assert followup["properties"]["parameters"]["additionalProperties"] is False
    assert followup["properties"]["parameters"]["required"] == ["mode", "event_index"]


def test_codex_adapter_contract_and_jsonl_parser(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    class Process:
        pid = 42
        returncode = 0

        def communicate(self, *, timeout: float) -> tuple[str, str]:
            assert timeout == 3
            return ('{"type":"item.completed","item":{"type":"agent_message","text":"{\\"schema\\":\\"ok\\"}"}}\n{"type":"turn.completed","model":"reported-model","usage":{"input_tokens":12,"output_tokens":4}}\n', "")

    def fake_popen(argv: list[str], **kwargs: object) -> Process:
        calls.append(argv)
        assert kwargs["stdout"] is not None and kwargs["stderr"] is not None
        return Process()

    monkeypatch.setattr("app.research_pipeline.providers.subprocess.Popen", fake_popen)
    request = ProviderRequest("thinker", "proposal", "json", {}, "model-a", "low", 3, 10, 10, {"schema_path": str(tmp_path / "schema.json")})
    response = CodexCLIProvider(model="model-a").complete(request)
    assert response.payload == {"schema": "ok"}
    assert response.reported_model == "reported-model"
    assert response.usage is not None and response.usage["runtime"]["output_tokens"] == 4
    assert calls[0][0:2] == ["codex", "exec"]
    assert "--sandbox" in calls[0] and "read-only" in calls[0]
    assert "--output-schema" in calls[0] and "--model" in calls[0]
    assert "-c" in calls[0] and 'model_reasoning_effort="low"' in calls[0]


def test_opencode_requires_explicit_provider_qualified_model() -> None:
    request = ProviderRequest("executor", "execution", "", {}, "model", "low", 1, 1, 1)
    with pytest.raises(ProviderError, match="provider/model"):
        OpenCodeProvider().complete(request)


def test_offline_stop_persists_complete_loop_and_usage(tmp_path: Path) -> None:
    controller = PipelineController(config(tmp_path))
    campaign = controller.create_campaign()
    state = controller.run(campaign, branch="stop")
    assert state["status"] == "STOPPED"
    assert state["attempt_count"] == 3
    assert state["result_count"] == 1
    assert state["decisions"][0]["action"] == "STOP"
    assert state["budget"]["thinker_calls"] == 2
    evidence = controller.store.result(state["jobs"][0]["result_id"])
    payload = json.loads(evidence["evidence_json"])
    assert payload["status"] == "VERIFIED"
    assert payload["verification_mode"] == "fixture_validation"
    assert (Path(evidence["artifact_dir"]) / "evidence.json").is_file()


def test_propose_next_is_linked_and_deferred_at_job_limit(tmp_path: Path) -> None:
    controller = PipelineController(config(tmp_path))
    campaign = controller.create_campaign()
    state = controller.run(campaign, branch="next")
    assert state["status"] == "LIMIT_REACHED"
    decision = state["decisions"][0]
    assert decision["action"] == "PROPOSE_NEXT"
    next_job = controller.store.job(decision["next_job_id"])
    assert next_job["parent_job_id"] == decision["job_id"]
    assert next_job["status"] == "DEFERRED_LIMIT"


def test_tamper_reaches_repair_decision(tmp_path: Path) -> None:
    controller = PipelineController(config(tmp_path))
    campaign = controller.create_campaign()
    state = controller.run(campaign, branch="tamper")
    assert state["status"] == "PAUSED"
    assert state["decisions"][0]["action"] == "REPAIR"
    evidence = controller.store.result(state["jobs"][0]["result_id"])
    assert json.loads(evidence["evidence_json"])["status"] == "FAILED"


def test_tool_restrictions_reject_unregistered_and_outside_paths(tmp_path: Path) -> None:
    context = ToolContext(ROOT, tmp_path)
    with pytest.raises(ToolRestrictionError):
        execute_registered_tool("shell", {}, context)
    with pytest.raises(ToolRestrictionError):
        execute_registered_tool("verify_m5_horizons", {"mode": "fixture", "horizon_packet": str(Path("C:/outside"))}, context)


def test_budget_exhaustion_is_persisted(tmp_path: Path) -> None:
    controller = PipelineController(config(tmp_path, max_thinker_calls=1))
    campaign = controller.create_campaign()
    state = controller.run(campaign, branch="stop")
    assert state["status"] == "BUDGET_EXHAUSTED"
    assert any(failure["kind"] == "budget_exhausted" for failure in state["failures"])


@pytest.mark.parametrize("kind", ["timeout", "rate_limit", "auth"])
def test_provider_failures_pause_and_are_resumable(tmp_path: Path, kind: str) -> None:
    cfg = config(tmp_path)
    fixture = FixtureProvider(role="thinker", failure=f"{kind}:proposal")
    controller = PipelineController(cfg, thinkers={"fixture": fixture})
    campaign = controller.create_campaign()
    state = controller.run(campaign)
    assert state["status"] == "PAUSED"
    assert state["failures"][0]["kind"] == kind
    assert state["failures"][0]["retryable"] == 1


def test_verification_mode_is_frozen_into_campaign_context(tmp_path: Path) -> None:
    controller = PipelineController(config(tmp_path, verification_mode="real"))
    campaign = controller.create_campaign()
    assert controller.store.context(campaign)["verification_mode"] == "real"


def test_matching_verified_result_is_reused_across_campaigns(tmp_path: Path) -> None:
    controller = PipelineController(config(tmp_path))
    first = controller.run(controller.create_campaign(), branch="stop")
    second = controller.run(controller.create_campaign(), branch="stop")
    assert first["status"] == second["status"] == "STOPPED"
    evidence = json.loads(controller.store.result(second["jobs"][0]["result_id"])["evidence_json"])
    assert evidence["reused_evidence"] is True
    assert evidence["reused_from_result_id"] == first["jobs"][0]["result_id"]
    assert evidence["cache_key"]


def test_resume_does_not_repeat_completed_work(tmp_path: Path) -> None:
    controller = PipelineController(config(tmp_path))
    campaign = controller.create_campaign()
    first = controller.run(campaign, branch="stop")
    second = controller.resume(campaign)
    assert second["status"] == "STOPPED"
    assert second["attempt_count"] == first["attempt_count"] == 3
    assert second["result_count"] == first["result_count"] == 1
    assert len(second["decisions"]) == 1


def test_uncertain_inflight_attempt_is_paused_without_dispatch(tmp_path: Path) -> None:
    controller = PipelineController(config(tmp_path))
    campaign = controller.create_campaign()
    controller.store.reserve_job(campaign)
    job_id = "job_crash_fixture"
    controller.store.create_job(job_id, campaign, 1, {"schema": PROPOSAL_SCHEMA}, "fixture", status="PROPOSED")
    controller.store.create_attempt("attempt_crash_fixture", campaign, job_id, "executor", "execution", "fixture", "fixture-executor", {"phase": "execution"})
    state = controller.resume(campaign)
    assert state["status"] == "PAUSED"
    assert any(failure["kind"] == "interrupted_uncertain" for failure in state["failures"])
    with sqlite3.connect(tmp_path / "pipeline.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1


def test_offline_nonfixture_provider_is_rejected_before_dispatch(tmp_path: Path) -> None:
    provider = CountingFixtureProvider(role="thinker")
    controller = PipelineController(config(tmp_path, thinker_provider="codex", thinker_model="saved-model"), thinkers={"codex": provider})
    campaign = controller.create_campaign()
    state = controller.run(campaign)
    assert state["status"] == "FAILED"
    assert provider.calls == []
    assert state["attempt_count"] == 0
    assert state["failures"][0]["kind"] == "authorization"
    details = json.loads(state["failures"][0]["details_json"])
    assert details["provider_call_performed"] is False


def test_cli_rejects_offline_nonfixture_before_controller(monkeypatch: pytest.MonkeyPatch) -> None:
    constructed = False

    def fail_if_constructed(*args: object, **kwargs: object) -> object:
        nonlocal constructed
        constructed = True
        raise AssertionError("controller should not be constructed")

    monkeypatch.setattr(btc_ai_pipeline, "PipelineController", fail_if_constructed)
    with pytest.raises(SystemExit):
        btc_ai_pipeline.main(["run", "--offline-fixture", "--thinker-provider", "codex"])
    assert constructed is False


def test_status_does_not_construct_runtime_providers(tmp_path: Path) -> None:
    factory_calls: list[str] = []

    def factory(provider: str, **kwargs: object) -> object:
        factory_calls.append(provider)
        return CountingFixtureProvider(role=str(kwargs.get("role", "thinker")))

    controller = PipelineController(config(tmp_path, thinker_provider="codex", executor_provider="codex"), provider_factory=factory)
    campaign = controller.create_campaign()
    assert controller.status(campaign)["status"] == "RUNNING"
    assert factory_calls == []


def test_resume_restores_persisted_provider_model_and_verification_mode(tmp_path: Path) -> None:
    thinker = CountingFixtureProvider(role="thinker")
    executor = CountingFixtureProvider(role="executor", failure="auth:execution")
    saved, _, _ = real_fixture_layout(tmp_path)
    saved = replace(saved, thinker_model="saved-thinker", executor_model="saved-executor")
    controller = PipelineController(saved, thinkers={"fixture": thinker}, executors={"fixture": executor})
    campaign = controller.create_campaign()
    first = controller.run(campaign)
    assert first["status"] == "PAUSED"
    controller.config = config(tmp_path, verification_mode="fixture", thinker_model="fixture-thinker", executor_model="fixture-executor")
    second = controller.resume(campaign)
    assert controller.config.verification_mode == "real"
    assert controller.config.thinker_model == "saved-thinker"
    assert controller.config.executor_model == "saved-executor"
    execution_attempts = [attempt for attempt in second["failures"] if attempt["kind"] == "auth"]
    assert execution_attempts
    with sqlite3.connect(tmp_path / "pipeline.sqlite") as db:
        row = db.execute("SELECT model FROM attempts WHERE phase = 'execution' ORDER BY started_at DESC LIMIT 1").fetchone()
    assert row[0] == "saved-executor"
    assert executor.calls[-1].metadata["proposal"]["parameters"]["mode"] == "real"


def test_completed_executor_response_is_recovered_after_result_commit_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executor = CountingFixtureProvider(role="executor")
    controller = PipelineController(config(tmp_path), executors={"fixture": executor})
    campaign = controller.create_campaign()
    original_create_result = controller.store.create_result

    def crash_before_result(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated crash after executor response")

    monkeypatch.setattr(controller.store, "create_result", crash_before_result)
    first = controller.run(campaign, branch="stop")
    monkeypatch.setattr(controller.store, "create_result", original_create_result)
    controller.store.set_campaign_status(campaign, "PAUSED")
    assert first["budget"]["executor_calls"] == 1
    assert executor.calls and len(executor.calls) == 1
    resumed = controller.resume(campaign, branch="stop")
    assert resumed["status"] == "STOPPED"
    assert len(executor.calls) == 1
    assert resumed["budget"]["executor_calls"] == 1
    assert resumed["result_count"] == 1


def test_completed_proposal_response_is_recovered_before_redispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    thinker = CountingFixtureProvider(role="thinker")
    controller = PipelineController(config(tmp_path), thinkers={"fixture": thinker})
    campaign = controller.create_campaign()
    original_update = controller.store.update_job_specification

    def crash_before_proposal_commit(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated crash after proposal response")

    monkeypatch.setattr(controller.store, "update_job_specification", crash_before_proposal_commit)
    first = controller.run(campaign, branch="stop")
    monkeypatch.setattr(controller.store, "update_job_specification", original_update)
    controller.store.set_campaign_status(campaign, "PAUSED")
    assert first["budget"]["thinker_calls"] == 1
    resumed = controller.resume(campaign, branch="stop")
    assert resumed["status"] == "STOPPED"
    assert resumed["budget"]["thinker_calls"] == 2
    assert len(thinker.calls) == 2


def test_completed_review_response_is_recovered_without_duplicate_thinker_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    thinker = CountingFixtureProvider(role="thinker")
    controller = PipelineController(config(tmp_path), thinkers={"fixture": thinker})
    campaign = controller.create_campaign()
    original_create_decision = controller.store.create_decision

    def crash_before_decision(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated crash after review response")

    monkeypatch.setattr(controller.store, "create_decision", crash_before_decision)
    first = controller.run(campaign, branch="stop")
    monkeypatch.setattr(controller.store, "create_decision", original_create_decision)
    controller.store.set_campaign_status(campaign, "PAUSED")
    assert first["budget"]["thinker_calls"] == 2
    resumed = controller.resume(campaign, branch="stop")
    assert resumed["status"] == "STOPPED"
    assert resumed["budget"]["thinker_calls"] == 2
    assert len(thinker.calls) == 2
    assert len(resumed["decisions"]) == 1


@pytest.mark.parametrize(
    ("branch", "expected_status", "expected_job_status"),
    [
        ("stop", "STOPPED", "CHECKED"),
        ("reject", "REJECTED", "CHECKED"),
        ("tamper", "PAUSED", "REPAIR_REQUIRED"),
    ],
)
def test_committed_review_decision_effects_replay_after_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    branch: str,
    expected_status: str,
    expected_job_status: str,
) -> None:
    class SimulatedProcessCrash(BaseException):
        pass

    class RejectingReviewProvider(CountingFixtureProvider):
        def complete(self, request: ProviderRequest) -> ProviderResponse:
            response = super().complete(request)
            if request.phase == "review":
                payload = dict(response.payload)
                payload["action"] = "REJECT"
                response = replace(response, payload=payload)
            return response

    thinker_class = RejectingReviewProvider if branch == "reject" else CountingFixtureProvider
    thinker = thinker_class(role="thinker")
    executor = CountingFixtureProvider(role="executor")
    controller = PipelineController(config(tmp_path), thinkers={"fixture": thinker}, executors={"fixture": executor})
    campaign = controller.create_campaign()
    original_create_decision = controller.store.create_decision

    def commit_then_crash(*args: object, **kwargs: object) -> None:
        original_create_decision(*args, **kwargs)
        raise SimulatedProcessCrash("simulated crash after decision commit")

    monkeypatch.setattr(controller.store, "create_decision", commit_then_crash)
    with pytest.raises(SimulatedProcessCrash):
        controller.run(campaign, branch="tamper" if branch == "reject" else branch)
    monkeypatch.setattr(controller.store, "create_decision", original_create_decision)
    first = controller.status(campaign)

    assert first["status"] == "RUNNING"
    assert len(first["decisions"]) == 1
    assert first["attempt_count"] == 3
    assert first["result_count"] == 1
    first_budget = dict(first["budget"])
    first_thinker_calls = len(thinker.calls)
    first_executor_calls = len(executor.calls)
    first_failure_count = len(first["failures"])

    resumed = controller.resume(campaign, branch="tamper" if branch == "reject" else branch)

    assert resumed["status"] == expected_status
    assert resumed["jobs"][0]["status"] == expected_job_status
    assert len(resumed["decisions"]) == 1
    assert resumed["attempt_count"] == first["attempt_count"]
    assert resumed["result_count"] == first["result_count"]
    assert dict(resumed["budget"]) == first_budget
    assert len(thinker.calls) == first_thinker_calls
    assert len(executor.calls) == first_executor_calls
    assert len(resumed["failures"]) == first_failure_count


def test_followup_reservations_count_each_job_and_stop_at_cap(tmp_path: Path) -> None:
    controller = PipelineController(config(tmp_path, max_thinker_calls=4, max_executor_calls=2, max_jobs=2))
    campaign = controller.create_campaign()
    first = controller.run(campaign, branch="next")
    assert first["status"] == "RUNNING"
    assert first["budget"]["jobs_started"] == 2
    assert len(first["jobs"]) == 2
    second = controller.resume(campaign, branch="next")
    assert second["status"] == "LIMIT_REACHED"
    assert second["budget"]["jobs_started"] == 2
    assert second["result_count"] == 2
    assert len(second["jobs"]) == 3
    assert second["jobs"][-1]["status"] == "DEFERRED_LIMIT"
    third = controller.resume(campaign, branch="next")
    assert third["status"] == "LIMIT_REACHED"
    assert third["attempt_count"] == second["attempt_count"]


def test_followup_job_creation_is_idempotent_for_one_parent(tmp_path: Path) -> None:
    controller = PipelineController(config(tmp_path, max_jobs=2))
    campaign = controller.create_campaign()
    root_id = "job_root_idempotency"
    controller.store.create_initial_job(root_id, campaign, 1, {}, "pending")
    assert controller.store.ensure_initial_job("job_root_second", campaign, 1, {}, "pending") == root_id
    specification = _proposal()
    first_status = controller.store.create_followup_job("job_child_first", campaign, 2, specification, "child-hash", root_id)
    second_status = controller.store.create_followup_job("job_child_second", campaign, 2, specification, "child-hash", root_id)
    children = [row for row in controller.store.jobs(campaign) if row["parent_job_id"] == root_id]
    assert first_status == second_status == "PROPOSED"
    assert [row["id"] for row in children] == ["job_child_first"]
    assert controller.store.budget(campaign)["jobs_started"] == 2


def test_repair_pause_is_durable_and_generic_resume_does_not_re_review(tmp_path: Path) -> None:
    thinker = CountingFixtureProvider(role="thinker")
    controller = PipelineController(config(tmp_path), thinkers={"fixture": thinker})
    campaign = controller.create_campaign()
    first = controller.run(campaign, branch="tamper")
    assert first["status"] == "PAUSED"
    assert first["jobs"][0]["status"] == "REPAIR_REQUIRED"
    resumed = controller.resume(campaign, branch="tamper")
    assert resumed["status"] == "PAUSED"
    assert resumed["attempt_count"] == first["attempt_count"]
    assert resumed["budget"]["thinker_calls"] == first["budget"]["thinker_calls"]


def test_uncertain_call_requires_explicit_reconciliation_before_redispatch(tmp_path: Path) -> None:
    executor = CountingFixtureProvider(role="executor")
    controller = PipelineController(config(tmp_path), executors={"fixture": executor})
    campaign = controller.create_campaign()
    controller.store.reserve_job(campaign)
    job_id = "job_uncertain_explicit"
    controller.store.create_job(job_id, campaign, 1, _proposal(), "fixture", status="PROPOSED", budget_reserved=True)
    controller.store.create_attempt("attempt_uncertain_explicit", campaign, job_id, "executor", "execution", "fixture", "fixture-executor", {"phase": "execution"})
    first = controller.resume(campaign)
    second = controller.resume(campaign)
    assert first["status"] == second["status"] == "PAUSED"
    assert len(executor.calls) == 0
    reconciled = controller.resume(campaign, reconcile_uncertain=True)
    assert len(executor.calls) == 1
    assert reconciled["status"] in {"FAILED", "PAUSED", "STOPPED"}


def test_changed_executor_parameters_are_rejected_before_checker(tmp_path: Path) -> None:
    executor = ChangedExecutionProvider(role="executor")
    controller = PipelineController(config(tmp_path), executors={"fixture": executor})
    state = controller.run(controller.create_campaign())
    assert state["status"] == "FAILED"
    assert state["result_count"] == 0
    assert state["failures"][0]["kind"] == "tool_restriction"


def test_changed_executor_mode_is_rejected_before_checker(tmp_path: Path) -> None:
    class ChangedModeProvider(FixtureProvider):
        def complete(self, request: ProviderRequest) -> ProviderResponse:
            response = super().complete(request)
            if request.phase == "execution":
                payload = dict(response.payload)
                payload["parameters"] = {"mode": "real", "event_index": 0}
                return replace(response, payload=payload)
            return response

    controller = PipelineController(config(tmp_path), executors={"fixture": ChangedModeProvider(role="executor")})
    state = controller.run(controller.create_campaign())
    assert state["status"] == "FAILED"
    assert state["result_count"] == 0
    assert state["failures"][0]["kind"] == "tool_restriction"


def test_wrong_review_reference_cannot_create_decision(tmp_path: Path) -> None:
    thinker = WrongReviewReferenceProvider(role="thinker")
    controller = PipelineController(config(tmp_path), thinkers={"fixture": thinker})
    state = controller.run(controller.create_campaign())
    assert state["status"] == "FAILED"
    assert state["decisions"] == []
    assert state["failures"][0]["kind"] == "tool_restriction"


def test_empty_review_reference_cannot_create_decision(tmp_path: Path) -> None:
    class EmptyReviewProvider(FixtureProvider):
        def complete(self, request: ProviderRequest) -> ProviderResponse:
            response = super().complete(request)
            if request.phase == "review":
                payload = dict(response.payload)
                payload["evidence_refs"] = []
                return replace(response, payload=payload)
            return response

    controller = PipelineController(config(tmp_path), thinkers={"fixture": EmptyReviewProvider(role="thinker")})
    state = controller.run(controller.create_campaign())
    assert state["status"] == "FAILED"
    assert state["decisions"] == []
    assert state["failures"][0]["kind"] == "malformed_json"


def test_wrong_followup_parent_reference_cannot_create_child(tmp_path: Path) -> None:
    thinker = WrongParentReviewProvider(role="thinker", branch="next")
    controller = PipelineController(config(tmp_path), thinkers={"fixture": thinker})
    state = controller.run(controller.create_campaign(), branch="next")
    assert state["status"] == "FAILED"
    assert len(state["jobs"]) == 1
    assert state["decisions"] == []


def test_codex_timeout_attempts_owned_process_tree_cleanup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class SlowProcess:
        pid = 123
        returncode = None
        killed = False

        def communicate(self, *, timeout: float | None = None) -> tuple[str, str]:
            if timeout in {2, 1}:
                raise subprocess.TimeoutExpired("codex", timeout)
            return "", ""

        def kill(self) -> None:
            self.killed = True

    process = SlowProcess()
    monkeypatch.setattr(providers_module.subprocess, "Popen", lambda argv, **kwargs: process)
    cleanup = {"attempted": True, "completed": True, "descendants": True}
    monkeypatch.setattr(providers_module, "terminate_process_tree", lambda candidate: cleanup)
    request = ProviderRequest("thinker", "proposal", "json", {}, "model-a", "low", 2, 10, 10, {"schema_path": str(tmp_path / "schema.json")})
    with pytest.raises(ProviderError) as raised:
        CodexCLIProvider(model="model-a").complete(request)
    assert raised.value.kind == "timeout"
    assert raised.value.details["owned_process_cleanup"] == cleanup
    assert process.killed is True


def test_real_cache_rejects_changed_source_and_reuses_unchanged_inputs(tmp_path: Path) -> None:
    cfg, source, _signals = real_fixture_layout(tmp_path)
    controller = PipelineController(cfg)
    first = controller.run(controller.create_campaign(), branch="stop")
    assert first["status"] == "STOPPED"
    source.write_bytes(source.read_bytes() + b"\n")
    changed = controller.run(controller.create_campaign(), branch="stop")
    assert changed["status"] == "FAILED"
    assert changed["attempt_count"] == 0
    assert changed["result_count"] == 0
    assert "input identity mismatch" in changed["failures"][0]["message"]


def test_real_cache_reuse_requires_intact_evidence_artifact(tmp_path: Path) -> None:
    cfg, _source, _signals = real_fixture_layout(tmp_path)
    controller = PipelineController(cfg)
    first = controller.run(controller.create_campaign(), branch="stop")
    first_result = controller.store.result(first["jobs"][0]["result_id"])
    artifact = Path(first_result["artifact_dir"]) / "evidence.json"
    artifact.write_text("{\"status\": \"tampered\"}\n", encoding="utf-8")
    second = controller.run(controller.create_campaign(), branch="stop")
    evidence = json.loads(controller.store.result(second["jobs"][0]["result_id"])["evidence_json"])
    assert second["status"] == "STOPPED"
    assert evidence["status"] == "VERIFIED"
    assert evidence["reused_evidence"] is False
    assert "cache_reuse_rejected" in evidence


def test_real_cache_rejects_changed_packet_contents(tmp_path: Path) -> None:
    cfg, _source, signals = real_fixture_layout(tmp_path)
    controller = PipelineController(cfg)
    first = controller.run(controller.create_campaign(), branch="stop")
    assert first["status"] == "STOPPED"
    frame = pd.read_csv(signals)
    row_index = frame.index[frame["horizon_minutes"] == 60][0]
    frame.loc[row_index, "target_close_price"] = float(frame.loc[row_index, "target_close_price"]) + 1.0
    frame.to_csv(signals, index=False)
    changed = controller.run(controller.create_campaign(), branch="stop")
    evidence = json.loads(controller.store.result(changed["jobs"][0]["result_id"])["evidence_json"])
    assert changed["status"] == "PAUSED"
    assert evidence["status"] == "FAILED"
    assert evidence["reused_evidence"] is False


def test_controller_output_budget_is_enforced_after_provider_response(tmp_path: Path) -> None:
    class LargeProvider(CountingFixtureProvider):
        def complete(self, request: ProviderRequest) -> ProviderResponse:
            response = super().complete(request)
            if request.phase == "proposal":
                payload = dict(response.payload)
                payload["rationale"] = "x" * 500
                return replace(response, payload=payload)
            return response

    thinker = LargeProvider(role="thinker")
    controller = PipelineController(config(tmp_path, output_budget=10), thinkers={"fixture": thinker})
    state = controller.run(controller.create_campaign())
    assert state["status"] == "FAILED"
    assert state["failures"][0]["kind"] == "output_budget_exceeded"
    assert state["budget"]["thinker_calls"] == 1
