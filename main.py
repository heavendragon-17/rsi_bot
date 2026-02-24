"""
RSI Trading Bot - Main Entry Point
====================================
Full execution mode with:
- WebSocket streaming for live market data
- PortfolioManager as sole execution path
- Normalized order types (market, stop_market, limit)
- Startup leverage setting + orphan position cleanup

Usage:
    python main.py
"""
import os
import sys
from dotenv import load_dotenv

# Add the current directory to sys.path to allow imports from app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load Env first (needed by exchange factory)
load_dotenv()

from app.core.config import AppConfig
from app.core.logging import setup_logging

# Setup logging immediately (before any other imports that use loggers)
setup_logging(level="INFO")

import structlog

from app.services.notification.telegram_bot import TelegramBot
from app.services.notification.null_notifier import NullNotifier
from app.strategies.rsi_no_retest import RsiNoRetestStrategy
from app.services.execution.exchange_factory import create_exchange
from app.core.runner import MultiSymbolRunner

logger = structlog.get_logger()


def main():
    # 1. Load Config (validates on construction)
    try:
        app_config = AppConfig.from_yaml("config.yaml")
    except FileNotFoundError:
        logger.error("config_file_not_found", path="config.yaml")
        sys.exit(1)
    except ValueError as e:
        logger.error("invalid_config", error=str(e))
        sys.exit(1)

    # Pass legacy dict to constructors not yet updated to AppConfig
    config = app_config.to_legacy_dict()

    bot_mode = app_config.exchange.mode
    logger.info("bot_starting", mode=bot_mode.upper())

    # 2. Initialize Telegram (optional — falls back to NullNotifier on failure)
    telegram = None
    if app_config.notification.telegram_enabled:
        try:
            telegram = TelegramBot()
            telegram.send_message(f"🤖 RSI Bot Started\nMode: {bot_mode.upper()}")
            logger.info("telegram_initialized")
        except Exception as e:
            logger.warning("telegram_init_failed_using_null_notifier", error=str(e))
            telegram = NullNotifier()
    else:
        telegram = NullNotifier()

    # 3. Create exchange via factory (returns IFuturesExchange)
    exchange = create_exchange(config)

    # 4. Create runner with execution
    runner = MultiSymbolRunner(
        config=config,
        strategy_class=RsiNoRetestStrategy,
        exchange=exchange,
        telegram=telegram,
    )

    # 5. Start and wait
    try:
        runner.start()
        runner.wait()
    except KeyboardInterrupt:
        logger.info("bot_stopped_by_user")
    finally:
        runner.stop()
        telegram.send_message("🛑 RSI Bot Stopped")


if __name__ == "__main__":
    main()
