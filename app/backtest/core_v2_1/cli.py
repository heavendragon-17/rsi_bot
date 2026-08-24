"""Command-line entry point for the Core V2.1 six-symbol replay."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import structlog

from app.backtest.core_v2_1.coverage import scan_local_coverage
from app.backtest.core_v2_1.replay import (
    CoreV21PointInTimeReplay,
    build_replay_frames,
    load_available_universe,
    load_pre_download_six,
    replay_metadata,
)

logger = structlog.get_logger()
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[3] / "artifacts" / "core_v2_1" / "replay"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a deterministic Core V2.1 point-in-time replay"
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--universe-mode",
        choices=("six", "available", "full"),
        default="six",
        help="six=stepping stone (default), available=all discovered, full=require all 25",
    )
    source.add_argument(
        "--symbols",
        nargs="+",
        help="Explicit locked strategy symbols; PUMP always resolves to Hyperliquid PUMP/USDC:USDC",
    )
    parser.add_argument("--start", default=None, help="Optional timezone-aware inclusive UTC start")
    parser.add_argument("--end", default=None, help="Optional timezone-aware inclusive UTC end")
    window = parser.add_mutually_exclusive_group()
    window.add_argument(
        "--common-window",
        action="store_true",
        help="Use the intersection shared by all six alts and BTC (default)",
    )
    window.add_argument(
        "--full-available",
        action="store_true",
        help="Export every available trigger; missing contexts remain explicit NOT_READY rows",
    )
    parser.add_argument(
        "--require-pre-download-six",
        action="store_true",
        help="Fail unless the directory still contains exactly the audited 6/25 subset",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.symbols:
        replay_source = load_available_universe(args.data_dir, symbols=args.symbols)
        source_mode = "selected"
    elif args.universe_mode == "full":
        replay_source = load_available_universe(args.data_dir, require_all=True)
        source_mode = "full"
    elif args.universe_mode == "available":
        replay_source = load_available_universe(args.data_dir)
        source_mode = "available"
    else:
        replay_source = load_pre_download_six(
            args.data_dir,
            assert_exact_six=args.require_pre_download_six,
        )
        source_mode = "six"
    frames = build_replay_frames(replay_source)
    window_mode = "full_available" if args.full_available else "common_window"
    default_start = None if args.full_available else replay_source.common_start
    default_end = None if args.full_available else replay_source.common_end
    start = args.start or default_start
    end = args.end or default_end
    result = CoreV21PointInTimeReplay(frames).run(start=start, end=end)
    validated_coverage = scan_local_coverage(args.data_dir, validate=True)
    metadata = replay_metadata(
        result=result,
        coverage=validated_coverage,
        source=replay_source,
        window_mode=f"{source_mode}:{window_mode}",
        requested_start=start,
        requested_end=end,
    )
    paths = result.ledger.export(args.output_dir, metadata=metadata)
    logger.info(
        "core_v2_1_point_in_time_replay_complete",
        source_mode=source_mode,
        processed_events=result.processed_events,
        evaluated_events=result.evaluated_events,
        skipped_events=result.not_ready_events,
        emitted_events=result.emitted_events,
        jsonl=str(paths.jsonl.resolve()),
        csv=str(paths.csv.resolve()),
        metadata=str(paths.metadata.resolve()),
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI wrapper
    raise SystemExit(main())
