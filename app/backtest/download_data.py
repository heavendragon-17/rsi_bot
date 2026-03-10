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

def download_data(symbol: str, timeframe: str, limit: int, output_dir: str) -> None:
    """
    Download historical OHLCV data from Binance.
    
    Binance API has a limit of 1000 candles per request.
    This function handles pagination to download more data.
    """
    print(f"Downloading {limit} candles for {symbol} ({timeframe})...")
    
    # Initialize Binance Futures
    exchange = ccxt.binanceusdm()
    
    # Binance max per request
    MAX_PER_REQUEST = 1000
    
    all_candles = []
    remaining = limit
    
    # First request - get most recent data
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=min(remaining, MAX_PER_REQUEST))
        if not ohlcv:
            print("No data received.")
            return
            
        all_candles.extend(ohlcv)
        remaining -= len(ohlcv)
        print(f"  Downloaded {len(ohlcv)} candles, total: {len(all_candles)}")
        
        # Continue fetching older data
        while remaining > 0 and ohlcv:
            time.sleep(0.5)  # Rate limiting
            
            # Get timestamp before oldest candle
            oldest_ts = ohlcv[0][0] - 1
            
            # Calculate start time (go back in time)
            batch_size = min(remaining, MAX_PER_REQUEST)
            
            # Fetch older data
            ohlcv = exchange.fetch_ohlcv(
                symbol, 
                timeframe,
                limit=batch_size,
                params={'endTime': oldest_ts}  # Use params for pagination with endTime
            )
            
            if not ohlcv:
                print("No more data available.")
                break
            
            # Filter out any candles we already have
            oldest_existing = all_candles[0][0]
            new_candles = [c for c in ohlcv if c[0] < oldest_existing]
            
            if not new_candles:
                print("Reached end of available data.")
                break
            
            all_candles = new_candles + all_candles
            remaining -= len(new_candles)
            print(f"  Downloaded {len(new_candles)} new candles, total: {len(all_candles)}")
            
    except Exception as e:
        print(f"Error downloading data: {e}")
        return

    if not all_candles:
        print("No data received.")
        return

    # Convert to DataFrame
    df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms') + pd.Timedelta(hours=7)
    
    # Sort by timestamp (oldest first)
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    # Remove duplicate timestamps (keep last value for each timestamp)
    before_dedup = len(df)
    df = df.drop_duplicates(subset='timestamp', keep='last').reset_index(drop=True)
    if before_dedup != len(df):
        print(f"Removed {before_dedup - len(df)} duplicate timestamps")
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Save to CSV
    safe_symbol = symbol.replace('/', '')
    filename = f"{safe_symbol}_{timeframe}.csv"
    filepath = os.path.join(output_dir, filename)
    
    df.to_csv(filepath, index=False)
    print(f"\nData saved to {filepath}")
    print(f"Total candles: {len(df)}")
    print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"\nPreview (first 3):\n{df.head(3)}")
    print(f"\nPreview (last 3):\n{df.tail(3)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download historical data from Binance")
    parser.add_argument("--symbol", type=str, default="BTC/USDT", help="Trading pair (e.g. BTC/USDT)")
    parser.add_argument("--timeframe", type=str, default="5m", help="Timeframe (e.g. 1m, 5m, 1h, 1d)")
    parser.add_argument("--limit", type=int, default=1000, help="Number of candles (can exceed 1000). Overridden by duration args if provided.")
    parser.add_argument("--days", type=int, default=0, help="Number of days of data to download")
    parser.add_argument("--months", type=int, default=0, help="Number of months of data to download (assumes 30 days/month)")
    parser.add_argument("--years", type=int, default=0, help="Number of years of data to download (assumes 365 days/year)")
    parser.add_argument("--output", type=str, default=os.path.join(SCRIPT_DIR, "data"), help="Output directory")
    
    args = parser.parse_args()
    
    # Calculate limit based on duration if any duration argument is provided
    if args.days > 0 or args.months > 0 or args.years > 0:
        limit = calculate_candle_limit(args.timeframe, days=args.days, months=args.months, years=args.years, default_limit=args.limit)
    else:
        limit = args.limit
        
    download_data(args.symbol, args.timeframe, limit, args.output)
