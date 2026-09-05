"""Repository-root CLI for the BTC research Phase 1 baseline."""

from __future__ import annotations

import argparse
from pathlib import Path

import structlog

from app.backtest.btc_research_phase1 import parse_cli_boundary, run_phase1_baseline

logger = structlog.get_logger(__name__)


def _parse_boundary(raw: str, *, is_end: bool):
    try:
        return parse_cli_boundary(raw, is_end=is_end)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"boundary must be YYYY-MM-DD or an ISO timestamp: {raw!r}"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write a reproducible offline BTC research Phase 1 evidence packet"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Directory containing BTCUSDT_5m/15m/1h/4h.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Parent directory for the timestamped evidence packet",
    )
    parser.add_argument(
        "--start",
        type=lambda value: _parse_boundary(value, is_end=False),
        help="Inclusive trigger close, YYYY-MM-DD or ISO timestamp",
    )
    parser.add_argument(
        "--end",
        type=lambda value: _parse_boundary(value, is_end=True),
        help="Inclusive trigger close, YYYY-MM-DD or ISO timestamp",
    )
    args = parser.parse_args(argv)
    try:
        packet = run_phase1_baseline(args.data_dir, args.output_dir, start=args.start, end=args.end)
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    logger.info("btc_research_phase1_complete", packet=str(packet))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
