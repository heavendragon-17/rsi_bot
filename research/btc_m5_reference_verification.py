"""Independent offline reproduction checks; never writes into old evidence packets."""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import structlog

from app.backtest import btc_research_phase1 as phase1
from app.backtest.signal_replay import run_btc_alert_replay
from research import btc_m5_horizon_diagnostic as m5_parent
from research import btc_m15_reference_backtest as engine
from research import btc_m15_reference_reporting as reporting
from research import btc_m15_signal_diagnostic as m15

logger = structlog.get_logger()
REPEAT_FILES = ("protocol.json", "summary.json", "equity_daily.csv", "full/actions.csv",
                "full/trades.csv", "full/equity_curve.csv", "full/signals.csv")


def compare_reference_fields(reference: Any, actual: Any, path: str = "root") -> int:
    """Compare every historical field; permit only newly explicit metadata keys."""
    if isinstance(reference, dict):
        if not isinstance(actual, dict):
            raise ValueError(f"Reproduction type mismatch: {path}")
        count = 0
        for key, value in reference.items():
            if key not in actual:
                raise ValueError(f"Reproduction missing field: {path}.{key}")
            count += compare_reference_fields(value, actual[key], f"{path}.{key}")
        return count
    if isinstance(reference, list):
        if not isinstance(actual, list) or len(reference) != len(actual):
            raise ValueError(f"Reproduction length mismatch: {path}")
        return sum(compare_reference_fields(a, b, f"{path}[{i}]")
                   for i, (a, b) in enumerate(zip(reference, actual, strict=True)))
    if isinstance(reference, (float, int)) and not isinstance(reference, bool):
        matches = isinstance(actual, (float, int)) and math.isclose(reference, actual, rel_tol=1e-12, abs_tol=1e-9)
    else:
        matches = reference == actual
    if not matches:
        raise ValueError(f"Reproduction value mismatch: {path}: {reference!r} != {actual!r}")
    return 1


def verify_repeat(packet: Path, repeat: Path) -> dict[str, str]:
    """Physical byte identity, including full ledgers, not rounded headline parity."""
    hashes = {}
    for name in REPEAT_FILES:
        a, b = phase1._hash_file(packet / name), phase1._hash_file(repeat / name)
        if a != b:
            raise ValueError(f"Deterministic reproduction mismatch: {name}")
        hashes[name] = a
    return hashes


def verify_reference(baseline: Path, data_dir: Path, m15_run: Path) -> dict:
    parent, _, rows = m5_parent.load_parent(baseline)
    parent_hashes = m5_parent.parent_identity(baseline)
    old_files = {name: phase1._hash_file(m15_run / name)
                 for name in ("manifest.json", "summary.json", "protocol.json", "report.md")}
    inputs = phase1.validate_inputs(data_dir)
    for tf in phase1.TIMEFRAMES:
        if inputs.source_report["files"][tf]["sha256"] != parent["inputs"]["files"][tf]["sha256"]:
            raise ValueError(f"Source hash mismatch: {tf}")
    replay = run_btc_alert_replay(
        m5_path=inputs.paths["5m"], m15_path=inputs.paths["15m"],
        h1_path=inputs.paths["1h"], h4_path=inputs.paths["4h"],
        start_utc7=engine.WINDOW_START, end_utc7=engine.WINDOW_END, write_output=False,
    )
    unique = rows.drop_duplicates("event_id").sort_values("trigger_close_at")
    expected = [(row.event_id, row.trigger_close_at, int(row.sequence), row.decision_reason)
                for row in unique.itertuples()]
    actual = [(signal.decision.event_id, phase1._utc_iso(signal.data.trigger_close_time),
               signal.sequence, signal.decision.reason) for signal in replay.signals if signal.timeframe == "5m"]
    if expected != actual:
        raise ValueError("Full replay M5 identity/sequence/reason parity mismatch")
    # The old M15 cohort has no unresolved entries. Verify the new accounting
    # engine reproduces ALL prior account fields and full-opportunity summaries.
    _, _, m15_rows = m15.load_parent(baseline)
    scan, audit = m15.scan_population(inputs, engine.WINDOW_START, engine.WINDOW_END)
    a = engine.policy_a_signals(m15_rows)
    if not engine.reconstruct_policy_a(scan, a)["matches"]:
        raise ValueError("M15 signal reconstruction mismatch")
    signals = {engine.POLICIES[0]: a, engine.POLICIES[1]: engine.policy_b_signals(scan)}
    grid = engine.M5Grid.from_frame(inputs.frames["5m"])
    scenarios = engine.run_cost_grid(signals, grid)
    full = engine.run_full_opportunity_grid(signals, grid)
    old = json.loads((m15_run / "summary.json").read_text(encoding="utf-8"))
    checked = 0
    for scenario in old["cost_sensitivity"]:
        key = engine.scenario_key(scenario["fee_rate_per_side"], scenario["slippage_rate_per_side"])
        for policy in engine.POLICIES:
            checked += compare_reference_fields(scenario[policy], scenarios[key][policy]["summary"], f"{key}.{policy}")
    checked += compare_reference_fields(old["full_opportunity_diagnostic"], full, "full_opportunity")
    if parent_hashes != m5_parent.parent_identity(baseline):
        raise ValueError("Parent packet changed during verification")
    for name, identity in old_files.items():
        if identity != phase1._hash_file(m15_run / name):
            raise ValueError(f"Historical M15 evidence changed: {name}")
    return {
        "evidence_role": "HISTORICAL_DEVELOPMENT_EVIDENCE",
        "full_replay_parity": {"matches": True, "m5_count": len(actual),
                              "compared_fields": ["event_id", "trigger_close_at", "sequence", "decision_reason"],
                              "counts": asdict(replay.counts)},
        "source_hash_parity": True,
        "source_sha256": {tf: inputs.source_report["files"][tf]["sha256"] for tf in phase1.TIMEFRAMES},
        "parent_sha256": parent_hashes,
        "m15_v2_preserved_sha256": old_files,
        "m15_v3_reproduction": {"matches": True, "accounting_version": engine.VERSION,
                                "compared_leaf_fields": checked, "scenario_count": len(scenarios),
                                "a_signals": len(a), "b_signals": len(signals[engine.POLICIES[1]]),
                                "scan": audit},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-run", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--m15-run", required=True, type=Path)
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--repeat", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if (args.packet is None) != (args.repeat is None):
        parser.error("--packet and --repeat must be supplied together")
    result = verify_reference(args.baseline_run, args.data_dir, args.m15_run)
    if args.packet:
        result["deterministic_sha256"] = verify_repeat(args.packet, args.repeat)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation: even verification evidence is never silently overwritten.
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(reporting._json_text(result))
    logger.info("frozen_reference_verified", output=str(args.output), m5_count=result["full_replay_parity"]["m5_count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
