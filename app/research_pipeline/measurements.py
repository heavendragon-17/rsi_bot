"""Measured provider overhead and an equivalent deterministic-work baseline."""

from __future__ import annotations

import json
from datetime import datetime
from time import perf_counter
from typing import Any

from .contracts import object_hash
from .inputs import tool_parameters
from .study_contracts import STUDY_TASKS
from .tools import ToolContext, ToolRestrictionError


def runtime_measurements(summary: dict[str, Any]) -> dict[str, Any]:
    attempts = [row for row in summary["attempts"] if row["provider"] != "fixture"]
    inputs: list[float] = []
    outputs: list[float] = []
    costs: list[float] = []
    supplemental: dict[str, list[float]] = {key: [] for key in ("total", "reasoning", "cache_read", "cache_write")}
    for attempt in attempts:
        envelope = json.loads(attempt.get("usage_json") or "{}")
        usage = envelope.get("provider_usage") or {}
        runtime = usage.get("runtime") or {}
        extra = {"total": runtime.get("total"), "reasoning": runtime.get("reasoning", runtime.get("reasoning_output_tokens")),
                 "cache_read": (runtime.get("cache") or {}).get("read", runtime.get("cached_input_tokens")),
                 "cache_write": (runtime.get("cache") or {}).get("write", runtime.get("cache_write_input_tokens"))}
        for key, value in extra.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                supplemental[key].append(value)
        for target, keys in ((inputs, ("input_tokens", "input")), (outputs, ("output_tokens", "output"))):
            value = next((runtime[key] for key in keys if key in runtime), None)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                target.append(value)
        cost = usage.get("runtime_cost")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            costs.append(cost)
    evidence = [json.loads(row["evidence_json"]) for row in summary["results"]]
    studies = [row for row in evidence if row.get("task") in STUDY_TASKS and row["status"] == "VERIFIED"]
    live_jobs = []
    for result in summary["results"]:
        phases = {a["phase"] for a in attempts if a["job_id"] == result["job_id"] and a["status"] == "COMPLETED"}
        if result["status"] == "VERIFIED" and {"proposal", "execution", "review"}.issubset(phases):
            live_jobs.append(result["job_id"])
    distinct = {object_hash({"task": row["task"], "parameters": row["parameters"]}) for row in studies}
    campaign = summary["campaign"]
    span = None
    if campaign.get("created_at") and campaign.get("updated_at"):
        span = max(0.0, (datetime.fromisoformat(campaign["updated_at"].replace("Z", "+00:00"))
                        - datetime.fromisoformat(campaign["created_at"].replace("Z", "+00:00"))).total_seconds())
    checker_times = [row["checker_elapsed_seconds"] for row in studies if "checker_elapsed_seconds" in row]
    return {
        "model_provider_attempts": len(attempts), "fixture_attempts": len(summary["attempts"]) - len(attempts),
        "completed_provider_attempts": sum(row["status"] == "COMPLETED" for row in attempts),
        "failed_provider_attempts": sum(row["status"] == "FAILED" for row in attempts),
        "provider_elapsed_seconds": sum(row.get("elapsed_ms") or 0 for row in attempts) / 1000,
        "campaign_span_seconds": span,
        "campaign_span_note": "Creation to last status transition; includes local preparation, waiting and any pauses, not CPU time.",
        "recorded_checker_seconds": sum(checker_times) if checker_times else None,
        "checker_timed_results": len(checker_times),
        "invalid_execution_plan_attempts": sum(row.get("error_kind") in {"malformed_json", "tool_restriction"} and row.get("phase") == "execution"
                                               for row in summary["attempts"]),
        "repair_decisions": sum(row.get("action") == "REPAIR" for row in summary.get("decisions", [])),
        "failure_records": len(summary.get("failures", [])),
        "supplemental_token_usage": {key: {"reported_tokens": sum(values) if values else None, "attempts": len(values)}
                                     for key, values in supplemental.items()},
        "reported_input_tokens": sum(inputs) if inputs else None,
        "reported_output_tokens": sum(outputs) if outputs else None,
        "input_usage_attempts": len(inputs), "output_usage_attempts": len(outputs),
        "all_attempts_have_token_usage": bool(attempts) and len(inputs) == len(outputs) == len(attempts),
        "reported_cost": sum(costs) if costs else None,
        "all_attempts_have_cost": bool(attempts) and len(costs) == len(attempts),
        "cost_note": "Provider-reported cost only; missing values are unknown, not zero. No price assumptions.",
        "verified_results": sum(row["status"] == "VERIFIED" for row in evidence),
        "distinct_verified_studies": len(distinct), "live_loop_verified": bool(live_jobs),
        "adaptive_sequence_verified": len(distinct) >= 2 and summary["campaign"]["status"] in {"STOPPED", "LIMIT_REACHED"},
    }


def replay_baseline(controller: Any, campaign_id: str) -> dict[str, Any]:
    """Re-run accepted study specifications with Python and zero provider calls."""
    from .study_tools import execute_study_tool

    controller._restore_campaign_config(campaign_id)
    summary = controller.store.summary(campaign_id)
    context = controller.store.context(campaign_id)
    rows = []
    for result in summary["results"]:
        expected = json.loads(result["evidence_json"])
        controller._validate_result_artifact(result, expected)
        if expected.get("task") not in STUDY_TASKS or expected.get("status") != "VERIFIED":
            continue
        workspace = controller.output_dir / campaign_id / "scripted_baseline" / result["job_id"]
        started = perf_counter()
        actual = execute_study_tool(expected["task"], tool_parameters(context, expected["parameters"]),
                                   ToolContext(controller.repo_root, workspace, context["evidence_hashes"]))
        elapsed = perf_counter() - started
        matches = (actual["status"] == "VERIFIED" and actual["tables"] == expected["tables"]
                   and actual["input_identity"] == expected["input_identity"]
                   and actual["checker_sha256"] == expected["checker_sha256"])
        rows.append({"job_id": result["job_id"], "task": expected["task"], "parameters": expected["parameters"],
                     "status": actual["status"], "same_evidence": matches, "elapsed_seconds": elapsed})
    if not rows:
        raise ToolRestrictionError("baseline requires at least one verified population research result")
    report = {"schema": "btc-research-baseline-v1", "campaign_id": campaign_id,
              "status": "MATCHED" if all(row["same_evidence"] for row in rows) else "MISMATCH",
              "selection_policy": "Replay the campaign's accepted experimental specifications without a model.",
              "provider_calls": 0, "jobs": rows, "elapsed_seconds": sum(row["elapsed_seconds"] for row in rows),
              "campaign_measurements": runtime_measurements(summary),
              "limitations": ["Measures numerical equivalence and orchestration overhead, not independent hypothesis-selection quality.",
                              "This local run does not establish monetary savings; provider costs may be unavailable."]}
    output = controller.output_dir / campaign_id / "baseline_report.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {**report, "report_path": str(output)}
