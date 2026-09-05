"""No-call contract tests for the OpenCode local-server adapter."""

from __future__ import annotations

import io
import json
import time
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request

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
        self.calls: list[tuple[Request, float]] = []

    def __call__(self, request: Request, *, timeout: float) -> FakeResponse:
        self.calls.append((request, timeout))
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        assert isinstance(response, FakeResponse)
        return response


def _request_payload(request: Request) -> dict[str, object]:
    data = request.data
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
    assert response.controls["structured_output"] == {
        "mode": "json_schema", "provider_enforced": True, "local_validation": True,
    }
    assert len(opener.calls) == 2

    session_request = opener.calls[0][0]
    prompt_request = opener.calls[1][0]
    assert session_request.method == "POST"
    assert prompt_request.method == "POST"
    assert "/session/ses_test123/message?" in prompt_request.full_url
    assert "directory=" in prompt_request.full_url
    headers = {key.lower(): value for key, value in prompt_request.header_items()}
    assert headers["x-opencode-session"] == "ses_test123"
    session_payload = _request_payload(session_request)
    assert session_payload["title"] == "btc-ai-pipeline-executor-execution"
    permissions = session_payload["permission"]
    assert isinstance(permissions, list)
    assert permissions == [
        {"permission": "*", "pattern": "*", "action": "deny"},
        {"permission": "StructuredOutput", "pattern": "*", "action": "allow"},
    ]
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
    assert [request.method for request, _timeout in opener.calls] == ["GET", "GET"]


def test_opencode_preflight_reports_unreachable_server_without_model_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCODE_SERVER_URL", "http://127.0.0.1:1")
    opener = FakeOpener([URLError("connection refused")])
    monkeypatch.setattr("app.research_pipeline.opencode_provider.urlopen", opener)
    result = preflight_provider("opencode", MODEL, effort="high", timeout_seconds=1)

    assert result["live_call_performed"] is False
    assert result["server_reachable"] is False
    assert result["notes"]
    assert len(opener.calls) == 1


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
    opener = FakeOpener([TimeoutError("timed out")])
    request = ProviderRequest("executor", "execution", "prompt", {}, MODEL, "minimal", 3, 10, 10)

    with pytest.raises(ProviderError) as caught:
        OpenCodeProvider(model=MODEL, opener=opener).complete(request)

    assert caught.value.kind == "timeout"
    assert caught.value.retryable is True


def test_opencode_persists_session_before_dispatch() -> None:
    opener = FakeOpener([
        FakeResponse({"id": "ses_durable"}),
        FakeResponse({"info": {"structured": {"ok": True}}}),
    ])
    persisted = []

    def persist(metadata: dict[str, object]) -> None:
        assert len(opener.calls) == 1
        persisted.append(dict(metadata))

    request = ProviderRequest("executor", "execution", "prompt", {}, MODEL, "high", 3, 10, 10,
                              metadata={"persist_provider_session": persist})

    response = OpenCodeProvider(model=MODEL, opener=opener).complete(request)

    assert persisted == [{"provider": "opencode", "session_id": "ses_durable", "server_url": "http://127.0.0.1:4096"}]
    assert response.payload == {"ok": True}
    assert response.usage["session_id"] == "ses_durable"


def test_opencode_persistence_failure_prevents_model_dispatch() -> None:
    opener = FakeOpener([FakeResponse({"id": "ses_durable"}), FakeResponse({"structured": {"ok": True}})])

    def persist(_metadata: dict[str, object]) -> None:
        raise OSError("database failed password=secret-value")

    request = ProviderRequest("executor", "execution", "prompt", {}, MODEL, "high", 3, 10, 10,
                              metadata={"persist_provider_session": persist})

    with pytest.raises(ProviderError) as caught:
        OpenCodeProvider(model=MODEL, opener=opener).complete(request)

    assert caught.value.kind == "session_persistence"
    assert caught.value.details["session_id"] == "ses_durable"
    assert caught.value.details["provider_call_performed"] is False
    assert "secret-value" not in str(caught.value) + json.dumps(caught.value.details)
    assert len(opener.calls) == 1


def test_opencode_invalid_persistence_callback_prevents_session_creation() -> None:
    opener = FakeOpener([FakeResponse({"id": "ses_durable"}), FakeResponse({"structured": {"ok": True}})])
    request = ProviderRequest("executor", "execution", "prompt", {}, MODEL, "high", 3, 10, 10,
                              metadata={"persist_provider_session": "not callable"})

    with pytest.raises(ProviderError) as caught:
        OpenCodeProvider(model=MODEL, opener=opener).complete(request)

    assert caught.value.kind == "configuration"
    assert opener.calls == []


def test_opencode_deadline_expiry_after_persistence_retains_session_without_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    opener = FakeOpener([FakeResponse({"id": "ses_durable"}), FakeResponse({"structured": {"ok": True}})])

    def persist(_metadata: dict[str, object]) -> None:
        now[0] = 4.0

    request = ProviderRequest("executor", "execution", "prompt", {}, MODEL, "high", 3, 10, 10,
                              metadata={"persist_provider_session": persist})

    with pytest.raises(ProviderError) as caught:
        OpenCodeProvider(model=MODEL, opener=opener).complete(request)

    assert caught.value.kind == "timeout"
    assert caught.value.details["session_id"] == "ses_durable"
    assert caught.value.details["provider_call_performed"] is False
    assert len(opener.calls) == 1


@pytest.mark.parametrize("failure", [
    TimeoutError("timed out"),
    URLError("connection reset"),
    IncompleteRead(b"partial response", 30),
])
def test_opencode_dispatched_transport_failure_aborts_and_retains_session(failure: BaseException, tmp_path: Path) -> None:
    opener = FakeOpener([FakeResponse({"id": "ses_durable"}), failure, FakeResponse(True)])
    request = ProviderRequest("executor", "execution", "prompt", {}, MODEL, "high", 30, 10, 10)

    with pytest.raises(ProviderError) as caught:
        OpenCodeProvider(model=MODEL, repo_root=tmp_path, opener=opener).complete(request)

    assert caught.value.kind in {"timeout", "provider_connect"}
    assert caught.value.retryable is True
    assert caught.value.details["provider"] == "opencode"
    assert caught.value.details["session_id"] == "ses_durable"
    assert caught.value.details["server_url"] == "http://127.0.0.1:4096"
    assert caught.value.details["provider_call_performed"] is True
    assert caught.value.details["abort"]["confirmed"] is True
    assert caught.value.details["manual_reconciliation_required"] is False
    assert len(opener.calls) == 3
    abort_request, abort_timeout = opener.calls[-1]
    assert abort_request.method == "POST"
    assert "/session/ses_durable/abort?directory=" in abort_request.full_url
    assert 0 < abort_timeout <= 5


@pytest.mark.parametrize("abort_response", [
    FakeResponse(False),
    FakeResponse({"ok": True}),
    FakeResponse(None, status=204),
    TimeoutError("abort timed out"),
    URLError("abort connection reset"),
])
def test_opencode_unconfirmed_abort_requires_manual_reconciliation(abort_response: object) -> None:
    opener = FakeOpener([FakeResponse({"id": "ses_durable"}), TimeoutError("message timed out"), abort_response])
    request = ProviderRequest("executor", "execution", "prompt", {}, MODEL, "high", 30, 10, 10)

    with pytest.raises(ProviderError) as caught:
        OpenCodeProvider(model=MODEL, opener=opener).complete(request)

    assert caught.value.kind == "interrupted_uncertain"
    assert caught.value.retryable is True
    assert caught.value.details["manual_reconciliation_required"] is True
    assert caught.value.details["original_error_kind"] == "timeout"
    assert caught.value.details["session_id"] == "ses_durable"
    assert caught.value.details["abort"]["attempted"] is True
    assert caught.value.details["abort"]["confirmed"] is False
    assert len(opener.calls) == 3


def test_opencode_explicit_message_rejection_retains_session_without_abort() -> None:
    opener = FakeOpener([
        FakeResponse({"id": "ses_durable"}),
        FakeResponse({"error": {"name": "ProviderAuthError", "message": "not authenticated"}}, status=401),
    ])
    request = ProviderRequest("executor", "execution", "prompt", {}, MODEL, "high", 30, 10, 10)

    with pytest.raises(ProviderError) as caught:
        OpenCodeProvider(model=MODEL, opener=opener).complete(request)

    assert caught.value.kind == "auth"
    assert caught.value.details["session_id"] == "ses_durable"
    assert len(opener.calls) == 2


@pytest.mark.parametrize("status", [408, 500, 502, 503, 504])
def test_opencode_ambiguous_server_failure_requires_confirmed_abort(status: int) -> None:
    opener = FakeOpener([
        FakeResponse({"id": "ses_durable"}),
        FakeResponse({"error": {"message": "request interrupted"}}, status=status),
        FakeResponse(False),
    ])
    request = ProviderRequest("executor", "execution", "prompt", {}, MODEL, "high", 30, 10, 10)

    with pytest.raises(ProviderError) as caught:
        OpenCodeProvider(model=MODEL, opener=opener).complete(request)

    assert caught.value.kind == "interrupted_uncertain"
    assert caught.value.details["http_status"] == status
    assert caught.value.details["session_id"] == "ses_durable"
    assert len(opener.calls) == 3


@pytest.mark.parametrize("status,message,kind,retryable", [
    (401, "Invalid API key", "auth", True),
    (429, "Provider quota exceeded", "rate_limit", True),
    (400, 'Error from provider (Console Go): Upstream request failed: [invalid_request_error] '
          'only `"auto"` is supported for `tool_choice`. `"none"`, `"required"`, and named '
          'function choices are not currently supported', "invalid_request", False),
    (403, "Requests from your country or region are not supported", "region_restriction", False),
])
def test_opencode_named_error_preserves_nested_status_and_cause(status, message, kind, retryable):
    error = {"name": "APIError", "data": {"message": message, "statusCode": status,
             "isRetryable": status == 429, "responseHeaders": {"authorization": "header-secret"},
             "requestBody": {"prompt": "private-request-text"}}}
    opener = FakeOpener([
        FakeResponse({"id": "ses_nested"}),
        FakeResponse({"info": {"id": "msg_failed", "sessionID": "ses_nested", "role": "assistant",
                     "providerID": "opencode-go", "modelID": "muse-spark-1.3-contributor",
                     "error": error, "time": {"created": 100, "completed": 200}, "cost": 0,
                     "tokens": {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}}},
                     "parts": []}),
    ])
    request = ProviderRequest("executor", "execution", "prompt", {}, MODEL, "high", 30, 10, 10)

    with pytest.raises(ProviderError) as caught:
        OpenCodeProvider(model=MODEL, opener=opener).complete(request)

    assert caught.value.kind == kind
    assert caught.value.retryable is retryable
    assert caught.value.details["http_status"] == status
    assert caught.value.details["provider_retryable"] is (status == 429)
    assert caught.value.details["provider_error"]["name"] == "APIError"
    assert caught.value.details["provider_error"]["message"] == message
    assert message in str(caught.value)
    assert caught.value.details["session_id"] == "ses_nested"
    assert len(opener.calls) == 2
    diagnostic = str(caught.value) + json.dumps(caught.value.details)
    assert all(secret not in diagnostic for secret in ("responseHeaders", "requestBody", "header-secret", "private-request-text"))


@pytest.mark.parametrize("envelope", ["assistant", "http"])
def test_opencode_nested_response_body_keeps_only_parsed_error_fields(envelope):
    error = {"name": "APIError", "data": {
        "message": "Upstream request failed", "statusCode": 400, "isRetryable": False,
        "responseHeaders": {"set-cookie": "header-secret"}, "requestBody": "request-secret",
        "responseBody": json.dumps({"error": {"message": "Unsupported parameter: temperature",
                        "type": "invalid_request_error", "code": "unsupported_parameter", "param": "temperature",
                        "responseHeaders": "inner-header-secret", "requestBody": "inner-request-secret"},
                        "debug": "raw-body-secret"}),
    }}
    if envelope == "assistant":
        responses = [FakeResponse({"id": "ses_nested"}), FakeResponse({"info": {"error": error}, "parts": []})]
    else:
        responses = [FakeResponse({"error": error}, status=400)]
    opener = FakeOpener(responses)
    request = ProviderRequest("executor", "execution", "prompt", {}, MODEL, "high", 30, 10, 10)

    with pytest.raises(ProviderError) as caught:
        OpenCodeProvider(model=MODEL, opener=opener).complete(request)

    assert caught.value.kind == "invalid_request"
    assert caught.value.details["provider_error"] == {
        "name": "APIError", "message": "Unsupported parameter: temperature", "type": "invalid_request_error",
        "code": "unsupported_parameter", "param": "temperature",
    }
    diagnostic = str(caught.value) + json.dumps(caught.value.details)
    assert all(secret not in diagnostic for secret in ("responseHeaders", "requestBody", "responseBody", "-secret"))
    assert len(opener.calls) == len(responses)


def test_opencode_named_error_bounds_and_redacts_every_extracted_field():
    message = "Bearer bearer-secret; Basic dXNlcjpwYXNzd29yZA== api_key=key-secret password=password-secret sk-secretkey " + "x" * 3000
    error = {"name": "APIError Bearer name-secret", "data": {
        "message": message, "statusCode": 400, "isRetryable": False,
        "code": "unsupported_parameter", "responseBody": "<html>opaque-body-secret</html>",
    }}
    opener = FakeOpener([FakeResponse({"id": "ses_nested"}), FakeResponse({"info": {"error": error}})])
    request = ProviderRequest("executor", "execution", "prompt", {}, MODEL, "high", 30, 10, 10)

    with pytest.raises(ProviderError) as caught:
        OpenCodeProvider(model=MODEL, opener=opener).complete(request)

    assert caught.value.kind == "invalid_request"
    record = caught.value.details["provider_error"]
    assert record["code"] == "unsupported_parameter"
    assert record["message"].startswith("Bearer [REDACTED]")
    assert all(len(value) <= 1600 for value in record.values())
    diagnostic = str(caught.value) + json.dumps(caught.value.details)
    assert all(secret not in diagnostic for secret in (
        "bearer-secret", "dXNlcjpwYXNzd29yZA==", "key-secret", "password-secret", "sk-secretkey",
        "name-secret", "opaque-body-secret", "responseBody",
    ))


def test_opencode_nested_error_code_classifies_region_without_status():
    error = {"name": "APIError", "data": {"message": "Request not permitted", "isRetryable": False,
             "responseBody": json.dumps({"error": {"code": "unsupported_country_region_territory", "message": "Request denied"}})}}
    opener = FakeOpener([FakeResponse({"id": "ses_nested"}), FakeResponse({"info": {"error": error}})])
    request = ProviderRequest("executor", "execution", "prompt", {}, MODEL, "high", 30, 10, 10)

    with pytest.raises(ProviderError) as caught:
        OpenCodeProvider(model=MODEL, opener=opener).complete(request)

    assert caught.value.kind == "region_restriction"
    assert caught.value.retryable is False
    assert caught.value.details["provider_error"]["code"] == "unsupported_country_region_territory"
    assert len(opener.calls) == 2


@pytest.mark.parametrize("mode", [None, "", "auto", True, ["json_text"]])
def test_opencode_invalid_output_mode_prevents_session_creation(mode):
    opener = FakeOpener([FakeResponse({"id": "ses_mode"}), FakeResponse({"structured": {"ok": True}})])
    request = ProviderRequest("executor", "execution", "prompt", {}, MODEL, "high", 30, 10, 10,
                              metadata={"opencode_output_mode": mode})

    with pytest.raises(ProviderError) as caught:
        OpenCodeProvider(model=MODEL, opener=opener).complete(request)

    assert caught.value.kind == "configuration"
    assert opener.calls == []


def test_opencode_explicit_json_text_mode_omits_format_and_denies_every_tool():
    opener = FakeOpener([
        FakeResponse({"id": "ses_mode"}),
        FakeResponse({"info": {"providerID": "opencode-go", "modelID": "muse-spark-1.3-contributor"},
                      "parts": [{"type": "text", "text": '{"ok": true}'}]}),
    ])
    request = ProviderRequest("executor", "execution", "Return one JSON object matching this schema: ...",
                              {"type": "object"}, MODEL, "high", 30, 10, 10,
                              metadata={"opencode_output_mode": "json_text"})

    response = OpenCodeProvider(model=MODEL, opener=opener).complete(request)

    assert response.payload == {"ok": True}
    assert _request_payload(opener.calls[0][0])["permission"] == [
        {"permission": "*", "pattern": "*", "action": "deny"},
    ]
    payload = _request_payload(opener.calls[1][0])
    assert "format" not in payload
    assert payload["parts"] == [{"type": "text", "text": request.prompt}]
    assert response.controls["structured_output"] == {
        "mode": "json_text", "provider_enforced": False, "local_validation": True,
    }
    assert len(opener.calls) == 2


@pytest.mark.parametrize("text", [
    "not JSON", '```json\n{"ok":true}\n```', '{"ok":true} trailing', "[]",
    '{"value":NaN}', '{"value":Infinity}', '{"ok":true,"ok":false}',
])
def test_opencode_json_text_mode_rejects_invalid_object_without_retry(text):
    opener = FakeOpener([FakeResponse({"id": "ses_mode"}), FakeResponse({"parts": [{"type": "text", "text": text}]})])
    request = ProviderRequest("executor", "execution", "prompt", {}, MODEL, "high", 30, 10, 10,
                              metadata={"opencode_output_mode": "json_text"})

    with pytest.raises(ProviderError) as caught:
        OpenCodeProvider(model=MODEL, opener=opener).complete(request)

    assert caught.value.kind == "malformed_json"
    assert caught.value.details["session_id"] == "ses_mode"
    assert len(opener.calls) == 2
    assert "format" not in _request_payload(opener.calls[1][0])


@pytest.mark.parametrize("parts,expected", [
    (['{"ok":', 'true}'], {"ok": True}),
    (['{"ok":true}', ' trailing prose'], None),
    (['intro prose ', '{"ok":true}'], None),
    (['{"ok":true}', '{"other":true}'], None),
])
def test_opencode_json_text_parses_entire_message_without_structured_shortcuts(parts, expected):
    opener = FakeOpener([FakeResponse({"id": "ses_mode"}), FakeResponse({
        "structured": {"shortcut": True}, "parts": [{"type": "text", "text": part} for part in parts],
    })])
    request = ProviderRequest("executor", "execution", "prompt", {}, MODEL, "high", 30, 10, 10,
                              metadata={"opencode_output_mode": "json_text"})
    provider = OpenCodeProvider(model=MODEL, opener=opener)

    if expected is None:
        with pytest.raises(ProviderError, match="structured JSON") as caught:
            provider.complete(request)
        assert caught.value.kind == "malformed_json"
    else:
        assert provider.complete(request).payload == expected
    assert len(opener.calls) == 2


@pytest.mark.parametrize("reachable", [True, False])
def test_opencode_preflight_reports_explicit_json_text_mode(reachable):
    responses = [FakeResponse({"healthy": True}), FakeResponse(_catalog())] if reachable else [URLError("connection refused")]
    opener = FakeOpener(responses)

    result = OpenCodeProvider(model=MODEL, opener=opener).preflight(output_mode="json_text")

    assert result["live_call_performed"] is False
    assert result["server_reachable"] is reachable
    assert result["controls"]["structured_output"] == {
        "mode": "json_text", "provider_enforced": False, "local_validation": True,
    }
    assert all(request.method == "GET" for request, _timeout in opener.calls)
