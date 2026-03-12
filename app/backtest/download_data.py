"""
Download Historical Data from Binance
======================================
Supports downloading more than 1000 candles via pagination.
"""
import ccxt
import pandas as pd
import argparse
import os
from datetime import datetime
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
import re

def calculate_candle_limit(timeframe: str, days: int = 0, months: int = 0, years: int = 0, default_limit: int = 8832) -> int:
    """
    Calculate the number of candles to download based on the given duration.
    Assumes 30 days per month and 365 days per year.
    Fallbacks to default_limit if duration is 0.
    """
    total_days = days + (months * 30) + (years * 365)
    if total_days <= 0:
        return default_limit
        
    # Parse timeframe string (e.g. "15m", "1h", "1d") to get minutes
    match = re.match(r"(\d+)([mhd])", timeframe)
    if not match:
        raise ValueError(f"Invalid timeframe format: {timeframe}")
        
    value = int(match.group(1))
    unit = match.group(2).lower()
    
    if unit == 'm':
        tf_minutes = value
    elif unit == 'h':
        tf_minutes = value * 60
    elif unit == 'd':
        tf_minutes = value * 60 * 24
    else:
        raise ValueError(f"Unsupported timeframe unit: {unit}")
        
    total_minutes = total_days * 24 * 60
    return total_minutes // tf_minutes

def download_data(symbol: str, timeframe: str, limit: int, output_dir: str, exchange=None) -> None:
    """
    Download historical OHLCV data from Binance incrementally.

    Args:
        exchange: Optional pre-loaded ccxt.binanceusdm instance. If None, a new one is
                  created and markets are loaded here. Pass a shared instance when calling
                  in a loop to avoid redundant load_markets() calls per symbol.
    """
    print(f"Downloading data for {symbol} ({timeframe})...")
    
    os.makedirs(output_dir, exist_ok=True)
    safe_symbol = symbol.replace('/', '')
    filepath = os.path.join(output_dir, f"{safe_symbol}_{timeframe}.csv")
    
    if exchange is None:
        exchange = ccxt.binanceusdm()
        exchange.load_markets()  # Sync full symbol list so all valid tickers are recognized
    MAX_PER_REQUEST = 1000
    
    # CCXT binanceusdm requires futures symbol format: "PYTH/USDT:USDT" not "PYTH/USDT"
    # Auto-convert spot-style symbols from symbols.txt / config.yaml
    fetch_symbol = symbol
    if hasattr(exchange, 'id') and exchange.id == 'binanceusdm':
        if ':' not in symbol and '/USDT' in symbol:
            fetch_symbol = symbol + ':USDT'
    
    all_new_candles = []
    
    existing_df = None
    since_ts = None
    
    # 1. Check if we already have data
    if os.path.exists(filepath):
        try:
            existing_df = pd.read_csv(filepath)
            
            if len(existing_df) < int(limit * 0.95):
                print(f"  Existing file has only {len(existing_df)} candles (needs ~{limit}). Discarding and fetching fresh.")
                existing_df = None
            else:
                existing_df['timestamp'] = pd.to_datetime(existing_df['timestamp'])
                existing_df = existing_df.sort_values('timestamp').reset_index(drop=True)
                last_ts = existing_df['timestamp'].iloc[-1]
                print(f"  Found existing file with {len(existing_df)} candles. Last timestamp: {last_ts}")
                # Convert UTC+7 back to UTC ms
                since_ts = int((last_ts - pd.Timedelta(hours=7)).timestamp() * 1000)
        except Exception as e:
            print(f"  Error reading existing file: {e}")
            existing_df = None

    # 2. Fetch missing data
    if since_ts is not None:
        # INCREMENTAL FORWARD FETCH
        print("  Fetching new candles forward...")
        try:
            current_since = since_ts
            while True:
                time.sleep(0.5)
                ohlcv = exchange.fetch_ohlcv(fetch_symbol, timeframe, since=current_since, limit=MAX_PER_REQUEST)
                if not ohlcv:
                    break
                
                # Exclude the exact 'since' candle if it overlaps (it usually does)
                new_candles = [c for c in ohlcv if c[0] > current_since]
                if not new_candles:
                    break
                
                all_new_candles.extend(new_candles)
                current_since = new_candles[-1][0]
                print(f"  Downloaded {len(new_candles)} new candles...")
                
                # If we received less than MAX_PER_REQUEST, we're likely up to date
                if ohlcv and len(ohlcv) < MAX_PER_REQUEST:
                    break
        except Exception as e:
            print(f"Error fetching incremental data: {e}")
            
    else:
        # FULL BACKWARD FETCH (original behavior for new files)
        print(f"  No existing file. Fetching {limit} candles backwards...")
        remaining = limit
        try:
            ohlcv = exchange.fetch_ohlcv(fetch_symbol, timeframe, limit=min(remaining, MAX_PER_REQUEST))
            if ohlcv:
                all_new_candles.extend(ohlcv)
                remaining -= len(ohlcv)
                
                while remaining > 0:
                    time.sleep(0.5)
                    oldest_ts = ohlcv[0][0] - 1
                    batch_size = min(remaining, MAX_PER_REQUEST)
                    ohlcv = exchange.fetch_ohlcv(fetch_symbol, timeframe, limit=batch_size, params={'endTime': oldest_ts})
                    
                    if not ohlcv:
                        print("  No more historical data available.")
                        break
                        
                    oldest_existing = all_new_candles[0][0]
                    new_candles = [c for c in ohlcv if c[0] < oldest_existing]
                    
                    if not new_candles:
                        break
                        
                    all_new_candles = new_candles + all_new_candles
                    remaining -= len(new_candles)
                    print(f"  Downloaded {len(new_candles)} candles, total: {len(all_new_candles)}")
        except Exception as e:
            print(f"Error fetching historical data: {e}")

    # 3. Combine and save
    if not all_new_candles and existing_df is None:
        print("No data received and no existing file.")
        return
        
    df_new = pd.DataFrame(all_new_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    if not df_new.empty:
        # localized to UTC+7 for the bot's standard usage
        df_new['timestamp'] = pd.to_datetime(df_new['timestamp'], unit='ms') + pd.Timedelta(hours=7)
        
        if existing_df is not None:
            df = pd.concat([existing_df, df_new], ignore_index=True)
        else:
            df = df_new
    else:
        df = existing_df
        print("  No new data was downloaded, using existing file.")

    if df is None or df.empty:
        print("No final data.")
        return
        
    # Sort and remove duplicates
    df = df.sort_values('timestamp').reset_index(drop=True)
    before_dedup = len(df)
    df = df.drop_duplicates(subset='timestamp', keep='last').reset_index(drop=True)
    if before_dedup != len(df):
        print(f"  Removed {before_dedup - len(df)} duplicate timestamps")
    
    # Save output
    df.to_csv(filepath, index=False)
    print(f"\nData ready at {filepath}")
    print(f"Total candles: {len(df)}")
    print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download historical data from Binance")
    parser.add_argument("--symbol", type=str, default="BTC/USDT", help="Trading pair (e.g. BTC/USDT)")
    parser.add_argument("--timeframe", type=str, default="5m", help="Timeframe (e.g. 1m, 5m, 1h, 1d)")
    parser.add_argument("--limit", type=int, default=1000, help="Number of candles (can exceed 1000).")
    parser.add_argument("--days", type=int, default=0, help="Duration config override")
    parser.add_argument("--months", type=int, default=0, help="Duration config override")
    parser.add_argument("--years", type=int, default=0, help="Duration config override")
    parser.add_argument("--output", type=str, default=os.path.join(SCRIPT_DIR, "data"), help="Output directory")
    
    args = parser.parse_args()
    
    if args.days > 0 or args.months > 0 or args.years > 0:
        limit = calculate_candle_limit(args.timeframe, days=args.days, months=args.months, years=args.years, default_limit=args.limit)
    else:
        limit = args.limit
        
    download_data(args.symbol, args.timeframe, limit, args.output)
