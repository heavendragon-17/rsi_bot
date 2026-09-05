"""Runtime model provider contracts.

The controller only receives structured JSON from this module. Research tools
are never selected by shell prose from a model response.
"""

from __future__ import annotations

import json
import os
import re
import signal
import socket
import shutil
import subprocess
import time
from base64 import b64encode
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .contracts import (
    EXECUTION_SCHEMA,
    PROPOSAL_SCHEMA,
    REVIEW_SCHEMA,
    M5_VERIFICATION_TASK,
    SUPPORTED_CODEX_EFFORTS,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    UnsupportedProviderError,
)


DEFAULT_OPENCODE_SERVER_URL = "http://127.0.0.1:4096"
OPENCODE_RESPONSE_LIMIT_BYTES = 16 * 1024 * 1024
OPENCODE_TOOL_PERMISSIONS = (
    "read",
    "edit",
    "glob",
    "grep",
    "list",
    "bash",
    "task",
    "external_directory",
    "todowrite",
    "todoread",
    "webfetch",
    "websearch",
    "lsp",
    "skill",
    "question",
    "doom_loop",
)


def _diagnostic_text(value: Any, limit: int = 1600) -> str:
    """Keep actionable errors without copying credentials into campaign logs."""

    text = str(value)
    text = re.sub(r"(?i)\bBearer\s+[^\s\"'<>]+", "Bearer [REDACTED]", text)
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
        error = value.get("error") if isinstance(value.get("error"), dict) else value
        message = error.get("message")
        if isinstance(message, str):
            try:
                nested = json.loads(message)
            except json.JSONDecodeError:
                nested = None
            if isinstance(nested, dict) and isinstance(nested.get("error"), dict):
                extract(nested, stream, depth + 1)
                return
        record = {key: _diagnostic_text(error[key]) for key in ("type", "code", "param", "message") if isinstance(error.get(key), str)}
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


def _proposal(*, mode: str = "fixture", parent_result_id: str | None = None) -> dict[str, Any]:
    params = {"mode": mode, "event_index": 0}
    return {
        "schema": PROPOSAL_SCHEMA,
        "title": "Verify one existing BTC M5 horizon result",
        "hypothesis": "The saved M5 event has the same exact 1h, 2h, and 3h close-to-close outcomes when recomputed from frozen candles.",
        "question": "Does one frozen M5 event preserve its saved trigger identity and exact 1h/2h/3h targets under independent arithmetic?",
        "rationale": "A bounded identity and arithmetic check is the first safe research job; it makes no new alpha claim.",
        "expected_evidence": ["source hash", "event identity", "exact target timestamps", "recomputed returns", "checker status"],
        "task": M5_VERIFICATION_TASK,
        "parameters": params,
        "invariants": ["use frozen BTC evidence", "check 1h, 2h, and 3h", "do not change strategy or data", "no model shell execution"],
        "stop_conditions": ["stop after one bounded job", "stop on verified evidence or unrecoverable restriction"],
        "falsification_conditions": ["source identity differs", "target timestamp or price differs", "required evidence is missing"],
        **({"parent_result_id": parent_result_id} if parent_result_id else {}),
    }


@dataclass
class FixtureProvider:
    """Deterministic provider used by the offline demonstration and tests."""

    role: str
    branch: str = "stop"
    failure: str | None = None
    name: str = "fixture"

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        if self.failure and request.phase == self.failure.split(":", 1)[-1]:
            kind = self.failure.split(":", 1)[0]
            raise ProviderError(f"fixture {kind} failure", kind=kind, retryable=kind in {"timeout", "rate_limit", "auth"})
        if request.phase == "proposal":
            payload = _proposal(mode=str(request.metadata.get("verification_mode", "fixture")), parent_result_id=request.metadata.get("parent_result_id"))
        elif request.phase == "execution":
            proposal = request.metadata.get("proposal", {})
            payload = {
                "schema": EXECUTION_SCHEMA,
                "task": proposal.get("task", M5_VERIFICATION_TASK),
                "tool": M5_VERIFICATION_TASK,
                "parameters": dict(proposal.get("parameters", {"mode": "fixture", "event_index": 0})),
                "invariants": list(proposal.get("invariants", [])),
                "workspace_manifest": "fixture_manifest.json",
            }
        elif request.phase == "review":
            evidence = request.metadata.get("evidence", {})
            status = evidence.get("verification", {}).get("status", evidence.get("status"))
            if status != "VERIFIED":
                action = "REJECT" if self.branch == "reject" else "REPAIR"
                payload = {"schema": REVIEW_SCHEMA, "action": action, "reasons": ["deterministic checker did not verify the current evidence"], "evidence_refs": [str(evidence.get("result_id", "unknown"))]}
            elif self.branch == "next":
                next_job = _proposal(mode="fixture", parent_result_id=str(evidence.get("result_id")))
                next_job["title"] = "Follow-up bounded evidence review"
                payload = {"schema": REVIEW_SCHEMA, "action": "PROPOSE_NEXT", "reasons": ["current result is verified; record a bounded follow-up without executing it in this milestone"], "evidence_refs": [str(evidence.get("result_id"))], "next_job": next_job}
            else:
                payload = {"schema": REVIEW_SCHEMA, "action": "STOP", "reasons": ["current result is verified and the MVP limit is reached"], "evidence_refs": [str(evidence.get("result_id"))]}
        else:
            raise ProviderError(f"unknown fixture phase {request.phase}", kind="provider_contract")
        return ProviderResponse(
            payload=payload,
            provider=self.name,
            model=request.model,
            usage={"fixture": True, "input_tokens": None, "output_tokens": None, "usage_available": False, "usage_note": "deterministic fixture; no model call"},
            controls={
                "effort": {"requested": request.effort, "provider_supported": False, "enforced": False, "note": "fixture provider does not run a model"},
                "context_budget": {"requested": request.context_budget, "provider_supported": False, "enforced": False},
                "output_budget": {"requested": request.output_budget, "provider_supported": False, "enforced": False},
                "timeout": {"requested_seconds": request.timeout_seconds, "provider_supported": False, "enforced": False},
            },
            raw_excerpt=None,
        )


def terminate_process_tree(process: Any) -> dict[str, Any]:
    """Best-effort cleanup for the process group owned by one Codex call."""

    pid = getattr(process, "pid", None)
    details: dict[str, Any] = {"attempted": True, "pid": pid, "descendants": True, "method": "process_group"}
    if not isinstance(pid, int):
        details["completed"] = False
        details["note"] = "provider process did not expose a PID"
        return details
    if os.name == "nt":
        try:
            completed = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=5, check=False)  # nosec B603: fixed taskkill argv
            details["completed"] = completed.returncode == 0
            details["command_returncode"] = completed.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            details["completed"] = False
            details["error"] = type(exc).__name__
    else:
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            details["completed"] = True
        except (OSError, ProcessLookupError) as exc:
            details["completed"] = False
            details["error"] = type(exc).__name__
    return details


class CodexCLIProvider:
    """Codex non-interactive structured-output adapter.

    It deliberately uses argv execution with a read-only sandbox. The adapter
    is opt-in and never runs in the default offline command.
    """

    name = "codex"

    def __init__(self, *, model: str, binary: str = "codex", cwd: str | Path | None = None) -> None:
        self.model = model
        self.binary = binary
        self.cwd = str(cwd) if cwd else None

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        if not self.model or self.model == "unset":
            raise ProviderError("Codex model is not configured", kind="configuration")
        if request.effort not in SUPPORTED_CODEX_EFFORTS:
            raise ProviderError(f"unsupported Codex reasoning effort: {request.effort}", kind="configuration", details={"supported_efforts": sorted(SUPPORTED_CODEX_EFFORTS)})
        schema_raw = request.metadata.get("schema_path")
        if not isinstance(schema_raw, str) or not schema_raw:
            raise ProviderError("Codex structured-output schema path is missing", kind="configuration")
        schema_path = Path(schema_raw)
        prompt = request.prompt
        argv = [self.binary, "exec", "--sandbox", "read-only", "--output-schema", str(schema_path), "--json", "--model", self.model, "-c", f'model_reasoning_effort="{request.effort}"', prompt]
        try:
            stdout, stderr, returncode, cleanup = self._run_bounded(argv, request.timeout_seconds, cwd=self.cwd)
        except FileNotFoundError as exc:
            raise ProviderError(f"Codex executable not found: {self.binary}", kind="missing_executable", details={"executable": self.binary}) from exc
        except subprocess.TimeoutExpired as exc:
            raise ProviderError("Codex invocation timed out", kind="timeout", retryable=True, details={"timeout_seconds": request.timeout_seconds, "owned_process_cleanup": getattr(exc, "cleanup", None)}) from exc
        except OSError as exc:
            raise ProviderError("Codex process could not be started", kind="provider_spawn", retryable=True, details={"exception_type": type(exc).__name__}) from exc
        if returncode != 0:
            details = {"exit_code": returncode, **_provider_failure_details(stdout, stderr)}
            kind = _provider_failure_kind(details)
            diagnostic = details.get("provider_error", {}).get("message") or details.get("stderr_diagnostic")
            message = f"Codex exited with status {returncode} ({kind})"
            if diagnostic:
                message += f": {diagnostic}"
            raise ProviderError(message, kind=kind, retryable=kind in {"rate_limit", "auth"}, details=details)
        payload, runtime = self._parse_jsonl_with_metadata(stdout)
        runtime_usage = runtime.get("usage")
        usage_available = isinstance(runtime_usage, dict)
        usage = {
            "runtime": runtime_usage if usage_available else None,
            "usage_available": usage_available,
            "usage_note": "Codex turn.completed usage" if usage_available else "Codex JSONL did not expose token usage",
            "exit_code": returncode,
        }
        controls = {
            "effort": {"requested": request.effort, "provider_supported": True, "enforced": True, "mechanism": "-c model_reasoning_effort"},
            "context_budget": {"requested": request.context_budget, "provider_supported": False, "enforced": "controller_prompt_estimate", "note": "Codex exec has no per-call context-budget flag in the installed CLI"},
            "output_budget": {"requested": request.output_budget, "provider_supported": False, "enforced": "controller_response_estimate", "note": "Codex exec has no per-call output-token flag in the installed CLI"},
            "timeout": {"requested_seconds": request.timeout_seconds, "provider_supported": True, "enforced": True, "owned_process_cleanup": True, "cleanup": cleanup},
        }
        return ProviderResponse(payload=payload, provider=self.name, model=self.model, reported_model=runtime.get("reported_model"), usage=usage, controls=controls, raw_excerpt=stdout[-1000:])

    @staticmethod
    def _run_bounded(argv: list[str], timeout_seconds: float, *, cwd: str | None = None) -> tuple[str, str, int, dict[str, Any] | None]:
        kwargs: dict[str, Any] = {"cwd": cwd, "stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(argv, **kwargs)  # nosec B603: argv contains fixed subcommand/options and a configured prompt
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            cleanup = terminate_process_tree(process)
            try:
                stdout, stderr = process.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except OSError:
                    # The descendant cleanup may already have terminated the
                    # root process between communicate calls.
                    pass
                stdout, stderr = process.communicate()
            error = subprocess.TimeoutExpired(exc.cmd, exc.timeout, output=stdout, stderr=stderr)
            error.cleanup = cleanup  # type: ignore[attr-defined]
            raise error
        return stdout or "", stderr or "", int(process.returncode), None

    @staticmethod
    def _parse_jsonl(stdout: str) -> Mapping[str, Any]:
        payload, _ = CodexCLIProvider._parse_jsonl_with_metadata(stdout)
        return payload

    @staticmethod
    def _parse_jsonl_with_metadata(stdout: str) -> tuple[Mapping[str, Any], dict[str, Any]]:
        candidates: list[Any] = []
        metadata: dict[str, Any] = {}
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                if isinstance(event.get("usage"), dict):
                    metadata["usage"] = event["usage"]
                for key in ("model", "model_id", "modelId"):
                    if isinstance(event.get(key), str) and event[key].strip():
                        metadata["reported_model"] = event[key]
                item = event.get("item")
                if isinstance(item, dict) and item.get("type") in {"agent_message", "assistant_message"}:
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        try:
                            candidates.append(json.loads(text))
                        except json.JSONDecodeError:
                            pass
                    for key in ("model", "model_id", "modelId"):
                        if isinstance(item.get(key), str) and item[key].strip():
                            metadata["reported_model"] = item[key]
                if event.get("type") in {"final", "result"} and isinstance(event.get("result"), dict):
                    candidates.append(event["result"])
                if "schema" in event:
                    candidates.append(event)
        if len(candidates) == 1 and isinstance(candidates[0], dict):
            return candidates[0], metadata
        if candidates and isinstance(candidates[-1], dict):
            return candidates[-1], metadata
        try:
            direct = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ProviderError("Codex returned no JSON object", kind="malformed_json") from exc
        if not isinstance(direct, dict):
            raise ProviderError("Codex returned non-object JSON", kind="malformed_json")
        return direct, metadata


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


def _opencode_error_details(status: int, body: str) -> dict[str, Any]:
    """Extract bounded, credential-safe fields from an OpenCode error response."""

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
    for key in ("type", "name", "code", "param", "message"):
        value = error.get(key)
        if isinstance(value, str) and value.strip():
            details.setdefault("provider_error", {})[key] = _diagnostic_text(value)
    nested = error.get("data")
    if isinstance(nested, dict):
        for key in ("code", "param", "message", "name"):
            value = nested.get(key)
            if isinstance(value, str) and value.strip():
                details.setdefault("provider_error", {}).setdefault(key, _diagnostic_text(value))
    return details


def _opencode_failure_kind(status: int, details: Mapping[str, Any]) -> str:
    error = details.get("provider_error", {})
    code = error.get("code") if isinstance(error, dict) else None
    text = " ".join(
        str(error.get(key, "")) for key in ("type", "name", "code", "message")
    ) if isinstance(error, dict) else ""
    if status == 429 or code in {"rate_limit_exceeded", "rate_limit"} or re.search(r"(?i)rate[ -]?limit|\b429\b", text):
        return "rate_limit"
    if status in {401, 403} or re.search(r"(?i)auth|unauthorized|forbidden|credential|login", text):
        return "auth"
    if status == 404 or code in {"model_not_found", "provider_not_found"} or re.search(r"(?i)model.*not found|provider.*not found", text):
        return "model_access"
    if status == 400 or code in {"invalid_request_error", "invalid_request"}:
        return "invalid_request"
    if status >= 500:
        return "provider_exit"
    return "provider_exit"


def _opencode_error_message(kind: str, status: int, details: Mapping[str, Any]) -> str:
    error = details.get("provider_error", {})
    diagnostic = error.get("message") if isinstance(error, dict) else None
    message = f"OpenCode server returned status {status} ({kind})"
    if isinstance(diagnostic, str) and diagnostic:
        message += f": {diagnostic}"
    return message


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
        deadline = time.monotonic() + request.timeout_seconds
        session = self._request_json(
            "POST",
            "/session",
            payload={
                "title": f"btc-ai-pipeline-{request.role}-{request.phase}",
                "permission": [
                    {"permission": permission, "pattern": "*", "action": "deny"}
                    for permission in OPENCODE_TOOL_PERMISSIONS
                ],
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
        response = self._request_json(
            "POST",
            f"/session/{session_id}/message",
            payload={
                "model": {"providerID": provider_id, "modelID": model_id},
                "variant": request.effort,
                "format": {"type": "json_schema", "schema": dict(request.schema), "retryCount": 0},
                "parts": [{"type": "text", "text": request.prompt}],
            },
            query=self._directory_query(),
            timeout=self._remaining(deadline),
            session_id=session_id,
        )
        return self._response_from_message(response, request=request, session_id=session_id, provider_id=provider_id, model_id=model_id)

    def preflight(
        self,
        *,
        effort: str = "medium",
        context_budget: int | None = None,
        output_budget: int | None = None,
        timeout_seconds: float | None = None,
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
            result["controls"] = self._controls(effort, context_budget, output_budget, timeout_seconds, effort_supported=False)
            result["notes"] = "OpenCode local server is not reachable; no model call was attempted"
            return result
        result["server_reachable"] = health.get("healthy") is True
        try:
            provider_id, model_id = _opencode_model_parts(self.model)
        except ProviderError as exc:
            result["error"] = {"kind": exc.kind, "message": _diagnostic_text(str(exc))}
            result["controls"] = self._controls(effort, context_budget, output_budget, timeout_seconds, effort_supported=False)
            result["notes"] = "OpenCode server is reachable, but the configured model ID is invalid"
            return result
        try:
            catalog = self._request_json("GET", "/provider", timeout=timeout)
        except ProviderError as exc:
            result["error"] = {"kind": exc.kind, "message": _diagnostic_text(str(exc))}
            result["controls"] = self._controls(effort, context_budget, output_budget, timeout_seconds, effort_supported=False)
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
        result["controls"] = self._controls(effort, context_budget, output_budget, timeout_seconds, effort_supported=effort_supported)
        if not result["provider_connected"]:
            result["notes"] = "OpenCode server is reachable, but the configured provider is not connected; no model call was attempted"
        elif not result["model_available"]:
            result["notes"] = "OpenCode provider is connected, but the configured model is unavailable; no model call was attempted"
        elif not effort_supported:
            result["notes"] = "OpenCode model is available, but the requested variant is not listed; no model call was attempted"
        else:
            result["notes"] = "OpenCode server, provider connection, model ID, and requested variant are available; no model call was attempted"
        return result

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        query: Mapping[str, str] | None = None,
        timeout: float,
        session_id: str | None = None,
    ) -> dict[str, Any]:
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
            credentials = b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("ascii")
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
            except OSError:
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
        except (TimeoutError, socket.timeout) as exc:
            raise ProviderError("OpenCode request timed out", kind="timeout", retryable=True, details={"timeout_seconds": timeout, "server_url": self.server_url}) from exc
        except URLError as exc:
            reason = str(getattr(exc, "reason", exc))
            if re.search(r"(?i)timed out|timeout", reason):
                raise ProviderError("OpenCode request timed out", kind="timeout", retryable=True, details={"timeout_seconds": timeout, "server_url": self.server_url}) from exc
            raise ProviderError("OpenCode server could not be reached", kind="provider_connect", retryable=True, details={"server_url": self.server_url, "reason": _diagnostic_text(reason)}) from exc
        except OSError as exc:
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
    ) -> ProviderResponse:
        info = response.get("info") if isinstance(response.get("info"), dict) else {}
        error = info.get("error") if isinstance(info, dict) else None
        if isinstance(error, dict):
            name = str(error.get("name") or error.get("type") or "")
            message = _diagnostic_text(str(error.get("message") or name or "OpenCode assistant error"))
            if "auth" in name.lower() or "credential" in name.lower():
                kind = "auth"
            elif "structured" in name.lower() or "output" in name.lower():
                kind = "malformed_json"
            elif "context" in name.lower():
                kind = "context_budget_exceeded"
            else:
                kind = "provider_exit"
            raise ProviderError(f"OpenCode assistant returned {name or 'an error'}: {message}", kind=kind, retryable=kind in {"auth", "provider_exit"}, details={"provider_error": {"name": name, "message": message}, "session_id": session_id})
        payload = self._structured_payload(response)
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
        controls = self._controls(request.effort, request.context_budget, request.output_budget, request.timeout_seconds, effort_supported=True)
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
    def _controls(effort: str, context_budget: int | None, output_budget: int | None, timeout_seconds: float | None, *, effort_supported: bool) -> dict[str, Any]:
        return {
            "effort": {"requested": effort, "provider_supported": effort_supported, "enforced": effort_supported, "mechanism": "session.prompt.variant"},
            "context_budget": {"requested": context_budget, "provider_supported": False, "enforced": "controller_prompt_estimate", "provider_flag": False},
            "output_budget": {"requested": output_budget, "provider_supported": False, "enforced": "controller_response_estimate", "provider_flag": False},
            "timeout": {"requested_seconds": timeout_seconds, "provider_supported": True, "enforced": "overall_http_deadline", "owned_process_cleanup": False},
        }


def provider_from_config(provider: str, *, role: str, model: str, repo_root: str | Path) -> Provider:
    del role
    if provider == "fixture":
        return FixtureProvider(role="configured")
    if provider == "codex":
        return CodexCLIProvider(model=model, cwd=repo_root)
    if provider == "opencode":
        return OpenCodeProvider(model=model, repo_root=repo_root)
    raise UnsupportedProviderError(provider)


def preflight_provider(provider: str, model: str, *, effort: str = "medium", context_budget: int | None = None, output_budget: int | None = None, timeout_seconds: float | None = None) -> dict[str, Any]:
    if provider == "opencode":
        try:
            return OpenCodeProvider(model=model).preflight(effort=effort, context_budget=context_budget, output_budget=output_budget, timeout_seconds=timeout_seconds)
        except ProviderError as exc:
            return {
                "provider": provider,
                "model_configured": bool(model and model != "unset"),
                "server_reachable": False,
                "provider_connected": False,
                "model_available": False,
                "live_call_performed": False,
                "controls": OpenCodeProvider._controls(effort, context_budget, output_budget, timeout_seconds, effort_supported=False),
                "error": {"kind": exc.kind, "message": _diagnostic_text(str(exc))},
                "notes": "OpenCode preflight configuration is invalid; no model call was attempted",
            }
    executable = shutil.which(provider if provider != "codex" else "codex")
    controls = {
        "effort": {"requested": effort, "provider_supported": provider == "codex" and effort in SUPPORTED_CODEX_EFFORTS, "enforced": provider == "codex" and effort in SUPPORTED_CODEX_EFFORTS, "mechanism": "-c model_reasoning_effort" if provider == "codex" else None},
        "context_budget": {"requested": context_budget, "provider_supported": False, "enforced": "controller_prompt_estimate" if context_budget is not None else False},
        "output_budget": {"requested": output_budget, "provider_supported": False, "enforced": "controller_response_estimate" if output_budget is not None else False},
        "timeout": {"requested_seconds": timeout_seconds, "provider_supported": provider == "codex", "enforced": "owned_process_group" if provider == "codex" else False},
    }
    return {
        "provider": provider,
        "model_configured": bool(model and model != "unset"),
        "executable_found": executable is not None if provider == "codex" else None,
        "executable_path": executable if provider == "codex" else None,
        "server_reachable": None,
        "live_call_performed": False,
        "controls": controls,
        "notes": ("Fixture provider performs no executable or network call" if provider == "fixture" else "Codex executable presence is checked; authentication/model access is not probed")
    }
