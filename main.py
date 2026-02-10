"""
RSI Trading Bot - Main Entry Point (Signal-Only Mode)
======================================================
Telegram signal notifications with:
- WebSocket streaming for live market data
- Portfolio-based position sizing
- NO trade execution (commented out)

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
from app.services.notification.telegram_bot import TelegramBot
from app.strategies.rsi_no_retest import RsiNoRetestStrategy
from app.core.context import StrategyContext, SCANNING

# WebSocket streaming components
from app.services.market_data.store import MarketDataStore
from app.services.market_data.stream_manager import BinanceStreamManager

# Portfolio for position sizing (used for signal info, not execution)
from app.core.portfolio import PortfolioManager

# --- COMMENTED OUT: Binance execution components ---
# from app.services.execution.cex.binance_adapter import BinanceAdapter
# from app.services.execution.cex.binance_signal_executor import BinanceSignalExecutor

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

def normalize_symbol(symbol: str) -> str:
    """
    Normalize symbol to base asset for store lookup.
    E.g., 'BTC/USDT' -> 'BTC', 'BTCUSDT' -> 'BTC'
    """
    s = symbol.upper().replace('/', '')
    for quote in ['USDT', 'USDC', 'BUSD', 'USD']:
        if s.endswith(quote):
            return s[:-len(quote)]
    return s

def parse_timeframe_to_seconds(tf: str) -> int:
    """Helper to convert timeframe string to seconds."""
    if tf.endswith('m'):
        return int(tf[:-1]) * 60
    elif tf.endswith('h'):
        return int(tf[:-1]) * 3600
    elif tf.endswith('d'):
        return int(tf[:-1]) * 86400
    elif tf.endswith('w'):
        return int(tf[:-1]) * 604800
    return 60  # Default 1m

def format_signal_message(signal, symbol: str, timeframe: str, config: dict) -> str:
    """
    Format a detailed Telegram message for a trading signal.
    """
    # Calculate position size info (for display only)
    risk_cfg = config.get("risk", {})
    leverage = risk_cfg.get("leverage", 10)
    risk_pct = risk_cfg.get("risk_per_trade_pct", 0.02)
    initial_capital = config.get("backtest", {}).get("initial_balance", 10000)
    
    # Calculate SL distance
    sl_price = signal.soft_sl_price or signal.sl_price
    sl_distance_pct = 0
    if sl_price and signal.price:
        sl_distance_pct = abs(float(signal.price) - float(sl_price)) / float(signal.price) * 100
    
    # Get current time for scan timestamp (UTC+7)
    scan_time = datetime.now(timezone.utc) + pd.Timedelta(hours=7)
    scan_time_str = scan_time.strftime('%Y-%m-%d %H:%M:%S')

    # Convert signal timestamp (candle open) to UTC+7
    candle_ts = signal.timestamp
    if isinstance(candle_ts, (int, float)):
        candle_ts = datetime.fromtimestamp(candle_ts, tz=timezone.utc)
    
    # Check if candle_ts is naive, if so assume UTC (since normalizer is now UTC)
    if candle_ts.tzinfo is None:
        candle_ts = candle_ts.replace(tzinfo=timezone.utc)
        
    candle_ts_str = (candle_ts + pd.Timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')

    # Build message
    tp_allocations = getattr(signal, "tp_allocations", None)
    
    # Build message
    msg_lines = [
        f"🚨 <b>{signal.signal_type} SIGNAL</b>",
        f"--------------------------",
        f"<b>Scan Time:</b> {scan_time_str}",
        f"<b>Candle Time:</b> {candle_ts_str}",
        f"<b>Symbol:</b> #{symbol.replace('/', '')}",
        f"<b>Timeframe:</b> {timeframe}",
        f"<b>Entry:</b> ${signal.price:.6f}",
    ]
    
    if signal.sl_price:
        msg_lines.append(f"<b>SL:</b> ${signal.sl_price:.6f} (Disaster)")
    if signal.soft_sl_price:
        msg_lines.append(f"<b>Soft SL:</b> ${signal.soft_sl_price:.6f} ({sl_distance_pct:.2f}%)")
    
    if signal.tp1_price:
        tp_str = f"<b>TP1:</b> ${signal.tp1_price:.6f}"
        if tp_allocations and "TP1" in tp_allocations:
            tp_str += f" ({tp_allocations['TP1']*100:.0f}%)"
        msg_lines.append(tp_str)

    if signal.tp2_price:
        tp_str = f"<b>TP2:</b> ${signal.tp2_price:.6f}"
        if tp_allocations and "TP2" in tp_allocations:
             tp_str += f" ({tp_allocations['TP2']*100:.0f}%)"
        msg_lines.append(tp_str)

    if signal.tp3_price:
        tp_str = f"<b>TP3:</b> ${signal.tp3_price:.6f}"
        if tp_allocations and "TP3" in tp_allocations:
             tp_str += f" ({tp_allocations['TP3']*100:.0f}%)"
        msg_lines.append(tp_str)
    
    msg_lines.extend([
        f"",
        f"<b>Trigger:</b> {signal.reason}",
        f"",
        f"<i>Leverage: {leverage}x | Risk: {float(risk_pct)*100:.1f}%</i>",
        f"--------------------------",
    ])
    
    return "\n".join(msg_lines)

def main():
    logger.info("Starting RSI Bot (Signal-Only Mode with WebSocket)...")
    
    # 1. Load Config
    config = load_config()
    
    bot_mode = config.get("bot", {}).get("mode", "paper")
    logger.info(f"Bot Mode: {bot_mode.upper()} (SIGNAL-ONLY - No execution)")
    
    # 2. Initialize Components
    
    # Telegram
    try:
        telegram = TelegramBot()
        telegram.send_message(f"🤖 RSI Bot Started [SIGNAL-ONLY]\nMode: {bot_mode.upper()}")
        logger.info("Telegram bot initialized successfully")
    except Exception as e:
        logger.error(f"Telegram init failed: {e}")
        telegram = None
        sys.exit(1)  # Exit if Telegram fails - it's our main output
    
    # Context (State Machine)
    context = StrategyContext()
    
    # Strategy
    strategy = RsiNoRetestStrategy(config)
    strategy.context = context
    
    # 3. Setup Symbols & Timeframe
    symbols = config.get("symbols", ["BTC/USDT"])
    timeframe = config.get("timeframe", "15m")
    
    logger.info(f"Monitoring: {symbols} on {timeframe}")
    
    # 4. Initialize WebSocket Streaming
    store = MarketDataStore()
    stream = BinanceStreamManager(
        symbols=symbols,
        timeframe=timeframe,
        store=store,
        history_limit=300,
        enable_history=True
    )
    
    # Start the stream
    stream.start()
    logger.info("WebSocket stream started")
    
    # Wait for initial data
    logger.info("Waiting for initial historical data...")
    time.sleep(5)
    
    # 5. Track last processed candle per symbol
    last_processed = {normalize_symbol(s): None for s in symbols}
    
    # 6. Main Loop - Process closed candles
    tf_secs = parse_timeframe_to_seconds(timeframe)
    
    try:
        while True:
            for symbol in symbols:
                try:
                    norm_symbol = normalize_symbol(symbol)
                    
                    # Skip if active trade exists
                    if context.has_active_trade(norm_symbol):
                        continue
                    
                    # Get data from store
                    df = store.get_dataframe(norm_symbol)
                    
                    if df is None or df.empty:
                        continue
                    
                    # Only process closed candles
                    # Logic: If df.iloc[-1] is closed, use it.
                    # If df.iloc[-1] is open (new candle started), check df.iloc[-2] (previous closed).
                    
                    candidate_row = df.iloc[-1]
                    if not candidate_row.get('closed', False):
                        if len(df) >= 2:
                            candidate_row = df.iloc[-2]
                            if not candidate_row.get('closed', False):
                                continue # Both last and second-last not closed? Wait.
                        else:
                            continue # Not enough data
                    
                    current_ts = candidate_row.name # Timestamp is the index
                    
                    # Skip if already processed
                    if current_ts == last_processed[norm_symbol]:
                        continue

                    # Precise timing check: Scan at XX:XX:01
                    # Timestamp from normalizer is now UTC (removed +7h)
                    candle_open_ts = current_ts.timestamp()
                    target_scan_ts = candle_open_ts + tf_secs + 1
                    now_ts = datetime.now(timezone.utc).timestamp()
                    
                    if now_ts < target_scan_ts:
                        # Wait for next loop iteration
                        continue
                    
                    # Prepare DataFrame for strategy (needs specific columns)
                    # We need to slice UP TO the candidate row to ensure backtest/live consistency
                    # If we use df directly, it might include the open candle at the end.
                    # Best to slice: df[:candidate_index+1]
                    
                    # Find integer index of candidate_row (it's either -1 or -2)
                    # We can simply filter or slice based on timestamp, but slicing by position is faster if we know it.
                    # If candidate was -2, we exclude -1.
                    
                    if candidate_row.name == df.iloc[-1].name:
                         df_slice = df.copy()
                    else:
                         df_slice = df.iloc[:-1].copy()

                    df_for_strategy = df_slice[['open', 'high', 'low', 'close', 'volume']].copy()
                    df_for_strategy.reset_index(inplace=True)
                    df_for_strategy.rename(columns={'index': 'timestamp'}, inplace=True)
                    
                    # Analyze
                    signal = strategy.analyze(norm_symbol, df_for_strategy)
                    
                    # Handle Signal
                    if signal:
                        logger.info(f"[{symbol}] SIGNAL: {signal.signal_type} | {signal.reason}")
                        
                        # Send Telegram notification
                        if telegram:
                            msg = format_signal_message(signal, symbol, timeframe, config)
                            
                            # Add trade URL button
                            trade_url = TelegramBot.binance_futures_url(symbol)
                            telegram.send_message(
                                msg,
                                button_text="📈 Open Chart",
                                button_url=trade_url
                            )
                            logger.info(f"[{symbol}] Telegram notification sent")
                        
                        # --- COMMENTED OUT: Trade execution ---
                        # if signal.signal_type == "BUY":
                        #     sig_dict = {
                        #         "Symbol": symbol,
                        #         "Side": "BUY",
                        #         "SL": signal.sl_price or signal.soft_sl_price,
                        #         "Timeframe": timeframe
                        #     }
                        #     if signal.tp1_price: sig_dict["TP 1"] = signal.tp1_price
                        #     if signal.tp2_price: sig_dict["TP 2"] = signal.tp2_price
                        #     invest_amount = Decimal("100")
                        #     t = threading.Thread(
                        #         target=run_executor_thread,
                        #         args=(executor, sig_dict, invest_amount, symbol),
                        #         daemon=True
                        #     )
                        #     t.start()
                    
                    last_processed[norm_symbol] = current_ts
                    
                except Exception as e:
                    logger.error(f"[{symbol}] Loop Error: {e}", exc_info=True)
            
            # Small sleep to prevent CPU spinning
            time.sleep(0.5)

    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
        if telegram:
            telegram.send_message("🛑 RSI Bot Stopped")
        stream.stop()

if __name__ == "__main__":
    main()
