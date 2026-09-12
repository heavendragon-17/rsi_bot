"""Independent M5 scientific checker (frozen schema v1).

Verifies a candidate/baseline diagnostic pair against raw 5-minute candles
without calling the diagnostic under test and without opening any real BTC
dataset, holdout, trading configuration or strategy. All fixtures in tests
are synthetic and hand-calculated.

Input schemas (CSV, UTF-8, header required):

Candles: timestamp,open,high,low,close,volume
  timestamp is the bar OPEN with an explicit timezone (``Z`` or ``+-hh:mm``),
  unique, strictly increasing and aligned to the 5-minute grid; the close is
  exactly five minutes later (matching
  ``app/research_pipeline/study_checks.py``). Decision/target times in
  diagnostics are CLOSE times.

Diagnostic (candidate and baseline share the schema):
  event_id,decision_time_utc,available_at_utc,horizon_minutes,
  target_time_utc,decision_close_price,target_close_price,
  outcome_status,return_pct,included

  outcome_status in {COMPLETE,MISSING_TARGET,GAP}; included is a boolean
  literal (true/false, case-insensitive) and must equal
  (outcome_status == COMPLETE).

Frozen rules:

- available_at_utc <= decision_time_utc for every row; a later available_at
  is a timing violation (future information), never a scientific result.
- target_time_utc == decision_time_utc + horizon_minutes exactly; any shift
  (including a later-candle substitution) is a horizon violation.
- decision_close_price and target_close_price must equal the exact candle
  closes within 1e-10; a substituted later candle is a data violation.
- A missing target candle or a cadence gap between decision and target
  excludes the observation (MISSING_TARGET/GAP); claiming COMPLETE there is
  a data violation. Correctly marked non-COMPLETE rows are excluded, not
  violations, but their counts/reasons are retained.
- return_pct must equal (target/decision - 1) * 100 within 1e-9 for
  COMPLETE rows; otherwise a numerical violation.
- Duplicate (event_id) or duplicate decision_time_utc, empty identities,
  unknown horizons, non-boolean included flags and target_time <=
  decision_time are schema violations.
- Candidate and baseline must share the same candles source and requested
  horizon; their eligible (COMPLETE) decision_time sets must be disjoint
  (two groups from one window, not overlapping populations).

Timing/data/schema violations are reported separately from the scientific
verdict. When no violation exists the scientific verdict is ``succeeded``
if candidate mean exceeds baseline mean else ``rejected``; both are valid
scientific outcomes. When any violation exists the verdict is ``INVALID``
and ``passed`` is False.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCHEMA_VERSION = "m5-scientific-check-v1"
REQUIRED_CANDLES = ("timestamp", "open", "high", "low", "close", "volume")
REQUIRED_DIAG = ("event_id", "decision_time_utc", "available_at_utc",
                 "horizon_minutes", "target_time_utc", "decision_close_price",
                 "target_close_price", "outcome_status", "return_pct", "included")
ALLOWED_STATUSES = ("COMPLETE", "MISSING_TARGET", "GAP")
PRICE_ATOL = 1e-10
RETURN_ATOL = 1e-9


def _require_tz(values: pd.Series, name: str) -> pd.DatetimeIndex:
    strings = values.astype(str)
    if not strings.str.contains(r"(?:Z|[+-]\d{2}:\d{2})$", regex=True).all():
        raise ValueError(f"{name} must carry explicit timezone offsets")
    result = pd.DatetimeIndex(pd.to_datetime(values, utc=True, format="mixed", errors="raise"))
    if result.hasnans:
        raise ValueError(f"{name} contains missing timestamps")
    return result


def load_candles(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, keep_default_na=False, encoding="utf-8-sig")
    missing = set(REQUIRED_CANDLES) - set(frame.columns)
    if missing:
        raise ValueError(f"candles: missing columns {sorted(missing)}")
    if frame.empty:
        raise ValueError("candles: empty population")
    frame["timestamp"] = _require_tz(frame["timestamp"], "candles.timestamp")
    if not frame["timestamp"].is_unique:
        raise ValueError("candles: duplicate timestamps")
    if not frame["timestamp"].is_monotonic_increasing:
        raise ValueError("candles: timestamps are not strictly increasing")
    minutes = pd.DatetimeIndex(frame["timestamp"])
    if not ((minutes.minute % 5 == 0) & (minutes.second == 0) & (minutes.microsecond == 0)).all():
        raise ValueError("candles: timestamps are off the 5-minute grid")
    for field in ("open", "high", "low", "close", "volume"):
        frame[field] = pd.to_numeric(frame[field], errors="raise")
    if not np.isfinite(frame["close"].to_numpy()).all() or (frame["close"] <= 0).any():
        raise ValueError("candles: close prices must be finite and positive")
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    # Native convention (matching app/research_pipeline/study_checks.py):
    # ``timestamp`` is the bar OPEN; the close is exactly five minutes later.
    # Decision/target times in diagnostics are CLOSE times.
    frame["_close_time"] = pd.DatetimeIndex(frame["timestamp"]) + pd.Timedelta(minutes=5)
    return frame


def load_diagnostic(path: Path, population: str, horizon_minutes: int) -> pd.DataFrame:
    rows = pd.read_csv(path, keep_default_na=False, encoding="utf-8-sig")
    missing = set(REQUIRED_DIAG) - set(rows.columns)
    if missing:
        raise ValueError(f"{population}: missing columns {sorted(missing)}")
    if rows.empty:
        raise ValueError(f"{population}: empty population")
    rows = rows.copy()
    if rows["event_id"].isna().any() or rows["event_id"].astype(str).str.strip().eq("").any():
        raise ValueError(f"{population}: empty event identity")
    rows["event_id"] = rows["event_id"].astype(str)
    if rows["event_id"].duplicated().any():
        raise ValueError(f"{population}: duplicate event_id")
    horizon = pd.to_numeric(rows["horizon_minutes"], errors="raise")
    if not (horizon == horizon_minutes).all():
        raise ValueError(f"{population}: every row must request horizon {horizon_minutes}")
    rows["horizon_minutes"] = horizon.astype(int)
    rows["decision_time_utc"] = _require_tz(rows["decision_time_utc"], f"{population}.decision_time_utc")
    rows["available_at_utc"] = _require_tz(rows["available_at_utc"], f"{population}.available_at_utc")
    rows["target_time_utc"] = _require_tz(rows["target_time_utc"], f"{population}.target_time_utc")
    if rows["decision_time_utc"].duplicated().any():
        raise ValueError(f"{population}: multiple IDs share a decision_time_utc")
    truth = rows["included"].astype(str).str.lower()
    if not truth.isin(["true", "false"]).all():
        raise ValueError(f"{population}: included must be a boolean")
    rows["included"] = truth.eq("true")
    if not rows["outcome_status"].isin(ALLOWED_STATUSES).all():
        raise ValueError(f"{population}: unsupported outcome_status")
    if not (rows["included"] == rows["outcome_status"].eq("COMPLETE")).all():
        raise ValueError(f"{population}: included must equal (outcome_status == COMPLETE)")
    for field in ("decision_close_price", "target_close_price", "return_pct"):
        rows[field] = pd.to_numeric(rows[field].replace("", np.nan), errors="coerce")
    return rows


def check_pair(
    *,
    candles: pd.DataFrame,
    candidate: pd.DataFrame,
    baseline: pd.DataFrame,
    horizon_minutes: int,
) -> dict[str, Any]:
    violations: dict[str, list[dict[str, Any]]] = {
        "schema": [], "timing": [], "horizon": [], "data": [],
        "numerical": [], "population": [],
    }
    excluded: dict[str, Any] = {"candidate": {}, "baseline": {}}

    closes = pd.Series(candles["close"].to_numpy(dtype=float),
                       index=pd.DatetimeIndex(candles["_close_time"]))
    # Gap prefix over the 5-minute cadence (measured on opens; closes shift
    # uniformly by five minutes so the same breaks apply).
    stamps = pd.DatetimeIndex(candles["timestamp"])
    breaks = np.zeros(len(stamps), dtype=np.int64)
    breaks[1:] = np.asarray(stamps[1:] - stamps[:-1]) != np.timedelta64(5, "m")
    prefix = breaks.cumsum()
    closes_index = pd.DatetimeIndex(candles["_close_time"])
    position_of = {t: i for i, t in enumerate(closes_index)}

    def _check_one(rows: pd.DataFrame, population: str) -> pd.DataFrame:
        rows = rows.copy()
        expected_status: list[str] = []
        expected_return: list[float] = []
        for _, row in rows.iterrows():
            decision = row["decision_time_utc"]
            available = row["available_at_utc"]
            target = row["target_time_utc"]
            if not (available <= decision):
                violations["timing"].append({
                    "population": population, "event_id": row["event_id"],
                    "reason": "available_at_utc is after decision_time_utc"})
            if not (target == decision + pd.Timedelta(minutes=int(horizon_minutes))):
                violations["horizon"].append({
                    "population": population, "event_id": row["event_id"],
                    "reason": "target_time_utc is not decision_time_utc + horizon"})
            if not (target > decision):
                violations["schema"].append({
                    "population": population, "event_id": row["event_id"],
                    "reason": "target_time_utc does not follow decision_time_utc"})
            # Exact lookup, never a later-candle substitution.
            if decision not in position_of or target not in position_of:
                expected_status.append("MISSING_TARGET")
                expected_return.append(float("nan"))
                continue
            start, end = position_of[decision], position_of[target]
            if prefix[end] != prefix[start]:
                expected_status.append("GAP")
                expected_return.append(float("nan"))
                continue
            decision_close = float(closes.iloc[start])
            target_close = float(closes.iloc[end])
            if not np.isclose(row["decision_close_price"], decision_close,
                              rtol=0, atol=PRICE_ATOL):
                violations["data"].append({
                    "population": population, "event_id": row["event_id"],
                    "reason": "decision_close_price does not match the exact candle"})
            if row["outcome_status"] == "COMPLETE" and not np.isclose(
                    row["target_close_price"], target_close, rtol=0, atol=PRICE_ATOL,
                    equal_nan=True):
                violations["data"].append({
                    "population": population, "event_id": row["event_id"],
                    "reason": "target_close_price does not match the exact candle"})
            expected_status.append("COMPLETE")
            expected_return.append((target_close / decision_close - 1) * 100)
        rows["_expected_status"] = expected_status
        rows["_expected_return"] = expected_return
        for _, row in rows.iterrows():
            if row["outcome_status"] != row["_expected_status"]:
                # Either direction is a data violation: a COMPLETE claim over
                # a gap/missing target fabricates evidence, while hiding an
                # eligible COMPLETE row as MISSING/GAP under-reports the
                # population. Correctly marked non-COMPLETE rows are excluded
                # with retained counts; they are not violations only when
                # they match the recomputed expectation.
                violations["data"].append({
                    "population": population, "event_id": row["event_id"],
                    "reason": f"claimed {row['outcome_status']} but expected {row['_expected_status']}"})
            elif row["outcome_status"] == "COMPLETE":
                if not np.isclose(row["return_pct"], row["_expected_return"],
                                  rtol=0, atol=RETURN_ATOL, equal_nan=True):
                    violations["numerical"].append({
                        "population": population, "event_id": row["event_id"],
                        "reason": "return_pct does not reproduce the exact candle return",
                        "expected": float(row["_expected_return"]),
                        "declared": float(row["return_pct"])})
        counts = dict(rows["outcome_status"].value_counts().to_dict())
        excluded[population] = {
            "total": len(rows), "eligible": int(rows["included"].sum()),
            "status_counts": {k: int(v) for k, v in counts.items()},
        }
        return rows

    cand = _check_one(candidate, "candidate")
    base = _check_one(baseline, "baseline")

    cand_eligible = set(cand.loc[cand["included"], "decision_time_utc"].astype(str))
    base_eligible = set(base.loc[base["included"], "decision_time_utc"].astype(str))
    if cand_eligible & base_eligible:
        violations["population"].append({
            "reason": "candidate and baseline eligible decision_times overlap; "
                      "groups must be disjoint slices of one window"})

    def _metrics(rows: pd.DataFrame) -> dict[str, Any]:
        eligible = rows.loc[rows["included"] & rows["outcome_status"].eq("COMPLETE")]
        values = pd.to_numeric(eligible["return_pct"], errors="coerce").to_numpy(dtype=float)
        values = values[np.isfinite(values)]
        if len(values) == 0:
            return {"n": 0, "mean": None, "median": None, "positive_share": None}
        return {"n": int(len(values)), "mean": float(np.mean(values)),
                "median": float(np.median(values)),
                "positive_share": float(np.mean(values > 0))}

    cand_m = _metrics(cand)
    base_m = _metrics(base)
    if cand_m["mean"] is None or base_m["mean"] is None:
        # No eligible science to judge, but no rule was broken: report
        # undecided separately from violations. Callers that require a
        # succeeded/rejected verdict must treat undecided as not accepted.
        verdict, difference, passed = "undecided", None, not any(violations.values())
    else:
        difference = float(cand_m["mean"] - base_m["mean"])
        verdict = "INVALID" if any(v for v in violations.values()) else (
            "succeeded" if difference > 0 else "rejected")
        passed = not any(violations.values())
    return {
        "schema": SCHEMA_VERSION,
        "horizon_minutes": horizon_minutes,
        "violations": violations,
        "excluded": excluded,
        "scientific": {"candidate": cand_m, "baseline": base_m,
                       "difference_pp": difference, "verdict": verdict},
        "passed": passed,
    }


def run_files(
    *,
    candles_path: Path,
    candidate_path: Path,
    baseline_path: Path,
    horizon_minutes: int,
) -> dict[str, Any]:
    """Load the three CSVs, run :func:`check_pair` and bind source hashes."""
    candles = load_candles(candles_path)
    candidate = load_diagnostic(candidate_path, "candidate", horizon_minutes)
    baseline = load_diagnostic(baseline_path, "baseline", horizon_minutes)
    result = check_pair(candles=candles, candidate=candidate,
                        baseline=baseline, horizon_minutes=horizon_minutes)
    result["inputs"] = {
        "candles": {"path": Path(candles_path).as_posix(),
                    "sha256": hashlib.sha256(Path(candles_path).read_bytes()).hexdigest(),
                    "rows": len(candles)},
        "candidate": {"path": Path(candidate_path).as_posix(),
                      "sha256": hashlib.sha256(Path(candidate_path).read_bytes()).hexdigest(),
                      "rows": len(candidate)},
        "baseline": {"path": Path(baseline_path).as_posix(),
                     "sha256": hashlib.sha256(Path(baseline_path).read_bytes()).hexdigest(),
                     "rows": len(baseline)},
    }
    return result
