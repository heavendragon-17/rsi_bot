"""Diagnostic-specific acceptance over the row-level scientific checker.

The row-level checker (``checker.py``) validates supplied rows against raw
candles and enforces disjointness, but it cannot tell whether rows were
omitted, swapped between groups, truncated, or drawn from a different
window: any internally consistent pair passes. This module closes that gap
for one frozen diagnostic declaration. It reconstructs the declared
eligible population directly from the raw candles — expected decision
timestamps per group, exclusion counts, metrics and verdict — and requires
exact agreement with the submitted candidate/baseline files and the
summary/result artifacts:

- every expected decision timestamp present exactly once, in its declared
  group (omissions, extras, swaps and window changes fail);
- recomputed group means, difference and verdict bound to ``summary.json``
  and ``result.json`` within a frozen tolerance.

The existing numerical checker stays underneath as the row-level layer; the
checker must pass before acceptance is evaluated. All fixtures in tests are
synthetic and hand-calculated. No dataset, holdout, trading configuration
or strategy is opened or changed beyond reading the caller-supplied files.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.m5_checks import checker

ACCEPTANCE_SCHEMA = "m5-acceptance-v1"
METRIC_ATOL = 1e-9
SUPPORTED_REJECTION_RULES = ("reject_if_nonpositive",)
_HEX64_RE = re.compile(r"\A[0-9a-f]{64}\Z")


def _reject_constant(token: str) -> Any:
    raise ValueError(f"non-strict JSON constant {token!r}")


def _load_strict_json(path: Path, label: str) -> Any:
    """Parse JSON with no NaN/Infinity constants and no duplicate keys."""
    def _no_duplicates(pairs):
        mapping: dict[str, Any] = {}
        for key, value in pairs:
            if key in mapping:
                raise ValueError(f"{label}: duplicate JSON key {key!r}")
            mapping[key] = value
        return mapping

    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"),
                          object_pairs_hook=_no_duplicates,
                          parse_constant=_reject_constant)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} artifact unreadable or not strict JSON: {exc}") from exc


def _finite_number(value: Any) -> float | None:
    """A real finite number, or None for anything else (bool included)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


@dataclass(frozen=True)
class Declaration:
    """Frozen population contract for one diagnostic.

    ``candles_sha256`` pins the exact raw input bytes. The window bounds are
    decision-close timestamps (inclusive start, exclusive end). ``target_hours``
    lists the UTC hours forming the candidate group; every other eligible
    hour forms the baseline group. ``rejection_rule`` names the frozen
    verdict mapping (``reject_if_nonpositive``: difference <= 0 → rejected).
    """

    candles_sha256: str
    window_start_close_utc: str
    window_end_close_utc: str
    horizon_minutes: int
    target_hours_utc: tuple[int, ...]
    rejection_rule: str = "reject_if_nonpositive"


FROZEN_HOUR_SEASONALITY = Declaration(
    candles_sha256="97d3c169eaa68cbfeadfea5251180ab581dc09506b066306a544e27b5c0fb18d",
    window_start_close_utc="2022-08-28T00:00:00Z",
    window_end_close_utc="2026-08-28T00:00:00Z",
    horizon_minutes=60,
    target_hours_utc=(13, 14, 15, 16),
)


def _parse_utc(value: str, label: str) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        raise ValueError(f"declaration {label} requires an explicit timezone offset")
    return stamp.tz_convert("UTC")


def validate_declaration(declaration: Declaration) -> list[str]:
    """Type/range/enum validation for a declaration; [] means valid.

    Runs before either the row-level or the reconstruction path so a
    malformed declaration always yields a structured rejection, never an
    uncaught exception or a vacuous pass.
    """
    reasons: list[str] = []
    if not isinstance(declaration, Declaration):
        return ["declaration must be a Declaration"]
    if not isinstance(declaration.candles_sha256, str) \
            or _HEX64_RE.match(declaration.candles_sha256) is None:
        reasons.append("declaration candles_sha256 must be 64 lowercase hex characters")
    try:
        window_start = _parse_utc(declaration.window_start_close_utc, "window_start_close_utc")
        window_end = _parse_utc(declaration.window_end_close_utc, "window_end_close_utc")
    except (ValueError, TypeError) as exc:
        reasons.append(f"declaration window is invalid: {exc}")
    else:
        if not window_start < window_end:
            reasons.append("declaration window is empty or inverted")
    horizon = declaration.horizon_minutes
    if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon <= 0:
        reasons.append("declaration horizon_minutes must be a positive integer")
    elif horizon % 5 != 0:
        reasons.append("declaration horizon_minutes must be a multiple of 5 minutes")
    hours = declaration.target_hours_utc
    if not isinstance(hours, (tuple, list)) or not hours:
        reasons.append("declaration target_hours_utc must be a non-empty list")
    else:
        bad = [h for h in hours
               if not isinstance(h, int) or isinstance(h, bool) or not 0 <= h <= 23]
        if bad:
            reasons.append(f"declaration target_hours_utc entries must be integers 0-23: {bad!r}")
        elif len(set(hours)) != len(list(hours)):
            reasons.append("declaration target_hours_utc entries must be unique")
    if declaration.rejection_rule not in SUPPORTED_REJECTION_RULES:
        reasons.append(
            f"unsupported declaration rejection_rule {declaration.rejection_rule!r}")
    return reasons


def reconstruct(candles_path: Path, declaration: Declaration) -> dict[str, Any]:
    """Rebuild the declared eligible population from the raw candles.

    Returns expected candidate/baseline decision-close sets plus exclusion
    counts. Raises ``ValueError`` on a hash mismatch or an unusable input.
    """
    problems = validate_declaration(declaration)
    if problems:
        raise ValueError("invalid declaration: " + "; ".join(problems))
    digest = hashlib.sha256(Path(candles_path).read_bytes()).hexdigest()
    if digest != declaration.candles_sha256:
        raise ValueError("candles sha256 does not match the declaration")
    window_start = _parse_utc(declaration.window_start_close_utc, "window_start_close_utc")
    window_end = _parse_utc(declaration.window_end_close_utc, "window_end_close_utc")
    if not window_start < window_end:
        raise ValueError("declaration window is empty or inverted")
    candles = checker.load_candles(candles_path)
    close_times = pd.DatetimeIndex(candles["_close_time"])
    steps = declaration.horizon_minutes // 5
    if declaration.horizon_minutes % 5 != 0 or steps <= 0:
        raise ValueError("declaration horizon must be a positive multiple of 5 minutes")
    position_of = {t: i for i, t in enumerate(close_times)}
    stamps = pd.DatetimeIndex(candles["timestamp"])
    breaks = np.zeros(len(stamps), dtype=np.int64)
    breaks[1:] = np.asarray(stamps[1:] - stamps[:-1]) != np.timedelta64(5, "m")
    prefix = breaks.cumsum()
    candidate: set[pd.Timestamp] = set()
    baseline: set[pd.Timestamp] = set()
    excluded = {"missing_target": 0, "gap": 0, "outside_window": 0}
    horizon = pd.Timedelta(minutes=declaration.horizon_minutes)
    for i, close_time in enumerate(close_times):
        if not window_start <= close_time < window_end:
            excluded["outside_window"] += 1
            continue
        target_time = close_time + horizon
        if target_time not in position_of:
            excluded["missing_target"] += 1
            continue
        end = position_of[target_time]
        if end - i != steps or prefix[end] != prefix[i]:
            excluded["gap"] += 1
            continue
        (candidate if close_time.hour in declaration.target_hours_utc else baseline).add(close_time)
    return {
        "candidate_times": candidate,
        "baseline_times": baseline,
        "excluded": excluded,
        "candles_rows": len(candles),
    }


def _decision_set(rows: pd.DataFrame) -> set[pd.Timestamp]:
    return set(pd.DatetimeIndex(rows["decision_time_utc"]))


def accept(
    *,
    candles_path: Path,
    candidate_path: Path,
    baseline_path: Path,
    summary_path: Path | None = None,
    result_path: Path | None = None,
    declaration: Declaration = FROZEN_HOUR_SEASONALITY,
) -> dict[str, Any]:
    """Accept or reject a submitted diagnostic pair under a declaration.

    The row-level checker runs first and must pass; acceptance then requires
    exact population agreement plus metric/verdict binding when summary and
    result artifacts are supplied.
    """
    reasons: list[str] = []
    reasons.extend(f"declaration: {problem}" for problem in validate_declaration(declaration))
    if reasons:
        return {
            "schema": ACCEPTANCE_SCHEMA,
            "accepted": False,
            "reasons": reasons,
            "checker": {"passed": None},
            "declaration": _declaration_dict(declaration),
        }
    try:
        check_report = checker.run_files(
            candles_path=Path(candles_path), candidate_path=Path(candidate_path),
            baseline_path=Path(baseline_path),
            horizon_minutes=declaration.horizon_minutes)
    except (ValueError, OSError) as exc:
        return {
            "schema": ACCEPTANCE_SCHEMA,
            "accepted": False,
            "reasons": [f"row-level checker input rejected: {exc}"],
            "checker": {"passed": False},
            "declaration": _declaration_dict(declaration),
        }
    if not check_report["passed"]:
        return {
            "schema": ACCEPTANCE_SCHEMA,
            "accepted": False,
            "reasons": ["row-level checker violations present"],
            "checker": _checker_summary(check_report),
            "declaration": _declaration_dict(declaration),
        }
    try:
        expected = reconstruct(candles_path, declaration)
    except (ValueError, OSError) as exc:
        return {
            "schema": ACCEPTANCE_SCHEMA,
            "accepted": False,
            "reasons": [f"population reconstruction rejected: {exc}"],
            "checker": _checker_summary(check_report),
            "declaration": _declaration_dict(declaration),
        }
    candidate = checker.load_diagnostic(candidate_path, "candidate", declaration.horizon_minutes)
    baseline = checker.load_diagnostic(baseline_path, "baseline", declaration.horizon_minutes)
    comparison: dict[str, Any] = {}
    for label, rows, expected_times in (
        ("candidate", candidate, expected["candidate_times"]),
        ("baseline", baseline, expected["baseline_times"]),
    ):
        submitted = _decision_set(rows[rows["included"]])
        missing = sorted(t.isoformat() for t in expected_times - submitted)
        unexpected = sorted(t.isoformat() for t in submitted - expected_times)
        comparison[label] = {
            "expected_n": len(expected_times),
            "submitted_n": len(submitted),
            "missing_n": len(missing),
            "unexpected_n": len(unexpected),
            "missing_sample": missing[:5],
            "unexpected_sample": unexpected[:5],
        }
        if missing:
            reasons.append(f"{label}: {len(missing)} declared timestamps omitted")
        if unexpected:
            reasons.append(f"{label}: {len(unexpected)} timestamps outside the declared population")
    metrics: dict[str, Any] | None = None
    if summary_path is not None or result_path is not None:
        metrics = _bind_metrics(
            candidate, baseline, summary_path, result_path, declaration,
            expected["excluded"], reasons)
    inputs: dict[str, Any] = dict(check_report.get("inputs") or {})
    for label, path in (("summary", summary_path), ("result", result_path)):
        if path is not None:
            try:
                raw = Path(path).read_bytes()
            except OSError:
                raw = None
            inputs[label] = {
                "path": Path(path).as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None,
            }
    accepted = not reasons
    return {
        "schema": ACCEPTANCE_SCHEMA,
        "accepted": accepted,
        "reasons": reasons,
        "checker": _checker_summary(check_report),
        "declaration": _declaration_dict(declaration),
        "reconstruction": {
            "candidate_n": len(expected["candidate_times"]),
            "baseline_n": len(expected["baseline_times"]),
            "excluded": expected["excluded"],
            "candles_rows": expected["candles_rows"],
        },
        "comparison": comparison,
        "metrics": metrics,
        "inputs": inputs,
    }


def _full_metrics(rows) -> dict[str, Any]:
    """Recomputed group statistics: n, mean, median and positive share."""
    eligible = rows.loc[rows["included"] & rows["outcome_status"].eq("COMPLETE")]
    values = pd.to_numeric(eligible["return_pct"], errors="coerce").to_numpy(dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        return {"n": 0, "mean": None, "median": None, "positive_share": None}
    return {"n": int(len(values)), "mean": float(np.mean(values)),
            "median": float(np.median(values)),
            "positive_share": float(np.mean(values > 0))}


def _bind_metrics(candidate, baseline, summary_path, result_path, declaration,
                  expected_excluded, reasons) -> dict[str, Any]:
    """Recompute group metrics from the CSVs and bind summary/result files.

    Every certified field is compared: per-group n/mean/median/positive
    share, the difference, the rule-derived verdict, the exclusion counts
    and — when the summary carries them — the declared window, horizon,
    hour split and candle identity. Declared numbers must be finite; NaN,
    infinities and non-numeric values fail instead of comparing vacuously.
    """
    bound: dict[str, Any] = {}
    candidate_stats, baseline_stats = _full_metrics(candidate), _full_metrics(baseline)
    bound["recomputed"] = {"candidate": candidate_stats, "baseline": baseline_stats}
    candidate_mean, baseline_mean = candidate_stats["mean"], baseline_stats["mean"]
    if candidate_mean is None or baseline_mean is None:
        reasons.append("metrics: a group has no eligible rows")
        return bound
    difference = candidate_mean - baseline_mean
    bound["difference_pp"] = difference
    if declaration.rejection_rule == "reject_if_nonpositive":
        verdict = "succeeded" if difference > 0 else "rejected"
    else:  # Unreachable: validate_declaration runs before either checking path.
        reasons.append(
            f"metrics: unsupported rejection_rule {declaration.rejection_rule!r}")
        return bound
    bound["verdict"] = verdict
    if summary_path is not None:
        try:
            summary = _load_strict_json(summary_path, "summary")
        except ValueError as exc:
            reasons.append(f"metrics: {exc}")
            return bound
        if not isinstance(summary, dict):
            reasons.append("metrics: summary artifact is not a JSON object")
            return bound
        for label, recomputed in (("candidate", candidate_stats),
                                  ("baseline", baseline_stats)):
            group = summary.get(label)
            if not isinstance(group, dict):
                reasons.append(f"metrics: summary has no {label} object")
                continue
            if group.get("n") != recomputed["n"]:
                reasons.append(f"metrics: summary {label} n does not match recomputation")
            for field in ("mean", "median", "positive_share"):
                declared = _finite_number(group.get(field))
                expected = recomputed[field]
                if declared is None or expected is None \
                        or abs(declared - expected) > METRIC_ATOL:
                    reasons.append(
                        f"metrics: summary {label} {field} does not match recomputation")
        declared_difference = _finite_number(summary.get("difference_pp"))
        if declared_difference is None or abs(declared_difference - difference) > METRIC_ATOL:
            reasons.append("metrics: summary difference does not match recomputation")
        if summary.get("verdict") != verdict:
            reasons.append("metrics: summary verdict does not follow the rejection rule")
        # Window, exclusion and candle-identity bindings apply when the summary
        # carries those fields (the frozen diagnostic always does); a summary
        # without them binds only the metrics above, which the report states.
        if "excluded" in summary and summary["excluded"] != expected_excluded:
            reasons.append("metrics: summary exclusion counts do not match reconstruction")
        for key, expected in (
            ("window_start_close_utc", declaration.window_start_close_utc),
            ("window_end_close_utc", declaration.window_end_close_utc),
            ("horizon_minutes", declaration.horizon_minutes),
            ("target_hours_utc", list(declaration.target_hours_utc)),
        ):
            if key in summary and summary[key] != expected:
                reasons.append(f"metrics: summary {key} disagrees with the declaration")
        candles = summary.get("candles")
        if isinstance(candles, dict) and candles.get("sha256") != declaration.candles_sha256:
            reasons.append("metrics: summary candle identity disagrees with the declaration")
        bound["summary_checked"] = True
        bound["summary_scope_checked"] = (
            ["n", "mean", "median", "positive_share", "difference_pp", "verdict"]
            + [key for key in (
                "window_start_close_utc", "window_end_close_utc", "horizon_minutes",
                "target_hours_utc", "excluded",
            ) if key in summary]
            + (["candles.sha256"] if isinstance(candles, dict) else [])
        )
    if result_path is not None:
        try:
            result = _load_strict_json(result_path, "result")
        except ValueError as exc:
            reasons.append(f"metrics: {exc}")
            return bound
        if not isinstance(result, dict):
            reasons.append("metrics: result artifact is not a JSON object")
            return bound
        if result.get("verdict") != verdict:
            reasons.append("metrics: result verdict does not follow the rejection rule")
        bound["result_checked"] = True
    return bound


def _checker_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "passed": report.get("passed"),
        "verdict": (report.get("scientific") or {}).get("verdict"),
        "violations": {k: len(v) for k, v in (report.get("violations") or {}).items()},
    }


def _declaration_dict(declaration: Declaration) -> dict[str, Any]:
    return {
        "candles_sha256": declaration.candles_sha256,
        "window_start_close_utc": declaration.window_start_close_utc,
        "window_end_close_utc": declaration.window_end_close_utc,
        "horizon_minutes": declaration.horizon_minutes,
        "target_hours_utc": list(declaration.target_hours_utc),
        "rejection_rule": declaration.rejection_rule,
    }
