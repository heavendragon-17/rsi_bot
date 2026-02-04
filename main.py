"""
RSI Trading Bot - Main Entry Point
===================================
Realtime integration of:
- RsiNoRetestStrategy (Strategy)
- BinanceAdapter (Exchange/Paper)
- BinanceSignalExecutor (Execution)
- TelegramBot (Notification)

Usage:
    python main.py
"""
import os
import sys
import time
import yaml
import threading
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv
from decimal import Decimal

# Add the current directory to sys.path to allow imports from app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.utils.logger import setup_logger
from app.services.execution.cex.binance_adapter import BinanceAdapter
from app.services.execution.cex.binance_signal_executor import BinanceSignalExecutor
from app.services.notification.telegram_bot import TelegramBot
from app.strategies.rsi_no_retest import RsiNoRetestStrategy
from app.core.context import StrategyContext, SCANNING

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

def run_executor_thread(executor, signal_dict, usdt_amount, symbol):
    """
    Runs the executor in a separate thread to prevent blocking the main scanning loop.
    """
    logger.info(f"[{symbol}] Starting Executor Thread...")
    try:
        executor.execute(signal_dict, usdt_amount)
    except Exception as e:
        logger.exception(f"[{symbol}] Executor Thread Error: {e}")
    finally:
        logger.info(f"[{symbol}] Executor Thread Finished.")

def main():
    logger.info("Starting RSI Bot (Realtime)...")
    
    # 1. Load Config
    config = load_config()
    
    # Force Paper Mode based on user request/config
    bot_mode = config.get("bot", {}).get("mode", "paper")
    logger.info(f"Bot Mode: {bot_mode.upper()}")
    
    # 2. Initialize Components
    
    # Telegram
    try:
        telegram = TelegramBot()
        telegram.send_message(f"RSI Bot Started [{bot_mode.upper()}]")
    except Exception as e:
        logger.warning(f"Telegram init failed: {e}")
        telegram = None

    # Adapter (Exchange)
    adapter = BinanceAdapter(config, initial_balance=1000.0)
    # Ensure mode is set correctly
    try:
        adapter.mode = bot_mode
    except Exception as e:
        logger.error(f"Failed to set adapter mode: {e}")
        sys.exit(1)

    # Executor (Trade Monitoring)
    executor = BinanceSignalExecutor(adapter)
    
    # Context (State Machine)
    context = StrategyContext()
    
    # Strategy
    # We pass the shared context to the strategy so it persists state across loops
    strategy = RsiNoRetestStrategy(config)
    strategy.context = context # Inject context
    
    # 3. Setup Symbols & Timeframe
    symbols = config.get("symbols", ["BTC/USDT"])
    timeframe = config.get("bot", {}).get("timeframe", "15m") 
    # Check if timeframe is top-level (legacy) or in bot/strategy section
    if "timeframe" in config and isinstance(config["timeframe"], str):
         timeframe = config["timeframe"]
         
    lookback_candles = 500 # Ensure enough data for strategy
    
    logger.info(f"Monitoring: {symbols} on {timeframe}")
    
    # 4. Main Realtime Loop
    try:
        while True:
            for symbol in symbols:
                try:
                    # Skip if active trade exists (Executor is handling it)
                    # Note: Strategy check is still useful to update state/logging, 
                    # but we shouldn't trigger new BUYs.
                    if context.has_active_trade(symbol):
                        # Optional: Print status or just skip
                        continue

                    # A. Fetch Data
                    # logger.info(f"[{symbol}] Fetching data...")
                    ohlcv = adapter.fetch_ohlcv(symbol, timeframe, limit=lookback_candles)
                    if not ohlcv:
                        logger.warning(f"[{symbol}] No data returned.")
                        continue
                        
                    # Convert to DataFrame
                    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                    df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
                    
                    # B. Analyze
                    signal = strategy.analyze(symbol, df)
                    
                    # C. Handle Signal
                    if signal:
                        logger.info(f"[{symbol}] SIGNAL: {signal.signal_type} | {signal.reason}")
                        
                        # Notify
                        if telegram:
                            msg = (f"<b>{signal.signal_type} {symbol}</b>\n"
                                   f"Price: {signal.price}\n"
                                   f"Reason: {signal.reason}")
                            telegram.send_message(msg)

                        # Execute (Only BUY/LONG entries are handled by executor in this logic)
                        if signal.signal_type == "BUY":
                            # Prepare Signal Dict for Executor
                            # Executor expects:
                            # {"Symbol": ..., "Side": "BUY", "SL": ..., "TP 1": ..., "Timeframe": ...}
                            
                            sig_dict = {
                                "Symbol": symbol,
                                "Side": "BUY",
                                "SL": signal.sl_price or signal.soft_sl_price, # Use hard or soft SL
                                "Timeframe": timeframe
                            }
                            
                            # Add TPs
                            if signal.tp1_price: sig_dict["TP 1"] = signal.tp1_price
                            if signal.tp2_price: sig_dict["TP 2"] = signal.tp2_price
                            if signal.tp3_price: sig_dict["TP 3"] = signal.tp3_price
                            
                            # Fallback if only single TP in logic (strategy returns tp1_price usually)
                            
                            # Determine Position Size
                            # Simple approach: Fixed USDT amount or % of balance
                            # For paper mode simplicity: use fixed 100 USDT or similar
                            invest_amount = Decimal("100") 
                            
                            # Launch Thread
                            t = threading.Thread(
                                target=run_executor_thread,
                                args=(executor, sig_dict, invest_amount, symbol),
                                daemon=True
                            )
                            t.start()
                            
                except Exception as e:
                    logger.error(f"[{symbol}] Loop Error: {e}")
                    # time.sleep(1) # prevent rapid error loops
            
            # Match the loop to the timeframe boundary (Sync Mode)
            # e.g. if timeframe=15m, wait until next 15m mark + small buffer
            sleep_duration = get_seconds_to_next_candle(timeframe)
            logger.info(f"Sleeping {sleep_duration:.1f}s until next candle close...")
            time.sleep(sleep_duration)

    except KeyboardInterrupt:
        logger.info("Updates stopped by user.")
        if telegram:
             telegram.send_message("Bot Stopped")

def get_seconds_to_next_candle(timeframe_str: str, buffer_seconds: int = 5) -> float:
    """
    Calculates seconds until the next timeframe alignment (e.g. 00, 15, 30, 45 for 15m).
    """
    now = datetime.now(timezone.utc)
    
    # 1. Parse timeframe to minutes/seconds
    # Simple parser for common Binance timeframes
    # 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d
    tf_val = int(timeframe_str[:-1])
    tf_unit = timeframe_str[-1].lower()
    
    seconds_per_unit = {
        'm': 60,
        'h': 3600,
        'd': 86400,
        'w': 604800
    }
    
    if tf_unit not in seconds_per_unit:
        # Fallback to default 10s if unknown
        return 10.0
        
    interval_seconds = tf_val * seconds_per_unit[tf_unit]
    
    # 2. Calculate removal
    timestamp = now.timestamp()
    remainder = timestamp % interval_seconds
    wait_time = interval_seconds - remainder
    
    # 3. Add buffer (to ensure exchange has processed the candle close)
    total_wait = wait_time + buffer_seconds
    
    return total_wait

if __name__ == "__main__":
    main()
