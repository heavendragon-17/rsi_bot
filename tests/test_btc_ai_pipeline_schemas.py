"""Offline compatibility checks for strict provider JSON schemas."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from app.research_pipeline.contracts import (
    EXECUTION_SCHEMA,
    REVIEW_SCHEMA,
    ContractError,
    execution_schema,
    proposal_schema,
    review_schema,
    validate_execution_plan,
    validate_proposal,
    validate_review,
)
from app.research_pipeline.providers import _proposal


def _assert_strict_schema(schema: dict[str, Any], path: str = "$") -> None:
    """Check the provider subset that ordinary JSON Schema validation permits.

    In particular, JSON Schema itself allows an untyped const/enum, omitted
    optional properties, open objects, and oneOf; the provider rejects these.
    """

    assert "oneOf" not in schema, f"{path}: use supported anyOf"
    assert "type" in schema or "anyOf" in schema, f"{path}: missing explicit type"
    if "const" in schema or "enum" in schema:
        assert "type" in schema, f"{path}: const/enum needs an explicit type"
    if schema.get("type") == "object":
        assert schema.get("additionalProperties") is False, f"{path}: object must be closed"
        properties = schema["properties"]
        assert set(schema.get("required", [])) == set(properties), f"{path}: every property must be required"
        for name, child in properties.items():
            _assert_strict_schema(child, f"{path}.{name}")
    if schema.get("type") == "array":
        _assert_strict_schema(schema["items"], f"{path}[]")
    for index, child in enumerate(schema.get("anyOf", [])):
        _assert_strict_schema(child, f"{path}.anyOf[{index}]")


@pytest.fixture
def jsonschema_module() -> Any:
    # Structural compatibility still runs when this optional test dependency
    # is unavailable; no production dependency or network access is needed.
    return pytest.importorskip("jsonschema")


@pytest.mark.parametrize("factory", [proposal_schema, execution_schema, review_schema])
def test_provider_schema_uses_strict_structured_output_subset(factory: Callable[[], dict[str, Any]]) -> None:
    schema = factory()
    assert schema["type"] == "object"
    assert "anyOf" not in schema
    _assert_strict_schema(schema)


@pytest.mark.parametrize("factory", [proposal_schema, execution_schema, review_schema])
def test_provider_schema_is_valid_json_schema(factory: Callable[[], dict[str, Any]], jsonschema_module: Any) -> None:
    jsonschema_module.Draft202012Validator.check_schema(factory())


@pytest.mark.parametrize("mode", ["fixture", "real"])
@pytest.mark.parametrize("title", [None, "Verify one frozen M5 horizon result"])
def test_proposal_payload_accepts_nullable_metadata(mode: str, title: str | None, jsonschema_module: Any) -> None:
    payload = {**_proposal(mode=mode), "parent_result_id": None, "title": title}
    jsonschema_module.validate(payload, proposal_schema())
    assert validate_proposal(payload) == payload


@pytest.mark.parametrize("workspace_manifest", [None, "workspace_manifest.json"])
def test_execution_payload_accepts_nullable_manifest(workspace_manifest: str | None, jsonschema_module: Any) -> None:
    payload = {
        "schema": EXECUTION_SCHEMA,
        "task": "verify_m5_horizons",
        "tool": "verify_m5_horizons",
        "parameters": {"mode": "real", "event_index": 0},
        "invariants": ["Use the frozen BTC source and check exact 1h, 2h, and 3h horizons"],
        "workspace_manifest": workspace_manifest,
    }
    jsonschema_module.validate(payload, execution_schema())
    assert validate_execution_plan(payload) == payload


@pytest.mark.parametrize("action", ["STOP", "REPAIR", "REJECT"])
def test_terminal_review_payload_accepts_null_followup(action: str, jsonschema_module: Any) -> None:
    payload = {
        "schema": REVIEW_SCHEMA,
        "action": action,
        "reasons": ["The checker evidence determines the next bounded action"],
        "evidence_refs": ["result-btc-m5-001"],
        "next_job": None,
    }
    jsonschema_module.validate(payload, review_schema())
    assert validate_review(payload) == payload


def test_review_payload_accepts_typed_followup_proposal(jsonschema_module: Any) -> None:
    payload = {
        "schema": REVIEW_SCHEMA,
        "action": "PROPOSE_NEXT",
        "reasons": ["The verified result supports one bounded follow-up"],
        "evidence_refs": ["result-btc-m5-001"],
        "next_job": {**_proposal(mode="real", parent_result_id="result-btc-m5-001"), "title": None},
    }
    jsonschema_module.validate(payload, review_schema())
    assert validate_review(payload) == payload

    # Follow-up proposals retain the same closed controller-owned boundary.
    payload["next_job"]["parameters"]["data_dir"] = "different-source"
    with pytest.raises(jsonschema_module.ValidationError):
        jsonschema_module.validate(payload, review_schema())
    with pytest.raises(ContractError, match="controller-owned or unsupported fields"):
        validate_review(payload)


def test_local_proposal_validation_preserves_omitted_legacy_metadata() -> None:
    payload = _proposal()
    payload.pop("title")
    assert "parent_result_id" not in payload
    assert validate_proposal(payload) == payload
    assert "title" not in payload
    assert "parent_result_id" not in payload


def test_local_execution_validation_preserves_omitted_legacy_manifest() -> None:
    payload = {
        "schema": EXECUTION_SCHEMA,
        "task": "verify_m5_horizons",
        "tool": "verify_m5_horizons",
        "parameters": {"mode": "fixture", "event_index": 0},
        "invariants": ["Use frozen evidence"],
    }
    assert validate_execution_plan(payload) == payload
    assert "workspace_manifest" not in payload


def test_local_review_validation_preserves_omitted_legacy_followup() -> None:
    payload = {
        "schema": REVIEW_SCHEMA,
        "action": "STOP",
        "reasons": ["The bounded job is complete"],
        "evidence_refs": ["result-btc-m5-001"],
    }
    assert validate_review(payload) == payload
    assert "next_job" not in payload


def test_local_review_validation_keeps_action_specific_followup_rules() -> None:
    payload = {
        "schema": REVIEW_SCHEMA,
        "action": "PROPOSE_NEXT",
        "reasons": ["A follow-up needs an explicit proposal"],
        "evidence_refs": ["result-btc-m5-001"],
        "next_job": None,
    }
    with pytest.raises(ContractError, match="PROPOSE_NEXT review requires next_job"):
        validate_review(payload)
    payload.update(action="STOP", next_job=_proposal(parent_result_id="result-btc-m5-001"))
    with pytest.raises(ContractError, match="only PROPOSE_NEXT may include next_job"):
        validate_review(payload)
