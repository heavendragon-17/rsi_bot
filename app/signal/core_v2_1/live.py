"""Command-line entrypoint for the Core V2.1 signal-only live runtime."""

from __future__ import annotations

import argparse
import os
import signal
import threading
from collections.abc import Sequence
from pathlib import Path

import structlog
import yaml
from dotenv import load_dotenv

from app.signal.core_v2_1.hyperliquid_export import DEFAULT_DATA_DIR
from app.signal.core_v2_1.live_runtime import CoreV21LiveSignalRuntime
from app.trading.strategy.core_v2_1 import TRADE_CANDIDATES

logger = structlog.get_logger(__name__)
DEFAULT_STATE_DATABASE = Path("data/core_v2_1_signal.sqlite3")
DEFAULT_CONFIG_PATH = Path("config.yaml")


def _load_routing_config(path: Path) -> dict:
    """Load optional routing settings without touching credentials."""

    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return raw if isinstance(raw, dict) else {}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Core V2.1 advisories (public data + Telegram; no orders)"
    )
    parser.add_argument("--state-db", type=Path, default=DEFAULT_STATE_DATABASE)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="YAML config for optional Core V2.1 active/topic/chat settings",
    )
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
    config = _load_routing_config(args.config)
    core_config = config.get("core_v2_1")
    core_config = core_config if isinstance(core_config, dict) else {}
    configured_topic = core_config.get("telegram_topic_id")
    topic_id = args.topic_id
    if topic_id is None:
        topic_env = os.getenv("CORE_V2_1_TOPIC_ID")
        topic_id = int(topic_env) if topic_env else configured_topic
    if core_config.get("active") is False and args.topic_id is None and not os.getenv(
        "CORE_V2_1_TOPIC_ID"
    ):
        logger.info("core_v2_signal_disabled")
        return 0

    configured_chat = config.get("telegram")
    configured_chat = configured_chat if isinstance(configured_chat, dict) else {}
    chat_id = (
        args.chat_id
        or os.getenv("TELEGRAM_CHAT_ID")
        or configured_chat.get("group_id")
    )
    if not chat_id:
        parser.error("--chat-id, TELEGRAM_CHAT_ID, or telegram.group_id is required")
    if core_config.get("active") is True and topic_id is None:
        parser.error(
            "core_v2_1.telegram_topic_id, CORE_V2_1_TOPIC_ID, or --topic-id "
            "is required when Core V2.1 is active"
        )
    topics = {symbol: topic_id for symbol in TRADE_CANDIDATES}
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
