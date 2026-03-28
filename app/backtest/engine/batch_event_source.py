"""
Batch Portfolio Event Source (Phase 2.1)
=========================================
Replaces the heap-based PortfolioEventSource with a pre-sorted
timestamp-aligned batch approach. For each unique timestamp, ALL
symbols with a candle at that time are grouped into a single
BatchCandleCloseEvent — eliminating O(log n) heap operations and
enabling per-timestamp batching in the engine.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from decimal import Decimal

import numpy as np
import pandas as pd

from app.core.constants import WARMUP
from app.core.events import Candle, CandleCloseEvent, EngineEvent, EngineStopEvent
from app.trading.event_source import IEventSource


class BatchCandleCloseEvent:
    """A batch of candle close events for the same timestamp.

    Contains all symbols that have a candle at this timestamp.
    """

    __slots__ = ("timestamp", "events")

    def __init__(self, timestamp, events: list[CandleCloseEvent]) -> None:
        self.timestamp = timestamp
        self.events = events


class BatchPortfolioEventSource(IEventSource):
    """
    Timestamp-aligned batch event source for portfolio backtests.

    Pre-sorts all (timestamp, symbol, index) tuples at construction,
    then iterates linearly. Grouped by timestamp for batch processing.

    Args:
        dfs: Dict mapping symbol to pre-computed DataFrame with datetime index.
        start_idx: Warmup rows to skip per symbol.
    """

    def __init__(self, dfs: dict[str, pd.DataFrame], start_idx: int = WARMUP) -> None:
        self.dfs = dfs
        self.start_idx = start_idx
        self._stopped = False

        # Pre-build the full sorted timeline
        self._timeline: list[tuple] = []  # [(ts, [(symbol, idx), ...]), ...]
        self._build_timeline()

        # Progress tracking
        self.total_events = sum(
            max(0, len(df) - self.start_idx) for df in self.dfs.values()
        )
        self.events_yielded = 0
        self._on_progress = None

    def _build_timeline(self) -> None:
        """Pre-sort all events into a timestamp-aligned structure."""
        ts_to_items: defaultdict[pd.Timestamp, list[tuple[str, int]]] = defaultdict(list)

        for symbol, df in self.dfs.items():
            for idx in range(self.start_idx, len(df)):
                ts = df.index[idx]
                ts_to_items[ts].append((symbol, idx))

        # Sort by timestamp
        self._timeline = sorted(ts_to_items.items(), key=lambda x: x[0])

    def events(self) -> Iterator[EngineEvent]:
        """Yield BatchCandleCloseEvents grouped by timestamp."""
        # Pre-extract numpy arrays per symbol
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

        for ts, symbol_items in self._timeline:
            if self._stopped:
                break

            batch_events = []
            for symbol, idx in symbol_items:
                _open, _high, _low, _close, _volume, _index = _arrays[symbol]

                candle = Candle(
                    symbol=symbol,
                    timestamp=ts,
                    open=Decimal(str(_open[idx])),
                    high=Decimal(str(_high[idx])),
                    low=Decimal(str(_low[idx])),
                    close=Decimal(str(_close[idx])),
                    volume=(
                        Decimal(str(_volume[idx]))
                        if _volume is not None
                        else Decimal("0")
                    ),
                    closed=True,
                )

                event = CandleCloseEvent(
                    candle=candle,
                    df=self.dfs[symbol],
                    current_index=idx,
                )
                batch_events.append(event)

            yield BatchCandleCloseEvent(timestamp=ts, events=batch_events)

            self.events_yielded += len(batch_events)
            if self._on_progress and self.total_events > 0:
                self._on_progress(self.events_yielded / self.total_events)

        if self._stopped:
            yield EngineStopEvent(reason="cancelled")
        else:
            yield EngineStopEvent(reason="data_exhausted")

    def stop(self) -> None:
        self._stopped = True
