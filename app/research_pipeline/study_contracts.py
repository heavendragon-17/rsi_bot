"""Bounded research task parameters and strict provider schema extensions."""

from __future__ import annotations

from typing import Any

SUMMARY_TASK = "summarize_m5_horizons"
COHORT_TASK = "compare_m5_cohorts"
STUDY_TASKS = (SUMMARY_TASK, COHORT_TASK)
HORIZONS = (60, 120, 180)
GROUPINGS = ("calendar_year", "trend", "volatility")


def validate_study_parameters(task: str, params: Any, *, execution: bool = False) -> dict[str, Any]:
    from .contracts import ContractError

    required = {"mode"} if task == SUMMARY_TASK else {"mode", "horizon_minutes", "grouping"}
    if task not in STUDY_TASKS or not isinstance(params, dict) or set(params) != required:
        raise ContractError("research parameters do not match the registered task")
    if params["mode"] not in ("real", "fixture"):
        raise ContractError("research mode must be real or fixture")
    if task == COHORT_TASK:
        if type(params["horizon_minutes"]) is not int or params["horizon_minutes"] not in HORIZONS:
            raise ContractError("research horizon must be 60, 120, or 180 minutes")
        allowed = GROUPINGS if execution else (*GROUPINGS, "choose")
        if params["grouping"] not in allowed:
            raise ContractError("executor must select a concrete registered cohort grouping")
    return params


def parameter_schemas(*, execution: bool = False) -> list[dict[str, Any]]:
    mode = {"type": "string", "enum": ["fixture", "real"]}
    return [
        {"type": "object", "additionalProperties": False, "required": ["mode"], "properties": {"mode": mode}},
        {"type": "object", "additionalProperties": False,
         "required": ["mode", "horizon_minutes", "grouping"],
         "properties": {"mode": mode, "horizon_minutes": {"type": "integer", "enum": list(HORIZONS)},
                        "grouping": {"type": "string", "enum": list(GROUPINGS if execution else (*GROUPINGS, "choose"))}}},
    ]


def extend_schema(schema: dict[str, Any], *, execution: bool = False) -> dict[str, Any]:
    properties = schema["properties"]
    tasks = ["verify_m5_horizons", *STUDY_TASKS]
    properties["task"] = {"type": "string", "enum": tasks}
    properties["parameters"] = {"anyOf": [properties["parameters"], *parameter_schemas(execution=execution)]}
    if execution:
        properties["tool"] = {"type": "string", "enum": tasks}
        properties["diagnostic_rationale"] = {
            "type": "string", "pattern": r"\S",
            "description": "Explain why this comparison tests the hypothesis, including for a summary with fixed parameters. Never null or blank.",
        }
        schema["required"].append("diagnostic_rationale")
    return schema
