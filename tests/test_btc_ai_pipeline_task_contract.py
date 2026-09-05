"""Offline regressions for the v2 task-label failure and role contracts."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.research_pipeline.contracts import (
    EXECUTION_SCHEMA,
    M5_VERIFICATION_TASK,
    ContractError,
    PipelineConfig,
    ProviderRequest,
    execution_schema,
    proposal_schema,
    review_schema,
    validate_execution_plan,
    validate_proposal,
)
from app.research_pipeline.controller import PipelineController
from app.research_pipeline.providers import FixtureProvider, _proposal
from app.research_pipeline.tools import registered_tools

ROOT = Path(__file__).resolve().parents[1]
V2_REPORT = ROOT / "research/results/btc_ai_pipeline_live_smoke_v2/campaign_3a869ced481f44ab/report.json"


def config(tmp_path: Path, **values: object) -> PipelineConfig:
    return PipelineConfig(repo_root=str(ROOT), db_path=str(tmp_path / "pipeline.sqlite"), output_dir=str(tmp_path / "output"), **values)


def saved_proposal() -> dict:
    report = json.loads(V2_REPORT.read_text(encoding="utf-8"))
    return json.loads(report["attempts"][0]["response_json"])


class RecordingFixture(FixtureProvider):
    def __init__(self, role: str, mutation=None) -> None:
        super().__init__(role=role)
        self.requests = []
        self.mutation = mutation

    def complete(self, request: ProviderRequest):
        self.requests.append(request)
        response = super().complete(request)
        return replace(response, payload=self.mutation(request, dict(response.payload))) if self.mutation else response


def test_saved_v2_proposal_rejected_by_schema_and_local_validator() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    payload = saved_proposal()
    assert payload["task"] != M5_VERIFICATION_TASK
    with pytest.raises(jsonschema.ValidationError, match=M5_VERIFICATION_TASK):
        jsonschema.validate(payload, proposal_schema())
    with pytest.raises(ContractError, match="registered identifier"):
        validate_proposal(payload)


def test_all_task_fields_use_the_actual_registry_identifier() -> None:
    assert set(registered_tools()) == {M5_VERIFICATION_TASK}
    assert proposal_schema()["properties"]["task"]["const"] == M5_VERIFICATION_TASK
    for field in ("task", "tool"):
        assert execution_schema()["properties"][field]["const"] == M5_VERIFICATION_TASK
    assert review_schema()["properties"]["next_job"]["anyOf"][0]["properties"]["task"]["const"] == M5_VERIFICATION_TASK


@pytest.mark.parametrize("field", ["task", "tool"])
def test_execution_rejects_descriptive_task_or_tool(field: str) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    payload = {"schema": EXECUTION_SCHEMA, "task": M5_VERIFICATION_TASK, "tool": M5_VERIFICATION_TASK, "parameters": {"mode": "real", "event_index": 0}, "invariants": ["preserve frozen inputs"], "workspace_manifest": None}
    payload[field] = "Independently recompute the existing BTC result"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, execution_schema())
    with pytest.raises(ContractError, match="registered identifier"):
        validate_execution_plan(payload)


@pytest.mark.parametrize("field,value", [("hypothesis", " "), ("expected_evidence", []), ("invariants", [" "]), ("stop_conditions", []), ("falsification_conditions", [])])
def test_proposal_schema_rejects_empty_locally_required_values(field: str, value: object) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    payload = {**_proposal(), "parent_result_id": None}
    payload[field] = value
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, proposal_schema())
    with pytest.raises(ContractError):
        validate_proposal(payload)


def test_replayed_v2_failure_preserves_response_usage_and_attempt_link(tmp_path: Path) -> None:
    from test_btc_ai_pipeline import real_fixture_layout

    rejected = saved_proposal()
    thinker = RecordingFixture("thinker", lambda request, payload: rejected)
    executor = RecordingFixture("executor")
    saved_config, _, _ = real_fixture_layout(tmp_path)
    controller = PipelineController(saved_config, thinkers={"fixture": thinker}, executors={"fixture": executor})
    state = controller.run(controller.create_campaign())
    summary = controller.store.summary(state["campaign_id"])
    attempt = summary["attempts"][0]
    failure = summary["failures"][0]
    assert state["status"] == "FAILED"
    assert attempt["status"] == "FAILED"
    assert json.loads(attempt["response_json"]) == rejected
    assert attempt["usage_json"] is not None
    assert failure["attempt_id"] == attempt["id"]
    assert failure["job_id"] == attempt["job_id"]
    assert json.loads(failure["details_json"])["provider_call_performed"] is True
    assert state["budget"]["thinker_calls"] == 1
    assert state["budget"]["executor_calls"] == 0
    assert state["jobs"][0]["specification_hash"] == "pending"
    assert state["result_count"] == 0
    assert len(thinker.requests) == 1 and not executor.requests


@pytest.mark.parametrize("phase", ["proposal", "execution", "review"])
def test_context_mismatch_is_a_failed_attributed_attempt(tmp_path: Path, phase: str) -> None:
    def mutate(request, payload):
        if request.phase != phase:
            return payload
        if phase == "proposal":
            payload["parameters"] = {"mode": "real", "event_index": 0}
        elif phase == "execution":
            payload["parameters"] = {"mode": "fixture", "event_index": 1}
        else:
            payload["evidence_refs"] = ["unrelated-result"]
        return payload

    controller = PipelineController(config(tmp_path), thinkers={"fixture": RecordingFixture("thinker", mutate)}, executors={"fixture": RecordingFixture("executor", mutate)})
    state = controller.run(controller.create_campaign())
    summary = controller.store.summary(state["campaign_id"])
    failure = summary["failures"][-1]
    attempt = next(item for item in summary["attempts"] if item["id"] == failure["attempt_id"])
    assert state["status"] == "FAILED"
    assert attempt["phase"] == phase
    assert attempt["status"] == "FAILED"
    assert attempt["response_json"] is not None
    assert failure["job_id"] == attempt["job_id"]
    assert failure["kind"] == "tool_restriction"
    assert not state["decisions"]


def test_complete_fixture_loop_supplies_catalog_and_binding_context(tmp_path: Path) -> None:
    thinker, executor = RecordingFixture("thinker"), RecordingFixture("executor")
    controller = PipelineController(config(tmp_path), thinkers={"fixture": thinker}, executors={"fixture": executor})
    state = controller.run(controller.create_campaign(), branch="stop")
    assert state["status"] == "STOPPED"
    assert state["budget"]["thinker_calls"] == 2
    assert state["budget"]["executor_calls"] == 1
    requests = [thinker.requests[0], executor.requests[0], thinker.requests[1]]
    for request in requests:
        context = json.loads(request.prompt[request.prompt.index("{"):])
        tool = context["registered_tasks"][0]
        assert tool["task"] == tool["tool"] == M5_VERIFICATION_TASK
        assert tool["parameters_schema"] == proposal_schema()["properties"]["parameters"]
        assert context["verification_mode"] == "fixture"
        assert context["campaign_budget"]["max_jobs"] == 1
    executor_context = json.loads(executor.requests[0].prompt[executor.requests[0].prompt.index("{"):])
    assert executor_context["proposal"] == executor.requests[0].metadata["proposal"]
    review_context = json.loads(thinker.requests[1].prompt[thinker.requests[1].prompt.index("{"):])
    assert review_context["evidence"]["result_id"] == state["jobs"][0]["result_id"]
