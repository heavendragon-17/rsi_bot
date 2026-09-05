"""Bounded research role context and checked study execution."""

from __future__ import annotations

import json
import uuid
from functools import partial
from time import perf_counter
from typing import Any

from .contracts import execution_schema, object_hash
from .controller_context import ControllerContext
from .inputs import tool_parameters, validate_inputs
from .study_contracts import COHORT_TASK, GROUPINGS, SUMMARY_TASK
from .tools import ToolContext, ToolRestrictionError


class AdaptiveSupport(ControllerContext):
    """Controller support for model-selected, deterministic research tasks."""

    def _research_context(self, campaign_id: str) -> dict[str, Any]:
        context = self.store.context(campaign_id)
        return {
            "objective": context["question"],
            "registered_tasks": [
                {"task": SUMMARY_TASK, "description": "Compare gross signal and eligible-baseline returns at 60, 120 and 180 minutes.",
                 "example_parameters": {"mode": context["verification_mode"]}},
                {"task": COHORT_TASK, "description": "Check whether a horizon's pooled difference is concentrated in time or a point-in-time regime.",
                 "example_parameters": {"mode": context["verification_mode"], "horizon_minutes": 120, "grouping": "choose"},
                 "groupings": list(GROUPINGS)},
            ],
            "verification_mode": context["verification_mode"],
            "campaign_budget": dict(self.store.budget(campaign_id)),
            "parameter_rules": "Paths are controller-owned. A cohort proposal may use grouping=choose; the executor must select one concrete grouping and explain the diagnostic. All other parameters and invariants are frozen.",
            "interpretation": "Descriptive gross returns, dependent observations, no executable P&L or alpha approval. Propose a distinct follow-up from current evidence; do not repeat a completed experiment.",
        }

    def _study_preview(self, campaign_id: str, parameters: dict[str, Any]) -> dict[str, Any]:
        from .study_tools import prepare_study_context

        context = self.store.context(campaign_id)
        validate_inputs(context, self.repo_root, self.output_dir / campaign_id)
        return prepare_study_context(tool_parameters(context, parameters),
                                     ToolContext(self.repo_root, self.output_dir / campaign_id, context["evidence_hashes"]))

    def _execute_study_job(self, campaign_id: str, job_id: str, proposal: dict[str, Any]) -> None:
        from . import study_tools

        context = self.store.context(campaign_id)
        preview = self._study_preview(campaign_id, proposal["parameters"])
        supplied = {"proposal": proposal, "study_context": preview, **self._research_context(campaign_id)}
        prompt = (
            "Return a structured execution plan for this research proposal. Copy its task to tool. "
            "Preserve parameters and ordered invariants; only grouping=choose may be resolved to one registered grouping. "
            "Use the study context and hypothesis to explain the comparison in diagnostic_rationale. "
            "That field must contain nonblank text even for a summary with fully fixed parameters; never return null. "
            "workspace_manifest must be null. The independent checker evaluates the selected comparison. "
            + json.dumps(supplied, sort_keys=True)
        )
        validator = partial(self._validate_execution_plan_for_proposal, proposal=proposal)
        plan = self._completed_response(campaign_id, job_id, "execution", validator)
        if plan is None:
            plan = self._provider_call(campaign_id, job_id, role="executor", phase="execution", prompt=prompt,
                                       schema=execution_schema(adaptive=True), metadata=supplied, validator=validator)
        for row in self.store.summary(campaign_id)["results"]:
            prior = json.loads(row["evidence_json"])
            if prior.get("task") == plan["task"] and prior.get("parameters") == plan["parameters"]:
                raise ToolRestrictionError("adaptive executor repeated an already checked experiment")
        params = tool_parameters(context, plan["parameters"])
        workspace = self.output_dir / campaign_id / job_id
        started = perf_counter()
        evidence = study_tools.execute_study_tool(plan["tool"], params,
                    ToolContext(self.repo_root, workspace, context["evidence_hashes"]))
        evidence["checker_elapsed_seconds"] = perf_counter() - started
        evidence["result_id"] = "result_" + uuid.uuid4().hex[:16]
        evidence["reused_evidence"] = False
        evidence["executor_diagnostic"] = plan["diagnostic_rationale"]
        evidence["cache_key"] = object_hash({"task": plan["tool"], "parameters": plan["parameters"],
            "inputs": evidence.get("input_identity"), "checker": evidence["checker_sha256"]})
        artifacts = workspace / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "evidence.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.store.create_result(evidence["result_id"], job_id, evidence["status"], str(artifacts), evidence,
                                 object_hash(evidence), evidence["cache_key"])


