"""
Portfolio Event Source
======================
Iterates over multiple pre-computed DataFrames from different symbols and yields
CandleCloseEvents strictly sorted by timestamp. This provides the multiplexed
chronological stream required for the unified portfolio backtest.

Optimization (Phase 2.1): Pre-sorts all (timestamp, symbol, index) triples
at init time, then iterates linearly — no heap operations in the hot loop.
Pre-extracts OHLC arrays per symbol for zero-pandas Candle construction.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import numpy as np
import pandas as pd

from app.core.constants import WARMUP
from app.core.events import Candle, CandleCloseEvent, EngineEvent, EngineStopEvent
from app.trading.event_source import IEventSource


class PortfolioEventSource(IEventSource):
    """
    Multiplexes multiple DataFrames into a single chronological stream of events.

    Uses a pre-sorted event schedule instead of a heap for O(1) per-event
    access and better cache locality.

    Args:
        dfs (Dict[str, pd.DataFrame]): Dictionary mapping symbol to its pre-computed
            DataFrame with a datetime index.
        start_idx (int): Global warmup rows to skip per symbol.
    """

    def __init__(self, dfs: dict[str, pd.DataFrame], start_idx: int = WARMUP) -> None:
        self.dfs = dfs
        self.start_idx = start_idx
        self._stopped = False

        # Pre-extract NumPy arrays per symbol for zero-pandas Candle construction
        self._arrays: dict[str, dict[str, np.ndarray]] = {}
        for symbol, df in self.dfs.items():
            self._arrays[symbol] = {
                "open": df["open"].values,
                "high": df["high"].values,
                "low": df["low"].values,
                "close": df["close"].values,
                "volume": df["volume"].values if "volume" in df.columns else np.zeros(len(df)),
                "timestamps": df.index.values,
            }

        # Build sorted event schedule: list of (timestamp, symbol, index_in_df)
        # Sort once up front — O(N log N) total instead of O(N log S) incremental heap
        schedule: list[tuple] = []
        for symbol, df in self.dfs.items():
            ts_values = df.index.values
            for idx in range(self.start_idx, len(df)):
                schedule.append((ts_values[idx], symbol, idx))

        # Sort by timestamp (stable sort preserves insertion order for ties)
        schedule.sort(key=lambda x: x[0])
        self._schedule = schedule

        # Progress tracking
        self.total_events = len(schedule)
        self.events_yielded = 0
        self._on_progress = None

    def events(self) -> Iterator[EngineEvent]:
        for ts, symbol, idx in self._schedule:
            if self._stopped:
                yield EngineStopEvent(reason="cancelled")
                return

            arrays = self._arrays[symbol]

            candle = Candle(
                symbol=symbol,
                timestamp=pd.Timestamp(ts),
                open=Decimal(str(arrays["open"][idx])),
                high=Decimal(str(arrays["high"][idx])),
                low=Decimal(str(arrays["low"][idx])),
                close=Decimal(str(arrays["close"][idx])),
                volume=Decimal(str(arrays["volume"][idx])),
                closed=True,
            )

            yield CandleCloseEvent(candle=candle, df=self.dfs[symbol], current_index=idx)

            self.events_yielded += 1
            if self._on_progress and self.total_events > 0:
                self._on_progress(self.events_yielded / self.total_events)

        if not self._stopped:
            yield EngineStopEvent(reason="data_exhausted")

    def stop(self) -> None:
        self._stopped = True
