import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def create_dummy_data(symbol="BTC/USDT", timeframe="15min", days=7):
    print(f"Generating dummy data for {symbol}...")

    # Generate time range
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)
    timestamps = pd.date_range(start=start_time, end=end_time, freq=timeframe)

    n = len(timestamps)

    # Generate random walk price data
    base_price = 50000
    returns = np.random.normal(0, 0.001, n)
    prices = base_price * np.exp(np.cumsum(returns))

    # Create OHLC data
    data = []
    for t, p in zip(timestamps, prices):
        vol = np.random.uniform(10, 100)
        # Randomize OHLC a bit around the "close" price
        o = p * (1 + np.random.uniform(-0.0005, 0.0005))
        c = p
        h = max(o, c) * (1 + np.random.uniform(0, 0.001))
        l = min(o, c) * (1 - np.random.uniform(0, 0.001))

        data.append([t, o, h, l, c, vol])

    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

    # Save
    safe_symbol = symbol.replace('/', '')
    filename = f"data/{safe_symbol}_{timeframe}.csv"
    df.to_csv(filename, index=False)
    print(f"Saved {len(df)} rows of dummy data to {filename}")

if __name__ == "__main__":
    create_dummy_data(timeframe="15min")
