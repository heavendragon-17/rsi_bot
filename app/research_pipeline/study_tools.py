"""Bounded population studies over immutable local M5 research packets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from app.backtest import signal_replay_data
from app.backtest.signal_replay_data import load_ohlcv_csv
from research import btc_m5_horizon_diagnostic as diagnostic
from research import btc_m5_regime_review as regimes

from . import study_checks
from .contracts import object_hash
from .tools import (
    ToolContext,
    ToolInputAccessError,
    ToolRestrictionError,
    ToolVerificationError,
    _load_json,
    _safe_path,
    _sha256,
)

SCHEMA = "btc-m5-study-evidence-v1"
TASKS = ("summarize_m5_horizons", "compare_m5_cohorts")
GROUPINGS = ("calendar_year", "trend", "volatility")
HORIZONS = (60, 120, 180)
LIMITATIONS = [
    "Descriptive gross close-to-close historical returns; not fills, profit, or executable P&L.",
    "Fees, spread, slippage, funding and overlapping-position constraints are omitted.",
    "All four saved horizons must be complete to include an event at any reported horizon.",
    "Preparation eligibility is inherited from the hash-bound parent packet; strategy gates are not replayed.",
    "Cohort sizes vary, calendar years may be partial, and no selection-adjusted significance or alpha is assessed.",
]


def _parameters(task: str, params: dict[str, Any]) -> dict[str, Any]:
    if task not in TASKS:
        raise ToolRestrictionError(f"unregistered study task: {task}")
    if params.get("mode") not in {"fixture", "real"}:
        raise ToolRestrictionError("study mode must be fixture or real")
    allowed = {"mode", "baseline_packet", "horizon_packet", "source_csv", "h1_source_csv"}
    selected = {"mode": params["mode"]}
    if task == "compare_m5_cohorts":
        allowed |= {"horizon_minutes", "grouping"}
        horizon = params.get("horizon_minutes")
        grouping = params.get("grouping")
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon not in HORIZONS:
            raise ToolRestrictionError("horizon_minutes must be 60, 120, or 180")
        if grouping not in GROUPINGS:
            raise ToolRestrictionError("grouping must be calendar_year, trend, or volatility")
        selected.update(horizon_minutes=horizon, grouping=grouping)
    if set(params) - allowed:
        raise ToolRestrictionError("unsupported study parameters: " + ", ".join(sorted(set(params) - allowed)))
    return selected


def _inputs(params: dict[str, Any], context: ToolContext) -> tuple[dict, dict, dict]:
    root = context.repo_root.resolve()
    results = ((root / "research/results").resolve(),)
    data = ((root / "research/data").resolve(), (root / "app/backtest/data").resolve())
    paths = {key: _safe_path(params.get(key), label=key, roots=roots, base_dir=root)
             for key, roots in (("baseline_packet", results), ("horizon_packet", results),
                                ("source_csv", data), ("h1_source_csv", data))}
    # Validate child files as well, so a symlink cannot escape an allowed packet.
    for key, directory, name in (("manifest", "horizon_packet", "manifest.json"),
                                 ("signals", "horizon_packet", "signals.csv"),
                                 ("baseline", "horizon_packet", "baseline.csv"),
                                 ("parent_manifest", "baseline_packet", "manifest.json"),
                                 ("parent_signals", "baseline_packet", "signals.csv")):
        paths[key] = _safe_path(str(paths[directory] / name), label=key, roots=results)
    manifest = _load_json(paths["manifest"])
    hashes = {"source_sha256": _sha256(paths["source_csv"]),
              "h1_source_sha256": _sha256(paths["h1_source_csv"]),
              "horizon_manifest_sha256": _sha256(paths["manifest"]),
              "horizon_signals_sha256": _sha256(paths["signals"]),
              "horizon_baseline_sha256": _sha256(paths["baseline"]),
              "baseline_manifest_sha256": _sha256(paths["parent_manifest"]),
              "baseline_signals_sha256": _sha256(paths["parent_signals"])}
    identity = {**hashes, "source_path": str(paths["source_csv"]),
                "h1_source_path": str(paths["h1_source_csv"]), "mode": params["mode"]}
    mismatches = []
    for key, current in hashes.items():
        if key == "baseline_signals_sha256":
            continue  # Its required expectation is frozen inside the horizon manifest.
        expected = context.frozen_inputs.get(key)
        if not isinstance(expected, str) or len(expected) != 64:
            mismatches.append(f"missing frozen {key}")
        elif expected != current:
            mismatches.append(f"frozen {key} differs")
    for key in ("source_path", "h1_source_path"):
        expected = context.frozen_inputs.get(key)
        if expected is not None and str(Path(expected).resolve()) != identity[key]:
            mismatches.append(f"frozen {key} differs")
    def object_field(value: Any, name: str) -> dict:
        if not isinstance(value, dict):
            raise ToolVerificationError(f"manifest {name} must be an object")
        return value

    inputs = object_field(manifest.get("inputs"), "inputs")
    files = object_field(inputs.get("files"), "inputs.files")
    for timeframe, key in (("5m", "source_sha256"), ("1h", "h1_source_sha256")):
        facts = object_field(files.get(timeframe), f"inputs.files.{timeframe}")
        if facts.get("sha256") != hashes[key]:
            mismatches.append(f"manifest {timeframe} source SHA-256 differs or is missing")
    parent_facts = object_field(manifest.get("parent"), "parent")
    parent_hashes = object_field(parent_facts.get("files_sha256"), "parent.files_sha256")
    definitions = object_field(manifest.get("definitions"), "definitions")
    object_field(manifest.get("comparator"), "comparator")
    for filename, key in (("manifest.json", "baseline_manifest_sha256"), ("signals.csv", "baseline_signals_sha256")):
        if parent_hashes.get(filename) != hashes[key]:
            mismatches.append(f"parent {filename} SHA-256 differs or is missing")
    parent_manifest = _load_json(paths["parent_manifest"])
    if (manifest.get("completion_status") != "SUCCESS" or manifest.get("definition_version") != diagnostic.VERSION
            or definitions.get("horizons_minutes") != list(study_checks.HORIZONS)
            or parent_manifest.get("completion_status") != "SUCCESS"
            or parent_facts.get("run_id") != parent_manifest.get("run_id")):
        mismatches.append("saved packet completion, horizon definition, or parent identity differs")
    identity["mismatches"] = mismatches
    return paths, manifest, identity


def _read_rows(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, keep_default_na=False, usecols=lambda column: column in study_checks.REQUIRED or column == "timeframe")
    except OSError as exc:
        raise ToolInputAccessError(f"could not read saved study rows: {path}: {exc}") from exc


def _metrics(rows: pd.DataFrame) -> dict[str, Any]:
    # Existing metrics also support excursion fields. This tool reports only
    # independently checked returns, so any saved excursions are never surfaced.
    return diagnostic.metrics(rows.assign(mfe_pct=0.0, mae_pct=0.0))


def _comparison(signals: pd.DataFrame, baseline: pd.DataFrame, horizon: int,
                grouping: str = "all", group: str = "ALL") -> dict[str, Any]:
    output: dict[str, Any] = {"horizon_minutes": horizon, "grouping": grouping, "group": group}
    for label, frame in (("signal", signals), ("baseline", baseline)):
        metrics = _metrics(frame)
        for target, original in (("n", "n_matched"), ("total_n", "n_total"), ("complete_n", "n_complete"),
                                  ("mean_return_pct", "mean_return_pct"), ("median_return_pct", "median_return_pct"),
                                  ("positive_return_share", "positive_return_share")):
            output[f"{label}_{target}"] = metrics[original]
    signal_mean, baseline_mean = output["signal_mean_return_pct"], output["baseline_mean_return_pct"]
    output["signal_minus_baseline_pp"] = None if signal_mean is None or baseline_mean is None else signal_mean - baseline_mean
    return output


def _summary(signals: pd.DataFrame, baseline: pd.DataFrame) -> list[dict[str, Any]]:
    return [_comparison(signals.loc[signals.horizon_minutes.eq(horizon)],
                        baseline.loc[baseline.horizon_minutes.eq(horizon)], horizon) for horizon in HORIZONS]


def _artifact(evidence: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    evidence["evidence_id"] = object_hash(evidence)
    directory = _safe_path(str(context.workspace / "artifacts"), label="artifact directory",
                           roots=(context.workspace.resolve(),), must_exist=False)
    directory.mkdir(parents=True, exist_ok=True)
    for name in ("evidence.json", "study_tables.csv"):
        _safe_path(str(directory / name), label="study artifact", roots=(directory,), must_exist=False)
    (directory / "evidence.json").write_text(json.dumps(evidence, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    pd.DataFrame(evidence["tables"]).to_csv(directory / "study_tables.csv", index=False)
    return evidence


def execute_study_tool(task: str, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Return checked descriptive evidence; never trust saved returns as raw data."""
    selected = _parameters(task, params)
    evidence: dict[str, Any] = {
        "schema": SCHEMA, "task": task, "parameters": selected, "status": "FAILED",
        "verification_mode": "fixture_validation" if selected["mode"] == "fixture" else "real_local_data",
        "alpha_assessment": "NOT_ASSESSED", "horizons_minutes": list(HORIZONS),
        "population_rule": "Saved parent IDs and preparation-eligible baseline; all-four-complete at 60/120/180/240 minutes.",
        "input_identity": {}, "tables": [], "checks": [], "limitations": list(LIMITATIONS),
        "checker_sha256": {Path(path).name: _sha256(Path(path))
                           for path in (__file__, study_checks.__file__, diagnostic.__file__, regimes.__file__, signal_replay_data.__file__)},
    }
    if selected["mode"] == "fixture":
        evidence["limitations"].append("Synthetic supplied packet/source validation only; not real-market verification.")
    try:
        paths, manifest, identity = _inputs(params, context)
        evidence["input_identity"] = identity
        evidence["checks"].append({"name": "frozen_input_identity", "passed": not identity["mismatches"],
                                   "mismatches": identity["mismatches"]})
        if identity["mismatches"]:
            return _artifact(evidence, context)
        signals = study_checks.normalize_rows(_read_rows(paths["signals"]), "signals")
        baseline = study_checks.normalize_rows(_read_rows(paths["baseline"]), "baseline")
        source = load_ohlcv_csv(paths["source_csv"], "5m")
        for label, frame in (("signals", signals), ("baseline", baseline)):
            evidence["checks"].extend(study_checks.check_raw_returns(frame, source, label))
        evidence["checks"].extend(study_checks.check_population(signals, baseline, _read_rows(paths["parent_signals"]), manifest, source))
        if not all(check["passed"] for check in evidence["checks"]):
            return _artifact(evidence, context)
        if task == "summarize_m5_horizons":
            tables = _summary(signals, baseline)
        else:
            grouping, horizon = selected["grouping"], selected["horizon_minutes"]
            signals, baseline = (frame.loc[frame.horizon_minutes.eq(horizon)].copy() for frame in (signals, baseline))
            if grouping == "calendar_year":
                for frame in (signals, baseline):
                    frame["calendar_year"] = frame.trigger_close_at.dt.year.astype(str)
                evidence["checks"].append({"name": "calendar_year_uses_trigger_close_utc", "passed": True})
            else:
                hourly = load_ohlcv_csv(paths["h1_source_csv"], "1h")
                study_checks.validate_h1_source(hourly)
                daily = regimes.daily_context(hourly)
                signals, baseline = (regimes.attach_labels(frame, daily) for frame in (signals, baseline))
                for label, frame in (("signals", signals), ("baseline", baseline)):
                    check = study_checks.check_label_alignment(frame, daily)
                    check["population"] = label
                    evidence["checks"].append(check)
                evidence["unavailable_regime_events"] = {
                    label: int(frame.loc[frame[grouping].eq("UNAVAILABLE"), "event_id"].nunique())
                    for label, frame in (("signals", signals), ("baseline", baseline))}
            groups = sorted(set(signals[grouping]) | set(baseline[grouping]))
            tables = [_comparison(signals.loc[signals[grouping].eq(group)], baseline.loc[baseline[grouping].eq(group)],
                                  horizon, grouping, group) for group in groups]
        _, _, final_identity = _inputs(params, context)
        evidence["checks"].append({"name": "inputs_unchanged_during_check", "passed": identity == final_identity})
        if all(check["passed"] for check in evidence["checks"]):
            evidence.update(status="VERIFIED", tables=tables)
    except ToolRestrictionError:
        raise
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        evidence["checks"].append({"name": "study_input_validation", "passed": False, "error": str(exc)[:1000]})
    return _artifact(evidence, context)


def prepare_study_context(params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Compact saved summaries for planning; full raw checker remains authoritative."""
    # Preparation also accepts an injected proposal's cohort fields.
    base = {key: value for key, value in params.items() if key in {"mode", "baseline_packet", "horizon_packet", "source_csv", "h1_source_csv"}}
    _parameters("summarize_m5_horizons", base)
    paths, _, identity = _inputs(base, context)
    if identity["mismatches"]:
        raise ToolVerificationError("study preview input identity mismatch: " + ", ".join(identity["mismatches"]))
    signals = study_checks.normalize_rows(_read_rows(paths["signals"]), "signals")
    baseline = study_checks.normalize_rows(_read_rows(paths["baseline"]), "baseline")
    return {"schema": "btc-m5-study-context-v1", "status": "UNVERIFIED",
            "description": "Saved packet preview only. Numerical and population checks run in the study tool.",
            "alpha_assessment": "NOT_ASSESSED", "horizons_minutes": list(HORIZONS),
            "available_groupings": list(GROUPINGS),
            "calendar_years": sorted(signals.trigger_close_at.dt.year.unique().tolist()),
            "tables": _summary(signals, baseline), "input_identity": identity,
            "limitations": list(LIMITATIONS)}
