"""Frozen retrospective policy comparison using no model providers."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from typing import Any

from .benchmark_data import load_benchmark_data, verify_benchmark_inputs
from .benchmark_reporting import comparison_report, render_report
from .benchmark_source import load_benchmark_source, verify_benchmark_source
from .benchmark_statistics import _validate_settings, evaluate_diagnostics
from .contracts import object_hash
from .inputs import tool_parameters, validate_inputs
from .measurements import runtime_measurements
from .study_tools import execute_study_tool
from .tools import ToolContext, ToolVerificationError, _safe_path, _sha256


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _code_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parents[2]
    files = sorted(Path(__file__).parent.glob("*.py")) + [
        root / "btc_ai_pipeline.py", root / "research/btc_m5_horizon_diagnostic.py",
        root / "research/btc_m5_regime_review.py", root / "app/backtest/signal_replay_data.py",
    ]
    return {path.relative_to(root).as_posix(): _sha256(path) for path in files}


def _match_evidence(actual: dict, expected: dict, label: str) -> None:
    if actual.get("status") != "VERIFIED" or any(actual.get(key) != expected.get(key)
                                                for key in ("tables", "input_identity", "checker_sha256")):
        raise ToolVerificationError(f"{label} does not reproduce frozen checked evidence")


def _scripted_run(source: dict, root: Path, output: Path) -> dict:
    """Time a separate summary and fixed-policy follow-up, excluding evaluator work."""
    started = perf_counter()
    saved = source["context"]
    summary = execute_study_tool("summarize_m5_horizons", tool_parameters(saved, {}),
                                 ToolContext(root, output / "summary", saved["evidence_hashes"]))
    _match_evidence(summary, source["summary_evidence"], "scripted summary")
    choice = max(summary["tables"], key=lambda row: (abs(row["signal_minus_baseline_pp"]), -row["horizon_minutes"]))
    parameters = {"mode": saved["verification_mode"], "horizon_minutes": choice["horizon_minutes"], "grouping": "calendar_year"}
    if parameters != source["scripted_parameters"]:
        raise ToolVerificationError("scripted policy changed after the protocol freeze")
    cohort = execute_study_tool("compare_m5_cohorts", tool_parameters(saved, parameters),
                                ToolContext(root, output / "cohort", saved["evidence_hashes"]))
    if cohort["status"] != "VERIFIED" or cohort["input_identity"] != summary["input_identity"]:
        raise ToolVerificationError("scripted cohort did not pass the frozen evidence checks")
    return {"provider_calls": 0, "parameters": parameters, "elapsed_seconds": perf_counter() - started,
            "summary": summary, "cohort": cohort,
            "timing_note": "One separate local summary plus fixed-policy cohort run, including their checks; uncontrolled load and cache state."}


def _candidate(candidates: list[dict], parameters: dict) -> dict:
    key = {name: parameters[name] for name in ("horizon_minutes", "grouping")}
    matches = [row for row in candidates if all(row["parameters"][name] == value for name, value in key.items())]
    if len(matches) != 1:
        raise ToolVerificationError("candidate catalog does not uniquely cover the frozen policy")
    return matches[0]


def _validate_statistics(catalog: list[dict], diagnostics: dict) -> None:
    if len(catalog) != 9 or len(diagnostics["candidates"]) != 9:
        raise ToolVerificationError("benchmark must cover exactly nine candidates")
    for candidate in catalog:
        cohorts = _candidate(diagnostics["candidates"], candidate["parameters"])["cohorts"]
        checked = {str(row["group"]): row for row in candidate["tables"]}
        if set(checked) != {str(row["group"]) for row in cohorts}:
            raise ToolVerificationError("statistical cohorts differ from checked catalog")
        for cohort in cohorts:
            row = checked[str(cohort["group"])]
            if any(row[name] != cohort[name] for name in ("signal_n", "baseline_n")):
                raise ToolVerificationError("statistical cohort support differs from checked catalog")
            expected, actual = row["signal_minus_baseline_pp"], cohort["delta_pp"]
            if (expected is None) != (actual is None) or (expected is not None and not math.isclose(expected, actual, rel_tol=1e-10, abs_tol=1e-10)):
                raise ToolVerificationError("statistical mean differs from checked catalog")


def run_selection_benchmark(repo_root: Path, db_path: Path, campaign_id: str, workspace: Path,
                            *, replications: int = 2000, block_lengths: tuple[int, ...] = (7, 28), seed: int = 20260905) -> dict:
    """Compare a saved live choice with a fixed policy; never open a provider."""
    _validate_settings(replications, block_lengths, seed)
    root = repo_root.resolve()
    output = _safe_path(str(workspace), label="benchmark workspace", roots=((root / "research/results").resolve(),),
                        must_exist=False, base_dir=root)
    if output.exists():
        raise FileExistsError(f"benchmark output already exists: {output}")
    source = load_benchmark_source(root, db_path, campaign_id)
    saved = source["context"]
    identity = validate_inputs(saved, root, output, adaptive=True)
    if identity != source["summary_evidence"]["input_identity"]:
        raise ToolVerificationError("current input identity differs from source campaign")
    code_hashes = _code_hashes()
    protocol = {
        "schema": "btc-selection-benchmark-protocol-v1", "created_at": datetime.now(UTC).isoformat(),
        "campaign_id": campaign_id, "source_hash": source["source_hash"], "source_artifacts": source["artifacts"],
        "input_identity": identity, "code_sha256": code_hashes,
        "runtime_versions": {package: version(package) for package in ("numpy", "pandas")},
        "policies": {"ai": source["ai_parameters"], "scripted": source["scripted_parameters"]},
        "scripted_rule": "Maximum absolute checked pooled gap; smaller horizon wins ties; fixed calendar_year grouping.",
        "candidate_space": [{"horizon_minutes": horizon, "grouping": grouping}
                            for horizon in (60, 120, 180) for grouping in ("calendar_year", "trend", "volatility")],
        "statistics": {"replications": replications, "block_lengths": list(block_lengths), "seed": seed,
                       "influence_block_days": 28, "interval_quantiles": [0.025, 0.975]},
        "population": "Original all-four-horizon complete events with separate signal and baseline denominators.",
        "interpretation": "Retrospective post-selection descriptive pilot; AI already saw this historical dataset. No untouched holdout.",
        "decision_rule": "BENEFIT_NOT_ESTABLISHED: one exposed choice cannot establish general selection or cost superiority.",
        "new_provider_call_cap": 0,
    }
    output.mkdir(parents=True, exist_ok=False)
    _write(output / "protocol.json", protocol)
    _write(output / "source_snapshot.json", source)
    frozen_outputs = {name: _sha256(output / name) for name in ("protocol.json", "source_snapshot.json")}
    try:
        verify_benchmark_source(source)
        scripted = _scripted_run(source, root, output / "scripted_policy")
        started = perf_counter()
        params = tool_parameters(saved, {})
        tool_context = ToolContext(root, output / "evaluation", saved["evidence_hashes"])
        data = load_benchmark_data(params, tool_context)
        _match_evidence(data.summary, source["summary_evidence"], "catalog summary")
        ai_catalog = _candidate(data.candidates, source["ai_parameters"])
        if ai_catalog["tables"] != source["selected_evidence"]["tables"]:
            raise ToolVerificationError("catalog differs from recorded AI cohort tables")
        scripted_catalog = _candidate(data.candidates, source["scripted_parameters"])
        if scripted_catalog["tables"] != scripted["cohort"]["tables"]:
            raise ToolVerificationError("catalog differs from independently executed scripted tables")
        statistics_started = perf_counter()
        diagnostics = evaluate_diagnostics(data.signals, data.baseline, replications=replications, block_lengths=block_lengths, seed=seed)
        statistics_seconds = perf_counter() - statistics_started
        _validate_statistics(data.candidates, diagnostics)
        verify_benchmark_inputs(params, tool_context, identity)
        verify_benchmark_source(source)
        if _code_hashes() != code_hashes:
            raise ToolVerificationError("benchmark or checker code changed during evaluation")
        if any(_sha256(output / name) != digest for name, digest in frozen_outputs.items()):
            raise ToolVerificationError("frozen protocol or source snapshot changed during evaluation")
        evaluator_seconds = perf_counter() - started
        _write(output / "candidate_catalog.json", {"summary": data.summary, "candidates": data.candidates,
                                                  "input_identity": data.input_identity, "checks": data.checks})
        _write(output / "diagnostics.json", diagnostics)
        report = {
            "schema": "btc-selection-benchmark-report-v1", "status": "COMPLETED", "campaign_id": campaign_id,
            "verdict": "BENEFIT_NOT_ESTABLISHED", "new_provider_calls": 0, "source_hash": source["source_hash"],
            "protocol_hash": object_hash(protocol), "comparison": comparison_report(source, diagnostics),
            "resources": {"historical_ai": runtime_measurements(source["summary"]),
                          "scripted": {key: value for key, value in scripted.items() if key not in {"summary", "cohort"}},
                          "evaluator": {"elapsed_seconds": evaluator_seconds, "statistics_seconds": statistics_seconds,
                                        "data_timings": data.timings, "provider_calls": 0}},
            "validity": {"source_unchanged": True, "input_identity_unchanged": True, "checker_and_evaluator_unchanged": True,
                         "saved_summary_reproduced": True, "saved_ai_cohorts_reproduced": True,
                         "scripted_policy_reproduced": True, "candidate_statistics_match_checked_tables": True},
            "artifacts_sha256": {name: _sha256(output / name) for name in
                                 ("protocol.json", "source_snapshot.json", "candidate_catalog.json", "diagnostics.json")},
        }
        _write(output / "report.json", report)
        (output / "report.md").write_text(render_report(report, diagnostics), encoding="utf-8")
        return report
    except Exception as exc:
        _write(output / "report.json", {"schema": "btc-selection-benchmark-report-v1", "status": "FAILED",
                                       "campaign_id": campaign_id, "new_provider_calls": 0,
                                       "error_type": type(exc).__name__, "error": str(exc), "protocol_hash": object_hash(protocol)})
        raise
