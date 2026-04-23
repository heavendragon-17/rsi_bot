"""
RSI Trading Bot - Main Entry Point
====================================
Branches on ``bot.mode``:

* ``"signal"`` → ``SignalRunner`` (multi-strategy signal-only runtime).
* any other mode → ``MultiSymbolRunner`` (live-trading path, unchanged).

Usage:
    python main.py
"""

import os
import sys

import yaml
from dotenv import load_dotenv

# Add the current directory to sys.path to allow imports from app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load Env first (needed by exchange factory and TelegramNotifier)
load_dotenv()

from app.core.config import AppConfig  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402

# Setup logging immediately (before any other imports that use loggers)
setup_logging(level="INFO")

import structlog  # noqa: E402

from app.notification.notification_service import NotificationService  # noqa: E402
from app.notification.null_notifier import NullNotifier  # noqa: E402

logger = structlog.get_logger()


def _load_raw_yaml(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _build_notifier(bot_mode: str, *, require_telegram: bool) -> NotificationService:
    """Build the NotificationService. Signal mode requires a real Telegram
    token — messages are the bot's only output. Live mode falls back to
    NullNotifier if Telegram init fails."""
    try:
        from app.notification.telegram_notifier import TelegramNotifier

        ns = NotificationService(TelegramNotifier(mode=bot_mode), mode=bot_mode)
        logger.info("telegram_initialized")
        return ns
    except Exception as e:
        if require_telegram:
            logger.error("telegram_required_but_init_failed", error=str(e))
            sys.exit(1)
        logger.warning("telegram_init_failed_using_null_notifier", error=str(e))
        return NotificationService(NullNotifier(), mode=bot_mode)


def _run_signal_mode(raw: dict, ns: NotificationService) -> None:
    """Start and run the SignalRunner lifecycle.

    Imports are lazy so unit tests that patch only the live-bot path don't
    pay the cost of loading the multiplexer / stream manager / VP store.
    """
    from app.signal.runner import SignalRunner

    try:
        runner = SignalRunner(raw, ns)
        runner.start()
    except ValueError as e:
        logger.error("signal_config_invalid", error=str(e))
        ns.stop()
        sys.exit(1)

    try:
        runner.wait()
    finally:
        runner.stop()


def _run_live_mode(
    config_path: str, bot_mode: str, ns: NotificationService
) -> None:
    """Existing live-bot path; kept separate so the signal branch doesn't
    pay the AppConfig overhead."""
    from app.trading.exchange.factory import create_exchange
    from app.trading.runner import MultiSymbolRunner
    from app.trading.status_writer import StatusWriter
    from app.trading.strategy.loader import load_strategy

    try:
        app_config = AppConfig.from_yaml(config_path)
    except (FileNotFoundError, ValueError) as e:
        logger.error("invalid_config", error=str(e))
        ns.stop()
        sys.exit(1)

    config = app_config.to_legacy_dict()
    exchange = create_exchange(config, notification_service=ns)

    runner = MultiSymbolRunner(
        config=config,
        strategy_class=load_strategy(config),
        exchange=exchange,
        notification_service=ns,
    )
    status_writer = StatusWriter(runner)

    ns.send_message(f"🤖 RSI Bot Started\nMode: {bot_mode.upper()}")
    try:
        runner.start()
        status_writer.start()
        runner.wait()
    finally:
        status_writer.stop()
        runner.stop()
        ns.send_message("🛑 RSI Bot Stopped")


def main(config_path: str = "config.yaml") -> None:
    try:
        raw = _load_raw_yaml(config_path)
    except FileNotFoundError:
        logger.error("config_file_not_found", path=config_path)
        sys.exit(1)

    bot_mode = (raw.get("bot") or {}).get("mode", "mock")
    logger.info("bot_starting", mode=bot_mode.upper())

    ns = _build_notifier(bot_mode, require_telegram=(bot_mode == "signal"))

    try:
        if bot_mode == "signal":
            _run_signal_mode(raw, ns)
        else:
            _run_live_mode(config_path, bot_mode, ns)
    except KeyboardInterrupt:
        logger.info("bot_stopped_by_user")


if __name__ == "__main__":
    main()
