"""
Portfolio Event Source
======================
Iterates over multiple pre-computed DataFrames from different symbols and yields
CandleCloseEvents strictly sorted by timestamp. This provides the multiplexed
chronological stream required for the unified portfolio backtest.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterator
from decimal import Decimal

import pandas as pd

from app.core.constants import WARMUP
from app.core.events import Candle, CandleCloseEvent, EngineEvent, EngineStopEvent
from app.trading.event_source import IEventSource


class PortfolioEventSource(IEventSource):
    """
    Multiplexes multiple DataFrames into a single chronological stream of events.

    Args:
        dfs (Dict[str, pd.DataFrame]): Dictionary mapping symbol to its pre-computed
            DataFrame with a datetime index.
        start_idx (int): Global warmup rows to skip.
            Note: Since different dataframes might have different start dates,
            warmup is handled by computing indicators for the whole df but
            only yielding events after `start_idx` candles have been skipped
            *per symbol*.
    """

    def __init__(self, dfs: dict[str, pd.DataFrame], start_idx: int = WARMUP) -> None:
        self.dfs = dfs
        self.start_idx = start_idx
        self._stopped = False

        # Priority Queue for merging
        # Items in queue: (timestamp, counter, symbol, index_in_df)
        self.pq: list[tuple[pd.Timestamp, int, str, int]] = []
        self._counter = 0  # tie-breaker

        # Initialize priority queue with the first valid candle for each symbol
        for symbol, df in self.dfs.items():
            if len(df) > self.start_idx:
                ts = df.index[self.start_idx]
                heapq.heappush(self.pq, (ts, self._counter, symbol, self.start_idx))
                self._counter += 1

        # Progress tracking
        self.total_events = sum(max(0, len(df) - self.start_idx) for df in self.dfs.values())
        self.events_yielded = 0
        self._on_progress = None

    def events(self) -> Iterator[EngineEvent]:
        # Pre-extract numpy arrays per symbol for fast Candle construction (Phase 1.1)
        _arrays: dict[str, tuple] = {}
        for symbol, df in self.dfs.items():
            _arrays[symbol] = (
                df["open"].values,
                df["high"].values,
                df["low"].values,
                df["close"].values,
                df["volume"].values if "volume" in df.columns else None,
                df.index,
            )

        while self.pq and not self._stopped:
            # Pop the earliest event
            ts, _, symbol, idx = heapq.heappop(self.pq)
            df = self.dfs[symbol]
            _open, _high, _low, _close, _volume, _index = _arrays[symbol]

            candle = Candle(
                symbol=symbol,
                timestamp=ts,
                open=Decimal(str(_open[idx])),
                high=Decimal(str(_high[idx])),
                low=Decimal(str(_low[idx])),
                close=Decimal(str(_close[idx])),
                volume=Decimal(str(_volume[idx])) if _volume is not None else Decimal("0"),
                closed=True,
            )

            # Phase 1.1: pass the full DataFrame + current_index
            yield CandleCloseEvent(candle=candle, df=df, current_index=idx)

            self.events_yielded += 1
            if self._on_progress and self.total_events > 0:
                self._on_progress(self.events_yielded / self.total_events)

            # Push the next candle for this symbol
            next_idx = idx + 1
            if next_idx < len(df):
                next_ts = _index[next_idx]
                heapq.heappush(self.pq, (next_ts, self._counter, symbol, next_idx))
                self._counter += 1

        if self._stopped:
            yield EngineStopEvent(reason="cancelled")
        else:
            yield EngineStopEvent(reason="data_exhausted")

    def stop(self) -> None:
        self._stopped = True
