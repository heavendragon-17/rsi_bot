#!/usr/bin/env python
"""Generate a synthetic BTC/USDT 15m dataset with ~2000 candles for regression testing.

Creates realistic price action with trending + mean-reverting regimes to trigger
both RSI Momentum (SHORT) and RSI No-Retest (LONG) strategies.
"""
import os

import numpy as np
import pandas as pd

np.random.seed(42)  # Reproducible

N = 2000
start_price = 50000.0
timestamps = pd.date_range("2024-01-01", periods=N, freq="15min")

# Generate price series with regime changes
prices = [start_price]
for i in range(1, N):
    # Create trending regimes
    phase = (i // 200) % 5
    if phase == 0:
        drift = 0.0002   # Uptrend
    elif phase == 1:
        drift = -0.0003  # Downtrend (triggers SHORT divergence)
    elif phase == 2:
        drift = 0.0001   # Mild uptrend (triggers LONG reclaim)
    elif phase == 3:
        drift = -0.0002  # Downtrend
    else:
        drift = 0.00005  # Sideways

    vol = 0.002
    ret = drift + vol * np.random.randn()
    prices.append(prices[-1] * (1 + ret))

closes = np.array(prices)
# Generate OHLC from closes
highs = closes * (1 + np.abs(np.random.randn(N)) * 0.001)
lows = closes * (1 - np.abs(np.random.randn(N)) * 0.001)
opens = np.roll(closes, 1)
opens[0] = start_price
volumes = np.random.uniform(100, 500, N)

df = pd.DataFrame({
    "timestamp": timestamps,
    "open": np.round(opens, 1),
    "high": np.round(highs, 1),
    "low": np.round(lows, 1),
    "close": np.round(closes, 1),
    "volume": np.round(volumes, 1),
})

out_path = os.path.join(os.path.dirname(__file__), "regression_btc_2k.csv")
df.to_csv(out_path, index=False)
print(f"Written {len(df)} candles to {out_path}")
print(f"Price range: {closes.min():.1f} - {closes.max():.1f}")
