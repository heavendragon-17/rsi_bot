"""Stable direct-argv CLI for the frozen M5 scientific checker.

Reads three CSVs, writes one JSON report. Exit 0 when the pair passes,
2 when timing/data/schema/horizon/numerical/population violations exist,
1 on usage errors. No dataset, holdout, trading configuration or strategy
is opened or changed by this wrapper; paths are supplied by the caller.

With ``--declaration`` (plus optional ``--summary``/``--result``), the
diagnostic-specific acceptance layer additionally reconstructs the declared
eligible population from the raw candles and requires exact group
agreement plus metric/verdict binding; the output file then holds the
acceptance report (which embeds the row-level checker outcome).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from research.m5_checks.acceptance import Declaration, accept
from research.m5_checks.checker import run_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="m5-scientific-check",
        description="Independently verify one M5 candidate/baseline pair.")
    parser.add_argument("--candles", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--horizon-minutes", required=True, type=int)
    parser.add_argument("--output", required=True)
    parser.add_argument("--declaration", default=None,
                        help="frozen population declaration JSON (enables acceptance)")
    parser.add_argument("--summary", default=None,
                        help="diagnostic summary.json to bind (requires --declaration)")
    parser.add_argument("--result", default=None,
                        help="diagnostic result.json to bind (requires --declaration)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if (args.summary is not None or args.result is not None) and args.declaration is None:
        print("m5-scientific-check usage/schema error: --summary/--result require --declaration",
              file=sys.stderr)
        return 1
    if args.declaration is None:
        try:
            result = run_files(
                candles_path=Path(args.candles), candidate_path=Path(args.candidate),
                baseline_path=Path(args.baseline),
                horizon_minutes=int(args.horizon_minutes))
        except (ValueError, OSError) as exc:
            print(f"m5-scientific-check usage/schema error: {exc}", file=sys.stderr)
            return 1
        Path(args.output).write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"passed": result["passed"],
                          "verdict": result["scientific"]["verdict"],
                          "violations": {k: len(v) for k, v in result["violations"].items()}},
                         indent=2, sort_keys=True))
        return 0 if result["passed"] else 2
    try:
        raw = json.loads(Path(args.declaration).read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict):
            raise ValueError("declaration JSON must be an object")
        raw_horizon = raw.get("horizon_minutes", args.horizon_minutes)
        # The declared horizon is evidence: it is validated as a non-boolean
        # integer in its own right and never coerced (a fractional 60.9 is a
        # malformed declaration, not a 60-minute one).
        if isinstance(raw_horizon, bool) or not isinstance(raw_horizon, int):
            raise ValueError(
                f"declaration horizon_minutes must be an integer, got {raw_horizon!r}")
        declaration = Declaration(
            candles_sha256=raw["candles_sha256"],
            window_start_close_utc=raw["window_start_close_utc"],
            window_end_close_utc=raw["window_end_close_utc"],
            horizon_minutes=raw_horizon,
            target_hours_utc=tuple(raw["target_hours_utc"]),
            rejection_rule=raw.get("rejection_rule", "reject_if_nonpositive"))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"m5-scientific-check usage/schema error: bad declaration: {exc}", file=sys.stderr)
        return 1
    if declaration.horizon_minutes != args.horizon_minutes:
        print("m5-scientific-check usage/schema error: declaration horizon disagrees with "
              "--horizon-minutes", file=sys.stderr)
        return 1
    report = accept(
        candles_path=Path(args.candles), candidate_path=Path(args.candidate),
        baseline_path=Path(args.baseline),
        summary_path=Path(args.summary) if args.summary else None,
        result_path=Path(args.result) if args.result else None,
        declaration=declaration)
    Path(args.output).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"accepted": report["accepted"], "reasons": report["reasons"]},
                     indent=2, sort_keys=True))
    return 0 if report["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
