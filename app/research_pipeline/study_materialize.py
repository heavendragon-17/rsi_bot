"""Reconstruct a missing frozen all-bar comparator into a new derived packet."""

from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.backtest.signal_replay_data import load_ohlcv_csv
from research import btc_m5_horizon_diagnostic as diagnostic

from . import study_checks
from .tools import _safe_path, _sha256

SCHEMA = "btc-m5-study-materialization-v1"
PACKET_FILES = ("manifest.json", "signals.csv", "summary.json", "report.md")


def _bytes_hash(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def _json(contents: bytes, label: str) -> dict[str, Any]:
    value = json.loads(contents)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _read_packet(directory: Path, roots: tuple[Path, ...]) -> dict[str, bytes]:
    return {name: _safe_path(str(directory / name), label=name, roots=roots).read_bytes() for name in PACKET_FILES}


def _restore_parent(contents: dict[str, bytes], expected: dict) -> tuple[dict[str, bytes], dict[str, str]]:
    restored, transformations = {}, {}
    if set(expected) != set(PACKET_FILES):
        raise ValueError("Frozen parent must bind exactly the four canonical packet files")
    for name, raw in contents.items():
        if _bytes_hash(raw) == expected[name]:
            restored[name], transformations[name] = raw, "UNCHANGED"
        else:
            normalized = raw.replace(b"\r\n", b"\n")
            if _bytes_hash(normalized) != expected[name]:
                raise ValueError(f"parent {name} differs from both frozen raw and exact LF identity")
            restored[name], transformations[name] = normalized, "CRLF_TO_LF_EXACT_EXPECTED_HASH"
    return restored, transformations


def _rebuild_baseline(frame: pd.DataFrame, positions: np.ndarray) -> pd.DataFrame:
    """Vectorized equivalent of the frozen four-horizon profile for all bars."""
    closes_at = pd.DatetimeIndex(frame.index) + pd.Timedelta(minutes=5)
    prices = frame.close.to_numpy(dtype=float)
    trigger_at = closes_at[positions]
    trigger_text = trigger_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    breaks = np.zeros(len(frame), dtype=np.int64)
    breaks[1:] = np.asarray(closes_at[1:] - closes_at[:-1]) != np.timedelta64(5, "m")
    prefix = breaks.cumsum()
    parts, complete_masks = [], []
    for horizon in diagnostic.HORIZONS:
        targets = trigger_at + pd.Timedelta(minutes=horizon)
        ends = closes_at.get_indexer(targets)
        safe_ends = np.maximum(ends, 0)
        statuses = np.full(len(positions), "COMPLETE", dtype=object)
        statuses[prefix[safe_ends] != prefix[positions]] = "GAP"
        statuses[ends < 0] = "MISSING_TARGET"
        statuses[(ends < 0) & (targets > closes_at[-1])] = "INCOMPLETE_TAIL"
        complete = statuses == "COMPLETE"
        complete_masks.append(complete)
        steps = horizon // 5
        future_high = frame.high.rolling(steps, min_periods=steps).max().shift(-steps).to_numpy()[positions]
        future_low = frame.low.rolling(steps, min_periods=steps).min().shift(-steps).to_numpy()[positions]
        trigger_price = prices[positions]
        parts.append(pd.DataFrame({
            "event_id": "bar_" + trigger_text, "trigger_close_at": trigger_text,
            "trigger_close_price": trigger_price, "horizon_minutes": horizon,
            "target_close_at": targets.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "target_close_price": np.where(complete, prices[safe_ends], np.nan), "outcome_status": statuses,
            "return_pct": np.where(complete, np.round((prices[safe_ends] / trigger_price - 1) * 100, 12), np.nan),
            "mfe_pct": np.where(complete, np.maximum(0, (future_high / trigger_price - 1) * 100), np.nan),
            "mae_pct": np.where(complete, np.minimum(0, (future_low / trigger_price - 1) * 100), np.nan),
            "_source_position": positions,
        }))
    matched = np.logical_and.reduce(complete_masks)
    for part in parts:
        part["included_all_horizons"] = matched
    return pd.concat(parts, ignore_index=True).sort_values(["_source_position", "horizon_minutes"]).drop(columns="_source_position").reset_index(drop=True)


def _verify_saved_summary(baseline: pd.DataFrame, summary: dict) -> None:
    horizons = summary.get("horizon_summaries", [])
    if sorted(item["horizon_minutes"] for item in horizons) != list(diagnostic.HORIZONS):
        raise ValueError("Saved summary requires exactly four baseline horizons")
    for item in horizons:
        observed = diagnostic.metrics(baseline.loc[baseline.horizon_minutes.eq(item["horizon_minutes"])])
        expected = item["baseline"]
        for field, value in observed.items():
            saved = expected.get(field)
            if isinstance(value, float):
                matches = isinstance(saved, (float, int)) and bool(np.isclose(value, saved, rtol=0, atol=1e-10))
            else:
                matches = value == saved
            if not matches:
                raise ValueError(f"Saved baseline summary parity failed: {item['horizon_minutes']}m {field}")
    excluded = int(baseline.loc[~baseline.included_all_horizons, "event_id"].nunique())
    if excluded != summary.get("excluded_baseline_count"):
        raise ValueError("Saved excluded baseline count differs")


def materialize_study_packet(*, repo_root: Path, horizon_packet: Path, baseline_packet: Path,
                             data_dir: Path, workspace: Path) -> dict[str, str]:
    """Create new verified derived inputs; never rewrite a historical packet.

    Reconstruction is permitted only for a frozen comparator where every candidate
    was preparation-eligible. More selective populations require their saved rows.
    """
    root = Path(repo_root).resolve()
    results = ((root / "research/results").resolve(),)
    data_roots = ((root / "research/data").resolve(), (root / "app/backtest/data").resolve())
    horizon_packet = _safe_path(str(horizon_packet), label="horizon_packet", roots=results, base_dir=root)
    baseline_packet = _safe_path(str(baseline_packet), label="baseline_packet", roots=results, base_dir=root)
    data_dir = _safe_path(str(data_dir), label="data_dir", roots=data_roots, base_dir=root)
    workspace = _safe_path(str(workspace), label="workspace", roots=results, must_exist=False, base_dir=root)
    if workspace.exists():
        raise FileExistsError(f"Derived workspace already exists: {workspace}")
    if any(packet == workspace or packet in workspace.parents for packet in (horizon_packet, baseline_packet)):
        raise ValueError("Derived workspace must not be inside a historical packet")
    horizon_files, parent_files = _read_packet(horizon_packet, results), _read_packet(baseline_packet, results)
    manifest = _json(horizon_files["manifest.json"], "horizon manifest")
    summary = _json(horizon_files["summary.json"], "horizon summary")
    if (manifest.get("definition_version") != diagnostic.VERSION or manifest.get("completion_status") != "SUCCESS"
            or manifest.get("definitions", {}).get("horizons_minutes") != list(diagnostic.HORIZONS)):
        raise ValueError("Horizon packet has an unsupported or incomplete definition")
    parent_facts = manifest["parent"]
    restored_parent, transformations = _restore_parent(parent_files, parent_facts["files_sha256"])
    parent_manifest = _json(restored_parent["manifest.json"], "parent manifest")
    parent_id, horizon_id = parent_manifest.get("run_id"), manifest.get("run_id")
    if (parent_manifest.get("completion_status") != "SUCCESS" or parent_id != parent_facts["run_id"]
            or parent_id != baseline_packet.name or horizon_id != horizon_packet.name or parent_id == horizon_id):
        raise ValueError("Historical packet run IDs do not match their directory contracts")
    comparator = manifest["comparator"]
    candidate_n = comparator["candidate_bar_count"]
    if (isinstance(candidate_n, bool) or not isinstance(candidate_n, int) or candidate_n <= 0
            or comparator["eligible_bar_count"] != candidate_n or comparator["preparation_excluded_count"] != 0
            or any(comparator.get("preparation_exclusion_reasons", {}).values())):
        raise ValueError("Cannot reconstruct a comparator with preparation exclusions or unknown eligibility")
    source_paths, source_hashes = {}, {}
    for timeframe, facts in manifest["inputs"]["files"].items():
        if timeframe not in {"5m", "15m", "1h", "4h"}:
            raise ValueError(f"Unregistered source timeframe: {timeframe}")
        source = _safe_path(str(data_dir / f"BTCUSDT_{timeframe}.csv"), label=f"{timeframe} source", roots=data_roots)
        observed = _sha256(source)
        if observed != facts.get("sha256"):
            raise ValueError(f"Current {timeframe} source bytes differ from frozen SHA-256")
        source_paths[timeframe], source_hashes[timeframe] = source, observed
    if not {"5m", "1h"}.issubset(source_paths):
        raise ValueError("Frozen M5 and H1 source identities are required")
    frame = load_ohlcv_csv(source_paths["5m"], "5m")
    closes_at = pd.DatetimeIndex(frame.index) + pd.Timedelta(minutes=5)
    start, end = pd.Timestamp(comparator["window_start_close_utc"]), pd.Timestamp(comparator["window_end_close_utc"])
    if start.tzinfo is None or end.tzinfo is None or start > end:
        raise ValueError("Comparator requires ordered timezone-aware boundaries")
    positions = np.flatnonzero((closes_at >= start) & (closes_at <= end))
    if len(positions) != candidate_n:
        raise ValueError("Current native candidate count differs from frozen comparator")
    signals = study_checks.normalize_rows(pd.read_csv(io.BytesIO(horizon_files["signals.csv"]), keep_default_na=False), "signals")
    checks = study_checks.check_raw_returns(signals, frame, "signals")
    if not all(check["passed"] for check in checks):
        raise ValueError("Saved signal raw-candle verification failed")
    baseline = _rebuild_baseline(frame, positions)
    checked_baseline = study_checks.normalize_rows(baseline, "baseline")
    checks.extend(study_checks.check_raw_returns(checked_baseline, frame, "baseline"))
    parent_rows = pd.read_csv(io.BytesIO(restored_parent["signals.csv"]), keep_default_na=False)
    checks.extend(study_checks.check_population(signals, checked_baseline, parent_rows, manifest, frame))
    if not all(check["passed"] for check in checks):
        failed = [check["name"] for check in checks if not check["passed"]]
        raise ValueError("Reconstructed comparator check failed: " + ", ".join(failed))
    _verify_saved_summary(baseline, summary)
    # Recheck originals before publishing derived files. Their bytes are never changed.
    originals = {**{str(horizon_packet / name): _bytes_hash(raw) for name, raw in horizon_files.items()},
                 **{str(baseline_packet / name): _bytes_hash(raw) for name, raw in parent_files.items()},
                 **{str(source_paths[timeframe]): sha for timeframe, sha in source_hashes.items()}}
    if any(_sha256(Path(path)) != expected for path, expected in originals.items()):
        raise ValueError("Historical packet or source changed during reconstruction")
    workspace.mkdir(parents=True, exist_ok=False)
    derived_parent, derived_horizon = workspace / parent_id, workspace / horizon_id
    derived_parent.mkdir()
    derived_horizon.mkdir()
    for name, contents in restored_parent.items():
        (derived_parent / name).write_bytes(contents)
    for name, contents in horizon_files.items():
        if name != "manifest.json":
            (derived_horizon / name).write_bytes(contents)
    baseline.to_csv(derived_horizon / "baseline.csv", index=False, lineterminator="\n")
    derived_manifest = copy.deepcopy(manifest)
    for timeframe, path in source_paths.items():
        derived_manifest["inputs"]["files"][timeframe]["path"] = str(path)
    derived_manifest["parent"]["path"] = str(derived_parent)
    derived_manifest["materialization"] = {
        "schema": SCHEMA, "original_horizon_packet": str(horizon_packet), "original_parent_packet": str(baseline_packet),
        "original_file_sha256": originals, "original_comparator": comparator,
        "source_sha256": source_hashes, "parent_copy_transformations": transformations,
        "baseline_rows": len(baseline), "baseline_events": len(positions), "saved_summary_parity": True,
        "baseline_sha256": _sha256(derived_horizon / "baseline.csv"), "code_sha256": _sha256(Path(__file__)),
        "limitation": "Reconstructed numerical comparator; original absent baseline CSV byte identity is unknown. Alpha NOT_ASSESSED.",
    }
    (derived_horizon / "manifest.json").write_text(json.dumps(derived_manifest, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    output_hashes = {str(path.relative_to(workspace)): _sha256(path)
                     for directory in (derived_parent, derived_horizon) for path in directory.iterdir() if path.is_file()}
    report = {"schema": SCHEMA, "status": "VERIFIED", "alpha_assessment": "NOT_ASSESSED", "checks": checks,
              "baseline_events": len(positions), "baseline_rows": len(baseline), "saved_summary_parity": True,
              "output_sha256": output_hashes, "historical_input_sha256": originals}
    (workspace / "materialization_report.json").write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return {"horizon_packet": str(derived_horizon), "baseline_packet": str(derived_parent), "data_dir": str(data_dir)}
