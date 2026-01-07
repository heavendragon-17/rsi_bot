import ccxt
import pandas as pd
import os
import argparse
from datetime import datetime, timedelta

def download_data(symbol, timeframe, days):
    print(f"Downloading {days} days of {timeframe} data for {symbol}...")

    # Initialize Exchange
    exchange = ccxt.binance()

    # Calculate start time
    since = exchange.parse8601((datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S'))

    all_candles = []

    while True:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not ohlcv:
                break

            all_candles.extend(ohlcv)
            print(f"Fetched {len(ohlcv)} candles. Last: {datetime.fromtimestamp(ohlcv[-1][0]/1000)}")

            since = ohlcv[-1][0] + 1

            # Break if we reached current time (roughly)
            if since > datetime.utcnow().timestamp() * 1000:
                break

        except Exception as e:
            print(f"Error: {e}")
            break

    # Convert to DataFrame
    df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

    # Save
    safe_symbol = symbol.replace('/', '')
    filename = f"data/{safe_symbol}_{timeframe}.csv"
    df.to_csv(filename, index=False)
    print(f"Saved {len(df)} rows to {filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", type=str, default="BTC/USDT")
    parser.add_argument("--timeframe", type=str, default="5m")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    download_data(args.symbol, args.timeframe, args.days)
