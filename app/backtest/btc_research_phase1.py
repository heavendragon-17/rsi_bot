"""Reproducible offline BTC research Phase 1 baseline.

This module is deliberately a thin research wrapper around the existing BTC
alert replay.  It does not implement a second signal strategy or an order
simulation.  The replay remains the authority for point-in-time M5/M15
signals and cooldowns; this module adds strict source/provenance checks and
exact close-to-close descriptive outcomes.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import platform
import subprocess  # nosec B404 - fixed git argv only
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import pandas as pd

from app.backtest.signal_replay import HISTORICAL_READY_AT, run_btc_alert_replay
from app.backtest.signal_replay_data import events_for_frame, load_ohlcv_csv
from app.backtest.signal_replay_models import ReplaySignal, SignalReplayInputError
from app.backtest.signal_replay_preparation import ReplayPreparationCache
from app.trading.strategy.btc_rsi_cross_alert.evaluator import (
    H1_DURATION,
    H4_DURATION,
    TRIGGER_DURATION_BY_TIMEFRAME,
)
from app.trading.strategy.btc_rsi_cross_alert.models import COMPONENT_NAME, PREPARATION_READY

UTC_PLUS_7 = timezone(timedelta(hours=7), name="UTC+7")
SYMBOL = "BTC/USDT"
VENUE = "Binance USD-M Futures"
VENUE_INSTRUMENT = "BTC/USDT:USDT"
DEFINITION_VERSION = "btc-research-phase1-v1"
HORIZONS: tuple[tuple[str, int], ...] = (
    ("1h", 60),
    ("4h", 240),
    ("12h", 720),
    ("24h", 1440),
)
TIMEFRAMES = ("5m", "15m", "1h", "4h")
EXPECTED_FILES = {timeframe: f"BTCUSDT_{timeframe}.csv" for timeframe in TIMEFRAMES}
SIGNAL_TIMEFRAMES = ("5m", "15m")
OUTCOME_STATUSES = ("COMPLETE", "INCOMPLETE_TAIL", "MISSING_TARGET", "GAP")
CSV_FIELDS = (
    "event_id",
    "sequence",
    "timeframe",
    "trigger_open_at",
    "trigger_close_at",
    "trigger_close_price",
    "decision_reason",
    "rsi21",
    "rsi_ema9",
    "rsi_wma45",
    "rsi_spread",
    "h1_close_at",
    "h1_close_price",
    "h1_price_ema21",
    "h4_close_at",
    "h4_close_price",
    "h4_price_ema21",
    "horizon",
    "horizon_minutes",
    "target_close_at",
    "target_close_price",
    "outcome_status",
    "return_pct",
    "warning",
)


@dataclass(frozen=True)
class ValidatedInputs:
    data_dir: Path
    paths: dict[str, Path]
    frames: dict[str, pd.DataFrame]
    source_report: dict[str, Any]


@dataclass(frozen=True)
class _ForwardIndex:
    close_times: pd.DatetimeIndex
    closes: np.ndarray
    position_by_close: dict[datetime, int]
    bad_interval_prefix: np.ndarray


def _utc_iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z") if value else None


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 12)


def _timeframe_minutes(timeframe: str) -> int:
    return int(TRIGGER_DURATION_BY_TIMEFRAME.get(timeframe, H1_DURATION if timeframe == "1h" else H4_DURATION).total_seconds() // 60)


def _source_frame_report(path: Path, timeframe: str, frame: pd.DataFrame) -> dict[str, Any]:
    index = pd.DatetimeIndex(frame.index).tz_convert(UTC)
    cadence = pd.Series(index).diff().dropna().dt.total_seconds().div(60)
    expected_minutes = _timeframe_minutes(timeframe)
    gap_positions = np.flatnonzero(cadence.to_numpy() > expected_minutes).tolist()
    non_cadence = int((cadence != expected_minutes).sum())
    return {
        "path": str(path.resolve()),
        "expected_filename": EXPECTED_FILES[timeframe],
        "sha256": _hash_file(path),
        "timeframe": timeframe,
        "row_count": int(len(frame)),
        "available_start_open_utc": _utc_iso(index[0].to_pydatetime()),
        "available_end_open_utc": _utc_iso(index[-1].to_pydatetime()),
        "available_start_close_utc": _utc_iso((index[0] + timedelta(minutes=expected_minutes)).to_pydatetime()),
        "available_end_close_utc": _utc_iso((index[-1] + timedelta(minutes=expected_minutes)).to_pydatetime()),
        "expected_cadence_minutes": expected_minutes,
        "duplicate_count": 0,
        "non_cadence_count": non_cadence,
        "gap_count": len(gap_positions),
        "gap_examples": [
            {
                "previous_open_utc": _utc_iso(index[position].to_pydatetime()),
                "next_open_utc": _utc_iso(index[position + 1].to_pydatetime()),
                "observed_minutes": float(cadence.iloc[position]),
            }
            for position in gap_positions[:5]
        ],
    }


def validate_inputs(data_dir: str | Path) -> ValidatedInputs:
    """Load the four native inputs and return auditable validation facts.

    Loader failures are raised as ``SignalReplayInputError`` so a caller can
    report an INVALID run without allowing pandas to silently repair a source.
    Cadence gaps are retained as explicit source facts; they make affected
    forward outcomes incomplete rather than being bridged.
    """

    directory = Path(data_dir).resolve()
    if not directory.is_dir():
        raise SignalReplayInputError(f"BTC research data directory is not a directory: {directory}")
    paths = {timeframe: directory / filename for timeframe, filename in EXPECTED_FILES.items()}
    frames: dict[str, pd.DataFrame] = {}
    report: dict[str, Any] = {
        "identity": {
            "venue": VENUE,
            "symbol": SYMBOL,
            "venue_instrument": VENUE_INSTRUMENT,
            "source_kind": "local_csv",
            "filename_contract": dict(EXPECTED_FILES),
        },
        "files": {},
        "errors": [],
        "warnings": [],
    }
    for timeframe in TIMEFRAMES:
        path = paths[timeframe]
        if path.name != EXPECTED_FILES[timeframe]:
            report["errors"].append(f"Unexpected filename for {timeframe}: {path.name}")
        try:
            frame = load_ohlcv_csv(path, timeframe)
        except (FileNotFoundError, SignalReplayInputError, TypeError, ValueError) as exc:
            report["errors"].append(str(exc))
            continue
        frames[timeframe] = frame
        facts = _source_frame_report(path, timeframe, frame)
        report["files"][timeframe] = facts
        if facts["non_cadence_count"]:
            report["warnings"].append(
                f"{timeframe} has {facts['non_cadence_count']} non-cadence intervals; affected outcomes are not bridged."
            )
    if report["errors"]:
        raise SignalReplayInputError("; ".join(report["errors"]))
    return ValidatedInputs(directory, paths, frames, report)


def _close_times(frame: pd.DataFrame, timeframe: str) -> pd.DatetimeIndex:
    duration = timedelta(minutes=_timeframe_minutes(timeframe))
    return pd.DatetimeIndex(frame.index).tz_convert(UTC) + duration


def _forward_index(frame: pd.DataFrame, timeframe: str) -> _ForwardIndex:
    close_times = _close_times(frame, timeframe)
    expected_delta = np.timedelta64(_timeframe_minutes(timeframe), "m")
    bad_intervals = np.zeros(len(close_times), dtype=np.int64)
    if len(close_times) > 1:
        bad_intervals[1:] = np.asarray(close_times[1:] - close_times[:-1]) != expected_delta
    return _ForwardIndex(
        close_times=close_times,
        closes=frame["close"].to_numpy(dtype="float64", copy=False),
        position_by_close={value.to_pydatetime(): position for position, value in enumerate(close_times)},
        bad_interval_prefix=np.cumsum(bad_intervals),
    )


def _exact_forward_outcome(
    frame: pd.DataFrame,
    timeframe: str,
    *,
    trigger_close: datetime,
    trigger_price: float,
    horizon_minutes: int,
) -> dict[str, Any]:
    """Return one exact target close outcome without gap bridging."""

    source = _forward_index(frame, timeframe)
    return _exact_forward_outcome_from_index(
        source,
        timeframe,
        trigger_close=trigger_close,
        trigger_price=trigger_price,
        horizon_minutes=horizon_minutes,
    )


def _exact_forward_outcome_from_index(
    source: _ForwardIndex,
    timeframe: str,
    *,
    trigger_close: datetime,
    trigger_price: float,
    horizon_minutes: int,
) -> dict[str, Any]:
    """Indexed implementation shared by signal and all-bar calculations."""

    close_times = source.close_times
    trigger_utc = trigger_close.astimezone(UTC)
    target = trigger_utc + timedelta(minutes=horizon_minutes)
    target_position = source.position_by_close.get(target, -1)
    trigger_position = source.position_by_close.get(trigger_utc, -1)
    if target_position < 0:
        if len(close_times) == 0 or close_times[-1].to_pydatetime() < target:
            status = "INCOMPLETE_TAIL"
            warning = "Source ends before the exact target close; no partial suffix return is reported."
        else:
            status = "MISSING_TARGET"
            warning = "Exact target close is absent; no later candle is substituted."
        return {
            "target_close_at": _utc_iso(target),
            "target_close_price": None,
            "outcome_status": status,
            "return_pct": None,
            "warning": warning,
        }
    if trigger_position < 0:
        return {
            "target_close_at": _utc_iso(target),
            "target_close_price": None,
            "outcome_status": "MISSING_TARGET",
            "return_pct": None,
            "warning": "Trigger close is absent from the native source.",
        }
    if source.bad_interval_prefix[target_position] - source.bad_interval_prefix[trigger_position] > 0:
        return {
            "target_close_at": _utc_iso(target),
            "target_close_price": None,
            "outcome_status": "GAP",
            "return_pct": None,
            "warning": "A native timeframe gap occurs before the exact target close; outcome invalidated.",
        }
    target_price = float(source.closes[target_position])
    return {
        "target_close_at": _utc_iso(target),
        "target_close_price": str(target_price),
        "outcome_status": "COMPLETE",
        "return_pct": _round((target_price / trigger_price - 1.0) * 100.0),
        "warning": None,
    }


def _cache_for(inputs: ValidatedInputs) -> ReplayPreparationCache:
    from app.backtest.signal_replay_data import all_h1_close_times, all_h4_close_times

    return ReplayPreparationCache(
        inputs.frames["5m"],
        inputs.frames["15m"],
        inputs.frames["4h"],
        inputs.frames["1h"],
        history_ready_at=HISTORICAL_READY_AT,
        observed_h1_closes=all_h1_close_times(inputs.frames["1h"]),
        observed_h4_closes=all_h4_close_times(inputs.frames["4h"]),
    )


def _signal_row(signal: ReplaySignal, outcome: dict[str, Any], horizon: str, horizon_minutes: int) -> dict[str, Any]:
    data = signal.data
    current = data.current_trigger
    return {
        "event_id": signal.decision.event_id,
        "sequence": signal.sequence,
        "timeframe": signal.timeframe,
        "trigger_open_at": _utc_iso(data.trigger_close_time - TRIGGER_DURATION_BY_TIMEFRAME[signal.timeframe]),
        "trigger_close_at": _utc_iso(data.trigger_close_time),
        "trigger_close_price": str(data.trigger_close_price),
        "decision_reason": signal.decision.reason,
        "rsi21": _round(current.rsi21),
        "rsi_ema9": _round(current.rsi_ema9),
        "rsi_wma45": _round(current.rsi_wma45),
        "rsi_spread": _round(current.rsi_ema9 - current.rsi_wma45),
        "h1_close_at": _utc_iso(data.h1_close_time),
        "h1_close_price": str(data.h1_close_price),
        "h1_price_ema21": str(data.h1_price_ema21),
        "h4_close_at": _utc_iso(data.h4_close_time),
        "h4_close_price": str(data.h4_close_price),
        "h4_price_ema21": str(data.h4_price_ema21),
        "horizon": horizon,
        "horizon_minutes": horizon_minutes,
        **outcome,
    }


def _preparation_coverage(
    inputs: ValidatedInputs,
    start: datetime | None,
    end: datetime | None,
    cache: ReplayPreparationCache,
) -> tuple[dict[str, Any], dict[str, dict[datetime, str]]]:
    """Audit shared point-in-time preparation over the requested trigger window."""

    by_timeframe: dict[str, dict[str, Any]] = {}
    readiness_by_timeframe: dict[str, dict[datetime, str]] = {}
    for timeframe in SIGNAL_TIMEFRAMES:
        events = events_for_frame(inputs.frames[timeframe], timeframe, start, end)
        readiness: dict[datetime, str] = {}
        for event in events:
            readiness[event.close_time] = cache.prepare(event, symbol=SYMBOL).reason
        readiness_by_timeframe[timeframe] = readiness
        ready_times = [event.close_time for event in events if readiness[event.close_time] == PREPARATION_READY]
        exclusions = Counter(reason for reason in readiness.values() if reason != PREPARATION_READY)
        by_timeframe[timeframe] = {
            "requested_event_count": len(events),
            "evaluable_event_count": len(ready_times),
            "preparation_excluded_count": len(events) - len(ready_times),
            "preparation_exclusion_reasons": dict(sorted(exclusions.items())),
            "requested_start_close_utc": _utc_iso(events[0].close_time) if events else None,
            "requested_end_close_utc": _utc_iso(events[-1].close_time) if events else None,
            "evaluable_start_close_utc": _utc_iso(min(ready_times)) if ready_times else None,
            "evaluable_end_close_utc": _utc_iso(max(ready_times)) if ready_times else None,
            "warmup_ready_at_utc": _utc_iso(cache.warmup_ready_at_by_timeframe[timeframe]),
            "warmup_missing": cache.warmup_ready_at_by_timeframe[timeframe] is None,
        }
    total_requested = sum(item["requested_event_count"] for item in by_timeframe.values())
    total_evaluable = sum(item["evaluable_event_count"] for item in by_timeframe.values())
    return (
        {
            "by_timeframe": by_timeframe,
            "total_requested_event_count": total_requested,
            "total_evaluable_event_count": total_evaluable,
            "timeframes_with_missing_warmup": [
                timeframe for timeframe, item in by_timeframe.items() if item["warmup_missing"]
            ],
            "timeframes_without_evaluable_coverage": [
                timeframe
                for timeframe, item in by_timeframe.items()
                if item["evaluable_event_count"] == 0
            ],
            "fully_prepared_requested_period": all(
                item["requested_event_count"] > 0
                and item["evaluable_event_count"] == item["requested_event_count"]
                and not item["warmup_missing"]
                for item in by_timeframe.values()
            ),
        },
        readiness_by_timeframe,
    )


def _baseline_outcomes(
    inputs: ValidatedInputs,
    start: datetime | None,
    end: datetime | None,
    *,
    matched_windows: dict[str, tuple[datetime | None, datetime | None]] | None = None,
    readiness_by_timeframe: dict[str, dict[datetime, str]] | None = None,
    comparator_report: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    cache = _cache_for(inputs)
    rows: list[dict[str, Any]] = []
    report_by_timeframe: dict[str, Any] = {}
    for timeframe in SIGNAL_TIMEFRAMES:
        frame = inputs.frames[timeframe]
        source = _forward_index(frame, timeframe)
        window_start, window_end = (matched_windows or {}).get(timeframe, (start, end))
        events = events_for_frame(frame, timeframe, window_start, window_end)
        event_readiness = (readiness_by_timeframe or {}).get(timeframe, {})
        exclusions = Counter()
        eligible_count = 0
        for event in events:
            reason = event_readiness.get(event.close_time)
            if reason is None:
                reason = cache.prepare(event, symbol=SYMBOL).reason
            if reason != PREPARATION_READY:
                exclusions[reason] += 1
                continue
            eligible_count += 1
            trigger_price = float(frame.iloc[event.position]["close"])
            for horizon, minutes in HORIZONS:
                outcome = _exact_forward_outcome_from_index(
                    source,
                    timeframe,
                    trigger_close=event.close_time,
                    trigger_price=trigger_price,
                    horizon_minutes=minutes,
                )
                rows.append(
                    {
                        "timeframe": timeframe,
                        "trigger_close_at": _utc_iso(event.close_time),
                        "horizon": horizon,
                        "horizon_minutes": minutes,
                        **outcome,
                    }
                )
        report_by_timeframe[timeframe] = {
            "matched_window_start_close_utc": _utc_iso(events[0].close_time) if events else None,
            "matched_window_end_close_utc": _utc_iso(events[-1].close_time) if events else None,
            "candidate_bar_count": len(events),
            "eligible_bar_count": eligible_count,
            "preparation_excluded_count": len(events) - eligible_count,
            "preparation_exclusion_reasons": dict(sorted(exclusions.items())),
        }
    if comparator_report is not None:
        comparator_report.update(
            {
                "by_timeframe": report_by_timeframe,
                "candidate_bar_count": sum(item["candidate_bar_count"] for item in report_by_timeframe.values()),
                "eligible_bar_count": sum(item["eligible_bar_count"] for item in report_by_timeframe.values()),
                "preparation_excluded_count": sum(item["preparation_excluded_count"] for item in report_by_timeframe.values()),
            }
        )
    return rows


def _metric(values: list[float], *, total: int | None = None) -> dict[str, Any]:
    """Summarize complete returns while retaining the population size."""

    return {
        "n": len(values),
        "n_complete": len(values),
        "n_total": len(values) if total is None else total,
        "mean_return_pct": _round(float(np.mean(values))) if values else None,
        "median_return_pct": _round(float(median(values))) if values else None,
    }


def _summaries(signal_rows: list[dict[str, Any]], baseline_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    summaries: list[dict[str, Any]] = []
    monthly: list[dict[str, Any]] = []
    for timeframe in SIGNAL_TIMEFRAMES:
        for horizon, minutes in HORIZONS:
            signal_subset = [row for row in signal_rows if row["timeframe"] == timeframe and row["horizon"] == horizon]
            baseline_subset = [row for row in baseline_rows if row["timeframe"] == timeframe and row["horizon"] == horizon]
            signal_complete = [float(row["return_pct"]) for row in signal_subset if row["outcome_status"] == "COMPLETE"]
            baseline_complete = [float(row["return_pct"]) for row in baseline_subset if row["outcome_status"] == "COMPLETE"]
            status_counts = {status: sum(row["outcome_status"] == status for row in signal_subset) for status in OUTCOME_STATUSES}
            summary = {
                "timeframe": timeframe,
                "horizon": horizon,
                "horizon_minutes": minutes,
                "signal_outcomes": {**_metric(signal_complete, total=len(signal_subset)), "status_counts": status_counts},
                "baseline_all_eligible_bars": {**_metric(baseline_complete, total=len(baseline_subset)), "status_counts": {
                    status: sum(row["outcome_status"] == status for row in baseline_subset) for status in OUTCOME_STATUSES
                }},
                "cost_sensitivity_illustrative_only": {
                    "round_trip_cost_pct": 0.10,
                    "signal_mean_return_minus_cost_pct": _round(float(np.mean(signal_complete)) - 0.10) if signal_complete else None,
                    "baseline_mean_return_minus_cost_pct": _round(float(np.mean(baseline_complete)) - 0.10) if baseline_complete else None,
                    "not_simulated_fills_or_strategy_pnl": True,
                },
            }
            summaries.append(summary)
            for label, rows in (("signals", signal_subset), ("baseline", baseline_subset)):
                grouped: dict[str, list[float]] = {}
                for row in rows:
                    if row["outcome_status"] == "COMPLETE" and row["return_pct"] is not None:
                        month = str(row["trigger_close_at"])[0:7]
                        grouped.setdefault(month, []).append(float(row["return_pct"]))
                for month, values in sorted(grouped.items()):
                    monthly.append({
                        "population": label,
                        "timeframe": timeframe,
                        "horizon": horizon,
                        "horizon_minutes": minutes,
                        "month": month,
                        **_metric(values),
                    })
    return summaries, monthly


def _git_identity(
    repo_root: Path,
    *,
    excluded_paths: tuple[Path, ...] = (),
) -> dict[str, Any]:
    """Capture revision and actual tracked/untracked content identity.

    Hashing the checked-out contents of tracked files covers both staged and
    unstaged changes. Untracked files are included separately. Generated
    evidence directories are excluded from both the status and content hash so
    writing a packet cannot change the identity of the code that produced it.
    """

    def run(args: list[str]) -> str | None:
        try:
            completed = subprocess.run(args, cwd=repo_root, check=True, capture_output=True, text=True, timeout=3)  # nosec B603
        except (OSError, subprocess.SubprocessError):
            return None
        return completed.stdout

    revision = (run(["git", "rev-parse", "HEAD"]) or "").strip() or None
    status = run(["git", "status", "--porcelain=v1", "--untracked-files=all"]) or ""
    excluded = tuple(path.resolve() for path in excluded_paths)

    def is_excluded(candidate: Path) -> bool:
        return any(candidate == excluded_path or excluded_path in candidate.parents for excluded_path in excluded)

    def status_path(line: str) -> Path | None:
        raw = line[3:]
        if " -> " in raw:
            raw = raw.rsplit(" -> ", 1)[-1]
        candidate = (repo_root / raw).resolve()
        return None if is_excluded(candidate) else candidate

    filtered_status = [line for line in status.splitlines() if status_path(line) is not None]
    identity: list[bytes] = []
    tracked = run(["git", "ls-files", "-z"]) or ""
    untracked = run(["git", "ls-files", "--others", "--exclude-standard", "-z"]) or ""
    relative_names = sorted({name for name in tracked.split("\0") + untracked.split("\0") if name})
    for relative_name in relative_names:
        if not relative_name:
            continue
        candidate = (repo_root / relative_name).resolve()
        if is_excluded(candidate):
            continue
        contents = candidate.read_bytes() if candidate.is_file() else b"<MISSING>"
        identity.extend(
            (
                relative_name.encode("utf-8"),
                b"\0",
                contents,
                b"\0",
            )
        )
    digest = hashlib.sha256(b"".join(identity)).hexdigest()
    return {
        "revision": revision,
        "dirty": bool(filtered_status),
        "dirty_code_identity_sha256": digest,
        "status": filtered_status,
    }


def _config_identity(repo_root: Path) -> dict[str, Any]:
    """Identify the repository configuration used alongside the locked logic."""

    path = repo_root / "config.yaml"
    if not path.is_file():
        return {"path": str(path), "available": False, "sha256": None}
    return {
        "path": str(path.resolve()),
        "available": True,
        "sha256": _hash_file(path),
        "note": "The Phase 1 evaluator has no parameter overrides; this hash records the repository config context.",
    }


def _coverage_report(
    source_report: dict[str, Any],
    start: datetime | None,
    end: datetime | None,
) -> dict[str, Any]:
    """Report common native coverage and any requested-window overrun."""

    files = source_report["files"]
    starts = [datetime.fromisoformat(facts["available_start_close_utc"].replace("Z", "+00:00")) for facts in files.values()]
    ends = [datetime.fromisoformat(facts["available_end_close_utc"].replace("Z", "+00:00")) for facts in files.values()]
    common_start = max(starts)
    common_end = min(ends)
    warnings: list[str] = []
    if start is not None and start < common_start:
        warnings.append("Requested start precedes the common native close-time coverage.")
    if end is not None and end > common_end:
        warnings.append("Requested end exceeds the common native close-time coverage.")
    return {
        "common_start_close_utc": _utc_iso(common_start),
        "common_end_close_utc": _utc_iso(common_end),
        "requested_start_within_common_coverage": start is None or start >= common_start,
        "requested_end_within_common_coverage": end is None or end <= common_end,
        "warnings": warnings,
    }


def _environment() -> dict[str, str]:
    versions = {"python": platform.python_version(), "platform": platform.platform()}
    for package in ("numpy", "pandas", "PyYAML"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "unavailable"
    return versions


def _historical_comparison(repo_root: Path, current_counts: dict[str, int]) -> dict[str, Any]:
    path = repo_root / "research" / "results" / "btc_signal_ev_summary.csv"
    if not path.is_file():
        return {"available": False, "path": str(path)}
    frame = pd.read_csv(path)
    historical = {
        timeframe: int(frame.loc[frame["timeframe"] == timeframe, "n_signals"].iloc[0])
        for timeframe in SIGNAL_TIMEFRAMES
        if not frame.loc[frame["timeframe"] == timeframe].empty
    }
    four_hour = frame[frame["horizon"].eq("4h")]
    return {
        "available": True,
        "path": str(path),
        "sha256": _hash_file(path),
        "historical_signal_counts": historical,
        "current_signal_counts": current_counts,
        "count_deltas_current_minus_historical": {
            timeframe: current_counts.get(timeframe, 0) - historical.get(timeframe, 0)
            for timeframe in SIGNAL_TIMEFRAMES
        },
        "historical_four_hour_mean_return_pct": {
            row["timeframe"]: _round(float(row["signal_mean_return_pct"]))
            for _, row in four_hour.iterrows()
        },
        "comparison_note": "Historical CSV is comparison evidence only; the absent original generator is not claimed reproduced.",
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _write_signals(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _report(summary: dict[str, Any], manifest: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        "# BTC research Phase 1 reproducible baseline",
        "",
        f"- Completion: `{summary['completion_status']}`",
        f"- Operational status: `{summary['operational_status']}`",
        "- Alpha assessment: `NOT_ASSESSED`",
        f"- Window (UTC): `{summary['window']['requested_start_utc'] or 'earliest'} → {summary['window']['requested_end_utc'] or 'latest'}`",
        f"- Signals: M5 `{summary['signal_counts']['5m']}`, M15 `{summary['signal_counts']['15m']}`",
        "",
        "This is a descriptive signal-close forward-return baseline. It is not a TP/SL policy, fill simulation, strategy P&L, or profitability finding. The original historical generator was absent; this CLI is an auditable rebuild using the existing replay evaluator.",
        "",
        "## Reproduction",
        "",
        f"`{manifest['command']}`",
        "",
        "## Source and provenance",
        "",
        f"- Definition: `{DEFINITION_VERSION}`; strategy: `{COMPONENT_NAME}`.",
        f"- Git revision: `{manifest['git']['revision'] or 'unavailable'}`; dirty-code identity: `{manifest['git']['dirty_code_identity_sha256']}`.",
        f"- Config SHA-256: `{manifest['configuration']['sha256'] or 'unavailable'}`.",
        "- Source identity is Binance USD-M Futures, BTC/USDT, native M5/M15/H1/H4 local CSVs. Hashes and cadence facts are in `manifest.json`.",
        f"- Common native close coverage: `{manifest['coverage']['common_start_close_utc']}` → `{manifest['coverage']['common_end_close_utc']}`.",
        "- Warnings: " + ("; ".join(summary["warnings"]) if summary["warnings"] else "none"),
        "",
        "## Preparation and operational validity",
        "",
        "Preparation is evaluated independently of bullish signal gates and cooldown. A `READY` trigger bar is evaluable; missing H1/H4 context, non-finite data, and insufficient contiguous history are recorded as preparation exclusions.",
        f"- Requested trigger bars: `{manifest['preparation']['total_requested_event_count']}`; evaluable after shared preparation: `{manifest['preparation']['total_evaluable_event_count']}`.",
        f"- Preparation exclusions: `{manifest['preparation']['total_requested_event_count'] - manifest['preparation']['total_evaluable_event_count']}`; per-timeframe counts and reasons are in `manifest.json` and `summary.json`.",
        f"- Operational status is `{summary['operational_status']}` while execution completion is `{summary['completion_status']}`. Missing warmup or no evaluable requested coverage is `INVALID`; partial readiness or incomplete outcomes is `INCOMPLETE`; a fully prepared zero-signal period may be `VALID`.",
        "",
        "## Comparator eligibility",
        "",
        "The matched all-eligible-bar comparator uses the same per-event point-in-time preparation as replay, but does not apply bullish gates, signal rules, or cooldown. Comparator exclusions and reasons are recorded under `baseline_comparator`.",
        "",
        "## Signal and matched all-eligible-bar summaries",
        "",
        "| Timeframe | Horizon | Signal complete / total | Signal mean % | Signal median % | Baseline complete / total | Baseline mean % | Baseline median % |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summary["horizon_summaries"]:
        signal = item["signal_outcomes"]
        baseline = item["baseline_all_eligible_bars"]
        lines.append(
            f"| {item['timeframe']} | {item['horizon']} | {signal['n_complete']} / {signal['n_total']} | {signal['mean_return_pct']} | {signal['median_return_pct']} | {baseline['n_complete']} / {baseline['n_total']} | {baseline['mean_return_pct']} | {baseline['median_return_pct']} |"
        )
    lines.extend(["", "Outcome statuses are exact: `COMPLETE`, `INCOMPLETE_TAIL`, `MISSING_TARGET`, or `GAP`. A target candle after the exact target time is never substituted, and gaps are not bridged.", ""])
    lines.extend(["## Monthly summaries", "", "Monthly rows for signals and matched all-eligible bars are in `summary.json` under `monthly_summaries`; only complete exact-horizon outcomes enter monthly means.", ""])
    lines.extend(["## Limitations", "", "- Alpha remains `NOT_ASSESSED`: no reserved evaluation, selection-aware analysis, bootstrap, DSR/PBO, walk-forward, or cost model is part of Phase 1.", "- The 0.10% round-trip cost subtraction is illustrative sensitivity only; it is not an exchange fee, spread, slippage, funding, fill, or P&L simulation.", "- Historical artifact counts and 4h means are reported for comparison, not hardcoded as acceptance targets.", "- The run uses the available local CSV coverage; incomplete tails remain explicitly visible.", "- Replay initializes cooldown at the requested window start. Separate windows have independent one-hour boundary state; comparisons must account for that behavior.", ""])
    return "\n".join(lines)


def run_phase1_baseline(
    data_dir: str | Path,
    output_dir: str | Path,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    repo_root: str | Path | None = None,
) -> Path:
    """Run the baseline and write one timestamped evidence packet."""

    root = Path(repo_root or Path(__file__).resolve().parents[2]).resolve()
    inputs = validate_inputs(data_dir)

    def as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            value = value.replace(tzinfo=UTC_PLUS_7)
        return value.astimezone(UTC)

    start_utc = as_utc(start)
    end_utc = as_utc(end)
    if start_utc and end_utc and start_utc > end_utc:
        raise ValueError("start must be before or equal to end")
    replay = run_btc_alert_replay(
        inputs.paths["5m"], inputs.paths["15m"], inputs.paths["4h"],
        h1_path=inputs.paths["1h"], start_utc7=start_utc, end_utc7=end_utc, write_output=False,
    )
    signal_rows: list[dict[str, Any]] = []
    forward_sources = {timeframe: _forward_index(inputs.frames[timeframe], timeframe) for timeframe in SIGNAL_TIMEFRAMES}
    for signal in replay.signals:
        for horizon, minutes in HORIZONS:
            signal_rows.append(_signal_row(signal, _exact_forward_outcome_from_index(
                forward_sources[signal.timeframe], signal.timeframe,
                trigger_close=signal.data.trigger_close_time,
                trigger_price=float(signal.data.trigger_close_price),
                horizon_minutes=minutes,
            ), horizon, minutes))
    matched_windows: dict[str, tuple[datetime | None, datetime | None]] = {}
    for timeframe in SIGNAL_TIMEFRAMES:
        signal_times = [signal.data.trigger_close_time.astimezone(UTC) for signal in replay.signals if signal.timeframe == timeframe]
        matched_windows[timeframe] = (
            (min(signal_times) if signal_times else start_utc),
            (max(signal_times) if signal_times else end_utc),
        )
    preparation_cache = _cache_for(inputs)
    preparation, readiness_by_timeframe = _preparation_coverage(
        inputs, start_utc, end_utc, preparation_cache
    )
    comparator_report: dict[str, Any] = {}
    baseline_rows = _baseline_outcomes(
        inputs,
        start_utc,
        end_utc,
        matched_windows=matched_windows,
        readiness_by_timeframe=readiness_by_timeframe,
        comparator_report=comparator_report,
    )
    horizon_summaries, monthly_summaries = _summaries(signal_rows, baseline_rows)
    signal_counts = {timeframe: sum(1 for signal in replay.signals if signal.timeframe == timeframe) for timeframe in SIGNAL_TIMEFRAMES}
    outcome_incomplete = sum(1 for row in signal_rows if row["outcome_status"] != "COMPLETE")
    coverage = _coverage_report(inputs.source_report, start_utc, end_utc)
    coverage["evaluable_requested_coverage"] = preparation
    source_warnings = list(inputs.source_report["warnings"])
    preparation_warnings: list[str] = []
    for timeframe, item in preparation["by_timeframe"].items():
        if item["warmup_missing"]:
            preparation_warnings.append(f"{timeframe} has no required preparation warmup; requested bars are not evaluable.")
        if item["requested_event_count"] and item["evaluable_event_count"] == 0:
            preparation_warnings.append(f"{timeframe} has no evaluable requested trigger coverage after preparation.")
        if item["preparation_excluded_count"] and item["evaluable_event_count"]:
            preparation_warnings.append(
                f"{timeframe} excludes {item['preparation_excluded_count']} trigger bars during shared preparation: "
                + ", ".join(f"{reason}={count}" for reason, count in item["preparation_exclusion_reasons"].items())
                + "."
            )
    warnings = source_warnings + coverage["warnings"] + preparation_warnings + ([f"{outcome_incomplete} signal-horizon outcomes are incomplete or invalid; exact targets were not substituted."] if outcome_incomplete else [])
    invalid_preparation = bool(
        preparation["timeframes_with_missing_warmup"]
        or preparation["timeframes_without_evaluable_coverage"]
    )
    operational_status = "INVALID" if invalid_preparation else "INCOMPLETE" if warnings else "VALID"
    timestamp = datetime.now(UTC)
    run_name = f"run_{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}_{_hash_file(inputs.paths['5m'])[:8]}"
    packet = Path(output_dir).resolve() / run_name
    packet.mkdir(parents=True, exist_ok=False)
    comparison = _historical_comparison(root, signal_counts)
    warmup = preparation_cache.warmup_ready_at_by_timeframe
    manifest = {
        "completion_status": "SUCCESS",
        "run_id": run_name,
        "generated_at_utc": _utc_iso(timestamp),
        "command": " ".join(sys.argv),
        "repository_root": str(root),
        "definition_version": DEFINITION_VERSION,
        "strategy": {"name": COMPONENT_NAME, "symbol": SYMBOL, "venue": VENUE, "venue_instrument": VENUE_INSTRUMENT, "logic_source": "app.backtest.signal_replay + existing btc_rsi_cross_alert evaluator"},
        "window": {"requested_start_utc": _utc_iso(start_utc), "requested_end_utc": _utc_iso(end_utc), "trigger_close_semantics": "inclusive"},
        "inputs": inputs.source_report,
        "warmup": {timeframe: _utc_iso(warmup[timeframe]) for timeframe in SIGNAL_TIMEFRAMES},
        "git": _git_identity(root, excluded_paths=(Path(output_dir).resolve(),)),
        "configuration": _config_identity(root),
        "environment": _environment(),
        "coverage": coverage,
        "preparation": preparation,
        "baseline_comparator": comparator_report,
        "historical_artifact_comparison": comparison,
        "definitions": {
            "return": "gross close-to-close percentage = (exact target close / trigger close - 1) * 100",
            "horizons": [f"{minutes} minutes" for _, minutes in HORIZONS],
            "outcome_statuses": list(OUTCOME_STATUSES),
            "baseline": "all native trigger bars in each matched signal coverage window that pass the shared per-event point-in-time preparation; no bullish gate, signal rule, or cooldown is applied",
            "preparation": "A requested trigger bar is evaluable only when the shared replay preparation returns READY, including trigger history and exact point-in-time H1/H4 context; exclusions are retained by reason.",
            "operational_status": "INVALID for missing required warmup or no evaluable requested coverage; INCOMPLETE for partial readiness or incomplete requested outcomes; VALID only when requested coverage is fully prepared and complete.",
            "replay_boundary_cooldown": "Replay initializes independent one-hour M5/M15 cooldown state at the requested window start; separate windows do not inherit prior alerts.",
            "cost_sensitivity": "illustrative mean return percentage minus 0.10 percentage points; not simulated execution or P&L",
            "alpha_assessment": "NOT_ASSESSED",
        },
        "warnings": warnings,
    }
    summary = {
        "completion_status": "SUCCESS",
        "operational_status": operational_status,
        "alpha_assessment": "NOT_ASSESSED",
        "definition_version": DEFINITION_VERSION,
        "window": manifest["window"],
        "coverage": coverage,
        "preparation": preparation,
        "baseline_comparator": comparator_report,
        "signal_counts": signal_counts,
        "replay_counts": {field: getattr(replay.counts, field) for field in replay.counts.__dataclass_fields__},
        "horizon_summaries": horizon_summaries,
        "monthly_summaries": monthly_summaries,
        "warnings": warnings,
        "historical_artifact_comparison": comparison,
    }
    _write_signals(packet / "signals.csv", signal_rows)
    _write_json(packet / "manifest.json", manifest)
    _write_json(packet / "summary.json", summary)
    (packet / "report.md").write_text(_report(summary, manifest, signal_rows), encoding="utf-8")
    return packet


def parse_cli_boundary(raw: str, *, is_end: bool) -> datetime:
    parsed = datetime.fromisoformat(raw)
    if len(raw) == 10 and is_end:
        parsed += timedelta(days=1) - timedelta(microseconds=1)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC_PLUS_7)
    return parsed.astimezone(UTC)
