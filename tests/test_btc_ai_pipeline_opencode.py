"""No-call contract tests for the OpenCode local-server adapter."""

from __future__ import annotations

import io
import json
import socket
from pathlib import Path
from urllib.error import HTTPError

import pytest

from app.research_pipeline.contracts import ProviderError, ProviderRequest
from app.research_pipeline.providers import OpenCodeProvider, preflight_provider


MODEL = "opencode-go/muse-spark-1.3-contributor"


class FakeResponse:
    def __init__(self, payload: object, *, status: int = 200) -> None:
        self.status = status
        self._body = json.dumps(payload).encode("utf-8")

    def read(self, _limit: int = -1) -> bytes:
        return self._body

    def close(self) -> None:
        return None


class FakeOpener:
    def __init__(self, responses: list[object]) -> None:
        self.responses = iter(responses)
        self.calls: list[tuple[object, float]] = []

    def __call__(self, request: object, *, timeout: float) -> FakeResponse:
        self.calls.append((request, timeout))
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        assert isinstance(response, FakeResponse)
        return response


def _request_payload(request: object) -> dict[str, object]:
    data = getattr(request, "data")
    assert isinstance(data, bytes)
    parsed = json.loads(data.decode("utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def _catalog() -> dict[str, object]:
    return {
        "connected": ["opencode-go"],
        "all": [
            {
                "id": "opencode-go",
                "models": {
                    "muse-spark-1.3-contributor": {
                        "id": "muse-spark-1.3-contributor",
                        "providerID": "opencode-go",
                        "name": "Muse Spark 1.3 Contributor",
                        "variants": {"minimal": {}, "low": {}, "medium": {}, "high": {}, "xhigh": {}},
                        "capabilities": {"reasoning": True, "toolcall": True},
                        "limit": {"context": 1048576, "output": 131072},
                    }
                },
            }
        ],
    }


def test_opencode_structured_completion_uses_model_variant_and_denies_tools(tmp_path: Path) -> None:
    payload = {"schema": "btc-research-proposal-v1", "ok": True}
    opener = FakeOpener([
        FakeResponse({"id": "ses_test123"}),
        FakeResponse(
            {
                "info": {
                    "providerID": "opencode-go",
                    "modelID": "muse-spark-1.3-contributor",
                    "variant": "high",
                    "tokens": {"input": 12, "output": 4, "reasoning": 1, "cache": {"read": 2, "write": 0}},
                    "cost": 0.01,
                },
                "parts": [],
                "structured": payload,
            }
        ),
    ])
    request = ProviderRequest(
        role="executor",
        phase="execution",
        prompt="Return the bounded execution plan as JSON.",
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False},
        model=MODEL,
        effort="high",
        timeout_seconds=3,
        context_budget=6000,
        output_budget=2000,
    )

    response = OpenCodeProvider(model=MODEL, repo_root=tmp_path, opener=opener).complete(request)

    assert response.payload == payload
    assert response.reported_model == MODEL
    assert response.usage is not None
    assert response.usage["runtime"]["output"] == 4
    assert response.usage["runtime_cost"] == 0.01
    assert response.controls is not None
    assert response.controls["effort"]["enforced"] is True
    assert response.controls["timeout"]["enforced"] == "overall_http_deadline"
    assert len(opener.calls) == 2

    session_request = opener.calls[0][0]
    prompt_request = opener.calls[1][0]
    assert getattr(session_request, "method") == "POST"
    assert getattr(prompt_request, "method") == "POST"
    assert "/session/ses_test123/message?" in getattr(prompt_request, "full_url")
    assert "directory=" in getattr(prompt_request, "full_url")
    headers = {key.lower(): value for key, value in getattr(prompt_request, "header_items")()}
    assert headers["x-opencode-session"] == "ses_test123"
    session_payload = _request_payload(session_request)
    assert session_payload["title"] == "btc-ai-pipeline-executor-execution"
    permissions = session_payload["permission"]
    assert isinstance(permissions, list)
    assert permissions and all(item["action"] == "deny" for item in permissions)
    prompt_payload = _request_payload(prompt_request)
    assert prompt_payload["model"] == {"providerID": "opencode-go", "modelID": "muse-spark-1.3-contributor"}
    assert prompt_payload["variant"] == "high"
    assert prompt_payload["format"]["type"] == "json_schema"
    assert prompt_payload["format"]["retryCount"] == 0
    assert prompt_payload["parts"] == [{"type": "text", "text": request.prompt}]


def test_opencode_preflight_checks_health_catalog_and_variant_without_model_call(tmp_path: Path) -> None:
    opener = FakeOpener([FakeResponse({"healthy": True, "version": "1.18.28"}), FakeResponse(_catalog())])

    result = OpenCodeProvider(model=MODEL, repo_root=tmp_path, opener=opener).preflight(effort="high", context_budget=6000, output_budget=2000, timeout_seconds=5)

    assert result["live_call_performed"] is False
    assert result["server_reachable"] is True
    assert result["provider_connected"] is True
    assert result["model_available"] is True
    assert result["model_metadata"]["variants"] == ["high", "low", "medium", "minimal", "xhigh"]
    assert result["controls"]["effort"]["provider_supported"] is True
    assert [getattr(request, "method") for request, _timeout in opener.calls] == ["GET", "GET"]


def test_opencode_preflight_reports_unreachable_server_without_model_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCODE_SERVER_URL", "http://127.0.0.1:1")
    result = preflight_provider("opencode", MODEL, effort="high", timeout_seconds=1)

    assert result["live_call_performed"] is False
    assert result["server_reachable"] is False
    assert result["notes"]


def test_opencode_rejects_a_reported_variant_mismatch() -> None:
    opener = FakeOpener([
        FakeResponse({"id": "ses_test123"}),
        FakeResponse({"info": {"variant": "low"}, "structured": {"ok": True}}),
    ])
    request = ProviderRequest("executor", "execution", "prompt", {"type": "object"}, MODEL, "high", 3, 10, 10)

    with pytest.raises(ProviderError) as caught:
        OpenCodeProvider(model=MODEL, opener=opener).complete(request)

    assert caught.value.kind == "provider_contract"
    assert caught.value.details["requested_variant"] == "high"
    assert caught.value.details["reported_variant"] == "low"


def test_opencode_auth_error_is_redacted_and_classified() -> None:
    body = json.dumps({"error": {"name": "ProviderAuthError", "message": "Bearer top-secret-token"}}).encode("utf-8")
    opener = FakeOpener([HTTPError("http://127.0.0.1:4096/session", 401, "Unauthorized", {}, io.BytesIO(body))])
    request = ProviderRequest("executor", "execution", "prompt", {}, MODEL, "minimal", 3, 10, 10)

    with pytest.raises(ProviderError) as caught:
        OpenCodeProvider(model=MODEL, opener=opener).complete(request)

    assert caught.value.kind == "auth"
    assert "top-secret-token" not in str(caught.value)
    assert caught.value.details["http_status"] == 401


def test_opencode_timeout_is_resumable() -> None:
    opener = FakeOpener([socket.timeout("timed out")])
    request = ProviderRequest("executor", "execution", "prompt", {}, MODEL, "minimal", 3, 10, 10)

    with pytest.raises(ProviderError) as caught:
        OpenCodeProvider(model=MODEL, opener=opener).complete(request)

    assert caught.value.kind == "timeout"
    assert caught.value.retryable is True
