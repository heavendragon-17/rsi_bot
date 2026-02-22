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
import yaml
from dotenv import load_dotenv

# Add the current directory to sys.path to allow imports from app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.utils.logger import setup_logger
from app.services.notification.telegram_bot import TelegramBot
from app.strategies.rsi_no_retest import RsiNoRetestStrategy
from app.services.execution.exchange_factory import create_exchange
from app.core.runner import MultiSymbolRunner

# Load Env
load_dotenv()

# Logger
logger = setup_logger()


def load_config():
    try:
        with open("config.yaml", "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("config.yaml not found.")
        sys.exit(1)


def main():
    # 1. Load Config
    config = load_config()
    bot_mode = config.get("bot", {}).get("mode", "paper")
    logger.info(f"Starting RSI Bot in {bot_mode.upper()} mode")

    # 2. Initialize Telegram
    telegram = None
    try:
        telegram = TelegramBot()
        telegram.send_message(f"🤖 RSI Bot Started\nMode: {bot_mode.upper()}")
        logger.info("Telegram bot initialized")
    except Exception as e:
        logger.error(f"Telegram init failed: {e}")
        sys.exit(1)

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
        logger.info("Bot stopped by user.")
    finally:
        runner.stop()
        if telegram:
            telegram.send_message("🛑 RSI Bot Stopped")


if __name__ == "__main__":
    main()
