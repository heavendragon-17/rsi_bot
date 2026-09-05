"""No-call regressions for actionable, bounded Codex failure evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.research_pipeline.contracts import PipelineConfig, ProviderError, ProviderRequest, proposal_schema
from app.research_pipeline.controller import PipelineController
from app.research_pipeline.providers import CodexCLIProvider, _provider_failure_details, _provider_failure_kind


SCHEMA_ERROR = {
    "type": "error",
    "error": {
        "type": "invalid_request_error",
        "code": "invalid_json_schema",
        "message": "Invalid schema for response_format 'codex_output_schema': In context=('properties', 'schema'), schema must have a 'type' key.",
        "param": "text.format.schema",
    },
    "status": 400,
}


def test_structured_failure_takes_precedence_over_stderr_warning() -> None:
    stdout = '\n'.join([
        json.dumps({"type": "thread.started", "thread_id": "saved-thread-123"}),
        json.dumps({"type": "turn.failed", "error": {"message": json.dumps(SCHEMA_ERROR)}}),
    ])
    details = _provider_failure_details(stdout, "WARNING: telemetry export failed")
    assert details["provider_thread_id"] == "saved-thread-123"
    assert details["provider_error"]["code"] == "invalid_json_schema"
    assert details["provider_error"]["http_status"] == 400
    assert details["provider_error"]["param"] == "text.format.schema"
    assert _provider_failure_kind(details) == "invalid_schema"


@pytest.mark.parametrize("code,status,kind", [
    ("rate_limit_exceeded", 429, "rate_limit"),
    ("invalid_api_key", 401, "auth"),
    ("model_not_found", 404, "model_access"),
    ("invalid_request_error", 400, "invalid_request"),
])
def test_failure_classification(code: str, status: int, kind: str) -> None:
    details = _provider_failure_details(json.dumps({"type": "error", "error": {"code": code, "message": "request failed"}, "status": status}), "")
    assert _provider_failure_kind(details) == kind


def test_diagnostics_are_bounded_and_redact_credentials() -> None:
    message = 'Error: Bearer bearer-secret sk-secret-123 access_token="token-secret" password="two word secret" OPENAI_API_KEY=secret-key ' + 'x' * 3000
    details = _provider_failure_details(json.dumps({"type": "error", "message": message}), "")
    safe = details["provider_error"]["message"]
    assert len(safe) <= 1600
    for secret in ("bearer-secret", "sk-secret-123", "token-secret", "two word secret", "secret-key"):
        assert secret not in safe
    assert "[REDACTED]" in safe


def test_non_error_stdout_is_not_saved_as_a_diagnostic() -> None:
    stdout = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "private research prompt"}})
    details = _provider_failure_details(stdout, "Error loading configuration: Could not find home directory")
    assert "private research prompt" not in json.dumps(details)
    assert "Could not find home directory" in details["stderr_diagnostic"]
    assert _provider_failure_kind(_provider_failure_details("", "Error: could not generate report")) == "provider_exit"


def test_adapter_retains_invalid_schema_error_without_subprocess(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(CodexCLIProvider, "_run_bounded", staticmethod(lambda *args, **kwargs: (json.dumps(SCHEMA_ERROR), "warning", 1, None)))
    request = ProviderRequest("thinker", "proposal", "bounded job", proposal_schema(), "gpt-5.6-sol", "high", 3, 6000, 2000, {"schema_path": str(tmp_path / "schema.json")})
    with pytest.raises(ProviderError) as caught:
        CodexCLIProvider(model="gpt-5.6-sol").complete(request)
    assert caught.value.kind == "invalid_schema"
    assert caught.value.retryable is False
    assert caught.value.details["provider_error"]["param"] == "text.format.schema"
    assert "must have a 'type' key" in str(caught.value)


def test_controller_persists_actionable_failure_and_does_not_retry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    invocations = []

    def fail(*args: object, **kwargs: object) -> tuple[str, str, int, None]:
        invocations.append(True)
        return json.dumps(SCHEMA_ERROR), "", 1, None

    monkeypatch.setattr(CodexCLIProvider, "_run_bounded", staticmethod(fail))
    root = Path(__file__).resolve().parents[1]
    config = PipelineConfig(repo_root=str(root), db_path=str(tmp_path / "pipeline.sqlite"), output_dir=str(tmp_path / "results"), thinker_provider="codex", thinker_model="gpt-5.6-sol", thinker_effort="high", executor_provider="codex", executor_model="gpt-5.6-luna", executor_effort="high", live_opt_in=True, verification_mode="real")
    controller = PipelineController(config)
    state = controller.run(controller.create_campaign())
    assert state["status"] == "FAILED"
    assert state["budget"]["thinker_calls"] == 1
    assert state["budget"]["executor_calls"] == 0
    assert len(invocations) == 1
    assert state["result_count"] == 0
    details = json.loads(state["failures"][0]["details_json"])
    assert details["provider_error"]["code"] == "invalid_json_schema"
    assert state["failures"][0]["kind"] == "invalid_schema"
