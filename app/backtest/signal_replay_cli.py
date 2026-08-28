"""Command-line entry point for the historical BTC signal replay."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta
from pathlib import Path

import structlog

from app.backtest.signal_replay import (
    UTC_PLUS_7,
    SignalReplayInputError,
    _default_paths,
    run_btc_alert_replay,
)

logger = structlog.get_logger(__name__)


def _parse_cli_datetime(raw: str, field_name: str) -> datetime:
    """Parse an ISO timestamp; naive CLI values are interpreted as UTC+7."""

    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"{field_name} must be ISO format, for example 2026-08-01 or "
            "2026-08-01T12:30:00"
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC_PLUS_7)
    return parsed


def _parse_cli_date(raw: str, field_name: str) -> datetime:
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"{field_name} must be YYYY-MM-DD or an ISO timestamp"
        ) from exc
    return datetime.combine(parsed, time.min, tzinfo=UTC_PLUS_7)


def _parse_cli_boundary(raw: str, field_name: str, *, is_start: bool) -> datetime:
    """Parse a date or timestamp and make an end date inclusive."""

    if len(raw) == 10:
        parsed = _parse_cli_date(raw, field_name)
        if not is_start:
            parsed += timedelta(days=1) - timedelta(microseconds=1)
        return parsed
    return _parse_cli_datetime(raw, field_name)


def _build_parser() -> argparse.ArgumentParser:
    default_m5, default_m15, default_h1, default_h4 = _default_paths()
    parser = argparse.ArgumentParser(
        description="Replay historical BTC RSI alert signals into a Markdown chart-review log"
    )
    parser.add_argument(
        "--m5",
        type=Path,
        default=default_m5,
        help=f"M5 OHLCV CSV (default: {default_m5})",
    )
    parser.add_argument(
        "--m15",
        type=Path,
        default=default_m15,
        help=f"M15 OHLCV CSV (default: {default_m15})",
    )
    parser.add_argument(
        "--h1",
        type=Path,
        default=default_h1,
        help=f"H1 OHLCV CSV (default: {default_h1})",
    )
    parser.add_argument(
        "--h4",
        type=Path,
        default=default_h4,
        help=f"H4 OHLCV CSV (default: {default_h4})",
    )
    parser.add_argument(
        "--start",
        type=lambda raw: _parse_cli_boundary(raw, "--start", is_start=True),
        help="Inclusive trigger close start as YYYY-MM-DD or ISO timestamp in UTC+7",
    )
    parser.add_argument(
        "--end",
        type=lambda raw: _parse_cli_boundary(raw, "--end", is_start=False),
        help="Inclusive trigger close end as YYYY-MM-DD or ISO timestamp in UTC+7",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Combined Markdown output path; omit for separate default M5/M15 files",
    )
    parser.add_argument(
        "--output-m5",
        type=Path,
        default=None,
        help="M5-only Markdown output path (must be used with --output-m15)",
    )
    parser.add_argument(
        "--output-m15",
        type=Path,
        default=None,
        help="M15-only Markdown output path (must be used with --output-m5)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.output is not None and (
        args.output_m5 is not None or args.output_m15 is not None
    ):
        parser.error("--output cannot be combined with --output-m5/--output-m15")
    if (args.output_m5 is None) != (args.output_m15 is None):
        parser.error("--output-m5 and --output-m15 must be used together")
    try:
        result = run_btc_alert_replay(
            args.m5,
            args.m15,
            args.h4,
            h1_path=args.h1,
            start_utc7=args.start,
            end_utc7=args.end,
            output_path=args.output,
            output_m5_path=args.output_m5,
            output_m15_path=args.output_m15,
        )
    except (FileNotFoundError, SignalReplayInputError, TypeError, ValueError) as exc:
        logger.error("btc_signal_replay_failed", error=str(exc))
        return 2

    for path in result.output_paths:
        logger.info(
            "btc_signal_replay_log_written",
            path=str(path),
            signal_count=len(result.signals),
        )
    return 0
