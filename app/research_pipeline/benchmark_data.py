"""Load one verified frozen population for a fixed nine-candidate benchmark.

The existing study verifier remains authoritative for raw returns, parent
identity and eligibility. This boundary only reuses its verified population,
checks causal labels once per event, and aggregates the registered cohorts.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import pandas as pd

from . import study_checks, study_tools
from .tools import ToolContext, ToolRestrictionError, ToolVerificationError


@dataclass
class BenchmarkData:
    """Four-horizon rows and descriptive tables sharing one verified identity."""

    signals: pd.DataFrame
    baseline: pd.DataFrame
    summary: dict
    candidates: list[dict]
    input_identity: dict
    checks: list[dict]
    timings: dict


def _require_identity(current: dict, expected: dict) -> None:
    if current.get("mismatches") or current != expected:
        raise ToolVerificationError("benchmark input identity differs from the fully verified population")


def verify_benchmark_inputs(params: dict, context: ToolContext, expected_identity: dict) -> None:
    """Rehash every frozen input after statistics; reject any identity change."""
    study_tools._parameters("summarize_m5_horizons", params)
    _, _, identity = study_tools._inputs(params, context)
    _require_identity(identity, expected_identity)


def _attach_population(rows: pd.DataFrame, daily: pd.DataFrame,
                       population: str, checks: list[dict]) -> pd.DataFrame:
    # Four horizons share one event close. A unique-event join avoids repeating
    # daily features four times and keeps the independent alignment check small.
    unique = rows.drop_duplicates("event_id")[["event_id", "trigger_close_at", "horizon_minutes"]]
    labels = study_tools.regimes.attach_labels(unique, daily)
    columns = ["available_at", *study_tools.GROUPINGS]
    if (not {"event_id", "trigger_close_at", "horizon_minutes", *columns}.issubset(labels)
            or labels.event_id.duplicated().any()
            or len(labels) != len(unique)
            or set(labels.event_id) != set(unique.event_id)):
        raise ToolVerificationError(f"{population}: incomplete or duplicate event label mapping")
    mapping = labels.set_index("event_id")
    aligned = mapping.loc[unique.event_id]
    if (not (aligned.trigger_close_at.to_numpy() == unique.trigger_close_at.to_numpy()).all()
            or not (aligned.horizon_minutes.to_numpy() == unique.horizon_minutes.to_numpy()).all()):
        raise ToolVerificationError(f"{population}: event identity changed during label mapping")
    check = study_checks.check_label_alignment(labels, daily)
    check["population"] = population
    checks.append(check)
    if not check["passed"]:
        raise ToolVerificationError(f"{population}: causal regime alignment failed")
    if not labels.calendar_year.eq(labels.trigger_close_at.dt.year.astype(str)).all():
        raise ToolVerificationError(f"{population}: calendar year label differs from UTC trigger close")
    checks.append({"name": "calendar_year_uses_trigger_close_utc", "population": population, "passed": True})
    for column in columns:
        rows[column] = rows.event_id.map(mapping[column])
    # NaT availability is legitimate before the first daily close; categorical
    # missing values are not. Insufficient history stays explicitly UNAVAILABLE.
    if rows[list(study_tools.GROUPINGS)].isna().any().any():
        raise ToolVerificationError(f"{population}: missing event label mapping")
    checks.append({"name": "complete_event_label_mapping", "population": population,
                   "passed": True, "checked_events": len(unique), "checked_rows": len(rows)})
    return rows


def _catalog(signals: pd.DataFrame, baseline: pd.DataFrame, mode: str) -> list[dict]:
    candidates = []
    for horizon in study_tools.HORIZONS:
        signal_rows = signals.loc[signals.horizon_minutes.eq(horizon)]
        baseline_rows = baseline.loc[baseline.horizon_minutes.eq(horizon)]
        for grouping in study_tools.GROUPINGS:
            groups = sorted(set(signal_rows[grouping]) | set(baseline_rows[grouping]))
            tables = [study_tools._comparison(
                signal_rows.loc[signal_rows[grouping].eq(group)],
                baseline_rows.loc[baseline_rows[grouping].eq(group)], horizon, grouping, group,
            ) for group in groups]
            candidates.append({"task": "compare_m5_cohorts",
                               "parameters": {"mode": mode, "horizon_minutes": horizon, "grouping": grouping},
                               "tables": tables})
    return candidates


def load_benchmark_data(params: dict, context: ToolContext) -> BenchmarkData:
    """Verify once, then build all nine standard cohorts without provider calls.

    Only the standard summary evidence is written, under ``verification`` in
    the caller's workspace. A failed raw, identity, population or label check
    raises ``ToolVerificationError`` before any benchmark data is returned.
    Excluded events and the fourth horizon remain present in the returned rows.
    """
    started = perf_counter()
    verification_context = ToolContext(context.repo_root, context.workspace / "verification", context.frozen_inputs)
    summary = study_tools.execute_study_tool("summarize_m5_horizons", params, verification_context)
    verified_at = perf_counter()
    if summary.get("status") != "VERIFIED":
        failed = [check["name"] for check in summary.get("checks", []) if not check.get("passed")]
        raise ToolVerificationError("full study verification failed: " + ", ".join(failed))
    identity = deepcopy(summary["input_identity"])
    checks = deepcopy(summary["checks"])
    try:
        paths, _, current_identity = study_tools._inputs(params, context)
        _require_identity(current_identity, identity)
        checks.append({"name": "benchmark_reload_input_identity", "passed": True})
        signals = study_checks.normalize_rows(study_tools._read_rows(paths["signals"]), "signals")
        baseline = study_checks.normalize_rows(study_tools._read_rows(paths["baseline"]), "baseline")
        hourly = study_tools.load_ohlcv_csv(paths["h1_source_csv"], "1h")
        study_checks.validate_h1_source(hourly)
        daily = study_tools.regimes.daily_context(hourly)
        signals = _attach_population(signals, daily, "signals", checks)
        baseline = _attach_population(baseline, daily, "baseline", checks)
        candidates = _catalog(signals, baseline, params["mode"])
        verify_benchmark_inputs(params, context, identity)
        checks.append({"name": "inputs_unchanged_during_benchmark_load", "passed": True})
    except (ToolRestrictionError, ToolVerificationError):
        raise
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        raise ToolVerificationError(f"benchmark data validation failed: {exc}") from exc
    completed = perf_counter()
    timings: dict[str, Any] = {
        "full_verification_seconds": verified_at - started,
        "reload_and_catalog_seconds": completed - verified_at,
        "total_seconds": completed - started,
    }
    return BenchmarkData(signals, baseline, summary, candidates, identity, checks, timings)
