"""Read-only provenance boundary for an accepted two-study live benchmark source."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from .contracts import object_hash, validate_execution_plan, validate_proposal, validate_review
from .study_contracts import COHORT_TASK, GROUPINGS, HORIZONS, SUMMARY_TASK


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"benchmark source: {message}")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        _require(key not in value, f"duplicate JSON key {key}")
        value[key] = item
    return value


def _constant(value: str) -> None:
    raise ValueError(f"benchmark source: nonfinite JSON constant {value}")


def _json(value: str) -> Any:
    def finite_float(raw: str) -> float:
        number = float(raw)
        _require(math.isfinite(number), "nonfinite JSON number")
        return number
    return json.loads(value, object_pairs_hook=_object, parse_constant=_constant, parse_float=finite_float)


def _path(root: Path, raw: str | Path) -> Path:
    path = Path(raw)
    return (root / path).resolve() if not path.is_absolute() else path.resolve()


def _snapshot(db_path: Path, campaign_id: str) -> dict[str, Any]:
    _require(db_path.is_file(), "database does not exist")
    # Do not instantiate PipelineStore: its constructor initializes/migrates the DB.
    # mode=ro retains WAL visibility; immutable=1 would incorrectly ignore a WAL.
    connection = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        def rows(sql: str) -> list[dict[str, Any]]:
            return [dict(row) for row in connection.execute(sql, (campaign_id,))]
        campaigns = rows("SELECT * FROM campaigns WHERE id=?")
        budgets = rows("SELECT * FROM budgets WHERE campaign_id=?")
        _require(len(campaigns) == len(budgets) == 1, "campaign/budget missing")
        return {
            "campaign": campaigns[0], "budget": budgets[0],
            "jobs": rows("SELECT * FROM jobs WHERE campaign_id=? ORDER BY sequence,id"),
            "attempts": rows("SELECT * FROM attempts WHERE campaign_id=? ORDER BY started_at,id"),
            "results": rows("SELECT r.* FROM results r JOIN jobs j ON j.id=r.job_id WHERE j.campaign_id=? ORDER BY j.sequence,r.id"),
            "decisions": rows("SELECT * FROM decisions WHERE campaign_id=? ORDER BY created_at,id"),
            "failures": rows("SELECT * FROM failures WHERE campaign_id=? ORDER BY created_at,id"),
        }
    finally:
        connection.close()


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def scripted_parameters(summary_evidence: dict[str, Any]) -> dict[str, Any]:
    """Fixed policy: largest absolute pooled gap, smaller horizon tie, calendar year."""
    _require(summary_evidence.get("task") == SUMMARY_TASK, "scripted policy requires summary")
    _require(summary_evidence.get("parameters") == {"mode": "real"}, "scripted policy requires real mode")
    tables: Any = summary_evidence.get("tables")
    _require(isinstance(tables, list) and len(tables) == 3, "summary requires three horizons")
    horizons = [row.get("horizon_minutes") for row in tables]
    _require(all(type(h) is int for h in horizons) and sorted(horizons) == list(HORIZONS), "summary horizons differ")
    _require(all(_finite(row.get("signal_minus_baseline_pp")) for row in tables), "summary gap must be finite")
    chosen = min(tables, key=lambda row: (-abs(row["signal_minus_baseline_pp"]), row["horizon_minutes"]))
    return {"mode": "real", "horizon_minutes": chosen["horizon_minutes"], "grouping": "calendar_year"}


def _validate_envelope(summary: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    campaign, budget = summary["campaign"], summary["budget"]
    config, context = _json(campaign["config_json"]), _json(campaign["context_json"])
    _require(isinstance(config, dict) and isinstance(context, dict), "configuration/context must be objects")
    _require(campaign["status"] == "STOPPED", "campaign must be STOPPED")
    _require(config.get("adaptive") is True and config.get("live_opt_in") is True, "campaign must be live adaptive")
    _require(config.get("verification_mode") == context.get("verification_mode") == "real", "real mode required")
    _require(context.get("alpha_assessment") == "NOT_ASSESSED", "source alpha scope differs")
    _require(context.get("question") == campaign["question"], "context question differs")
    _require(not summary["failures"], "accepted campaign contains failures")
    _require(len(summary["jobs"]) == len(summary["results"]) == len(summary["decisions"]) == 2, "requires exactly two accepted studies")
    _require(len(summary["attempts"]) == 5, "requires exactly five provider attempts")
    for role, count in (("thinker", 3), ("executor", 2)):
        _require(config.get(f"{role}_provider") in {"codex", "opencode"}, "model provider required")
        _require(budget[f"{role}_calls"] == count, "attempt budget count differs")
        _require(budget[f"max_{role}_calls"] == config.get(f"max_{role}_calls") == count, "call cap differs")
    _require(budget["jobs_started"] == budget["max_jobs"] == config.get("max_jobs") == 2, "job budget differs")
    return config, context


def _validate_attempts(summary: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = summary["jobs"]
    expected = [(jobs[0]["id"], "thinker", "proposal"), (jobs[0]["id"], "executor", "execution"),
                (jobs[0]["id"], "thinker", "review"), (jobs[1]["id"], "executor", "execution"),
                (jobs[1]["id"], "thinker", "review")]
    payloads = []
    validators = {"proposal": validate_proposal, "execution": validate_execution_plan, "review": validate_review}
    for attempt, (job_id, role, phase) in zip(summary["attempts"], expected, strict=True):
        _require((attempt["job_id"], attempt["role"], attempt["phase"]) == (job_id, role, phase), "attempt sequence differs")
        _require(attempt["status"] == "COMPLETED" and attempt["error_kind"] is None, "attempt is not completed cleanly")
        _require(attempt["provider"] == config[f"{role}_provider"] and attempt["model"] == config[f"{role}_model"], "attempt model/provider differs")
        request = _json(attempt["request_json"])
        _require(all(request.get(key) == attempt[key] for key in ("provider", "model", "phase", "role")), "request identity differs")
        _require(request.get("effort") == config.get(f"{role}_effort"), "request effort differs")
        _require(attempt["finished_at"] is not None and attempt["started_at"] <= attempt["finished_at"], "attempt time invalid")
        payloads.append(validators[phase](_json(attempt["response_json"])))
    return payloads


def _validate_tables(evidence: dict[str, Any]) -> None:
    tables: Any = evidence.get("tables")
    parameters = evidence["parameters"]
    _require(isinstance(tables, list) and bool(tables), "study tables missing")
    expected_grouping = "all" if evidence["task"] == SUMMARY_TASK else parameters["grouping"]
    if expected_grouping != "all":
        _require(expected_grouping in GROUPINGS, "unregistered table grouping")
    seen = set()
    for row in tables:
        key = (row["horizon_minutes"], row["group"])
        _require(key not in seen and isinstance(row["group"], str) and bool(row["group"]), "duplicate or empty table group")
        seen.add(key)
        _require(row["grouping"] == expected_grouping, "table grouping differs from execution")
        if expected_grouping == "all":
            _require(row["group"] == "ALL", "summary group differs")
        else:
            _require(row["horizon_minutes"] == parameters["horizon_minutes"], "table horizon differs from execution")
        for population in ("signal", "baseline"):
            counts = [row[f"{population}_{suffix}"] for suffix in ("n", "complete_n", "total_n")]
            _require(all(type(n) is int and n >= 0 for n in counts) and counts == sorted(counts), "table counts invalid")
            for metric in ("mean_return_pct", "median_return_pct", "positive_return_share"):
                value = row[f"{population}_{metric}"]
                _require(_finite(value) if counts[0] else value is None, "table metric/count mismatch")
            if counts[0]:
                _require(0 <= row[f"{population}_positive_return_share"] <= 1, "positive share invalid")
        gap = row["signal_minus_baseline_pp"]
        if row["signal_n"] and row["baseline_n"]:
            _require(_finite(gap) and math.isclose(gap, row["signal_mean_return_pct"] - row["baseline_mean_return_pct"],
                                                rel_tol=1e-12, abs_tol=1e-12), "table gap arithmetic differs")
        else:
            _require(gap is None, "empty table contrast must be null")


def _validate_evidence(root: Path, output: Path, job: dict[str, Any], result: dict[str, Any],
                       plan: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    evidence = _json(result["evidence_json"])
    _require(result["job_id"] == job["id"] and result["id"] == job["result_id"] == evidence.get("result_id"), "result/job identity differs")
    _require(evidence.get("schema") == "btc-m5-study-evidence-v1", "evidence schema differs")
    _require(result["status"] == evidence.get("status") == "VERIFIED", "evidence is not VERIFIED")
    _require(evidence.get("verification_mode") == "real_local_data" and evidence.get("reused_evidence") is False, "requires fresh real evidence")
    _require(evidence.get("alpha_assessment") == "NOT_ASSESSED", "evidence scope differs")
    _require(evidence.get("task") == plan["task"] and evidence.get("parameters") == plan["parameters"], "evidence execution parameters differ")
    _validate_tables(evidence)
    _require(evidence.get("executor_diagnostic") == plan["diagnostic_rationale"], "executor rationale differs")
    _require(object_hash(evidence) == result["result_hash"], "result hash differs")
    base = {k: v for k, v in evidence.items() if k not in {
        "evidence_id", "checker_elapsed_seconds", "result_id", "reused_evidence", "executor_diagnostic", "cache_key"}}
    _require(object_hash(base) == evidence.get("evidence_id"), "deterministic evidence hash differs")
    checks = evidence.get("checks")
    _require(isinstance(checks, list) and bool(checks) and all(c.get("passed") is True for c in checks), "evidence checks failed or missing")
    names = {check.get("name") for check in checks}
    _require({"frozen_input_identity", "inputs_unchanged_during_check", "nonempty_matched_population"} <= names, "required identity/population checks missing")
    identity, checker = evidence.get("input_identity"), evidence.get("checker_sha256")
    _require(isinstance(identity, dict) and identity.get("mismatches") == [] and identity.get("mode") == "real", "input identity invalid")
    hash_keys = {"source_sha256", "h1_source_sha256", "horizon_manifest_sha256", "horizon_signals_sha256",
                 "horizon_baseline_sha256", "baseline_manifest_sha256"}
    frozen = context.get("evidence_hashes", {})
    _require(all(key in frozen and frozen[key] == identity.get(key) for key in hash_keys), "frozen context hashes differ")
    checker_keys = {"study_tools.py", "study_checks.py", "btc_m5_horizon_diagnostic.py", "btc_m5_regime_review.py", "signal_replay_data.py"}
    _require(isinstance(checker, dict) and set(checker) == checker_keys, "checker fingerprint missing")
    for digest in [*checker.values(), *(identity.get(k) for k in hash_keys | {"baseline_signals_sha256"})]:
        _require(isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), "invalid fingerprint")
    cache = object_hash({"task": plan["tool"], "parameters": plan["parameters"], "inputs": identity, "checker": checker})
    _require(evidence.get("cache_key") == result["cache_key"] == cache, "cache identity differs")
    artifact = _path(root, result["artifact_dir"]) / "evidence.json"
    artifact = artifact.resolve()
    expected = (output / job["campaign_id"] / job["id"] / "artifacts/evidence.json").resolve()
    _require(artifact.is_relative_to(root / "research/results") and artifact == expected, "artifact path escapes accepted workspace")
    raw = artifact.read_bytes()
    _require(_json(raw.decode("utf-8")) == evidence, "artifact differs from result")
    return evidence, {"path": str(artifact), "sha256": hashlib.sha256(raw).hexdigest(), "result_id": result["id"]}


def _validate_chain(root: Path, summary: dict[str, Any]) -> dict[str, Any]:
    config, context = _validate_envelope(summary)
    jobs, results = summary["jobs"], summary["results"]
    output = _path(root, config["output_dir"])
    _require(output.is_relative_to(root / "research/results"), "artifact output root is outside research/results")
    proposals = [validate_proposal(_json(job["specification_json"])) for job in jobs]
    for index, (job, proposal) in enumerate(zip(jobs, proposals, strict=True)):
        _require(job["sequence"] == index + 1 and job["status"] == "CHECKED" and job["budget_reserved"] == 1, "job state differs")
        _require(object_hash(proposal) == job["specification_hash"], "specification hash differs")
    _require(proposals[0]["task"] == SUMMARY_TASK and proposals[1]["task"] == COHORT_TASK, "study order differs")
    _require(jobs[0]["parent_job_id"] is None and proposals[0].get("parent_result_id") is None, "root has a parent")
    _require(jobs[1]["parent_job_id"] == jobs[0]["id"] and proposals[1].get("parent_result_id") == jobs[0]["result_id"], "child parent link differs")
    initial, execution1, review1, execution2, review2 = _validate_attempts(summary, config)
    _require(initial == proposals[0] and review1["next_job"] == proposals[1], "proposal response/specification differs")
    evidence, artifacts = [], []
    for index, (proposal, plan, review) in enumerate(zip(proposals, [execution1, execution2], [review1, review2], strict=True)):
        _require(plan["task"] == plan["tool"] == proposal["task"] and plan.get("workspace_manifest") is None, "execution tool or workspace differs")
        expected_params = dict(proposal["parameters"])
        if expected_params.get("grouping") == "choose":
            expected_params["grouping"] = plan["parameters"].get("grouping")
        _require(expected_params == plan["parameters"] and plan["parameters"]["mode"] == "real", "execution changed frozen parameters")
        _require(plan["invariants"] == proposal["invariants"], "execution changed ordered invariants")
        ev, artifact = _validate_evidence(root, output, jobs[index], results[index], plan, context)
        evidence.append(ev)
        artifacts.append(artifact)
        action = "PROPOSE_NEXT" if index == 0 else "STOP"
        next_job = jobs[1]["id"] if index == 0 else None
        decision = summary["decisions"][index]
        _require(review["action"] == action and review["evidence_refs"] == [results[index]["id"]], "review evidence/action differs")
        _require(decision["job_id"] == jobs[index]["id"] and decision["phase"] == "review" and decision["action"] == action, "decision differs")
        _require(decision["next_job_id"] == next_job and _json(decision["reasons_json"]) == review["reasons"], "decision next job/reasons differ")
        decision_evidence = _json(decision["evidence_json"])
        _require(decision_evidence.get("result_id") == results[index]["id"]
                 and decision_evidence.get("checker_status") == decision_evidence.get("verification_status") == "VERIFIED"
                 and decision_evidence.get("review_evidence_refs") == review["evidence_refs"]
                 and decision_evidence.get("reused_evidence") is False, "decision evidence differs")
        _require(_path(root, decision_evidence["evidence_path"]) == Path(artifact["path"]), "decision artifact path differs")
    _require(evidence[0]["input_identity"] == evidence[1]["input_identity"] and evidence[0]["checker_sha256"] == evidence[1]["checker_sha256"], "studies have different frozen identities")
    _require(evidence[0]["cache_key"] != evidence[1]["cache_key"], "follow-up is not distinct")
    _require(evidence[0]["population_rule"] == evidence[1]["population_rule"], "population rule differs")
    return {"context": context, "summary_evidence": evidence[0], "selected_evidence": evidence[1],
            "ai_parameters": dict(evidence[1]["parameters"]), "scripted_parameters": scripted_parameters(evidence[0]),
            "artifacts": artifacts}


def load_benchmark_source(repo_root: Path, db_path: Path, campaign_id: str) -> dict[str, Any]:
    """Freeze one accepted chain without controllers, provider lookup, or DB writes."""
    root = repo_root.resolve()
    path = _path(root, db_path)
    try:
        _require(path.is_relative_to(root), "database is outside repository")
        summary = _snapshot(path, campaign_id)
        validated = _validate_chain(root, summary)
        return {"repo_root": str(root), "db_path": str(path), "campaign_id": campaign_id,
                "summary": summary, "source_hash": object_hash(summary), **validated}
    except (OSError, sqlite3.Error, KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise ValueError(f"benchmark source cannot be loaded: {exc}") from exc


def verify_benchmark_source(source: dict[str, Any]) -> None:
    """Reject durable or in-memory source drift after the benchmark choice freezes."""
    try:
        fresh = load_benchmark_source(Path(source["repo_root"]), Path(source["db_path"]), source["campaign_id"])
        _require(fresh == source, "source snapshot or artifact bytes changed after freezing")
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"benchmark source changed after freezing: {exc}") from exc
