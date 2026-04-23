"""
Layer 1: Data Ingestion - MarketDataStore
==========================================
Thread-safe in-memory storage for candle data.
Stores both float (for pandas operations) and Decimal (for precision).
"""

import threading

import pandas as pd

from app.core.constants import MAX_CANDLES_IN_RAM
from app.core.events import Candle
from app.data._candle_row import candle_to_row, last_row_to_decimal_dict


class MarketDataStore:
    """
    Thread-safe in-memory storage for candle data.

    Stores float values for pandas operations but preserves
    Decimal precision in separate columns for calculations.
    """

    def __init__(self) -> None:
        self.data: dict[str, pd.DataFrame] = {}
        self.locks: dict[str, threading.Lock] = {}
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
            new_row = candle_to_row(candle)

            if symbol not in self.data:
                df = pd.DataFrame([new_row])
                df.set_index("timestamp", inplace=True)
                self.data[symbol] = df
            else:
                df = self.data[symbol]
                last_time = df.index[-1]
                new_time = new_row["timestamp"]

                if new_time == last_time:
                    # Update current candle
                    for col in new_row:
                        if col != "timestamp":
                            df.at[last_time, col] = new_row[col]
                else:
                    # New candle
                    new_df = pd.DataFrame([new_row])
                    new_df.set_index("timestamp", inplace=True)
                    self.data[symbol] = pd.concat([df, new_df])

                # Limit memory usage
                if len(self.data[symbol]) > MAX_CANDLES_IN_RAM:
                    self.data[symbol] = self.data[symbol].tail(MAX_CANDLES_IN_RAM)

    def get_dataframe(self, symbol: str) -> pd.DataFrame | None:
        """Get a copy of the candle DataFrame for a symbol."""
        with self._get_lock(symbol):
            if symbol in self.data:
                return self.data[symbol].copy()
            return None

    def get_last_candle(self, symbol: str) -> dict | None:
        """
        Get the last candle as a dictionary with Decimal values.
        Useful for precise price calculations.
        """
        return last_row_to_decimal_dict(self.get_dataframe(symbol))
