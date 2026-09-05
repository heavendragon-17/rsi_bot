"""Resolve portable, hash-bound inputs used by preflight and the checker."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .tools import ToolContext, ToolVerificationError, _load_json, _safe_path, current_input_identity

DEFAULT_BASELINE = "research/results/phase1_four_year_runs/run_20260904T084317586748Z_97d3c169"
DEFAULT_HORIZON = "research/results/m5_four_year_horizon_runs/run_20260904T084448776441Z_97d3c169"
DEFAULT_DATA = "research/data/btc_four_year_20220828_20260828"


def file_hash(path: Path) -> str | None:
    try:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError:
        return None


def resolve_inputs(config: Any) -> dict[str, Any]:
    root = Path(config.repo_root).resolve()

    def resolve(value: str | None, default: str) -> Path:
        path = Path(value or default).expanduser()
        return (root / path).resolve() if not path.is_absolute() else path.resolve()

    data = resolve(config.data_dir, DEFAULT_DATA)
    baseline = resolve(config.baseline_packet, DEFAULT_BASELINE)
    horizon = resolve(config.horizon_packet, DEFAULT_HORIZON)
    try:
        manifest = json.loads((horizon / "manifest.json").read_text(encoding="utf-8"))
        files = manifest["inputs"]["files"]
    except (OSError, ValueError, KeyError, TypeError):
        files = {}
    hashes: dict[str, Any] = {
        "baseline_manifest_sha256": file_hash(baseline / "manifest.json"),
        "horizon_manifest_sha256": file_hash(horizon / "manifest.json"),
        "horizon_signals_sha256": file_hash(horizon / "signals.csv"),
        "horizon_baseline_sha256": file_hash(horizon / "baseline.csv"),
    }
    for timeframe, key in (("5m", "source"), ("1h", "h1_source")):
        entry = files.get(timeframe, {}) if isinstance(files, dict) else {}
        original = entry.get("path") if isinstance(entry, dict) else None
        candidate = data / f"BTCUSDT_{timeframe}.csv"
        # Existing callers with no explicit data directory can keep a valid
        # in-repository source location; explicit configuration takes priority.
        if not config.data_dir and isinstance(original, str):
            parts = Path(original).parts
            for prefix in (("research", "data"), ("app", "backtest", "data")):
                for index in range(len(parts)):
                    if tuple(parts[index:index + len(prefix)]) == prefix:
                        relocated = root.joinpath(*parts[index:]).resolve()
                        if relocated.is_file() and root in relocated.parents:
                            candidate = relocated
        hashes[f"{key}_path"] = str(candidate.resolve()) if config.verification_mode == "real" or config.adaptive else str(resolve(original, DEFAULT_DATA)) if original else None
        hashes[f"{key}_original_path"] = original
        hashes[f"{key}_sha256"] = entry.get("sha256") if isinstance(entry, dict) else None
    return {"data_dir": str(data), "baseline_packet": str(baseline),
            "horizon_packet": str(horizon), "verification_mode": config.verification_mode,
            "evidence_hashes": hashes}


def tool_parameters(context: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    hashes = context["evidence_hashes"]
    return {**parameters, "mode": context["verification_mode"],
            "baseline_packet": context["baseline_packet"], "horizon_packet": context["horizon_packet"],
            "source_csv": hashes.get("source_path"), "h1_source_csv": hashes.get("h1_source_path")}


def _validate_packet_ancestry(params: dict[str, Any], root: Path) -> None:
    """Apply the one-event checker's ancestry rule without parsing saved rows."""
    results = ((root / "research/results").resolve(),)
    manifests = {
        key: _load_json(_safe_path(str(Path(params[key]) / "manifest.json"),
                                  label=key + " manifest", roots=results, base_dir=root))
        for key in ("baseline_packet", "horizon_packet")
    }
    baseline = manifests["baseline_packet"]
    parent = manifests["horizon_packet"].get("parent", {})
    if baseline and (not isinstance(parent, dict) or parent.get("run_id") != baseline.get("run_id")):
        raise ToolVerificationError("horizon packet is not descended from the requested baseline packet")


def validate_inputs(context: dict[str, Any], root: Path, workspace: Path, *, adaptive: bool = False) -> dict[str, Any]:
    """Validate frozen bytes and packet ancestry before a model can be called.

    Adaptive identity covers H1, comparator and parent signal files as well.
    This gate reads manifests and hashes files; it never parses populations or
    recomputes study arithmetic during provider dispatch.
    """
    params = tool_parameters(context, {})
    tool_context = ToolContext(root, workspace, context["evidence_hashes"])
    if adaptive:
        from .study_tools import _inputs

        _, _, identity = _inputs(params, tool_context)
    else:
        identity = current_input_identity(params, tool_context)
        _validate_packet_ancestry(params, root)
    if identity.get("mismatches"):
        raise ToolVerificationError("frozen input identity mismatch: " + ", ".join(identity["mismatches"]))
    if context["verification_mode"] == "real" and not context["evidence_hashes"].get("source_sha256"):
        raise ToolVerificationError("frozen source SHA-256 is missing")
    return identity
