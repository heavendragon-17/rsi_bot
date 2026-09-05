"""Independent arithmetic and population checks for saved BTC M5 studies.

This module deliberately does not call the horizon evaluator: raw candle lookup,
contiguity, return arithmetic and all-four-horizon eligibility are recomputed.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import pandas as pd

HORIZONS = (60, 120, 180, 240)
REQUIRED = {"event_id", "trigger_close_at", "trigger_close_price", "horizon_minutes",
            "target_close_at", "target_close_price", "outcome_status", "return_pct",
            "included_all_horizons"}


def _timestamps(values: pd.Series, name: str) -> pd.DatetimeIndex:
    # UTC conversion alone would silently accept timezone-naive saved claims.
    strings = values.astype(str)
    if not strings.str.contains(r"(?:Z|[+-]\d{2}:\d{2})$", regex=True).all():
        raise ValueError(f"{name} must have explicit timezone offsets")
    result = pd.DatetimeIndex(pd.to_datetime(values, utc=True, format="mixed", errors="raise"))
    if result.hasnans:
        raise ValueError(f"{name} contains missing timestamps")
    return result


def normalize_rows(rows: pd.DataFrame, population: str) -> pd.DataFrame:
    missing = REQUIRED - set(rows)
    if missing or rows.empty:
        raise ValueError(f"{population}: empty population or missing columns: {sorted(missing)}")
    rows = rows.copy()
    if rows.event_id.isna().any() or rows.event_id.astype(str).str.strip().eq("").any():
        raise ValueError(f"{population}: empty event identity")
    rows["event_id"] = rows.event_id.astype(str)
    horizon = pd.to_numeric(rows.horizon_minutes, errors="raise")
    if not horizon.isin(HORIZONS).all() or rows.duplicated(["event_id", "horizon_minutes"]).any():
        raise ValueError(f"{population}: unsupported or duplicate event/horizon rows")
    rows["horizon_minutes"] = horizon.astype(int)
    if not rows.groupby("event_id", sort=False).size().eq(4).all():
        raise ValueError(f"{population}: each event requires exactly all four saved horizons")
    truth = rows.included_all_horizons.astype(str).str.lower()
    if not truth.isin(["true", "false"]).all():
        raise ValueError(f"{population}: included_all_horizons must be a boolean")
    rows["included_all_horizons"] = truth.eq("true")
    for field in ("trigger_close_price", "target_close_price", "return_pct"):
        rows[field] = pd.to_numeric(rows[field].replace("", np.nan), errors="raise")
    rows["trigger_close_at"] = _timestamps(rows.trigger_close_at, "trigger_close_at")
    rows["target_close_at"] = _timestamps(rows.target_close_at, "target_close_at")
    invariant = ["trigger_close_at", "trigger_close_price", "included_all_horizons"]
    if rows.groupby("event_id", sort=False)[invariant].nunique(dropna=False).gt(1).any().any():
        raise ValueError(f"{population}: event identity or eligibility differs across horizons")
    unique = rows.drop_duplicates("event_id")
    if unique.trigger_close_at.duplicated().any():
        raise ValueError(f"{population}: multiple IDs share a trigger close")
    return rows


def _check(name: str, matches: np.ndarray | pd.Series, rows: pd.DataFrame) -> dict[str, Any]:
    failed = np.flatnonzero(~np.asarray(matches, dtype=bool))
    samples = rows.iloc[failed[:3]][["event_id", "horizon_minutes"]].to_dict("records")
    return {"name": name, "passed": len(failed) == 0, "checked_rows": len(rows),
            "mismatch_count": len(failed), "examples": samples}


def check_raw_returns(rows: pd.DataFrame, frame: pd.DataFrame, population: str) -> list[dict[str, Any]]:
    """Vectorized exact lookup, gap classification and independent gross returns."""
    closes_at = pd.DatetimeIndex(frame.index).tz_convert("UTC") + pd.Timedelta(minutes=5)
    if frame.empty or not closes_at.is_unique or not closes_at.is_monotonic_increasing:
        raise ValueError("M5 source must be nonempty, ordered and unique")
    if not closes_at.floor("5min").equals(closes_at):
        raise ValueError("M5 source candle timestamps are off the native grid")
    prices = frame.close.to_numpy(dtype=float)
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("M5 close prices must be finite and positive")
    trigger = pd.DatetimeIndex(rows.trigger_close_at)
    targets = trigger + pd.to_timedelta(rows.horizon_minutes.to_numpy(), unit="min")
    starts = closes_at.get_indexer(trigger)
    ends = closes_at.get_indexer(targets)
    valid_start, valid_end = starts >= 0, ends >= 0
    safe_start, safe_end = np.maximum(starts, 0), np.maximum(ends, 0)
    # A prefix of cadence breaks detects intervening gaps even with exact endpoints.
    breaks = np.zeros(len(closes_at), dtype=np.int64)
    breaks[1:] = np.asarray(closes_at[1:] - closes_at[:-1]) != np.timedelta64(5, "m")
    prefix = breaks.cumsum()
    gaps = valid_start & valid_end & (prefix[safe_end] != prefix[safe_start])
    statuses = np.full(len(rows), "COMPLETE", dtype=object)
    statuses[gaps] = "GAP"
    statuses[~valid_start | ~valid_end] = "MISSING_TARGET"
    statuses[~valid_end & (targets > closes_at[-1])] = "INCOMPLETE_TAIL"
    complete = statuses == "COMPLETE"
    target_prices = np.where(complete, prices[safe_end], np.nan)
    returns = np.where(complete, (prices[safe_end] / prices[safe_start] - 1) * 100, np.nan)
    eligibility = pd.Series(complete, index=rows.index).groupby(rows.event_id).transform("all")
    comparisons = {
        "trigger_present": valid_start,
        "trigger_close_price": valid_start & np.isclose(rows.trigger_close_price, prices[safe_start], rtol=0, atol=1e-10),
        "target_close_at": pd.DatetimeIndex(rows.target_close_at) == targets,
        "outcome_status": rows.outcome_status.to_numpy() == statuses,
        "target_close_price": np.isclose(rows.target_close_price, target_prices, rtol=0, atol=1e-10, equal_nan=True),
        "return_pct": np.isclose(rows.return_pct, returns, rtol=0, atol=1e-10, equal_nan=True),
        "included_all_horizons": rows.included_all_horizons.to_numpy() == eligibility.to_numpy(),
    }
    return [_check(f"{population}.{name}", matches, rows) for name, matches in comparisons.items()]


def check_population(signals: pd.DataFrame, baseline: pd.DataFrame, parent: pd.DataFrame,
                     manifest: dict[str, Any], frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Retain the hash-bound parent IDs and saved preparation-eligible baseline."""
    source = signals.drop_duplicates("event_id").sort_values("trigger_close_at")
    comparator = baseline.drop_duplicates("event_id")
    if "timeframe" not in parent or not REQUIRED.intersection(parent.columns):
        raise ValueError("Parent signals have no timeframe/identity columns")
    parent = parent.loc[parent.timeframe.eq("5m")].copy()
    if parent.empty or not {"event_id", "trigger_close_at", "trigger_close_price"}.issubset(parent):
        raise ValueError("Parent M5 population is empty or malformed")
    parent["trigger_close_at"] = _timestamps(parent.trigger_close_at, "parent.trigger_close_at")
    identity = ["trigger_close_at", "trigger_close_price"]
    if parent.groupby("event_id")[identity].nunique(dropna=False).gt(1).any().any():
        raise ValueError("Parent M5 event identity is inconsistent")
    parent = parent.drop_duplicates("event_id").set_index("event_id")
    facts, audit = manifest["parent"], manifest["comparator"]
    start = pd.Timestamp(audit["window_start_close_utc"])
    end = pd.Timestamp(audit["window_end_close_utc"])
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Comparator boundaries require timezone offsets")
    raw_closes = pd.DatetimeIndex(frame.index) + pd.Timedelta(minutes=5)
    candidate_n = int(((raw_closes >= start) & (raw_closes <= end)).sum())
    signal_ids_hash = hashlib.sha256("\n".join(source.event_id).encode()).hexdigest()
    same_ids = set(source.event_id) == set(parent.index.astype(str))
    same_parent = False
    if same_ids:
        aligned = parent.loc[source.event_id]
        same_parent = bool((aligned.trigger_close_at.to_numpy() == source.trigger_close_at.to_numpy()).all()
                           and np.isclose(pd.to_numeric(aligned.trigger_close_price), source.trigger_close_price,
                                          rtol=0, atol=1e-10).all())
    conditions = {
        "parent_event_identity": same_ids and same_parent,
        "parent_signal_count": len(source) == facts["signal_count"],
        "parent_signal_ids_sha256": signal_ids_hash == facts["signal_ids_sha256"],
        "parent_cooldown": bool(source.trigger_close_at.diff().dropna().ge(pd.Timedelta(hours=1)).all()),
        "comparator_window": start == source.trigger_close_at.min() and end == source.trigger_close_at.max(),
        "baseline_inside_window": bool(comparator.trigger_close_at.between(start, end).all()),
        "signals_in_baseline": set(source.trigger_close_at).issubset(set(comparator.trigger_close_at)),
        "baseline_eligible_count": len(comparator) == audit["eligible_bar_count"],
        "baseline_candidate_count": candidate_n == audit["candidate_bar_count"],
        "baseline_exclusion_count": candidate_n - len(comparator) == audit["preparation_excluded_count"],
        "nonempty_matched_population": bool(signals.included_all_horizons.any() and baseline.included_all_horizons.any()),
    }
    return [{"name": name, "passed": bool(passed)} for name, passed in conditions.items()]


def check_label_alignment(rows: pd.DataFrame, daily: pd.DataFrame) -> dict[str, Any]:
    """Check merge results by an independent binary search of causal availability."""
    available = pd.DatetimeIndex(daily.available_at)
    if not available.is_monotonic_increasing or not available.is_unique or not available.floor("D").equals(available):
        raise ValueError("Regime availability must contain unique ordered UTC day closes")
    times = pd.DatetimeIndex(rows.trigger_close_at)
    positions = available.searchsorted(times, side="right") - 1
    valid = positions >= 0
    expected_times = pd.Series(pd.NaT, index=rows.index, dtype="datetime64[ns, UTC]")
    expected_times.loc[valid] = pd.Series(available[np.maximum(positions[valid], 0)], index=rows.index[valid])
    actual_times = pd.to_datetime(rows.available_at, utc=True)
    matching = (actual_times == expected_times) | (actual_times.isna() & expected_times.isna())
    for name in ("trend", "volatility"):
        expected = np.full(len(rows), "UNAVAILABLE", dtype=object)
        expected[valid] = daily[name].to_numpy()[positions[valid]]
        matching &= rows[name].to_numpy() == expected
    return _check("causal_regime_alignment", matching, rows)


def validate_h1_source(frame: pd.DataFrame) -> None:
    """Require actual hourly UTC bars before creating complete-day features."""
    index = pd.DatetimeIndex(frame.index).tz_convert("UTC")
    prices = frame.close.to_numpy(dtype=float)
    if not index.floor("h").equals(index):
        raise ValueError("H1 source candle timestamps are off the native grid")
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("H1 close prices must be finite and positive")
