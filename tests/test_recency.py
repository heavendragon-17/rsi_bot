import os

import pandas as pd

data_dir = "app/backtest/data"
os.makedirs(data_dir, exist_ok=True)
data_file = f"{data_dir}/BTC_USDT_15m.csv"

# Create a small CSV that claims to be from 2 hours ago (so > 2*15m old)
ts = pd.Timestamp.utcnow().tz_localize(None) + pd.Timedelta(hours=7) - pd.Timedelta(minutes=120)
content = "timestamp,open,high,low,close,volume\n"
for i in range(100):
    row_ts = ts + pd.Timedelta(minutes=i * 15)
    content += f"{row_ts},100,105,95,102,1000\n"

with open(data_file, "w") as f:
    f.write(content)

print(f"Created dummy file with latest timestamp: {ts + pd.Timedelta(minutes=99*15)}")
