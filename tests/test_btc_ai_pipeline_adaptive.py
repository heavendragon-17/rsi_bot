"""Research choices, durable external sessions and adaptive campaign contracts."""

import json
from pathlib import Path

import pytest
from test_btc_ai_pipeline import config

from app.research_pipeline.contracts import (
    EXECUTION_SCHEMA,
    ContractError,
    ProviderError,
    execution_schema,
    proposal_schema,
    validate_execution_plan,
    validate_proposal,
)
from app.research_pipeline.controller import PipelineController
from app.research_pipeline.providers import FixtureProvider, _proposal


def adaptive_config(tmp_path, **overrides):
    from test_btc_ai_pipeline_studies import build_study_packet

    from app.research_pipeline.contracts import PipelineConfig

    params, context = build_study_packet(tmp_path)
    values = dict(repo_root=str(context.repo_root), db_path=str(context.repo_root / "pipeline.sqlite"),
                  output_dir=str(context.repo_root / "research/results/campaigns"),
                  data_dir=str(Path(params["source_csv"]).parent), baseline_packet=params["baseline_packet"],
                  horizon_packet=params["horizon_packet"], verification_mode="real", adaptive=True,
                  max_jobs=2, max_thinker_calls=3, max_executor_calls=2)
    return PipelineConfig(**{**values, **overrides})


def study_proposal(task="summarize_m5_horizons", **parameters):
    return {**_proposal(), "task": task, "parameters": {"mode": "fixture", **parameters}}


def test_study_contracts_allow_constrained_executor_choice():
    proposal = study_proposal("compare_m5_cohorts", horizon_minutes=120, grouping="choose")
    assert validate_proposal(proposal) == proposal
    plan = {"schema": EXECUTION_SCHEMA, "task": proposal["task"], "tool": proposal["task"],
            "parameters": {"mode": "fixture", "horizon_minutes": 120, "grouping": "calendar_year"},
            "invariants": proposal["invariants"], "workspace_manifest": None,
            "diagnostic_rationale": "Compare years to test whether the pooled result is concentrated in one period."}
    assert validate_execution_plan(plan) == plan
    with pytest.raises(ContractError):
        validate_execution_plan({**plan, "parameters": proposal["parameters"]})
    with pytest.raises(ContractError):
        validate_execution_plan({**plan, "diagnostic_rationale": ""})


def test_adaptive_schemas_preserve_legacy_default():
    assert proposal_schema()["properties"]["task"]["const"] == "verify_m5_horizons"
    assert "compare_m5_cohorts" in proposal_schema(adaptive=True)["properties"]["task"]["enum"]
    assert "diagnostic_rationale" in execution_schema(adaptive=True)["required"]


@pytest.mark.parametrize("task,parameters", [
    ("summarize_m5_horizons", {"mode": "real"}),
    ("compare_m5_cohorts", {"mode": "real", "horizon_minutes": 180, "grouping": "calendar_year"}),
])
@pytest.mark.parametrize("rationale", [None, "", " \t\n", "Check whether the gross difference is consistent across the selected comparison."])
def test_study_schema_and_validator_agree_on_required_rationale(task, parameters, rationale):
    jsonschema = pytest.importorskip("jsonschema")
    plan = {"schema": EXECUTION_SCHEMA, "task": task, "tool": task, "parameters": parameters,
            "invariants": ["preserve frozen inputs"], "workspace_manifest": None,
            "diagnostic_rationale": rationale}
    if not isinstance(rationale, str) or not rationale.strip():
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(plan, execution_schema(adaptive=True))
        with pytest.raises(ContractError, match="diagnostic_rationale"):
            validate_execution_plan(plan)
    else:
        jsonschema.validate(plan, execution_schema(adaptive=True))
        assert validate_execution_plan(plan) == plan


def test_provider_session_is_durable_and_uncertain_resume_does_not_redispatch(tmp_path):
    class LostSession(FixtureProvider):
        calls = 0

        def complete(self, request):
            self.calls += 1
            request.metadata["persist_provider_session"]({"provider": "opencode", "session_id": "ses_durable", "server_url": "http://127.0.0.1:4096"})
            raise ProviderError("request outcome unknown", kind="interrupted_uncertain", retryable=True,
                                details={"manual_reconciliation_required": True, "session_id": "ses_durable"})

    provider = LostSession("thinker")
    controller = PipelineController(config(tmp_path), thinkers={"fixture": provider})
    campaign = controller.create_campaign()
    first = controller.run(campaign)
    assert first["status"] == "PAUSED"
    attempt = controller.store.summary(campaign)["attempts"][0]
    assert json.loads(attempt["request_json"])["provider_session"]["session_id"] == "ses_durable"
    assert attempt["status"] == "PAUSED"
    resumed = controller.resume(campaign)
    assert resumed["attempt_count"] == 1 and provider.calls == 1


def test_nonadaptive_campaign_rejects_study_task(tmp_path):
    controller = PipelineController(config(tmp_path))
    campaign = controller.create_campaign()
    with pytest.raises(ValueError):
        controller._validate_proposal_payload(campaign, study_proposal(), None)


def test_two_distinct_research_jobs_complete_without_manual_resume(tmp_path):
    controller = PipelineController(adaptive_config(tmp_path))
    campaign = controller.create_campaign()
    state = controller.run(campaign)
    assert state["status"] == "STOPPED", state["failures"]
    assert state["result_count"] == 2
    assert state["budget"]["thinker_calls"] == 3
    assert state["budget"]["executor_calls"] == 2
    records = controller.store.summary(campaign)
    evidence = [json.loads(row["evidence_json"]) for row in records["results"]]
    assert [row["task"] for row in evidence] == ["summarize_m5_horizons", "compare_m5_cohorts"]
    assert all(row["status"] == "VERIFIED" and not row["reused_evidence"] for row in evidence)
    chosen = max(evidence[0]["tables"], key=lambda row: abs(row["signal_minus_baseline_pp"]))
    assert evidence[1]["parameters"]["horizon_minutes"] == chosen["horizon_minutes"]
    assert records["jobs"][1]["parent_job_id"] == records["jobs"][0]["id"]
    assert controller.resume(campaign)["attempt_count"] == 5


def test_adaptive_crash_after_decision_commit_does_not_repeat_work(tmp_path, monkeypatch):
    cfg = adaptive_config(tmp_path)
    controller = PipelineController(cfg)
    campaign = controller.create_campaign()
    original = controller._apply_decision_status

    def interrupt_after_decision(campaign_id, job_id, action, next_job_id):
        if action == "PROPOSE_NEXT":
            raise KeyboardInterrupt("simulated process interruption")
        return original(campaign_id, job_id, action, next_job_id)

    monkeypatch.setattr(controller, "_apply_decision_status", interrupt_after_decision)
    with pytest.raises(KeyboardInterrupt):
        controller.run(campaign)
    resumed = PipelineController(cfg).resume(campaign)
    assert resumed["status"] == "STOPPED", resumed["failures"]
    assert resumed["attempt_count"] == 5 and resumed["result_count"] == 2
    assert resumed["budget"]["jobs_started"] == 2


def test_adaptive_job_cap_preserves_followup_without_dispatch(tmp_path):
    controller = PipelineController(adaptive_config(tmp_path, max_jobs=1))
    state = controller.run(controller.create_campaign())
    assert state["status"] == "LIMIT_REACHED", state["failures"]
    assert state["result_count"] == 1 and state["attempt_count"] == 3
    assert state["jobs"][1]["status"] == "DEFERRED_LIMIT"


def test_scripted_baseline_matches_without_new_model_attempts(tmp_path):
    from app.research_pipeline.measurements import replay_baseline

    controller = PipelineController(adaptive_config(tmp_path))
    campaign = controller.create_campaign()
    first = controller.run(campaign)
    baseline = replay_baseline(controller, campaign)
    assert baseline["status"] == "MATCHED"
    assert len(baseline["jobs"]) == 2 and baseline["provider_calls"] == 0
    assert all(row["same_evidence"] for row in baseline["jobs"])
    assert controller.status(campaign)["attempt_count"] == first["attempt_count"]
    assert baseline["campaign_measurements"]["reported_cost"] is None
    assert baseline["campaign_measurements"]["adaptive_sequence_verified"] is True
    assert baseline["campaign_measurements"]["live_loop_verified"] is False
    assert baseline["campaign_measurements"]["recorded_checker_seconds"] > 0
    assert baseline["campaign_measurements"]["checker_timed_results"] == 2
    assert baseline["campaign_measurements"]["campaign_span_seconds"] >= baseline["campaign_measurements"]["recorded_checker_seconds"]


def test_live_provider_success_does_not_imply_completed_loop():
    from app.research_pipeline.measurements import runtime_measurements

    report = json.loads((Path(__file__).resolve().parents[1] / "research/results/btc_ai_pipeline_live_smoke_v2/campaign_3a869ced481f44ab/report.json").read_text())
    measured = runtime_measurements(report)
    assert measured["live_loop_verified"] is False
    assert measured["reported_input_tokens"] > 0
    assert measured["reported_cost"] is None


def test_mixed_provider_usage_preserves_missing_coverage_and_cache_semantics():
    from app.research_pipeline.measurements import runtime_measurements

    attempts = [{"provider": provider, "status": "FAILED", "phase": "execution", "error_kind": "malformed_json",
                 "usage_json": json.dumps({"provider_usage": usage})}
                for provider, usage in (
                    ("codex", {"runtime": {"input_tokens": 100, "output_tokens": 20, "cached_input_tokens": 60}}),
                    ("opencode", {"runtime": {"input": 40, "output": 10, "reasoning": 5, "total": 95,
                                              "cache": {"read": 30, "write": 10}}, "runtime_cost": 0.02}),
                    ("codex", {"runtime": None}))]
    attempts[-1]["error_kind"] = "tool_restriction"
    measured = runtime_measurements({"attempts": attempts, "results": [], "decisions": [{"action": "REPAIR"}],
                                    "failures": [{}, {}, {}], "campaign": {"status": "PAUSED"}})
    assert measured["reported_input_tokens"] == 140
    assert measured["supplemental_token_usage"]["cache_read"] == {"reported_tokens": 90, "attempts": 2}
    assert measured["supplemental_token_usage"]["reasoning"] == {"reported_tokens": 5, "attempts": 1}
    assert measured["reported_cost"] == 0.02
    assert not measured["all_attempts_have_cost"] and not measured["all_attempts_have_token_usage"]
    assert measured["invalid_execution_plan_attempts"] == 3 and measured["repair_decisions"] == 1
