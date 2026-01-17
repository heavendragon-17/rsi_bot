"""
RSI Trading Bot - Main Entry Point
===================================
Multi-symbol concurrent trading bot with paper/live mode support.
"""
import yaml
import sys
import os

# Add the current directory to sys.path to allow imports from app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.utils.logger import setup_logger
from app.utils.validators import validate_config
from app.repository.db_connect import init_db
from app.core.runner import MultiSymbolRunner
from app.services.execution.exchange_factory import create_exchange
from app.strategies.loader import load_strategy


def load_config():
    try:
        with open("config.yaml", "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print("Error: config.yaml not found.")
        sys.exit(1)


def main():
    logger = setup_logger()
    logger.info("Starting RSI Bot System...")
    
    # 1. Load and validate config
    config = load_config()
    try:
        validate_config(config)
    except ValueError as e:
        logger.error(f"Configuration Error: {e}")
        sys.exit(1)
    
    # 2. Initialize database
    init_db()
    logger.info("Database initialized (trades.db checked).")
    
    # 3. Load strategy class
    try:
        strategy_class = load_strategy(config)
        logger.info(f"Strategy loaded: {strategy_class.__name__}")
    except ValueError as e:
        logger.error(f"Strategy Error: {e}")
        sys.exit(1)
    
    # 4. Create and start the multi-symbol runner
    runner = MultiSymbolRunner(
        config=config,
        strategy_class=strategy_class,
        exchange_factory=create_exchange,
    )
    
    mode = config.get('bot', {}).get('mode', 'paper')
    symbols = config.get('symbols', [])
    logger.info(f"Mode: {mode.upper()}")
    logger.info(f"Symbols: {symbols}")
    logger.info(f"Exchange: {type(runner.exchange).__name__}")
    
    # 5. Start trading
    runner.start()
    
    # 6. Wait (blocks until shutdown signal)
    logger.info("Bot is running. Press Ctrl+C to stop.")
    runner.wait()
    
    logger.info("Bot shutdown complete.")


if __name__ == "__main__":
    main()
