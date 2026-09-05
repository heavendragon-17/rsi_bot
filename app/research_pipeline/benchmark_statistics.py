"""Paired calendar-block diagnostics for fixed, post-selection comparisons.

This module is pure: it accepts normalized frames and performs no I/O. Separate
population sums/counts define every estimate; zero-event days stay in the common
calendar and every cohort uses the same bootstrap draws. Intervals are descriptive,
not selection-adjusted significance tests or research-quality pass/fail rules.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from .study_contracts import GROUPINGS, HORIZONS

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]
_BATCH_SIZE = 64
_INFLUENCE_DAYS = 28
_REQUIRED = ("event_id", "trigger_close_at", "horizon_minutes", "return_pct",
             "included_all_horizons", *GROUPINGS)


def _validate_settings(replications: int, block_lengths: tuple[int, ...], seed: int) -> None:
    if type(replications) is not int or not 2 <= replications <= 10000:
        raise ValueError("replications must be an integer from 2 to 10000")
    if (not isinstance(block_lengths, tuple) or not 1 <= len(block_lengths) <= 8
            or any(type(value) is not int or not 1 <= value <= 366 for value in block_lengths)
            or len(set(block_lengths)) != len(block_lengths)):
        raise ValueError("block_lengths must contain 1 to 8 distinct integers from 1 to 366")
    if type(seed) is not int or not 0 <= seed < 2**63:
        raise ValueError("seed must be an integer from 0 to 2**63-1")


def _included(frame: pd.DataFrame, population: str) -> pd.DataFrame:
    if frame.empty or set(_REQUIRED) - set(frame):
        raise ValueError(f"{population}: empty population or missing normalized columns")
    if not pd.api.types.is_bool_dtype(frame.included_all_horizons):
        raise ValueError(f"{population}: normalized eligibility must be boolean")
    rows = frame.loc[frame.included_all_horizons & frame.horizon_minutes.isin(HORIZONS), list(_REQUIRED)].copy()
    if rows.empty:
        raise ValueError(f"{population}: empty all-four-complete population")
    if not isinstance(rows.trigger_close_at.dtype, pd.DatetimeTZDtype) or rows.trigger_close_at.isna().any():
        raise ValueError(f"{population}: trigger_close_at must contain timezone-aware timestamps")
    if rows.duplicated(["event_id", "horizon_minutes"]).any():
        raise ValueError(f"{population}: duplicate event/horizon rows")
    rows["trigger_close_at"] = rows.trigger_close_at.dt.tz_convert("UTC")
    for grouping in GROUPINGS:
        if rows[grouping].isna().any():
            raise ValueError(f"{population}: missing {grouping} labels")
        rows[grouping] = rows[grouping].astype(str)
    rows["return_pct"] = pd.to_numeric(rows.return_pct, errors="raise")
    return rows


def _label_universe(frames: tuple[pd.DataFrame, pd.DataFrame]) -> dict[tuple[int, str], list[str]]:
    """Keep registered catalog labels even when all their events are excluded."""
    labels: dict[tuple[int, str], set[str]] = {(h, g): set() for h in HORIZONS for g in GROUPINGS}
    for frame in frames:
        for horizon in HORIZONS:
            rows = frame.loc[frame.horizon_minutes.eq(horizon), list(GROUPINGS)]
            for grouping in GROUPINGS:
                labels[horizon, grouping].update(rows[grouping].dropna().astype(str).unique())
    return {key: sorted(values) for key, values in labels.items()}


def _daily_statistics(frames: tuple[pd.DataFrame, pd.DataFrame], start: pd.Timestamp,
                      days: int, labels: dict[tuple[int, str], list[str]]) -> tuple[FloatArray, list[dict[str, Any]], IntArray]:
    entries: list[dict[str, Any]] = []
    offsets = {}
    pooled = list(range(len(HORIZONS)))
    for horizon_index, horizon in enumerate(HORIZONS):
        for grouping in GROUPINGS:
            offsets[horizon, grouping] = len(pooled)
            for group in labels[horizon, grouping]:
                entries.append({"horizon_minutes": horizon, "grouping": grouping, "group": group,
                                "column": len(pooled)})
                pooled.append(horizon_index)
    columns = len(pooled)
    # The six measures are signal sum/count/nonfinite-count, then baseline's.
    daily = np.zeros((days, columns, 6), dtype=np.float64)
    for population, frame in enumerate(frames):
        day = ((frame.trigger_close_at.dt.normalize() - start).dt.days).to_numpy(dtype=np.int64)
        horizon = frame.horizon_minutes.to_numpy(dtype=np.int64)
        horizon_index = np.searchsorted(np.asarray(HORIZONS), horizon)
        values = frame.return_pct.to_numpy(dtype=np.float64)
        finite = np.isfinite(values)
        sums = np.where(finite, values, 0.0)
        targets = [horizon_index]
        for grouping in GROUPINGS:
            target = np.empty(len(frame), dtype=np.int64)
            for selected_horizon in HORIZONS:
                mask = horizon == selected_horizon
                codes = {label: index for index, label in enumerate(labels[selected_horizon, grouping])}
                target[mask] = (frame.loc[mask, grouping].map(codes).to_numpy(dtype=np.int64)
                                + offsets[selected_horizon, grouping])
            targets.append(target)
        for target in targets:
            flat = day * columns + target
            for measure, weights in enumerate((sums, np.ones(len(frame)), (~finite).astype(float))):
                daily[:, :, population * 3 + measure] += np.bincount(flat, weights=weights, minlength=days * columns).reshape(days, columns)
    return daily, entries, np.asarray(pooled, dtype=np.int64)


def _estimates(statistics: FloatArray, pooled: IntArray) -> tuple[FloatArray, FloatArray]:
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        signal = statistics[..., 0] / statistics[..., 1]
        baseline = statistics[..., 3] / statistics[..., 4]
        delta = signal - baseline
        valid = ((statistics[..., 1] > 0) & (statistics[..., 4] > 0)
                 & (statistics[..., 2] == 0) & (statistics[..., 5] == 0) & np.isfinite(delta))
        delta = np.where(valid, delta, np.nan)
        contrast = delta - delta[..., pooled]
    return delta, contrast


def _bootstrap(daily: FloatArray, pooled: IntArray, *, replications: int,
               block_days: int, seed: int) -> tuple[FloatArray, FloatArray]:
    days, columns, _ = daily.shape
    rng = np.random.default_rng(np.random.SeedSequence([seed, block_days]))
    deltas = np.empty((replications, columns))
    contrasts = np.empty_like(deltas)
    block_count = (days + block_days - 1) // block_days
    offsets = np.arange(block_days, dtype=np.int64)
    flat_daily = daily.reshape(days, columns * 6)
    for first in range(0, replications, _BATCH_SIZE):
        count = min(_BATCH_SIZE, replications - first)
        starts = rng.integers(0, days, size=(count, block_count))
        # Circular blocks are concatenated then truncated to exactly grid length.
        sampled = ((starts[..., None] + offsets) % days).reshape(count, -1)[:, :days]
        indexes = sampled + np.arange(count, dtype=np.int64)[:, None] * days
        weights = np.bincount(indexes.ravel(), minlength=count * days).reshape(count, days).astype(float)
        with np.errstate(over="ignore", invalid="ignore"):
            statistics = (weights @ flat_daily).reshape(count, columns, 6)
        delta, contrast = _estimates(statistics, pooled)
        deltas[first:first + count], contrasts[first:first + count] = delta, contrast
    return deltas, contrasts


def _number(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


def _interval(values: FloatArray) -> list[float] | None:
    finite = values[np.isfinite(values)]
    if not len(finite):
        return None
    with np.errstate(over="ignore", invalid="ignore"):
        bounds = np.quantile(finite, [0.025, 0.975])
    return [float(value) for value in bounds] if np.isfinite(bounds).all() else None


def _bootstrap_record(delta: FloatArray, contrast: FloatArray, block_days: int) -> dict[str, Any]:
    valid = int(np.sum(np.isfinite(delta) & np.isfinite(contrast)))
    return {"block_days": block_days, "valid_replicates": valid, "undefined_replicates": len(delta) - valid,
            "delta_valid_replicates": int(np.isfinite(delta).sum()),
            "contrast_valid_replicates": int(np.isfinite(contrast).sum()),
            "delta_ci_pp": _interval(delta), "contrast_ci_pp": _interval(contrast)}


def _influence_record(delta: FloatArray, contrast: FloatArray, original_delta: float,
                      original_contrast: float) -> dict[str, Any]:
    result: dict[str, Any] = {"block_days": _INFLUENCE_DAYS, "blocks": len(delta)}
    for name, estimates, original in (("delta", delta, original_delta), ("contrast", contrast, original_contrast)):
        finite = estimates[np.isfinite(estimates)]
        available = len(finite) > 0 and np.isfinite(original)
        with np.errstate(over="ignore", invalid="ignore"):
            result[f"max_abs_{name}_change_pp"] = _number(np.max(np.abs(finite - original))) if available else None
        result[f"{name}_sign_changes"] = int(np.sum(np.sign(finite) * np.sign(original) < 0)) if np.isfinite(original) else None
        result[f"undefined_{name}_cases"] = len(estimates) - len(finite)
    return result


def _support(counts: FloatArray, week_index: IntArray) -> dict[str, Any]:
    weeks = np.bincount(week_index, weights=counts)
    total = counts.sum()
    return {"active_utc_weeks": int(np.count_nonzero(weeks)),
            "max_utc_week_share": float(weeks.max() / total) if total else None}


def evaluate_diagnostics(signals: pd.DataFrame, baseline: pd.DataFrame, *, replications: int = 2000,
                         block_lengths: tuple[int, ...] = (7, 28), seed: int = 20260905) -> dict[str, Any]:
    """Evaluate the nine fixed horizon/grouping candidates without selecting winners.

    Bootstrap percentiles use finite replicates only; counts expose undefined
    draws. Joint validity and each estimand's validity are reported separately.
    Leave-block sign changes mean strict positive/negative reversals, excluding
    zero. Partial calendar years refer to coverage of the common calendar grid.
    """
    _validate_settings(replications, block_lengths, seed)
    frames = (_included(signals, "signals"), _included(baseline, "baseline"))
    labels = _label_universe((signals, baseline))
    start = min(frame.trigger_close_at.min() for frame in frames).normalize()
    end = max(frame.trigger_close_at.max() for frame in frames).normalize()
    days = (end - start).days + 1
    if days > 36600:
        raise ValueError("common calendar exceeds the 36600-day resource bound")
    daily, entries, pooled = _daily_statistics(frames, start, days, labels)
    with np.errstate(over="ignore", invalid="ignore"):
        totals = daily.sum(axis=0)
    original_delta, original_contrast = _estimates(totals, pooled)
    bootstrap = {length: _bootstrap(daily, pooled, replications=replications, block_days=length, seed=seed)
                 for length in block_lengths}
    with np.errstate(over="ignore", invalid="ignore"):
        removed = np.add.reduceat(daily, np.arange(0, days, _INFLUENCE_DAYS), axis=0)
        remaining = totals[None, ...] - removed
    influence_delta, influence_contrast = _estimates(remaining, pooled)
    weeks = (np.arange(days, dtype=np.int64) + start.weekday()) // 7
    candidates = []
    for horizon in HORIZONS:
        for grouping in GROUPINGS:
            cohorts = []
            for entry in entries:
                if (entry["horizon_minutes"], entry["grouping"]) != (horizon, grouping):
                    continue
                column, group = entry["column"], entry["group"]
                partial = None
                if grouping == "calendar_year":
                    year_start = pd.Timestamp(year=int(group), month=1, day=1, tz="UTC")
                    year_end = pd.Timestamp(year=int(group), month=12, day=31, tz="UTC")
                    partial = bool(start > year_start or end < year_end)
                cohorts.append({
                    "group": group, "signal_n": int(totals[column, 1]), "baseline_n": int(totals[column, 4]),
                    "delta_pp": _number(original_delta[column]), "pooled_delta_pp": _number(original_delta[pooled[column]]),
                    "contrast_pp": _number(original_contrast[column]),
                    "support": {"signal": _support(daily[:, column, 1], weeks),
                                "baseline": _support(daily[:, column, 4], weeks), "partial_calendar_year": partial},
                    "bootstrap": [_bootstrap_record(bootstrap[length][0][:, column], bootstrap[length][1][:, column], length)
                                  for length in block_lengths],
                    "influence": _influence_record(influence_delta[:, column], influence_contrast[:, column],
                                                   original_delta[column], original_contrast[column]),
                })
            candidates.append({"parameters": {"horizon_minutes": horizon, "grouping": grouping}, "cohorts": cohorts})
    return {
        "schema": "btc-research-benchmark-diagnostics-v1",
        "settings": {"replications": replications, "seed": seed, "block_lengths": list(block_lengths),
                     "ci_quantiles": [0.025, 0.975], "influence_block_days": _INFLUENCE_DAYS,
                     "method": "paired_circular_utc_day_block_bootstrap", "interpretation": "post-selection descriptive",
                     "sign_change_rule": "Strict positive/negative reversals; zero is not a reversal.",
                     "undefined_replicates_rule": "Joint delta/contrast undefined count; intervals use each estimand's finite draws.",
                     "population_rule": "included_all_horizons; report 60/120/180 minutes separately",
                     "interval_note": "Descriptive percentile intervals; no selection-adjusted significance or pass/fail assessment."},
        "calendar_grid": {"start_utc": start.strftime("%Y-%m-%d"), "end_utc": end.strftime("%Y-%m-%d"), "days": days,
                          "signal_zero_days": int(np.sum(daily[:, :len(HORIZONS), 1].sum(axis=1) == 0)),
                          "baseline_zero_days": int(np.sum(daily[:, :len(HORIZONS), 4].sum(axis=1) == 0))},
        "candidates": candidates,
    }
