"""Bounded, credential-safe diagnostic extraction shared by model adapters."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any


def _diagnostic_text(value: Any, limit: int = 1600) -> str:
    """Keep actionable errors without copying credentials into campaign logs."""

    text = str(value)
    text = re.sub(r"(?i)\b(Bearer|Basic)\s+[^\s\"'<>]+", r"\1 [REDACTED]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[REDACTED]", text)
    text = re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[REDACTED]", text)
    text = re.sub(
        r'''(?ix)(\b(?:[a-z0-9_]*api_key|access_token|refresh_token|id_token|password|authorization|client_secret|cookie)\b["']?\s*[:=]\s*)(["'])(.*?)\2''',
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(
        r'''(?ix)(\b(?:[a-z0-9_]*api_key|access_token|refresh_token|id_token|password|authorization|client_secret|cookie)\b["']?\s*[:=]\s*)(["']?)([^\s,"'}]+)''',
        r"\1[REDACTED]",
        text,
    )
    return text[:limit]


def _provider_failure_details(stdout: str, stderr: str) -> dict[str, Any]:
    """Extract error events only; assistant output and prompts are not diagnostics."""

    details: dict[str, Any] = {"stderr_present": bool(stderr), "stdout_present": bool(stdout)}
    errors: list[dict[str, Any]] = []

    def extract(value: Any, stream: str, depth: int = 0) -> None:
        if not isinstance(value, dict) or depth > 3:
            return
        event_type = value.get("type")
        if event_type == "thread.started" and isinstance(value.get("thread_id"), str):
            if re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", value["thread_id"]):
                details["provider_thread_id"] = value["thread_id"]
            return
        if event_type not in {"error", "turn.failed", "invalid_request_error"} and not isinstance(value.get("error"), dict):
            return
        nested_error = value.get("error")
        error = nested_error if isinstance(nested_error, dict) else value
        message = error.get("message")
        if isinstance(message, str):
            try:
                nested = json.loads(message)
            except json.JSONDecodeError:
                nested = None
            if isinstance(nested, dict) and isinstance(nested.get("error"), dict):
                extract(nested, stream, depth + 1)
                return
        record: dict[str, Any] = {key: _diagnostic_text(error[key]) for key in ("type", "code", "param", "message") if isinstance(error.get(key), str)}
        status = value.get("status", error.get("status"))
        if isinstance(status, int) and not isinstance(status, bool):
            record["http_status"] = status
        record["stream"] = stream
        if record not in errors and any(key in record for key in ("code", "message")):
            errors.append(record)

    for stream, text in (("stdout", stdout), ("stderr", stderr)):
        try:
            extract(json.loads(text), stream)
        except json.JSONDecodeError:
            pass
        for line in text.splitlines():
            try:
                extract(json.loads(line), stream)
            except json.JSONDecodeError:
                continue
    if errors:
        # A structured service code is more useful than a generic CLI message.
        details["provider_error"] = next((error for error in reversed(errors) if error.get("code")), errors[-1])
    else:
        lines = [line for line in stderr.splitlines() if re.search(r"(?i)\b(error|failed|invalid|denied|unauthorized|forbidden)\b|not found", line)]
        if lines:
            details["stderr_diagnostic"] = _diagnostic_text("\n".join(lines[-4:]))
    return details


def _provider_failure_kind(details: Mapping[str, Any]) -> str:
    error = details.get("provider_error", {})
    code = error.get("code") if isinstance(error, dict) else None
    status = error.get("http_status") if isinstance(error, dict) else None
    text = str(error.get("message", "") if isinstance(error, dict) else "") + " " + str(details.get("stderr_diagnostic", ""))
    if code == "invalid_json_schema":
        return "invalid_schema"
    if status == 429 or code in {"rate_limit_exceeded", "insufficient_quota"} or re.search(r"(?i)\brate[ -]limit|\b429\b", text):
        return "rate_limit"
    if status in {401, 403} or code in {"invalid_api_key", "authentication_error"} or re.search(r"(?i)\b(auth(?:entication)?|login|unauthorized)\b", text):
        return "auth"
    if code == "model_not_found":
        return "model_access"
    if status == 400 or code == "invalid_request_error":
        return "invalid_request"
    return "provider_exit"


def _opencode_named_error_details(error: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize NamedError.data using only bounded diagnostic fields.

    Response/request headers and request bodies are never copied. A small
    responseBody may supply parsed error fields; its raw contents are discarded.
    The upstream retry flag is informational, not permission to retry a call.
    """
    record: dict[str, Any] = {}
    nested = error.get("data")
    data = nested if isinstance(nested, dict) else {}
    for container in (error, data):
        for key in ("type", "name", "code", "param", "message"):
            value = container.get(key)
            if isinstance(value, str) and value.strip() and (key != "name" or key not in record):
                record[key] = _diagnostic_text(value)
    raw_body = data.get("responseBody")
    if isinstance(raw_body, str) and len(raw_body) <= 65536:
        try:
            parsed_body = json.loads(raw_body)
        except json.JSONDecodeError:
            parsed_body = None
        if isinstance(parsed_body, dict):
            nested_body = parsed_body.get("error")
            body_error = nested_body if isinstance(nested_body, dict) else parsed_body
            for key in ("type", "code", "param", "message"):
                value = body_error.get(key)
                if isinstance(value, str) and value.strip():
                    record[key] = _diagnostic_text(value)
    details: dict[str, Any] = {"provider_error": record}
    status = data.get("statusCode", error.get("statusCode"))
    if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
        details["http_status"] = status
    retryable = data.get("isRetryable", error.get("isRetryable"))
    if isinstance(retryable, bool):
        details["provider_retryable"] = retryable
    return details


def _opencode_error_details(status: int, body: str) -> dict[str, Any]:
    """Extract bounded, credential-safe fields from an OpenCode HTTP error."""

    details: dict[str, Any] = {"http_status": status, "response_present": bool(body)}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = None
    if not isinstance(parsed, dict):
        return details
    error = parsed.get("error") if isinstance(parsed.get("error"), dict) else parsed
    if not isinstance(error, dict):
        return details
    extracted = _opencode_named_error_details(error)
    if "http_status" in extracted:
        details["provider_http_status"] = extracted.pop("http_status")
    details.update(extracted)
    return details


def _opencode_failure_kind(status: int, details: Mapping[str, Any]) -> str:
    error = details.get("provider_error", {})
    code = error.get("code") if isinstance(error, dict) else None
    text = " ".join(
        str(error.get(key, "")) for key in ("type", "name", "code", "message")
    ) if isinstance(error, dict) else ""
    status = details.get("provider_http_status", status)
    name = str(error.get("name", "")).lower() if isinstance(error, dict) else ""
    if "structured" in name or "output" in name:
        return "malformed_json"
    if "context" in name or code == "context_length_exceeded":
        return "context_budget_exceeded"
    if status == 429 or code in {"rate_limit_exceeded", "rate_limit", "insufficient_quota"} or re.search(r"(?i)rate[ -]?limit|\b429\b", text):
        return "rate_limit"
    if code in {"unsupported_country_region_territory", "unsupported_region", "region_restricted", "unsupported_country"} or re.search(
        r"(?i)(?:country|region|territor\w*).{0,80}(?:not supported|unsupported|not available|blocked|restricted)|"
        r"(?:unsupported|blocked|restricted).{0,80}(?:country|region|territor\w*)", text,
    ):
        return "region_restriction"
    if status in {401, 403} or code in {"invalid_api_key", "authentication_error"}:
        return "auth"
    if status == 404 or code in {"model_not_found", "provider_not_found"} or re.search(r"(?i)model.*not found|provider.*not found", text):
        return "model_access"
    if status == 400 or code in {"invalid_request_error", "invalid_request", "unsupported_parameter"}:
        return "invalid_request"
    if re.search(r"(?i)auth|unauthorized|forbidden|credential|login", text):
        return "auth"
    return "provider_exit"


def _opencode_error_message(kind: str, status: int, details: Mapping[str, Any]) -> str:
    error = details.get("provider_error", {})
    diagnostic = error.get("message") if isinstance(error, dict) else None
    message = f"OpenCode server returned status {status} ({kind})"
    if isinstance(diagnostic, str) and diagnostic:
        message += f": {diagnostic}"
    return message


