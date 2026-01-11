"""Debug actual backtest flow."""
import pandas as pd
import sys
sys.path.append('.')

from app.services.market_data.store import MarketDataStore
from app.core.events import Candle
from app.utils.indicators import Indicators
from app.strategies.rsi_wma_retest import RsiWmaRetestStrategy
from app.strategies.rsi_no_retest import RsiNoRetestStrategy
from decimal import Decimal
import yaml

# Load config
with open('config.yaml') as f:
    config = yaml.safe_load(f)
config['symbols'] = ['BTC']

# Create strategy
strategy = RsiNoRetestStrategy(config)

# Load data
df = pd.read_csv('data/BTCUSDT_5m.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'])

store = MarketDataStore()

# Add all candles
for i, row in df.iterrows():
    candle = Candle(
        symbol='BTC',
        timestamp=row['timestamp'],
        open=Decimal(str(row['open'])),
        high=Decimal(str(row['high'])),
        low=Decimal(str(row['low'])),
        close=Decimal(str(row['close'])),
        volume=Decimal(str(row['volume'])),
        closed=True
    )
    store.update_candle(candle)

# Get dataframe
df_store = store.get_dataframe('BTC')
print(f"Store df shape: {df_store.shape}")
print(f"Store df columns: {list(df_store.columns)}")

# Compute indicators
ind = Indicators()
df_ind = ind.compute(df_store.copy())
print(f"After indicators shape: {df_ind.shape}")
print(f"After indicators columns: {list(df_ind.columns)}")

# Check if indicators computed
print(f"RSI NaN: {df_ind['rsi'].isna().sum()}")
print(f"RSI sample: {df_ind['rsi'].tail(5).tolist()}")

# Check state
print(f"\nLast row WMA45: {df_ind['rsi_wma45'].iloc[-1]}")
print(f"Last row EMA9: {df_ind['rsi_ema9'].iloc[-1]}")
print(f"Last row RSI: {df_ind['rsi'].iloc[-1]}")

# Try analyze
signal = strategy.analyze('BTC', df_store)
print(f"\nSignal: {signal}")
print(f"State: {strategy.context.get_state('BTC:5m').phase}")
