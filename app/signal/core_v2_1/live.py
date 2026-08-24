"""Command-line entrypoint for the Core V2.1 signal-only live runtime."""

from __future__ import annotations

import argparse
import os
import signal
import threading
from collections.abc import Sequence
from pathlib import Path

import structlog
from dotenv import load_dotenv

from app.signal.core_v2_1.hyperliquid_export import DEFAULT_DATA_DIR
from app.signal.core_v2_1.live_runtime import CoreV21LiveSignalRuntime
from app.trading.strategy.core_v2_1 import TRADE_CANDIDATES

logger = structlog.get_logger(__name__)
DEFAULT_STATE_DATABASE = Path("data/core_v2_1_signal.sqlite3")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Core V2.1 advisories (public data + Telegram; no orders)"
    )
    parser.add_argument("--state-db", type=Path, default=DEFAULT_STATE_DATABASE)
    parser.add_argument(
        "--chat-id",
        default=None,
        help="Telegram chat/supergroup id; defaults to TELEGRAM_CHAT_ID",
    )
    parser.add_argument(
        "--topic-id",
        type=int,
        default=None,
        help="Optional Telegram forum topic shared by all Core V2.1 symbols",
    )
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Canonical replay CSV directory used to seed PUMP on first start",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    # Match the primary bot entrypoint: Telegram credentials and chat routing
    # may live in the repository's .env file.
    load_dotenv()
    parser = _build_parser()
    args = parser.parse_args(argv)
    chat_id = args.chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        parser.error("--chat-id or TELEGRAM_CHAT_ID is required")
    topics = {symbol: args.topic_id for symbol in TRADE_CANDIDATES}
    runtime = CoreV21LiveSignalRuntime.with_public_venues_and_telegram(
        state_database=args.state_db,
        telegram_chat_id=chat_id,
        topic_by_symbol=topics,
        poll_interval_seconds=args.poll_seconds,
        bootstrap_data_dir=args.data_dir,
    )
    stop_requested = threading.Event()

    def request_stop(signum, frame) -> None:
        logger.info("core_v2_signal_stop_requested", signal=signum)
        stop_requested.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        result = runtime.start()
        logger.info(
            "core_v2_signal_runtime_started",
            hydrated_candles=result.hydrated_candles,
            strategy_symbols=len(TRADE_CANDIDATES),
        )
        while not stop_requested.wait(1.0):
            continue
    finally:
        runtime.stop()
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI boundary
    raise SystemExit(main())
