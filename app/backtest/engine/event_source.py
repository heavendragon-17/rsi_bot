"""
Backtest Event Source (PR7: Unified Engine with Event Source Pattern)
======================================================================
Replays a pre-computed historical DataFrame as CandleCloseEvents.
Each event carries the full df slice up to and including that candle so
the Engine (and strategy) have access to all indicator history.

Usage:
    event_source = BacktestEventSource(df, symbol="BTC/USDT", start_idx=220)
    engine = BacktestEngine(event_source=event_source, ...)
    engine.run()
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import pandas as pd

from app.core.constants import WARMUP
from app.core.events import Candle, CandleCloseEvent, EngineEvent, EngineStopEvent
from app.trading.event_source import IEventSource


class BacktestEventSource(IEventSource):
    """
    Iterates a pre-computed DataFrame and yields one CandleCloseEvent per row.

    Args:
        df:        DataFrame with timestamp index and OHLCV + pre-computed
                   indicator columns. Produced by BacktestEngine._prepare_dataframe().
        symbol:    Trading pair symbol (e.g. "BTC/USDT").
        start_idx: Number of warmup rows to skip before yielding events.
                   Rows before start_idx are included in df slices so that
                   indicators are accurate, but no strategy call is made for them.
    """

    def __init__(self, df: pd.DataFrame, symbol: str, start_idx: int = WARMUP) -> None:
        self.df = df
        self.symbol = symbol
        self.start_idx = start_idx
        self._stopped = False

    def events(self) -> Iterator[EngineEvent]:
        n_rows = len(self.df)
        total = n_rows - self.start_idx  # events that will actually be yielded

        # Pre-extract numpy arrays for fast Candle construction (Phase 1.1)
        _open = self.df["open"].values
        _high = self.df["high"].values
        _low = self.df["low"].values
        _close = self.df["close"].values
        _volume = self.df["volume"].values if "volume" in self.df.columns else None
        _index = self.df.index

        for i in range(self.start_idx, n_rows):
            if self._stopped:
                yield EngineStopEvent(reason="cancelled")
                return

            ts = _index[i]

            candle = Candle(
                symbol=self.symbol,
                timestamp=ts,
                open=Decimal(str(_open[i])),
                high=Decimal(str(_high[i])),
                low=Decimal(str(_low[i])),
                close=Decimal(str(_close[i])),
                volume=Decimal(str(_volume[i])) if _volume is not None else Decimal("0"),
                closed=True,
            )

            # Phase 1.1: pass the full DataFrame + current_index instead of
            # an O(n) slice.  Downstream code uses current_index to locate
            # the "last" row, avoiding quadratic memory allocation.
            yield CandleCloseEvent(candle=candle, df=self.df, current_index=i)

            if self._on_progress and total > 0:
                self._on_progress((i - self.start_idx + 1) / total)

        yield EngineStopEvent(reason="data_exhausted")

    def stop(self) -> None:
        self._stopped = True

    # Optional progress callback — set by BacktestEngine if on_progress is provided
    _on_progress = None
