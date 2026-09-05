"""Runtime model provider contracts.

The controller only receives structured JSON from this module. Research tools
are never selected by shell prose from a model response.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import (
    EXECUTION_SCHEMA,
    M5_VERIFICATION_TASK,
    PROPOSAL_SCHEMA,
    REVIEW_SCHEMA,
    SUPPORTED_CODEX_EFFORTS,
    Provider,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    UnsupportedProviderError,
)
from .opencode_provider import OpenCodeProvider
from .provider_diagnostics import (
    _diagnostic_text,
    _provider_failure_details,
    _provider_failure_kind,
)


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
    if sys.platform == "win32":
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
            raise error from exc
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


def provider_from_config(provider: str, *, role: str, model: str, repo_root: str | Path) -> Provider:
    del role
    if provider == "fixture":
        return FixtureProvider(role="configured")
    if provider == "codex":
        return CodexCLIProvider(model=model, cwd=repo_root)
    if provider == "opencode":
        return OpenCodeProvider(model=model, repo_root=repo_root)
    raise UnsupportedProviderError(provider)


def preflight_provider(provider: str, model: str, *, effort: str = "medium", context_budget: int | None = None, output_budget: int | None = None, timeout_seconds: float | None = None, opencode_output_mode: str = "json_schema") -> dict[str, Any]:
    if provider == "opencode":
        try:
            return OpenCodeProvider(model=model).preflight(effort=effort, context_budget=context_budget, output_budget=output_budget, timeout_seconds=timeout_seconds, output_mode=opencode_output_mode)
        except ProviderError as exc:
            return {
                "provider": provider,
                "model_configured": bool(model and model != "unset"),
                "server_reachable": False,
                "provider_connected": False,
                "model_available": False,
                "live_call_performed": False,
                "controls": OpenCodeProvider._controls(effort, context_budget, output_budget, timeout_seconds, effort_supported=False, output_mode=opencode_output_mode),
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
