"""Explicitly scripted research policy for offline controller validation."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from .contracts import EXECUTION_SCHEMA, REVIEW_SCHEMA, ContractError
from .providers import FixtureProvider, _proposal
from .study_contracts import COHORT_TASK, SUMMARY_TASK


def research_proposal(mode: str, *, parent: str | None = None, horizon: int | None = None) -> dict[str, Any]:
    task = SUMMARY_TASK if horizon is None else COHORT_TASK
    parameters = {"mode": mode} if horizon is None else {"mode": mode, "horizon_minutes": horizon, "grouping": "choose"}
    return {**_proposal(mode=mode, parent_result_id=parent), "task": task, "parameters": parameters,
            "title": "Compare M5 population outcomes" if horizon is None else f"Diagnose {horizon}-minute cohort concentration",
            "hypothesis": "The signal-minus-baseline difference varies across horizons and may be concentrated in particular cohorts.",
            "question": "Which descriptive comparison most clearly tests concentration of the observed difference?",
            "rationale": "Use verified population summaries to choose a bounded follow-up, retaining independent numerical checks.",
            "expected_evidence": ["source identity", "matched population counts", "signal and baseline means", "mean differences"],
            "invariants": ["use frozen data and registered comparisons", "no executable P&L or alpha claim"],
            "stop_conditions": ["stop at persisted campaign budget or failed evidence"],
            "falsification_conditions": ["raw outcomes disagree with saved evidence", "insufficient matched observations"],
            "parent_result_id": parent}


class AdaptiveFixtureProvider(FixtureProvider):
    """Transparent scripted policy for offline tests; never represents a model."""

    def complete(self, request):
        if request.phase == "proposal":
            payload = research_proposal(request.metadata["verification_mode"])
        elif request.phase == "execution":
            proposal = request.metadata["proposal"]
            params = dict(proposal["parameters"])
            if params.get("grouping") == "choose":
                params["grouping"] = "calendar_year"
            payload = {"schema": EXECUTION_SCHEMA, "task": proposal["task"], "tool": proposal["task"],
                       "parameters": params, "invariants": proposal["invariants"], "workspace_manifest": None,
                       "diagnostic_rationale": "Use horizon comparisons first, then calendar cohorts to check temporal concentration without selecting a trading filter."}
        elif request.phase == "review":
            evidence = request.metadata["evidence"]
            payload = {"schema": REVIEW_SCHEMA, "action": "STOP", "reasons": ["The bounded study is complete; alpha remains NOT_ASSESSED."],
                       "evidence_refs": [evidence["result_id"]], "next_job": None}
            if evidence["status"] != "VERIFIED":
                payload.update(action="REPAIR", reasons=["The checker did not verify the current evidence."])
            elif evidence["task"] == SUMMARY_TASK:
                usable = [row for row in evidence["tables"] if row.get("signal_minus_baseline_pp") is not None]
                if usable:
                    chosen = max(usable, key=lambda row: (abs(row["signal_minus_baseline_pp"]), -row["horizon_minutes"]))
                    mode = evidence["parameters"]["mode"]
                    payload.update(action="PROPOSE_NEXT", next_job=research_proposal(mode, parent=evidence["result_id"], horizon=chosen["horizon_minutes"]),
                                   reasons=[f"The {chosen['horizon_minutes']}-minute horizon has the largest absolute descriptive difference ({chosen['signal_minus_baseline_pp']:.6f} percentage points); examine its cohort concentration."])
        else:
            raise ContractError("unknown adaptive fixture phase")
        # Use the existing fixture response envelope so usage remains explicitly unavailable.
        envelope_request = replace(request, phase="proposal")
        response = super().complete(envelope_request)
        return replace(response, payload=payload)
