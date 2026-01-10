"""Debug script to check strategy conditions."""
import pandas as pd
import sys
sys.path.append('.')
from app.utils.indicators import Indicators

df = pd.read_csv('data/BTCUSDT_5m.csv')
df['ts'] = range(len(df))

ind = Indicators()
df_ind = ind.compute(df.copy())

# Count conditions
scanning_pass = 0
retesting_pass = 0
confirming_pass = 0

in_scanning = True
in_retesting = False
in_confirming = False

for i in range(220, len(df_ind)):
    row = df_ind.iloc[i]
    prev = df_ind.iloc[i-1]
    
    rsi = row['rsi']
    rsi_ema9 = row['rsi_ema9']
    rsi_wma45 = row['rsi_wma45']
    close = row['close']
    ema21 = row['ema21']
    ema200 = row['ema200']
    prev_close = prev['close']
    prev_ema21 = prev['ema21']
    
    if pd.isna(rsi) or pd.isna(rsi_wma45) or pd.isna(rsi_ema9):
        continue
    
    # State machine simulation
    if in_scanning:
        # SCANNING: RSI > EMA9 > WMA45, close > EMA200
        if rsi > rsi_ema9 and rsi > rsi_wma45 and rsi_ema9 > rsi_wma45 and close > ema200:
            scanning_pass += 1
            in_scanning = False
            in_retesting = True
            print(f"[{i}] SCANNING -> RETESTING: RSI={rsi:.1f}, EMA9={rsi_ema9:.1f}, WMA45={rsi_wma45:.1f}")
    
    elif in_retesting:
        # Check if RSI within 3 of WMA45
        distance = abs(rsi - rsi_wma45)
        if distance <= 3:
            retesting_pass += 1
            in_retesting = False
            in_confirming = True
            print(f"[{i}] RETESTING -> CONFIRMING: RSI={rsi:.1f}, WMA45={rsi_wma45:.1f}, dist={distance:.1f}")
    
    elif in_confirming:
        # CONFIRMING: Price crossed UP EMA21 and RSI > WMA45
        crossed_up = prev_close <= prev_ema21 and close > ema21
        rsi_bounced = rsi > rsi_wma45
        
        if crossed_up and rsi_bounced:
            confirming_pass += 1
            print(f"[{i}] SIGNAL! close={close:.2f}, ema21={ema21:.2f}, RSI={rsi:.1f}")
            in_confirming = False
            in_scanning = True
        elif rsi < rsi_wma45 - 5:
            print(f"[{i}] CONFIRMING FAILED: RSI dropped below WMA45")
            in_confirming = False
            in_scanning = True

print(f"\n=== SUMMARY ===")
print(f"SCANNING passed: {scanning_pass}")
print(f"RETESTING passed: {retesting_pass}")
print(f"CONFIRMING passed (signals): {confirming_pass}")
