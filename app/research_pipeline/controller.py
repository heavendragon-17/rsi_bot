"""Campaign controller for the bounded thinker/executor/checker/reviewer loop."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from functools import partial
from pathlib import Path
from typing import Any

from .adaptive import AdaptiveSupport
from .adaptive_fixture import AdaptiveFixtureProvider
from .contracts import (
    M5_VERIFICATION_TASK,
    BudgetExceededError,
    ContractError,
    PipelineConfig,
    Provider,
    ProviderError,
    canonical_json,
    execution_schema,
    object_hash,
    proposal_schema,
    review_schema,
    validate_execution_plan,
    validate_proposal,
    validate_review,
)
from .controller_reporting import CampaignReporting
from .controller_runtime import ProviderRuntime
from .controller_utils import _id
from .inputs import resolve_inputs, validate_inputs
from .providers import FixtureProvider, provider_from_config
from .readiness import preflight as preflight
from .storage import PipelineStore
from .study_contracts import STUDY_TASKS
from .tools import (
    ToolContext,
    ToolInputAccessError,
    ToolRestrictionError,
    ToolVerificationError,
    current_input_identity,
    execute_registered_tool,
    registered_tools,
    verification_cache_key,
)

DEFAULT_BASELINE = "research/results/phase1_four_year_runs/run_20260904T084317586748Z_97d3c169"
DEFAULT_HORIZON = "research/results/m5_four_year_horizon_runs/run_20260904T084448776441Z_97d3c169"
TERMINAL_STATUSES = {"STOPPED", "REJECTED", "COMPLETED", "LIMIT_REACHED", "FAILED", "BUDGET_EXHAUSTED"}


class PipelineController(AdaptiveSupport, ProviderRuntime, CampaignReporting):
    """Orchestrate one bounded research job with durable state transitions."""

    def __init__(
        self,
        config: PipelineConfig,
        *,
        thinkers: dict[str, Provider] | None = None,
        executors: dict[str, Provider] | None = None,
        provider_factory: Callable[..., Provider] = provider_from_config,
    ) -> None:
        self.config = config
        self.repo_root = Path(config.repo_root).resolve()
        self.output_dir = self._repo_path(config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.store = PipelineStore(self._repo_path(config.db_path))
        # Provider construction is deliberately lazy. A read-only status query
        # and an offline authorization rejection must not initialize a runtime
        # provider or touch its executable.
        self.thinkers = dict(thinkers) if thinkers is not None else {}
        self.executors = dict(executors) if executors is not None else {}
        self.provider_factory = provider_factory

    def _repo_path(self, raw: str | Path) -> Path:
        path = Path(raw).expanduser()
        return (self.repo_root / path).resolve() if not path.is_absolute() else path.resolve()

    def _provider(self, role: str) -> Provider:
        provider_name = self.config.thinker_provider if role == "thinker" else self.config.executor_provider
        providers = self.thinkers if role == "thinker" else self.executors
        provider = providers.get(provider_name)
        if provider is None:
            if provider_name == "fixture" and self.config.adaptive:
                provider = AdaptiveFixtureProvider(role=role)
            else:
                provider = self.provider_factory(provider_name, role=role, model=self.config.thinker_model if role == "thinker" else self.config.executor_model, repo_root=self.repo_root)
            providers[provider_name] = provider
        return provider

    def create_campaign(self, *, name: str = "btc-ai-mvp", question: str = "Independently verify one existing BTC M5 1h/2h/3h result.") -> str:
        if self.config.adaptive and question == "Independently verify one existing BTC M5 1h/2h/3h result.":
            question = "Compare BTC M5 gross signal and eligible-baseline outcomes, then use verified evidence to investigate concentration across time or point-in-time regimes."
        campaign_id = _id("campaign")
        context = {"question": question, **resolve_inputs(self.config),
                   "previous_decisions": [], "previous_failures": [], "alpha_assessment": "NOT_ASSESSED"}
        self.store.create_campaign(campaign_id, name, question, self.config.as_dict(), context)
        return campaign_id

    def run(self, campaign_id: str, *, branch: str | None = None, reconcile_uncertain: bool = False) -> dict[str, Any]:
        """Advance ordinary adaptive jobs without exceeding persisted reservations."""
        for _ in range(self.config.max_jobs + 1):
            state = self._run_one(campaign_id, branch=branch, reconcile_uncertain=reconcile_uncertain)
            reconcile_uncertain = False
            if not self.config.adaptive or state["status"] != "RUNNING":
                return state
        return state

    def _run_one(self, campaign_id: str, *, branch: str | None = None, reconcile_uncertain: bool = False) -> dict[str, Any]:
        campaign = self.store.campaign(campaign_id)
        status = campaign["status"]
        if status in TERMINAL_STATUSES:
            self._write_report(campaign_id)
            return self.status(campaign_id)
        current_job_id: str | None = None
        try:
            self._assert_invocation_authorized()
            if self._reconcile_running_attempts(campaign_id) and not reconcile_uncertain:
                self._write_report(campaign_id)
                return self.status(campaign_id)
            if reconcile_uncertain:
                self.store.reconcile_uncertain_attempts(campaign_id)
            if self.store.uncertain_attempts(campaign_id):
                self._write_report(campaign_id)
                return self.status(campaign_id)

            jobs = self.store.jobs(campaign_id)
            if not jobs:
                validate_inputs(self.store.context(campaign_id), self.repo_root, self.output_dir / campaign_id)
            job = self._propose_initial(campaign_id) if not jobs else self._next_incomplete_job(jobs)
            if job is None:
                if any(row["status"] == "DEFERRED_LIMIT" for row in jobs):
                    self.store.set_campaign_status(campaign_id, "LIMIT_REACHED")
                self._write_report(campaign_id)
                return self.status(campaign_id)
            current_job_id = job["id"]
            if job["status"] == "REPAIR_REQUIRED":
                self.store.set_campaign_status(campaign_id, "PAUSED")
            elif job["status"] == "DEFERRED_LIMIT":
                self.store.set_campaign_status(campaign_id, "LIMIT_REACHED")
            elif job["status"] in {"PROPOSING", "PROPOSED"} and not self.store.claim_job_reservation(job["id"]):
                self.store.set_campaign_status(campaign_id, "LIMIT_REACHED")
            else:
                if job["status"] == "PROPOSING":
                    job = self._propose_job(campaign_id, job["id"])
                if job["status"] == "PROPOSED":
                    self._execute_and_check(campaign_id, job["id"], branch=branch)
                    job = self.store.job(job["id"])
                if job["status"] == "CHECKED":
                    self._review(campaign_id, job["id"], branch=branch)
        except (ProviderError, ContractError, ToolRestrictionError, ToolVerificationError, ValueError, RuntimeError, OSError) as caught:
            error = self._as_provider_error(caught)
            self._record_failure(campaign_id, getattr(error, "job_id", None) or current_job_id, getattr(error, "attempt_id", None), error)
            if isinstance(error, BudgetExceededError):
                self.store.set_campaign_status(campaign_id, "BUDGET_EXHAUSTED")
            else:
                self.store.set_campaign_status(campaign_id, "PAUSED" if error.retryable else "FAILED")
        self._write_report(campaign_id)
        return self.status(campaign_id)

    def resume(self, campaign_id: str, *, branch: str | None = None, reconcile_uncertain: bool = False) -> dict[str, Any]:
        """Restore the persisted campaign configuration before any provider lookup."""

        self._restore_campaign_config(campaign_id)
        return self.run(campaign_id, branch=branch, reconcile_uncertain=reconcile_uncertain)

    def status(self, campaign_id: str) -> dict[str, Any]:
        summary = self.store.summary(campaign_id)
        return {
            "campaign_id": campaign_id,
            "status": summary["campaign"]["status"],
            "budget": summary["budget"],
            "jobs": summary["jobs"],
            "attempt_count": len(summary["attempts"]),
            "result_count": len(summary["results"]),
            "decisions": summary["decisions"],
            "failures": summary["failures"],
            "report_path": str(self.output_dir / campaign_id / "report.json"),
        }

    def _restore_campaign_config(self, campaign_id: str) -> None:
        persisted = self.store.config(campaign_id)
        self.config = PipelineConfig.from_dict(persisted)
        self.repo_root = Path(self.config.repo_root).resolve()
        self.output_dir = self._repo_path(self.config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _assert_invocation_authorized(self) -> None:
        configured = (self.config.thinker_provider, self.config.executor_provider)
        non_fixture = [provider for provider in configured if provider != "fixture"]
        if non_fixture and not self.config.live_opt_in:
            raise ProviderError(
                "non-fixture providers require explicit live opt-in",
                kind="authorization",
                details={"providers": non_fixture, "provider_call_performed": False, "live_call_performed": False},
            )
        if self.config.live_opt_in and self.config.verification_mode != "real":
            raise ProviderError("live opt-in requires real local-data verification mode", kind="authorization", details={"provider_call_performed": False, "live_call_performed": False})

    def _next_incomplete_job(self, jobs: list[Any]) -> Any | None:
        for job in jobs:
            decision = self.store.decision_for_job(job["campaign_id"], job["id"])
            if job["status"] == "CHECKED" and decision is not None:
                # A review decision and its state effects are separate durable
                # mutations. If the process stopped between those commits, the
                # decision is authoritative and must be replayed before this
                # completed job is skipped. Each effect is idempotent, so this
                # also safely handles a resume after the normal path applied it.
                self._apply_decision_status(job["campaign_id"], job["id"], decision["action"], decision["next_job_id"])
                continue
            if job["status"] in {"PROPOSING", "PROPOSED", "CHECKED", "REPAIR_REQUIRED", "DEFERRED_LIMIT"}:
                return job
        return None

    def _registered_task_context(self, campaign_id: str) -> dict[str, Any]:
        """Supply the actual callable contract, not just a schema field name."""

        if self.config.adaptive:
            return self._research_context(campaign_id)
        tool = registered_tools()[M5_VERIFICATION_TASK]
        mode = self.store.context(campaign_id)["verification_mode"]
        return {
            "registered_tasks": [{
                "task": tool.name,
                "tool": tool.name,
                "description": tool.description,
                "parameters_schema": proposal_schema()["properties"]["parameters"],
                "example_parameters": {"mode": mode, "event_index": 0},
                "evidence_scope": "One existing M5 event: source identity, trigger identity and exact 1h/2h/3h close-to-close outcomes. No new signal replay, fills, P&L or alpha conclusion.",
            }],
            "verification_mode": mode,
            "parameter_rules": "mode must equal verification_mode. event_index is a non-negative integer. Packet/source paths are supplied by the controller, not model parameters.",
            "campaign_budget": dict(self.store.budget(campaign_id)),
        }

    def _propose_initial(self, campaign_id: str) -> Any:
        requested_job_id = _id("job")
        try:
            job_id = self.store.ensure_initial_job(requested_job_id, campaign_id, 1, {}, "pending", status="PROPOSING")
        except RuntimeError as exc:
            error = BudgetExceededError("job")
            error.job_id = requested_job_id
            self.store.set_campaign_status(campaign_id, "BUDGET_EXHAUSTED")
            raise error from exc
        return self._propose_job(campaign_id, job_id)

    def _validate_proposal_payload(self, campaign_id: str, proposal: dict[str, Any], expected_parent_result_id: str | None) -> dict[str, Any]:
        proposal = validate_proposal(proposal)
        if proposal["task"] not in registered_tools(adaptive=self.config.adaptive):
            raise ToolRestrictionError(f"proposal selected an unregistered task: {proposal['task']}")
        context = self.store.context(campaign_id)
        if proposal["parameters"]["mode"] != context["verification_mode"]:
            raise ToolRestrictionError("proposal mode does not match the campaign's frozen verification mode")
        supplied_parent = proposal.get("parent_result_id")
        if supplied_parent != expected_parent_result_id:
            raise ToolRestrictionError("proposal parent_result_id does not match the frozen parent result")
        if self.config.adaptive and expected_parent_result_id:
            for result in self.store.summary(campaign_id)["results"]:
                previous = json.loads(result["evidence_json"])
                if previous.get("task") == proposal["task"] and previous.get("parameters") == proposal["parameters"]:
                    raise ToolRestrictionError("adaptive follow-up must be a distinct experiment")
        return proposal

    def _validate_proposal_for_job(self, campaign_id: str, job_id: str, proposal: dict[str, Any]) -> dict[str, Any]:
        job = self.store.job(job_id)
        expected_parent_result_id = None
        if job["parent_job_id"]:
            parent = self.store.job(job["parent_job_id"])
            if not parent["result_id"]:
                raise ToolRestrictionError("follow-up proposal has no completed parent result")
            expected_parent_result_id = str(parent["result_id"])
        return self._validate_proposal_payload(campaign_id, proposal, expected_parent_result_id)

    def _propose_job(self, campaign_id: str, job_id: str) -> Any:
        context = self.store.context(campaign_id)
        history = {"previous_decisions": [dict(row) for row in self.store.decisions(campaign_id)][-3:], "previous_failures": [dict(row) for row in self.store.failures(campaign_id)][-3:]}
        job = self.store.job(job_id)
        proposal: dict[str, Any] | None = None
        if job["specification_hash"] != "pending":
            try:
                proposal = self._validate_proposal_for_job(campaign_id, job_id, json.loads(job["specification_json"]))
            except (json.JSONDecodeError, ContractError, ValueError) as exc:
                raise ToolRestrictionError("durable proposal is invalid; refusing to redispatch the thinker") from exc
        else:
            validator = partial(self._validate_proposal_for_job, campaign_id, job_id)
            proposal = self._completed_response(campaign_id, job_id, "proposal", validator)
            if proposal is None:
                prompt = (
                    f"Return only a schema-valid research proposal. Set task exactly to {M5_VERIFICATION_TASK!r}; it is a registered identifier. "
                    "Put descriptive prose in hypothesis, question and rationale. For this initial proposal, parent_result_id must be null. "
                    "Propose the bounded check for event_index 0 in the supplied mode. The controller and registered tool perform the numerical work; "
                    "your role is to specify this job from the supplied context. Task contract, context and history: "
                    + json.dumps({**context, **history, **self._registered_task_context(campaign_id)}, sort_keys=True)
                )
                if self.config.adaptive:
                    prompt = ("Propose one bounded research experiment using the registered tasks. Start with a population horizon summary before selecting a cohort diagnostic. "
                              "Use parent_result_id=null. Specify a falsifiable question and respect the campaign budget. Return only schema-valid JSON. "
                              + json.dumps({**context, **history, **self._research_context(campaign_id),
                                            "study_context": self._study_preview(campaign_id, {"mode": context["verification_mode"]})}, sort_keys=True))
                proposal = self._provider_call(campaign_id, job_id, role="thinker", phase="proposal", prompt=prompt, schema=proposal_schema(adaptive=self.config.adaptive), metadata={"context": context, "verification_mode": context["verification_mode"]}, validator=validator)
        proposal = self._validate_proposal_for_job(campaign_id, job_id, proposal)
        self.store.update_job_specification(job_id, proposal, object_hash(proposal))
        self.store.update_job(job_id, status="PROPOSED")
        return self.store.job(job_id)

    def _validate_execution_plan_for_proposal(self, plan: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
        plan = validate_execution_plan(plan)
        if plan["task"] != proposal["task"] or plan["tool"] != proposal["task"]:
            raise ToolRestrictionError("executor may only select the proposal task and registered verify_m5_horizons tool")
        expected_parameters = dict(proposal["parameters"])
        if proposal["task"] in STUDY_TASKS and expected_parameters.get("grouping") == "choose":
            expected_parameters["grouping"] = plan["parameters"].get("grouping")
        if canonical_json(plan["parameters"]) != canonical_json(expected_parameters):
            raise ToolRestrictionError("executor parameters differ from the frozen proposal")
        if plan["invariants"] != proposal["invariants"]:
            raise ToolRestrictionError("executor invariants differ from the frozen proposal")
        return plan

    def _execute_and_check(self, campaign_id: str, job_id: str, *, branch: str | None = None) -> None:
        job = self.store.job(job_id)
        existing = self.store.result_for_job(job_id)
        if existing is not None:
            if job["result_id"] != existing["id"] or job["status"] != "CHECKED":
                self.store.update_job(job_id, status="CHECKED", result_id=existing["id"])
            return
        proposal = self._validate_proposal_for_job(campaign_id, job_id, json.loads(job["specification_json"]))
        if proposal["task"] in STUDY_TASKS:
            self._execute_study_job(campaign_id, job_id, proposal)
            return
        history = {"previous_decisions": [dict(row) for row in self.store.decisions(campaign_id)][-3:], "previous_failures": [dict(row) for row in self.store.failures(campaign_id)][-3:]}
        prompt = (
            f"Return only a schema-valid execution plan. Set task and tool exactly to {M5_VERIFICATION_TASK!r}. "
            "Copy parameters and the ordered invariants array verbatim from the frozen proposal. Do not paraphrase or add paths. "
            "Use workspace_manifest=null unless a manifest actually exists. The controller executes the registered numerical tool after validating your plan. "
            "Frozen proposal, task contract and history: "
            + json.dumps({"proposal": proposal, **history, **self._registered_task_context(campaign_id)}, sort_keys=True)
        )
        validator = partial(self._validate_execution_plan_for_proposal, proposal=proposal)
        plan = self._completed_response(campaign_id, job_id, "execution", validator)
        if plan is None:
            plan = self._provider_call(campaign_id, job_id, role="executor", phase="execution", prompt=prompt, schema=execution_schema(), metadata={"proposal": proposal}, validator=validator)
        plan = self._validate_execution_plan_for_proposal(plan, proposal)
        context = self.store.context(campaign_id)
        params = dict(proposal["parameters"])
        params.update({"baseline_packet": context["baseline_packet"], "horizon_packet": context["horizon_packet"]})
        if context.get("evidence_hashes", {}).get("source_path") and proposal["parameters"]["mode"] == "real":
            params["source_csv"] = context["evidence_hashes"]["source_path"]
        params["mode"] = context["verification_mode"]
        if branch == "tamper":
            params["tamper_target_timestamp"] = "1999-01-01T00:00:00Z"
        workspace = self.output_dir / campaign_id / job_id
        workspace.mkdir(parents=True, exist_ok=True)
        tool_context = ToolContext(self.repo_root, workspace, frozen_inputs=context.get("evidence_hashes", {}))
        input_identity = current_input_identity(params, tool_context)
        cache_key = verification_cache_key(params, tool_context)
        cached = self.store.cached_result(cache_key)
        cache_rejection: str | None = None
        artifact_dir = workspace / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        if cached is not None:
            valid, cache_rejection = self._validate_cached_result(dict(cached), cache_key, input_identity)
        else:
            valid = False
        if valid and cached is not None:
            evidence = json.loads(cached["evidence_json"])
            evidence = {**evidence, "reused_evidence": True, "reused_from_result_id": cached["id"], "reused_from_artifact_dir": cached["artifact_dir"]}
            result_id = _id("result")
        else:
            evidence = execute_registered_tool(plan["tool"], params, tool_context)
            evidence["reused_evidence"] = False
            # The registered tool's deterministic ID identifies its numerical
            # output; the durable result ID must remain unique across
            # campaigns so a recomputation cannot collide with historical DB
            # rows.
            result_id = _id("result")
        evidence["result_id"] = result_id
        evidence["cache_key"] = cache_key
        evidence["input_identity"] = input_identity
        if cache_rejection:
            evidence["cache_reuse_rejected"] = cache_rejection
        (artifact_dir / "evidence.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if evidence.get("status") not in {"VERIFIED", "FAILED"}:
            raise ToolVerificationError("registered checker returned an unsupported status")
        self.store.create_result(result_id, job_id, str(evidence["status"]), str(artifact_dir), evidence, object_hash(evidence), cache_key=cache_key)

    def _validate_cached_result(self, row: Mapping[str, Any], cache_key: str, input_identity: dict[str, Any]) -> tuple[bool, str | None]:
        try:
            if row["status"] != "VERIFIED" or row["cache_key"] != cache_key:
                return False, "stored result row is not a matching VERIFIED cache entry"
            evidence = json.loads(row["evidence_json"])
            if not isinstance(evidence, dict) or evidence.get("status") != "VERIFIED":
                return False, "stored evidence is not VERIFIED"
            if evidence.get("cache_key") != cache_key:
                return False, "stored evidence cache key differs"
            if evidence.get("result_id") != row["id"]:
                return False, "stored evidence result_id differs from the result row"
            if evidence.get("input_identity") != input_identity:
                return False, "stored evidence input identity differs from current inputs"
            if object_hash(evidence) != row["result_hash"]:
                return False, "stored evidence hash differs from result_hash"
            artifact_dir = Path(row["artifact_dir"]).resolve()
            allowed_roots = (self.output_dir.resolve(), (self.repo_root / "research" / "results").resolve())
            if not any(artifact_dir == root or root in artifact_dir.parents for root in allowed_roots):
                return False, "stored artifact directory is outside the research boundary"
            artifact = json.loads((artifact_dir / "evidence.json").read_text(encoding="utf-8"))
            if artifact != evidence:
                return False, "stored artifact evidence differs from the durable result"
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            return False, f"stored cache artifact is unreadable or malformed: {type(exc).__name__}"
        return True, None

    def _review(self, campaign_id: str, job_id: str, *, branch: str | None) -> None:
        existing_decision = self.store.decision_for_job(campaign_id, job_id)
        if existing_decision is not None:
            self._apply_decision_status(campaign_id, job_id, existing_decision["action"], existing_decision["next_job_id"])
            return
        job = self.store.job(job_id)
        if not job["result_id"]:
            raise ToolRestrictionError("cannot review a job without a checker result")
        evidence_row = self.store.result(job["result_id"])
        evidence = json.loads(evidence_row["evidence_json"])
        self._validate_result_artifact(dict(evidence_row), evidence)
        current_proposal = json.loads(job["specification_json"])
        metadata = {"evidence": evidence, "proposal": current_proposal, "objective": self.store.context(campaign_id)["question"]}
        if branch and self.config.thinker_provider == "fixture":
            fixture = self._provider("thinker")
            if isinstance(fixture, FixtureProvider):
                fixture.branch = branch
        history = {"previous_decisions": [dict(row) for row in self.store.decisions(campaign_id)][-3:], "previous_failures": [dict(row) for row in self.store.failures(campaign_id)][-3:]}
        prompt = (
            "Review the supplied deterministic checker evidence and return only schema-valid JSON. Include the exact current result_id in evidence_refs. "
            "Choose STOP, REJECT, REPAIR, or PROPOSE_NEXT with non-empty reasons; next_job must be null unless proposing a follow-up. "
            "A follow-up requires VERIFIED evidence, a registered task, the same verification mode and parent_result_id equal to the current result_id. "
            "Respect the supplied budget: a next proposal at the job cap is saved only. A verified event does not establish alpha. Evidence, task contract and history: "
            + json.dumps({**metadata, **history, **self._registered_task_context(campaign_id)}, sort_keys=True)
        )
        validator = partial(self._validate_review_for_evidence, campaign_id, evidence=evidence)
        review = self._completed_response(campaign_id, job_id, "review", validator)
        if review is None:
            review = self._provider_call(campaign_id, job_id, role="thinker", phase="review", prompt=prompt, schema=review_schema(adaptive=self.config.adaptive), metadata=metadata, validator=validator)
        next_job_id = None
        if review["action"] == "PROPOSE_NEXT":
            if evidence["status"] != "VERIFIED":
                raise ToolRestrictionError("PROPOSE_NEXT requires VERIFIED checker evidence")
            next_spec = validate_proposal(review["next_job"])
            self._validate_proposal_payload(campaign_id, next_spec, str(evidence["result_id"]))
            existing_child = self.store.followup_for_parent(campaign_id, job_id)
            if existing_child is not None:
                if object_hash(json.loads(existing_child["specification_json"])) != object_hash(next_spec):
                    raise ToolRestrictionError("durable follow-up proposal differs from the reviewed proposal")
                next_job_id = existing_child["id"]
            else:
                requested_job_id = _id("job")
                next_job_id, _ = self.store.ensure_followup_job(requested_job_id, campaign_id, int(job["sequence"]) + 1, next_spec, object_hash(next_spec), job_id)
                durable_child = self.store.job(next_job_id)
                if object_hash(json.loads(durable_child["specification_json"])) != object_hash(next_spec):
                    raise ToolRestrictionError("durable follow-up proposal differs from the reviewed proposal")
        decision_evidence = {
            "result_id": evidence["result_id"],
            "checker_status": evidence["status"],
            "verification_status": evidence["status"],
            "evidence_path": str(Path(evidence_row["artifact_dir"]) / "evidence.json"),
            "review_evidence_refs": list(review["evidence_refs"]),
            "reused_evidence": bool(evidence.get("reused_evidence", False)),
        }
        self.store.create_decision(_id("decision"), campaign_id, job_id, "review", review["action"], review["reasons"], decision_evidence, next_job_id)
        self._apply_decision_status(campaign_id, job_id, review["action"], next_job_id)

    def _validate_review_for_evidence(self, campaign_id: str, value: Any, evidence: dict[str, Any]) -> dict[str, Any]:
        review = validate_review(value)
        if evidence["result_id"] not in review["evidence_refs"]:
            raise ToolRestrictionError("review evidence_refs must include the current checker result_id")
        if review["action"] == "PROPOSE_NEXT":
            if evidence["status"] != "VERIFIED":
                raise ToolRestrictionError("PROPOSE_NEXT requires VERIFIED checker evidence")
            self._validate_proposal_payload(campaign_id, review["next_job"], str(evidence["result_id"]))
        return review

    def _validate_result_artifact(self, row: Mapping[str, Any], evidence: dict[str, Any]) -> None:
        if row["status"] != evidence.get("status") or object_hash(evidence) != row["result_hash"]:
            raise ToolRestrictionError("durable checker evidence failed integrity validation")
        try:
            artifact = json.loads((Path(row["artifact_dir"]) / "evidence.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ToolRestrictionError("durable checker artifact is unreadable") from exc
        if artifact != evidence:
            raise ToolRestrictionError("durable checker artifact differs from durable evidence")

    def _apply_decision_status(self, campaign_id: str, job_id: str, action: str, next_job_id: str | None) -> None:
        if action == "REPAIR":
            self.store.update_job(job_id, status="REPAIR_REQUIRED")
            self.store.set_campaign_status(campaign_id, "PAUSED")
        elif action == "STOP":
            self.store.set_campaign_status(campaign_id, "STOPPED")
        elif action == "REJECT":
            self.store.set_campaign_status(campaign_id, "REJECTED")
        elif action == "PROPOSE_NEXT":
            next_status = self.store.job(next_job_id)["status"] if next_job_id else "DEFERRED_LIMIT"
            self.store.set_campaign_status(campaign_id, "LIMIT_REACHED" if next_status == "DEFERRED_LIMIT" else "RUNNING")

    def _as_provider_error(self, caught: Exception) -> ProviderError:
        if isinstance(caught, ProviderError):
            return caught
        if isinstance(caught, ToolInputAccessError):
            return ProviderError(str(caught), kind="data_access", retryable=True, details={"exception_type": type(caught).__name__, "infrastructure": True, "provider_call_performed": False})
        if isinstance(caught, ContractError):
            return ProviderError(str(caught), kind="contract_error", details={"exception_type": type(caught).__name__, "provider_call_performed": False})
        if isinstance(caught, ToolRestrictionError):
            return ProviderError(str(caught), kind="tool_restriction", details={"exception_type": type(caught).__name__, "provider_call_performed": False})
        if isinstance(caught, ToolVerificationError):
            return ProviderError(str(caught), kind="tool_verification", details={"exception_type": type(caught).__name__, "provider_call_performed": False})
        return ProviderError(str(caught), kind="pipeline_error", retryable=isinstance(caught, OSError), details={"exception_type": type(caught).__name__, "provider_call_performed": False})

    def _record_failure(self, campaign_id: str, job_id: str | None, attempt_id: str | None, error: ProviderError) -> None:
        details = dict(error.details)
        details.setdefault("resume_safe", error.retryable)
        details.setdefault("provider_call_performed", False)
        self.store.create_failure(_id("failure"), campaign_id, job_id=job_id, attempt_id=attempt_id, kind=error.kind, message=str(error), retryable=error.retryable, details=details)

    def _reconcile_running_attempts(self, campaign_id: str) -> bool:
        attempts = self.store.running_attempts(campaign_id)
        for attempt in attempts:
            error = ProviderError("previous process ended with an uncertain in-flight attempt; explicit reconciliation is required", kind="interrupted_uncertain", retryable=True, details={"manual_reconciliation_required": True, "provider_call_performed": None})
            self.store.finish_attempt(attempt["id"], status="PAUSED", error_kind=error.kind, error_message=str(error))
            self._record_failure(campaign_id, attempt["job_id"], attempt["id"], error)
            self.store.set_campaign_status(campaign_id, "PAUSED")
        return bool(attempts)

    @staticmethod
    def _read_optional_json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return value if isinstance(value, dict) else {}
