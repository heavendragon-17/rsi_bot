import yaml
import time
import sys
import os

# Add the current directory to sys.path to allow imports from app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.utils.logger import setup_logger
from app.utils.validators import validate_config
from app.repository.db_connect import init_db
from app.services.market_data.store import MarketDataStore
from app.services.market_data.stream_manager import BinanceStreamManager
from app.services.execution.factory import ExchangeFactory
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
    
    # 1. Config
    config = load_config()
    try:
        validate_config(config)
    except ValueError as e:
        logger.error(f"Configuration Error: {e}")
        sys.exit(1)
    
    # 2. Database
    init_db()
    logger.info("Database initialized (trades.db checked).")
    
    # 3. Components
    store = MarketDataStore()
    stream = BinanceStreamManager(
        symbols=config['symbols'], 
        timeframe=config['timeframe'], 
        store=store
    )
    
    # Initialize Exchange (API Keys assumed in .env)
    try:
        exchange = ExchangeFactory.create_exchange(config)
        logger.info(f"Initialized exchange: {config['exchange']['name']}")
    except Exception as e:
        logger.warning(f"Exchange initialization failed (Check API Keys): {e}")

    # Initialize Strategy
    strategy = load_strategy(config)
    logger.info("Strategy loaded.")
    
    # 4. Start Stream
    stream.start()
    logger.info(f"Market stream started for {config['symbols']}")
    
    # 5. Main Loop
    try:
        while True:
            time.sleep(10)
            logger.info("Bot heartbeat: alive...")
            # Here we would orchestrate the flow:
            # 1. Get latest data from store
            # 2. Check strategy signals
            # 3. Execute orders
            
    except KeyboardInterrupt:
        logger.info("Shutting down...")

if __name__ == "__main__":
    main()
