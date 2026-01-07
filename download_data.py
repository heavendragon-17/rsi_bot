import ccxt
import pandas as pd
import argparse
import os
from datetime import datetime

def download_data(symbol, timeframe, limit, output_dir):
    print(f"Downloading {limit} candles for {symbol} ({timeframe})...")
    
    # Initialize Binance
    exchange = ccxt.binance()
    
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    except Exception as e:
        print(f"Error downloading data: {e}")
        return

    if not ohlcv:
        print("No data received.")
        return

    # Convert to DataFrame
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Save to CSV
    safe_symbol = symbol.replace('/', '')
    filename = f"{safe_symbol}_{timeframe}.csv"
    filepath = os.path.join(output_dir, filename)
    
    df.to_csv(filepath, index=False)
    print(f"Data saved to {filepath}")
    print(f"Preview:\n{df.head()}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download historical data from Binance")
    parser.add_argument("--symbol", type=str, default="BTC/USDT", help="Trading pair symbol (e.g. BTC/USDT)")
    parser.add_argument("--timeframe", type=str, default="5m", help="Timeframe (e.g. 1m, 5m, 1h, 1d)")
    parser.add_argument("--limit", type=int, default=1000, help="Number of candles to download")
    parser.add_argument("--output", type=str, default="data", help="Output directory")
    
    args = parser.parse_args()
    
    download_data(args.symbol, args.timeframe, args.limit, args.output)
