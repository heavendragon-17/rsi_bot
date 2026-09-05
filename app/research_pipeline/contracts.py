"""Typed contracts and strict JSON validation for the research pipeline."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Protocol

from .study_contracts import STUDY_TASKS, extend_schema, validate_study_parameters

SCHEMA_VERSION = "btc-ai-pipeline-mvp-v1"
PROPOSAL_SCHEMA = "btc-research-proposal-v1"
EXECUTION_SCHEMA = "btc-research-execution-plan-v1"
REVIEW_SCHEMA = "btc-research-review-v1"
M5_VERIFICATION_TASK = "verify_m5_horizons"
SUPPORTED_CODEX_EFFORTS = frozenset({"minimal", "low", "medium", "high", "xhigh"})


class ContractError(ValueError):
    """Raised when a provider response is not the contract JSON."""


class ProviderError(RuntimeError):
    """A provider failure that must be persisted before pausing a campaign."""

    def __init__(self, message: str, *, kind: str = "provider_error", retryable: bool = False, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.details = dict(details or {})
        # Filled by the controller after the attempt is reserved. Keeping the
        # linkage on the exception lets the outer loop persist failures with
        # the exact attempt/job that caused them.
        self.attempt_id: str | None = None
        self.job_id: str | None = None


@dataclass(frozen=True)
class VerifyM5HorizonsParameters:
    """Model-owned parameters for the sole registered BTC research tool.

    Packet and source paths are controller-owned. Keeping them out of this
    typed contract prevents an executor from silently moving a frozen job to a
    different input while still allowing the controller to resolve its pinned
    paths for the registered callable.
    """

    mode: str
    event_index: int

    @classmethod
    def from_mapping(cls, value: Any) -> VerifyM5HorizonsParameters:
        if not isinstance(value, dict):
            raise ContractError("verify_m5_horizons.parameters must be an object")
        extra = sorted(set(value) - {"mode", "event_index"})
        if extra:
            raise ContractError("verify_m5_horizons.parameters has controller-owned or unsupported fields: " + ", ".join(extra))
        mode = value.get("mode")
        if mode not in {"fixture", "real"}:
            raise ContractError("verify_m5_horizons.parameters.mode must be fixture or real")
        event_index = value.get("event_index")
        if isinstance(event_index, bool) or not isinstance(event_index, int) or event_index < 0:
            raise ContractError("verify_m5_horizons.parameters.event_index must be a non-negative integer")
        return cls(mode=mode, event_index=event_index)

    def as_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "event_index": self.event_index}


class UnsupportedProviderError(ProviderError):
    """Raised for a provider boundary that has not been implemented."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"Provider {provider!r} is not implemented", kind="unsupported_provider")


class BudgetExceededError(ProviderError):
    """Raised before dispatch when a campaign budget is exhausted."""

    def __init__(self, role: str) -> None:
        super().__init__(f"{role} invocation budget exhausted", kind="budget_exhausted")


@dataclass(frozen=True)
class ProviderRequest:
    role: str
    phase: str
    prompt: str
    schema: Mapping[str, Any]
    model: str
    effort: str
    timeout_seconds: float
    context_budget: int
    output_budget: int
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResponse:
    payload: Mapping[str, Any]
    provider: str
    model: str
    usage: Mapping[str, Any] | None = None
    reported_model: str | None = None
    controls: Mapping[str, Any] | None = None
    raw_excerpt: str | None = None


class Provider(Protocol):
    name: str

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        """Return one schema-validatable JSON object or raise ProviderError."""


@dataclass(frozen=True)
class PipelineConfig:
    db_path: str
    output_dir: str
    thinker_provider: str = "fixture"
    thinker_model: str = "fixture-thinker"
    thinker_effort: str = "medium"
    executor_provider: str = "fixture"
    executor_model: str = "fixture-executor"
    executor_effort: str = "minimal"
    timeout_seconds: float = 120.0
    context_budget: int = 6000
    output_budget: int = 2000
    max_thinker_calls: int = 2
    max_executor_calls: int = 1
    max_jobs: int = 1
    repo_root: str = "."
    data_dir: str | None = None
    baseline_packet: str | None = None
    horizon_packet: str | None = None
    verification_mode: str = "fixture"
    live_opt_in: bool = False
    adaptive: bool = False
    opencode_output_mode: str = "json_schema"

    def __post_init__(self) -> None:
        if self.opencode_output_mode not in {"json_schema", "json_text"}:
            raise ValueError("opencode_output_mode must be json_schema or json_text")
        if self.verification_mode not in {"fixture", "real"}:
            raise ValueError("verification_mode must be fixture or real")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        for name in ("context_budget", "output_budget", "max_thinker_calls", "max_executor_calls", "max_jobs"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> PipelineConfig:
        """Restore only persisted configuration fields, including defaults."""

        allowed = {item.name for item in fields(cls)}
        return cls(**{key: value[key] for key in allowed if key in value})


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def object_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be a JSON object")
    return value


def _require_string(obj: Mapping[str, Any], key: str, label: str, *, nonempty: bool = True) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise ContractError(f"{label}.{key} must be a non-empty string")
    return value


def _require_string_list(obj: Mapping[str, Any], key: str, label: str, *, min_items: int = 1) -> list[str]:
    value = obj.get(key)
    if not isinstance(value, list) or len(value) < min_items or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ContractError(f"{label}.{key} must be a list of non-empty strings")
    return list(value)


def validate_proposal(value: Any) -> dict[str, Any]:
    obj = _require_object(value, "proposal")
    required = ("schema", "hypothesis", "question", "rationale", "expected_evidence", "task", "parameters", "invariants", "stop_conditions", "falsification_conditions")
    missing = [key for key in required if key not in obj]
    if missing:
        raise ContractError(f"proposal missing required fields: {', '.join(missing)}")
    if obj["schema"] != PROPOSAL_SCHEMA:
        raise ContractError(f"proposal.schema must be {PROPOSAL_SCHEMA!r}")
    for key in ("hypothesis", "question", "rationale", "task"):
        _require_string(obj, key, "proposal")
    if obj["task"] not in (M5_VERIFICATION_TASK, *STUDY_TASKS):
        raise ContractError(f"proposal.task must be the registered identifier {M5_VERIFICATION_TASK!r}")
    _require_string_list(obj, "expected_evidence", "proposal")
    _require_string_list(obj, "invariants", "proposal")
    _require_string_list(obj, "stop_conditions", "proposal")
    _require_string_list(obj, "falsification_conditions", "proposal")
    if obj["task"] == M5_VERIFICATION_TASK:
        VerifyM5HorizonsParameters.from_mapping(obj["parameters"])
    else:
        validate_study_parameters(obj["task"], obj["parameters"])
    if "parent_result_id" in obj and obj["parent_result_id"] is not None and (not isinstance(obj["parent_result_id"], str) or not obj["parent_result_id"].strip()):
        raise ContractError("proposal.parent_result_id must be a non-empty string or null")
    allowed = set(required) | {"parent_result_id", "title"}
    extra = sorted(set(obj) - allowed)
    if extra:
        raise ContractError(f"proposal has unsupported fields: {', '.join(extra)}")
    return obj


def validate_execution_plan(value: Any) -> dict[str, Any]:
    obj = _require_object(value, "execution plan")
    if obj.get("schema") != EXECUTION_SCHEMA:
        raise ContractError(f"execution plan.schema must be {EXECUTION_SCHEMA!r}")
    for key in ("task", "tool"):
        _require_string(obj, key, "execution plan")
        if obj[key] not in (M5_VERIFICATION_TASK, *STUDY_TASKS):
            raise ContractError(f"execution plan.{key} must be the registered identifier {M5_VERIFICATION_TASK!r}")
    if obj["task"] == M5_VERIFICATION_TASK:
        VerifyM5HorizonsParameters.from_mapping(obj.get("parameters"))
    else:
        validate_study_parameters(obj["task"], obj.get("parameters"), execution=True)
        _require_string(obj, "diagnostic_rationale", "execution plan")
    if not isinstance(obj.get("invariants"), list) or any(not isinstance(item, str) for item in obj["invariants"]):
        raise ContractError("execution plan.invariants must be a list of strings")
    allowed = {"schema", "task", "tool", "parameters", "invariants", "workspace_manifest", "diagnostic_rationale"}
    extra = sorted(set(obj) - allowed)
    if extra:
        raise ContractError(f"execution plan has unsupported fields: {', '.join(extra)}")
    return obj


def validate_review(value: Any) -> dict[str, Any]:
    obj = _require_object(value, "review")
    if obj.get("schema") != REVIEW_SCHEMA:
        raise ContractError(f"review.schema must be {REVIEW_SCHEMA!r}")
    action = obj.get("action")
    if action not in {"REPAIR", "PROPOSE_NEXT", "REJECT", "STOP"}:
        raise ContractError("review.action must be REPAIR, PROPOSE_NEXT, REJECT, or STOP")
    _require_string_list(obj, "reasons", "review")
    _require_string_list(obj, "evidence_refs", "review")
    next_job = obj.get("next_job")
    if next_job is not None:
        validate_proposal(next_job)
    allowed = {"schema", "action", "reasons", "evidence_refs", "next_job"}
    extra = sorted(set(obj) - allowed)
    if extra:
        raise ContractError(f"review has unsupported fields: {', '.join(extra)}")
    if action == "PROPOSE_NEXT" and next_job is None:
        raise ContractError("PROPOSE_NEXT review requires next_job")
    if action != "PROPOSE_NEXT" and next_job is not None:
        raise ContractError("only PROPOSE_NEXT may include next_job")
    return obj


def _verify_m5_horizons_parameters_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["mode", "event_index"],
        "properties": {
            "mode": {"type": "string", "enum": ["fixture", "real"]},
            "event_index": {"type": "integer", "minimum": 0},
        },
    }


def _nonempty_text_schema() -> dict[str, Any]:
    return {"type": "string", "pattern": r"\S"}


def _nonempty_text_list_schema() -> dict[str, Any]:
    return {"type": "array", "minItems": 1, "items": _nonempty_text_schema()}


def _task_identifier_schema() -> dict[str, Any]:
    return {
        "type": "string",
        "const": M5_VERIFICATION_TASK,
        "description": "Exact registered task identifier. Put the natural-language description in question, hypothesis, or rationale.",
    }


def proposal_schema(*, adaptive: bool = False) -> dict[str, Any]:
    # Strict provider schemas require every property. Optional metadata uses
    # null on the wire; local validators still accept older persisted omissions.
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema", "hypothesis", "question", "rationale", "expected_evidence",
            "task", "parameters", "invariants", "stop_conditions",
            "falsification_conditions", "parent_result_id", "title",
        ],
        "properties": {
            "schema": {"type": "string", "const": PROPOSAL_SCHEMA},
            "hypothesis": _nonempty_text_schema(),
            "question": _nonempty_text_schema(),
            "rationale": _nonempty_text_schema(),
            "expected_evidence": _nonempty_text_list_schema(),
            "task": _task_identifier_schema(),
            "parameters": _verify_m5_horizons_parameters_schema(),
            "invariants": _nonempty_text_list_schema(),
            "stop_conditions": _nonempty_text_list_schema(),
            "falsification_conditions": _nonempty_text_list_schema(),
            "parent_result_id": {"type": ["string", "null"]},
            "title": {"type": ["string", "null"]},
        },
    }
    return extend_schema(schema) if adaptive else schema


def execution_schema(*, adaptive: bool = False) -> dict[str, Any]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema", "task", "tool", "parameters", "invariants", "workspace_manifest"],
        "properties": {
            "schema": {"type": "string", "const": EXECUTION_SCHEMA},
            "task": _task_identifier_schema(),
            "tool": _task_identifier_schema(),
            "parameters": _verify_m5_horizons_parameters_schema(),
            "invariants": {"type": "array", "items": {"type": "string"}},
            "workspace_manifest": {"type": ["string", "null"]},
        },
    }
    return extend_schema(schema, execution=True) if adaptive else schema


def review_schema(*, adaptive: bool = False) -> dict[str, Any]:
    # Keep the follow-up proposal schema identical to the standalone proposal
    # contract, including the closed typed-parameter object for the registered
    # tool. Local validation remains authoritative after provider output.
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema", "action", "reasons", "evidence_refs", "next_job"],
        "properties": {
            "schema": {"type": "string", "const": REVIEW_SCHEMA},
            "action": {"type": "string", "enum": ["REPAIR", "PROPOSE_NEXT", "REJECT", "STOP"]},
            "reasons": _nonempty_text_list_schema(),
            "evidence_refs": _nonempty_text_list_schema(),
            "next_job": {"anyOf": [proposal_schema(adaptive=adaptive), {"type": "null"}]},
        },
    }
