"""Fixed, bounded research tools exposed to executors."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.backtest import btc_research_phase1 as phase1
from app.backtest.signal_replay_data import load_ohlcv_csv
from research import btc_m5_horizon_diagnostic as horizon_diagnostic

from .contracts import M5_VERIFICATION_TASK, ContractError, VerifyM5HorizonsParameters, object_hash


class ToolRestrictionError(ValueError):
    """Raised when a model-selected tool or path is outside the catalog."""


class ToolVerificationError(ValueError):
    """Raised only for malformed tool inputs; evidence mismatches are results."""


class ToolInputAccessError(OSError):
    """Raised when a frozen input cannot be read or hashed."""


@dataclass(frozen=True)
class ToolContext:
    repo_root: Path
    workspace: Path
    frozen_inputs: Mapping[str, Any] = field(default_factory=dict)


def _inside(path: Path, roots: tuple[Path, ...]) -> bool:
    resolved = path.resolve()
    return any(resolved == root or root in resolved.parents for root in roots)


def _safe_path(raw: Any, *, label: str, roots: tuple[Path, ...], must_exist: bool = True, base_dir: Path | None = None) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ToolRestrictionError(f"{label} must be a non-empty path string")
    path = Path(raw).expanduser()
    if not path.is_absolute() and base_dir is not None:
        # Model contracts may contain repository-relative paths. Resolve them
        # against the controller's repository, never the caller's cwd.
        path = base_dir / path
    path = path.resolve()
    if not _inside(path, roots):
        raise ToolRestrictionError(f"{label} is outside the registered research boundary")
    if must_exist:
        try:
            exists = path.is_file() or path.is_dir()
        except OSError as exc:
            raise ToolInputAccessError(f"{label} is not readable: {path}: {exc}") from exc
        if not exists:
            raise ToolVerificationError(f"{label} does not exist: {path}")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ToolInputAccessError(f"could not hash {path}: {exc}") from exc
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ToolInputAccessError(f"could not load JSON evidence {path}: {exc}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ToolVerificationError(f"could not load JSON evidence {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ToolVerificationError(f"evidence JSON must be an object: {path}")
    return value


def _event_rows(path: Path, event_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        frame = pd.read_csv(path, keep_default_na=False)
    except OSError as exc:
        raise ToolInputAccessError(f"could not load saved horizon rows {path}: {exc}") from exc
    except pd.errors.ParserError as exc:
        raise ToolVerificationError(f"could not load saved horizon rows {path}: {exc}") from exc
    rows = frame.loc[(frame["event_id"] == event_id) & frame["horizon_minutes"].isin([60, 120, 180])]
    if len(rows) != 3 or set(rows["horizon_minutes"]) != {60, 120, 180}:
        raise ToolVerificationError(f"saved evidence must contain exactly 1h/2h/3h rows for {event_id}")
    records = rows.to_dict(orient="records")
    identity = records[0]
    for row in records[1:]:
        for key in ("event_id", "trigger_close_at", "trigger_close_price"):
            if row[key] != identity[key]:
                raise ToolVerificationError(f"saved event identity differs across horizons: {key}")
    return identity, records


def _write_fixture_source(path: Path, expected: dict[str, Any]) -> None:
    trigger = datetime.fromisoformat(str(expected["trigger_close_at"]).replace("Z", "+00:00"))
    trigger_price = float(expected["trigger_close_price"])
    target_prices = {int(expected_row["horizon_minutes"]): float(expected_row["target_close_price"]) for expected_row in expected["rows"]}
    start_open = trigger - timedelta(minutes=5)
    rows: list[dict[str, Any]] = []
    for step in range(37):
        open_time = start_open + timedelta(minutes=5 * step)
        close_time = open_time + timedelta(minutes=5)
        close = target_prices.get(int((close_time - trigger).total_seconds() // 60), trigger_price)
        stamp = open_time.astimezone(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M:%S")
        rows.append({"timestamp": stamp, "open": close, "high": close, "low": close, "close": close, "volume": 1.0})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(rows)


def _expected_from_packet(horizon_packet: Path, event_index: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    frame = pd.read_csv(horizon_packet / "signals.csv", keep_default_na=False)
    events = frame.loc[frame["horizon_minutes"].isin([60, 120, 180]), ["event_id", "trigger_close_at"]].drop_duplicates().sort_values("trigger_close_at")
    if event_index < 0 or event_index >= len(events):
        raise ToolVerificationError(f"event_index {event_index} is outside the saved M5 evidence")
    event_id = str(events.iloc[event_index]["event_id"])
    return _event_rows(horizon_packet / "signals.csv", event_id)


def current_input_identity(params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Read and hash the current frozen inputs before any cache reuse."""

    results_root = (context.repo_root / "research" / "results").resolve()
    horizon_packet = _safe_path(params.get("horizon_packet"), label="horizon_packet", roots=(results_root,), base_dir=context.repo_root)
    manifest_path = horizon_packet / "manifest.json"
    manifest = _load_json(manifest_path)
    source_info = manifest.get("inputs", {}).get("files", {}).get("5m", {})
    if not isinstance(source_info, dict):
        raise ToolVerificationError("horizon manifest inputs.files.5m must be an object")
    horizon_manifest_sha256 = _sha256(manifest_path)
    horizon_signals_sha256 = _sha256(horizon_packet / "signals.csv")
    baseline_manifest_sha256 = None
    baseline_raw = params.get("baseline_packet")
    if baseline_raw:
        baseline_packet = _safe_path(baseline_raw, label="baseline_packet", roots=(results_root,), base_dir=context.repo_root)
        baseline_manifest_sha256 = _sha256(baseline_packet / "manifest.json")
    mode = params.get("mode", "fixture")
    source_path = source_info.get("path")
    source_sha256 = source_info.get("sha256")
    source_expected_sha256 = source_info.get("sha256")
    if mode == "real":
        source_path = params.get("source_csv") or source_path
        source_file = _safe_path(source_path, label="source_csv", roots=((context.repo_root / "research" / "data").resolve(), (context.repo_root / "app" / "backtest" / "data").resolve()), base_dir=context.repo_root)
        source_path = str(source_file)
        source_sha256 = _sha256(source_file)
    elif isinstance(source_path, str):
        source_path = str(Path(source_path).expanduser().resolve())
    identity = {
        "baseline_manifest_sha256": baseline_manifest_sha256,
        "horizon_manifest_sha256": horizon_manifest_sha256,
        "horizon_signals_sha256": horizon_signals_sha256,
        "source_path": source_path,
        "source_sha256": source_sha256,
        "source_expected_sha256": source_expected_sha256,
        "mode": mode,
    }
    mismatches: list[str] = []
    if mode == "real" and not source_expected_sha256:
        mismatches.append("horizon manifest has no expected 5m source SHA-256")
    if mode == "real" and source_expected_sha256 and source_sha256 != source_expected_sha256:
        mismatches.append(f"source SHA-256 differs from manifest: expected {source_expected_sha256}, observed {source_sha256}")
    for key in ("baseline_manifest_sha256", "horizon_manifest_sha256", "horizon_signals_sha256", "source_sha256", "source_path"):
        frozen = context.frozen_inputs.get(key)
        current = identity.get(key)
        if frozen is not None and current != frozen:
            mismatches.append(f"frozen {key} differs: expected {frozen}, observed {current}")
    identity["mismatches"] = mismatches
    return identity


def verification_cache_key(params: dict[str, Any], context: ToolContext) -> str:
    """Build the immutable identity used to reuse a completed verification.

    The key includes the selected parameters, source/packet hashes, horizon
    definitions, and the exact checker/evaluator source files. A new protocol
    or code revision therefore cannot silently consume an old result.
    """

    input_identity = current_input_identity(params, context)
    code_paths = (Path(__file__), Path(phase1.__file__), Path(horizon_diagnostic.__file__))
    return object_hash({
        "tool": "verify_m5_horizons",
        "protocol": "btc-m5-verification-evidence-v1",
        "parameters": params,
        "horizons_minutes": [60, 120, 180],
        "input_identity": input_identity,
        "code_sha256": {str(path): _sha256(path) for path in code_paths},
    })


def verify_m5_horizons(params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Independently recompute one saved event's 1h/2h/3h targets.

    The tool reads only a native M5 CSV and saved packet rows, then delegates
    target arithmetic to the existing horizon evaluator. It never executes a
    candidate command or arbitrary generated code.
    """

    allowed = {"mode", "event_index", "baseline_packet", "horizon_packet", "source_csv", "tamper_target_timestamp"}
    if not isinstance(params, dict) or set(params) - allowed:
        raise ContractError("verify_m5_horizons received unsupported parameters")
    mode = params.get("mode", "fixture")
    if mode not in {"fixture", "real"}:
        raise ContractError("verify_m5_horizons.mode must be fixture or real")
    VerifyM5HorizonsParameters.from_mapping({"mode": mode, "event_index": params.get("event_index", 0)})
    results_root = (context.repo_root / "research" / "results").resolve()
    horizon_packet = _safe_path(params.get("horizon_packet"), label="horizon_packet", roots=(results_root,), base_dir=context.repo_root)
    if not horizon_packet.is_dir():
        raise ToolRestrictionError("horizon_packet must be a directory")
    manifest = _load_json(horizon_packet / "manifest.json")
    baseline_raw = params.get("baseline_packet")
    baseline_packet = _safe_path(baseline_raw, label="baseline_packet", roots=(results_root,), base_dir=context.repo_root) if baseline_raw else None
    baseline_manifest = _load_json(baseline_packet / "manifest.json") if baseline_packet else None
    if baseline_manifest and manifest.get("parent", {}).get("run_id") != baseline_manifest.get("run_id"):
        raise ToolVerificationError("horizon packet is not descended from the requested baseline packet")
    cache_params = {**params, "horizon_packet": str(horizon_packet), "baseline_packet": str(baseline_packet) if baseline_packet else None}
    input_identity = current_input_identity(cache_params, context)
    cache_key = verification_cache_key(cache_params, context)
    if input_identity["mismatches"]:
        evidence = {
            "schema": "btc-m5-verification-evidence-v1",
            "status": "FAILED",
            "verification_mode": "fixture_validation" if mode == "fixture" else "real_local_data",
            "event_index": int(params.get("event_index", 0)),
            "horizons_minutes": [60, 120, 180],
            "checks": [],
            "input_identity": input_identity,
            "cache_key": cache_key,
            "saved_horizon_packet": str(horizon_packet),
            "saved_horizon_packet_sha256": input_identity["horizon_signals_sha256"],
            "verification_reason": "frozen_input_identity_mismatch",
            "limitations": ["current frozen inputs were not accepted; no numerical success is claimed", "not a fill, P&L, alpha, or strategy approval"],
        }
        evidence["result_id"] = object_hash({"status": evidence["status"], "event_index": evidence["event_index"], "input_identity": input_identity, "mode": mode})[:24]
        artifact_dir = context.workspace / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "evidence.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return evidence
    expected_identity, expected_rows = _expected_from_packet(horizon_packet, int(params.get("event_index", 0)))
    source_csv: Path
    if mode == "fixture":
        source_csv = context.workspace / "fixture_source_5m.csv"
        _write_fixture_source(source_csv, {"trigger_close_at": expected_identity["trigger_close_at"], "trigger_close_price": expected_identity["trigger_close_price"], "rows": expected_rows})
    else:
        source_raw = params.get("source_csv") or manifest.get("inputs", {}).get("files", {}).get("5m", {}).get("path")
        source_csv = _safe_path(source_raw, label="source_csv", roots=((context.repo_root / "research" / "data").resolve(), (context.repo_root / "app" / "backtest" / "data").resolve()), base_dir=context.repo_root)
        expected_hash = manifest.get("inputs", {}).get("files", {}).get("5m", {}).get("sha256")
        if expected_hash and _sha256(source_csv) != expected_hash:
            raise ToolVerificationError("source identity changed after the preflight identity check")
    frame = load_ohlcv_csv(source_csv, "5m")
    trigger_time = datetime.fromisoformat(str(expected_identity["trigger_close_at"]).replace("Z", "+00:00"))
    recomputed = horizon_diagnostic.profile(frame, [trigger_time], [str(expected_identity["event_id"])])
    actual_rows = {int(row["horizon_minutes"]): row for row in recomputed.to_dict(orient="records")}
    checks: list[dict[str, Any]] = []
    for expected in expected_rows:
        horizon = int(expected["horizon_minutes"])
        actual = actual_rows[horizon]
        comparison = {
            "trigger_close_at": actual["trigger_close_at"] == expected["trigger_close_at"],
            "trigger_close_price": float(actual["trigger_close_price"]) == float(expected["trigger_close_price"]),
            "target_close_at": actual["target_close_at"] == (str(params.get("tamper_target_timestamp")) if horizon == 120 and params.get("tamper_target_timestamp") else expected["target_close_at"]),
            "target_close_price": abs(float(actual["target_close_price"]) - float(expected["target_close_price"])) <= 1e-10,
            "outcome_status": actual["outcome_status"] == expected["outcome_status"],
            "return_pct": abs(float(actual["return_pct"]) - float(expected["return_pct"])) <= 1e-10,
        }
        checks.append({"horizon_minutes": horizon, "passed": all(comparison.values()), "fields": comparison, "actual": {key: actual[key] for key in ("target_close_at", "target_close_price", "outcome_status", "return_pct")}, "expected": {key: expected[key] for key in ("target_close_at", "target_close_price", "outcome_status", "return_pct")}})
    status = "VERIFIED" if all(item["passed"] for item in checks) else "FAILED"
    evidence = {
        "schema": "btc-m5-verification-evidence-v1",
        "status": status,
        "verification_mode": "fixture_validation" if mode == "fixture" else "real_local_data",
        "event_id": expected_identity["event_id"],
        "trigger_close_at": expected_identity["trigger_close_at"],
        "horizons_minutes": [60, 120, 180],
        "checks": checks,
        "source": {"path": str(source_csv), "sha256": _sha256(source_csv), "saved_source_sha256": manifest.get("inputs", {}).get("files", {}).get("5m", {}).get("sha256") if mode == "real" else None},
        "saved_horizon_packet": str(horizon_packet),
        "saved_horizon_packet_sha256": _sha256(horizon_packet / "signals.csv"),
        "cache_key": cache_key,
        "input_identity": input_identity,
        "evaluator": "research.btc_m5_horizon_diagnostic.profile + app.backtest.btc_research_phase1._exact_forward_outcome_from_index",
        "limitations": ["close-to-close evidence only", "not a fill, P&L, alpha, or strategy approval"] + (["fixture source is synthesized from saved target rows; this is not real-data verification"] if mode == "fixture" else []),
    }
    result_id = object_hash({"event_id": evidence["event_id"], "checks": evidence["checks"], "mode": mode})[:24]
    evidence["result_id"] = result_id
    artifact_dir = context.workspace / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "evidence.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    description: str
    execute: Callable[[dict[str, Any], ToolContext], dict[str, Any]]


def registered_tools(*, adaptive: bool = False) -> dict[str, RegisteredTool]:
    tools = {M5_VERIFICATION_TASK: RegisteredTool(M5_VERIFICATION_TASK, "Verify one saved BTC M5 event at 1h/2h/3h with exact raw-candle targets.", verify_m5_horizons)}
    if adaptive:
        from functools import partial

        from .study_contracts import STUDY_TASKS
        from .study_tools import execute_study_tool

        for task in STUDY_TASKS:
            tools[task] = RegisteredTool(task, "Checked M5 population research over frozen data.", partial(execute_study_tool, task))
    return tools


def execute_registered_tool(name: str, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    tool = registered_tools().get(name)
    if tool is None:
        raise ToolRestrictionError(f"unregistered research tool: {name}")
    return tool.execute(params, context)
