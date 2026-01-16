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

def download_from_exchange(exchange, symbol, timeframe, limit):
    """
    Helper to download from a specific exchange instance.
    Returns DataFrame or None.
    """
    MAX_PER_REQUEST = 1000
    if exchange.id == 'bybit':
        MAX_PER_REQUEST = 200

    all_candles = []
    remaining = limit
    
    # First request
    print(f"  [{exchange.id}] Fetching initial data...")
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=min(remaining, MAX_PER_REQUEST))
    if not ohlcv:
        print(f"  [{exchange.id}] No data received.")
        return None

    all_candles.extend(ohlcv)
    remaining -= len(ohlcv)
    print(f"  [{exchange.id}] Downloaded {len(ohlcv)} candles...")

    # Pagination
    while remaining > 0 and ohlcv:
        time.sleep(exchange.rateLimit / 1000.0 if exchange.rateLimit else 0.5)

        oldest_ts = ohlcv[0][0] - 1
        batch_size = min(remaining, MAX_PER_REQUEST)

        params = {}
        if exchange.id in ['binance', 'binanceusdm']:
            params = {'endTime': oldest_ts}
        elif exchange.id == 'kucoin':
            params = {'endAt': int(oldest_ts / 1000)}
        elif exchange.id == 'bybit':
            params = {'end': oldest_ts}
        elif exchange.id == 'kraken':
             # Kraken uses 'since' (forward). Backward is hard.
             # We will skip pagination for Kraken for now and just return what we have
             break

        ohlcv = exchange.fetch_ohlcv(
            symbol,
            timeframe,
            limit=batch_size,
            params=params
        )

        if not ohlcv:
            break
            
        # Deduplication / Sequencing check
        oldest_existing = all_candles[0][0]
        new_candles = [c for c in ohlcv if c[0] < oldest_existing]
        
        if not new_candles:
            break
            
        all_candles = new_candles + all_candles
        remaining -= len(new_candles)
        print(f"  [{exchange.id}] Downloaded {len(new_candles)} new candles...")

    df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def download_data(symbol: str, timeframe: str, limit: int, output_dir: str) -> None:
    print(f"Downloading {limit} candles for {symbol} ({timeframe})...")

    # Priority list
    exchanges_classes = [ccxt.binanceusdm, ccxt.binance, ccxt.kucoin, ccxt.bybit, ccxt.gateio, ccxt.kraken]

    df = None

    for ex_class in exchanges_classes:
        exchange = None
        try:
            exchange = ex_class()
            # Try to map symbol? CCXT handles BTC/USDT -> exchange specific
            # But specific pairs might be different.
            # Just try standard format first.
            
            df = download_from_exchange(exchange, symbol, timeframe, limit)
            if df is not None and not df.empty:
                print(f"Success with {exchange.id}")
                break
        except Exception as e:
            print(f"  [{exchange.id if exchange else ex_class.__name__}] Error: {e}")
        finally:
            if exchange and hasattr(exchange, 'close'):
                try:
                    exchange.close()
                except:
                    pass

    if df is None or df.empty:
        print(f"Failed to download data for {symbol} from any exchange.")
        return

    # Post-process
    # Sort by timestamp (oldest first)
    df = df.sort_values('timestamp').reset_index(drop=True)
    df = df.drop_duplicates(subset='timestamp', keep='last').reset_index(drop=True)
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Save to CSV
    safe_symbol = symbol.replace('/', '')
    filename = f"{safe_symbol}_{timeframe}.csv"
    filepath = os.path.join(output_dir, filename)
    
    df.to_csv(filepath, index=False)
    print(f"Data saved to {filepath}")
    print(f"Total candles: {len(df)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download historical data from Binance")
    parser.add_argument("--symbol", type=str, default="BTC/USDT", help="Trading pair (e.g. BTC/USDT)")
    parser.add_argument("--timeframe", type=str, default="5m", help="Timeframe (e.g. 1m, 5m, 1h, 1d)")
    parser.add_argument("--limit", type=int, default=1000, help="Number of candles (can exceed 1000)")
    parser.add_argument("--output", type=str, default=os.path.join(SCRIPT_DIR, "data"), help="Output directory")
    
    args = parser.parse_args()
    
    download_data(args.symbol, args.timeframe, args.limit, args.output)
