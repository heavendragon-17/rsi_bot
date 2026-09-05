"""OpenCode HTTP lifecycle with durable session identity and denied tools."""

from __future__ import annotations

import json
import os
import re
import time
from base64 import b64encode
from collections.abc import Callable, Mapping
from http.client import HTTPException
from pathlib import Path
from typing import Any, Literal, overload
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .contracts import ProviderError, ProviderRequest, ProviderResponse
from .provider_diagnostics import (
    _diagnostic_text,
    _opencode_error_details,
    _opencode_error_message,
    _opencode_failure_kind,
    _opencode_named_error_details,
)

DEFAULT_OPENCODE_SERVER_URL = "http://127.0.0.1:4096"
OPENCODE_RESPONSE_LIMIT_BYTES = 16 * 1024 * 1024
OPENCODE_ABORT_TIMEOUT_SECONDS = 5.0


def _opencode_model_parts(model: str) -> tuple[str, str]:
    """Split an OpenCode model reference without silently selecting a provider."""

    if not isinstance(model, str) or model.count("/") != 1:
        raise ProviderError(
            "OpenCode model must use the explicit provider/model form",
            kind="configuration",
            details={"expected_format": "provider/model"},
        )
    provider_id, model_id = (part.strip() for part in model.split("/", 1))
    if not provider_id or not model_id:
        raise ProviderError(
            "OpenCode model must include both provider and model IDs",
            kind="configuration",
            details={"expected_format": "provider/model"},
        )
    return provider_id, model_id


class OpenCodeProvider:
    """OpenCode local-server adapter for provider-qualified model IDs.

    OpenCode owns upstream provider authentication. This adapter only talks to
    the explicitly started local OpenCode server and never treats a ChatGPT or
    OpenCode credential as a generic model API key. The controller remains the
    only executor of registered research tools; the OpenCode session is denied
    tool permissions and is asked for one structured response.
    """

    name = "opencode"

    def __init__(
        self,
        *,
        model: str = "",
        server_url: str | None = None,
        repo_root: str | Path | None = None,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        configured_url = server_url or os.environ.get("OPENCODE_SERVER_URL", DEFAULT_OPENCODE_SERVER_URL)
        parsed = urlsplit(configured_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ProviderError("OpenCode server URL must be an http(s) URL", kind="configuration")
        if parsed.username is not None or parsed.password is not None:
            raise ProviderError("OpenCode server URL must not embed credentials", kind="configuration")
        self.model = model
        self.server_url = configured_url.rstrip("/")
        self.repo_root = Path(repo_root).resolve() if repo_root is not None else None
        self.username = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode")
        self.password = os.environ.get("OPENCODE_SERVER_PASSWORD")
        self._opener = opener or urlopen

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        model = request.model or self.model
        provider_id, model_id = _opencode_model_parts(model)
        output_mode = request.metadata.get("opencode_output_mode", "json_schema")
        if not isinstance(output_mode, str) or output_mode not in {"json_schema", "json_text"}:
            raise ProviderError("OpenCode output mode must be json_schema or json_text", kind="configuration")
        persist_session = request.metadata.get("persist_provider_session")
        if persist_session is not None and not callable(persist_session):
            raise ProviderError("OpenCode session persistence callback must be callable", kind="configuration")
        permissions = [{"permission": "*", "pattern": "*", "action": "deny"}]
        message_payload: dict[str, Any] = {
            "model": {"providerID": provider_id, "modelID": model_id},
            "variant": request.effort,
            "parts": [{"type": "text", "text": request.prompt}],
        }
        if output_mode == "json_schema":
            # OpenCode filters its injected schema-return tool through permissions.
            permissions.append({"permission": "StructuredOutput", "pattern": "*", "action": "allow"})
            message_payload["format"] = {"type": "json_schema", "schema": dict(request.schema), "retryCount": 0}
        deadline = time.monotonic() + request.timeout_seconds
        session = self._request_json(
            "POST",
            "/session",
            payload={
                "title": f"btc-ai-pipeline-{request.role}-{request.phase}",
                "permission": permissions,
            },
            query=self._directory_query(),
            timeout=self._remaining(deadline),
        )
        session_id = session.get("id") if isinstance(session, dict) else None
        if not isinstance(session_id, str) or not re.fullmatch(r"ses[A-Za-z0-9_-]+", session_id):
            raise ProviderError(
                "OpenCode returned an invalid session ID",
                kind="provider_contract",
                details={"response_shape": "session.id"},
            )
        identity = {"provider": self.name, "session_id": session_id, "server_url": self.server_url}
        if persist_session is not None:
            try:
                persist_session(dict(identity))
            except Exception as exc:
                raise ProviderError(
                    "OpenCode session persistence failed before model dispatch",
                    kind="session_persistence",
                    retryable=True,
                    details={**identity, "provider_call_performed": False, "exception_type": type(exc).__name__},
                ) from exc
        try:
            remaining = self._remaining(deadline)
        except ProviderError as exc:
            exc.details.update(identity, provider_call_performed=False)
            raise
        try:
            response = self._request_json(
                "POST",
                f"/session/{session_id}/message",
                payload=message_payload,
                query=self._directory_query(),
                timeout=remaining,
                session_id=session_id,
            )
        except ProviderError as exc:
            exc.details.update(identity, provider_call_performed=True)
            status = exc.details.get("http_status", 0)
            if exc.kind in {"timeout", "provider_connect"} or status == 408 or status >= 500:
                self._handle_interrupted_request(exc, session_id)
            raise
        try:
            return self._response_from_message(response, request=request, session_id=session_id,
                                               provider_id=provider_id, model_id=model_id, output_mode=output_mode)
        except ProviderError as exc:
            exc.details.update(identity, provider_call_performed=True)
            raise

    def _handle_interrupted_request(self, error: ProviderError, session_id: str) -> None:
        """Spend one bounded cleanup request before classifying external state."""
        abort: dict[str, Any] = {
            "attempted": True,
            "confirmed": False,
            "timeout_seconds": OPENCODE_ABORT_TIMEOUT_SECONDS,
        }
        try:
            response = self._request_json(
                "POST", f"/session/{session_id}/abort",
                query=self._directory_query(),
                timeout=OPENCODE_ABORT_TIMEOUT_SECONDS,
                session_id=session_id,
                allow_boolean=True,
            )
            # The documented abort contract returns a JSON boolean. A 2xx
            # status alone, an empty body, or a truthy object is not proof.
            abort["confirmed"] = response is True
        except ProviderError as exc:
            abort["error_kind"] = exc.kind
        error.details.update(abort=abort, manual_reconciliation_required=not abort["confirmed"])
        if not abort["confirmed"]:
            raise ProviderError(
                "OpenCode model dispatch was interrupted and cancellation could not be confirmed",
                kind="interrupted_uncertain",
                retryable=True,
                details={**error.details, "original_error_kind": error.kind},
            ) from error

    def preflight(
        self,
        *,
        effort: str = "medium",
        context_budget: int | None = None,
        output_budget: int | None = None,
        timeout_seconds: float | None = None,
        output_mode: str = "json_schema",
    ) -> dict[str, Any]:
        """Probe only local server/catalog state; this never invokes a model."""

        timeout = max(0.1, float(timeout_seconds or 5.0))
        result: dict[str, Any] = {
            "provider": self.name,
            "model_configured": bool(self.model and self.model != "unset"),
            "server_url": self.server_url,
            "server_reachable": False,
            "provider_connected": False,
            "model_available": False,
            "model_id": self.model,
            "model_metadata": None,
            "live_call_performed": False,
        }
        try:
            health = self._request_json("GET", "/global/health", timeout=timeout)
        except ProviderError as exc:
            result["error"] = {"kind": exc.kind, "message": _diagnostic_text(str(exc))}
            result["controls"] = self._controls(effort, context_budget, output_budget, timeout_seconds, effort_supported=False, output_mode=output_mode)
            result["notes"] = "OpenCode local server is not reachable; no model call was attempted"
            return result
        result["server_reachable"] = health.get("healthy") is True
        try:
            provider_id, model_id = _opencode_model_parts(self.model)
        except ProviderError as exc:
            result["error"] = {"kind": exc.kind, "message": _diagnostic_text(str(exc))}
            result["controls"] = self._controls(effort, context_budget, output_budget, timeout_seconds, effort_supported=False, output_mode=output_mode)
            result["notes"] = "OpenCode server is reachable, but the configured model ID is invalid"
            return result
        try:
            catalog = self._request_json("GET", "/provider", timeout=timeout)
        except ProviderError as exc:
            result["error"] = {"kind": exc.kind, "message": _diagnostic_text(str(exc))}
            result["controls"] = self._controls(effort, context_budget, output_budget, timeout_seconds, effort_supported=False, output_mode=output_mode)
            result["notes"] = "OpenCode health succeeded but provider catalog inspection failed; no model call was attempted"
            return result
        connected = catalog.get("connected", []) if isinstance(catalog, dict) else []
        result["provider_connected"] = provider_id in connected if isinstance(connected, list) else False
        providers = catalog.get("all", []) if isinstance(catalog, dict) else []
        entry = next((item for item in providers if isinstance(item, dict) and item.get("id") == provider_id), None) if isinstance(providers, list) else None
        models = entry.get("models", {}) if isinstance(entry, dict) else {}
        model_info = models.get(model_id) if isinstance(models, dict) else None
        result["model_available"] = isinstance(model_info, dict)
        if isinstance(model_info, dict):
            variants = model_info.get("variants", {})
            variant_names = sorted(variants) if isinstance(variants, dict) else []
            limits = model_info.get("limit", {})
            capabilities = model_info.get("capabilities", {})
            result["model_metadata"] = {
                "provider_id": provider_id,
                "model_id": model_id,
                "name": model_info.get("name"),
                "variants": variant_names,
                "reasoning": capabilities.get("reasoning") if isinstance(capabilities, dict) else None,
                "toolcall": capabilities.get("toolcall") if isinstance(capabilities, dict) else None,
                "context_limit": limits.get("context") if isinstance(limits, dict) else None,
                "output_limit": limits.get("output") if isinstance(limits, dict) else None,
            }
            effort_supported = not variant_names or effort in variant_names
        else:
            effort_supported = False
        result["controls"] = self._controls(effort, context_budget, output_budget, timeout_seconds, effort_supported=effort_supported, output_mode=output_mode)
        if not result["provider_connected"]:
            result["notes"] = "OpenCode server is reachable, but the configured provider is not connected; no model call was attempted"
        elif not result["model_available"]:
            result["notes"] = "OpenCode provider is connected, but the configured model is unavailable; no model call was attempted"
        elif not effort_supported:
            result["notes"] = "OpenCode model is available, but the requested variant is not listed; no model call was attempted"
        else:
            result["notes"] = "OpenCode server, provider connection, model ID, and requested variant are available; no model call was attempted"
        return result

    @overload
    def _request_json(
        self, method: str, path: str, *,
        payload: Mapping[str, Any] | None = None,
        query: Mapping[str, str] | None = None,
        timeout: float, session_id: str | None = None,
        allow_boolean: Literal[False] = False,
    ) -> dict[str, Any]: ...

    @overload
    def _request_json(
        self, method: str, path: str, *,
        payload: Mapping[str, Any] | None = None,
        query: Mapping[str, str] | None = None,
        timeout: float, session_id: str | None = None,
        allow_boolean: Literal[True],
    ) -> dict[str, Any] | bool: ...

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        query: Mapping[str, str] | None = None,
        timeout: float,
        session_id: str | None = None,
        allow_boolean: bool = False,
    ) -> dict[str, Any] | bool:
        url = self.server_url + path
        if query:
            url += "?" + urlencode(query)
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json", "User-Agent": "rsi-bot-btc-ai-pipeline/1"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if session_id:
            headers["x-opencode-session"] = session_id
        if self.password is not None:
            credentials = b64encode(f"{self.username}:{self.password}".encode()).decode("ascii")
            headers["Authorization"] = f"Basic {credentials}"
        request = Request(url, data=body, headers=headers, method=method)
        try:
            response = self._opener(request, timeout=max(0.01, timeout))
            try:
                status_value = getattr(response, "status", None)
                if status_value is None:
                    getcode = getattr(response, "getcode", None)
                    status_value = getcode() if callable(getcode) else 200
                status = int(status_value or 200)
                raw = response.read(OPENCODE_RESPONSE_LIMIT_BYTES + 1)
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
        except HTTPError as exc:
            try:
                raw_error = exc.read(OPENCODE_RESPONSE_LIMIT_BYTES + 1)
            except (OSError, HTTPException):
                raw_error = b""
            body_error = raw_error.decode("utf-8", errors="replace") if isinstance(raw_error, bytes) else str(raw_error)
            details = _opencode_error_details(exc.code, body_error)
            kind = _opencode_failure_kind(exc.code, details)
            raise ProviderError(
                _opencode_error_message(kind, exc.code, details),
                kind=kind,
                retryable=kind in {"rate_limit", "auth", "provider_exit"},
                details=details,
            ) from exc
        except TimeoutError as exc:
            raise ProviderError("OpenCode request timed out", kind="timeout", retryable=True, details={"timeout_seconds": timeout, "server_url": self.server_url}) from exc
        except URLError as exc:
            reason = str(getattr(exc, "reason", exc))
            if re.search(r"(?i)timed out|timeout", reason):
                raise ProviderError("OpenCode request timed out", kind="timeout", retryable=True, details={"timeout_seconds": timeout, "server_url": self.server_url}) from exc
            raise ProviderError("OpenCode server could not be reached", kind="provider_connect", retryable=True, details={"server_url": self.server_url, "reason": _diagnostic_text(reason)}) from exc
        except (OSError, HTTPException) as exc:
            raise ProviderError("OpenCode request could not be completed", kind="provider_connect", retryable=True, details={"server_url": self.server_url, "exception_type": type(exc).__name__}) from exc
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        if not isinstance(raw, bytes):
            raise ProviderError("OpenCode returned an invalid response body", kind="provider_contract")
        if len(raw) > OPENCODE_RESPONSE_LIMIT_BYTES:
            raise ProviderError("OpenCode response exceeded the adapter capture limit", kind="response_too_large", details={"limit_bytes": OPENCODE_RESPONSE_LIMIT_BYTES})
        if status >= 400:
            body_error = raw.decode("utf-8", errors="replace")
            details = _opencode_error_details(status, body_error)
            kind = _opencode_failure_kind(status, details)
            raise ProviderError(
                _opencode_error_message(kind, status, details),
                kind=kind,
                retryable=kind in {"rate_limit", "auth", "provider_exit"},
                details=details,
            )
        if status == 204 or not raw.strip():
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderError("OpenCode returned a non-JSON response", kind="malformed_json") from exc
        if allow_boolean and isinstance(parsed, bool):
            return parsed
        if not isinstance(parsed, dict):
            raise ProviderError("OpenCode returned a non-object JSON response", kind="malformed_json")
        return parsed

    def _response_from_message(
        self,
        response: Mapping[str, Any],
        *,
        request: ProviderRequest,
        session_id: str,
        provider_id: str,
        model_id: str,
        output_mode: str = "json_schema",
    ) -> ProviderResponse:
        info = response.get("info") if isinstance(response.get("info"), dict) else {}
        error = info.get("error") if isinstance(info, dict) else None
        if isinstance(error, dict):
            details = _opencode_named_error_details(error)
            diagnostic = details["provider_error"]
            name = diagnostic.get("name") or diagnostic.get("type") or "an error"
            message = diagnostic.get("message") or name
            kind = _opencode_failure_kind(details.get("http_status", 0), details)
            raise ProviderError(f"OpenCode assistant returned {name}: {message}", kind=kind,
                                retryable=kind in {"auth", "rate_limit", "provider_exit"},
                                details={**details, "session_id": session_id})
        payload = self._json_text_payload(response) if output_mode == "json_text" else self._structured_payload(response)
        if payload is None:
            part_types = [part.get("type") for part in response.get("parts", []) if isinstance(part, dict)] if isinstance(response.get("parts"), list) else []
            raise ProviderError("OpenCode returned no structured JSON object", kind="malformed_json", details={"session_id": session_id, "part_types": part_types})
        reported_provider = info.get("providerID") if isinstance(info, dict) else None
        reported_model_id = info.get("modelID") if isinstance(info, dict) else None
        reported_model: str | None = None
        if isinstance(reported_provider, str) and isinstance(reported_model_id, str):
            reported_model = reported_model_id if "/" in reported_model_id else f"{reported_provider}/{reported_model_id}"
        elif isinstance(reported_model_id, str):
            reported_model = reported_model_id
        tokens = self._usage_tokens(info.get("tokens") if isinstance(info, dict) else None)
        usage: dict[str, Any] = {
            "runtime": tokens,
            "usage_available": tokens is not None,
            "usage_note": "OpenCode AssistantMessage.info.tokens" if tokens is not None else "OpenCode response did not expose token usage",
            "session_id": session_id,
        }
        cost = info.get("cost") if isinstance(info, dict) else None
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            usage["runtime_cost"] = cost
        controls = self._controls(request.effort, request.context_budget, request.output_budget,
                                  request.timeout_seconds, effort_supported=True, output_mode=output_mode)
        if isinstance(info, dict) and isinstance(info.get("variant"), str):
            reported_variant = info["variant"]
            controls["effort"]["reported_variant"] = reported_variant
            controls["effort"]["reported_match"] = reported_variant == request.effort
            if reported_variant != request.effort:
                raise ProviderError(
                    "OpenCode reported a different reasoning variant than requested",
                    kind="provider_contract",
                    details={
                        "session_id": session_id,
                        "requested_variant": request.effort,
                        "reported_variant": reported_variant,
                        "provider_call_performed": True,
                    },
                )
        return ProviderResponse(payload=payload, provider=self.name, model=request.model or self.model, reported_model=reported_model, usage=usage, controls=controls, raw_excerpt=None)

    @staticmethod
    def _json_text_payload(response: Mapping[str, Any]) -> dict[str, Any] | None:
        """Parse the complete text response once, without structured-field shortcuts."""
        parts = response.get("parts")
        if not isinstance(parts, list):
            return None
        texts = []
        for part in parts:
            if isinstance(part, dict) and part.get("type") == "text":
                if not isinstance(part.get("text"), str):
                    return None
                texts.append(part["text"])

        def reject_constant(_value: str) -> None:
            raise ValueError("Non-finite constants are not JSON")

        def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate JSON object key")
                result[key] = value
            return result

        try:
            parsed = json.loads("".join(texts), parse_constant=reject_constant, object_pairs_hook=unique_object)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _structured_payload(response: Mapping[str, Any]) -> dict[str, Any] | None:
        info = response.get("info") if isinstance(response.get("info"), dict) else {}
        for container in (info, response):
            for key in ("structured", "structured_output", "structuredOutput"):
                candidate = container.get(key) if isinstance(container, Mapping) else None
                if isinstance(candidate, dict) and candidate:
                    return candidate
                if isinstance(candidate, str):
                    try:
                        parsed = json.loads(candidate)
                    except json.JSONDecodeError:
                        parsed = None
                    if isinstance(parsed, dict):
                        return parsed
        parts = response.get("parts")
        if isinstance(parts, list):
            for part in parts:
                if not isinstance(part, dict) or part.get("type") != "text" or not isinstance(part.get("text"), str):
                    continue
                try:
                    parsed = json.loads(part["text"])
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
        return None

    @staticmethod
    def _usage_tokens(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        result: dict[str, Any] = {}
        for key in ("total", "input", "output", "reasoning"):
            item = value.get(key)
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                result[key] = item
        cache = value.get("cache")
        if isinstance(cache, dict):
            cache_result = {key: item for key, item in cache.items() if key in {"read", "write"} and isinstance(item, (int, float)) and not isinstance(item, bool)}
            if cache_result:
                result["cache"] = cache_result
        return result or None

    def _directory_query(self) -> dict[str, str] | None:
        return {"directory": str(self.repo_root)} if self.repo_root is not None else None

    @staticmethod
    def _remaining(deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderError("OpenCode request timed out", kind="timeout", retryable=True, details={"timeout_seconds": 0})
        return remaining

    @staticmethod
    def _controls(effort: str, context_budget: int | None, output_budget: int | None, timeout_seconds: float | None, *, effort_supported: bool, output_mode: str = "json_schema") -> dict[str, Any]:
        return {
            "structured_output": {"mode": output_mode, "provider_enforced": output_mode == "json_schema", "local_validation": True},
            "effort": {"requested": effort, "provider_supported": effort_supported, "enforced": effort_supported, "mechanism": "session.prompt.variant"},
            "context_budget": {"requested": context_budget, "provider_supported": False, "enforced": "controller_prompt_estimate", "provider_flag": False},
            "output_budget": {"requested": output_budget, "provider_supported": False, "enforced": "controller_response_estimate", "provider_flag": False},
            "timeout": {"requested_seconds": timeout_seconds, "provider_supported": True, "enforced": "overall_http_deadline", "owned_process_cleanup": False, "abort_cleanup_timeout_seconds": OPENCODE_ABORT_TIMEOUT_SECONDS},
        }


