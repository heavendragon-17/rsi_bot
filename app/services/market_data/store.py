"""
Layer 1: Data Ingestion - MarketDataStore
==========================================
Thread-safe in-memory storage for candle data.
Stores both float (for pandas operations) and Decimal (for precision).
"""
import pandas as pd
import threading
from decimal import Decimal
from typing import Optional, Dict
from app.core.constants import MAX_CANDLES_IN_RAM
from app.core.events import Candle


class MarketDataStore:
    """
    Thread-safe in-memory storage for candle data.
    
    Stores float values for pandas operations but preserves
    Decimal precision in separate columns for calculations.
    """
    
    def __init__(self):
        self.data: Dict[str, pd.DataFrame] = {}
        self.locks: Dict[str, threading.Lock] = {}
        self.global_lock = threading.Lock()

    def _get_lock(self, symbol: str) -> threading.Lock:
        with self.global_lock:
            if symbol not in self.locks:
                self.locks[symbol] = threading.Lock()
            return self.locks[symbol]

    def update_candle(self, candle: Candle) -> None:
        """
        Update or append candle data.
        If timestamp matches last candle, update it; otherwise append.
        """
        symbol = candle.symbol
        with self._get_lock(symbol):
            # Convert Decimal to float for pandas, preserve Decimal for precision
            new_row = {
                'timestamp': candle.timestamp,
                'open': float(candle.open),
                'high': float(candle.high),
                'low': float(candle.low),
                'close': float(candle.close),
                'volume': float(candle.volume),
                'closed': candle.closed,
                # Preserve Decimal values for precise calculations
                'open_dec': candle.open,
                'high_dec': candle.high,
                'low_dec': candle.low,
                'close_dec': candle.close,
            }

            if symbol not in self.data:
                df = pd.DataFrame([new_row])
                df.set_index('timestamp', inplace=True)
                self.data[symbol] = df
            else:
                df = self.data[symbol]
                last_time = df.index[-1]
                new_time = new_row['timestamp']

                if new_time == last_time:
                    # Update current candle
                    for col in new_row:
                        if col != 'timestamp':
                            df.at[last_time, col] = new_row[col]
                else:
                    # New candle
                    new_df = pd.DataFrame([new_row])
                    new_df.set_index('timestamp', inplace=True)
                    self.data[symbol] = pd.concat([df, new_df])

                # Limit memory usage
                if len(self.data[symbol]) > MAX_CANDLES_IN_RAM:
                    self.data[symbol] = self.data[symbol].tail(MAX_CANDLES_IN_RAM)

    def get_dataframe(self, symbol: str) -> Optional[pd.DataFrame]:
        """Get a copy of the candle DataFrame for a symbol."""
        with self._get_lock(symbol):
            if symbol in self.data:
                return self.data[symbol].copy()
            return None
    
    def get_last_candle(self, symbol: str) -> Optional[Dict]:
        """
        Get the last candle as a dictionary with Decimal values.
        Useful for precise price calculations.
        """
        df = self.get_dataframe(symbol)
        if df is None or df.empty:
            return None
        
        row = df.iloc[-1]
        return {
            'timestamp': row.name,
            'open': row.get('open_dec', Decimal(str(row['open']))),
            'high': row.get('high_dec', Decimal(str(row['high']))),
            'low': row.get('low_dec', Decimal(str(row['low']))),
            'close': row.get('close_dec', Decimal(str(row['close']))),
            'volume': Decimal(str(row['volume'])),
            'closed': row['closed']
        }
