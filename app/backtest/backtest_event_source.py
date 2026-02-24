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

from decimal import Decimal
from typing import Iterator

import pandas as pd

from app.core.event_source import IEventSource
from app.core.events import Candle, CandleCloseEvent, EngineEvent, EngineStopEvent


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

    def __init__(self, df: pd.DataFrame, symbol: str, start_idx: int = 220) -> None:
        self.df = df
        self.symbol = symbol
        self.start_idx = start_idx
        self._stopped = False

    def events(self) -> Iterator[EngineEvent]:
        n_rows = len(self.df)
        total = n_rows - self.start_idx  # events that will actually be yielded

        for i in range(self.start_idx, n_rows):
            if self._stopped:
                yield EngineStopEvent(reason="cancelled")
                return

            row = self.df.iloc[i]
            ts = self.df.index[i]

            candle = Candle(
                symbol=self.symbol,
                timestamp=ts,
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row.get("volume", 0))),
                closed=True,
            )

            # df slice includes all history up to and including this candle
            df_slice = self.df.iloc[: i + 1]

            yield CandleCloseEvent(candle=candle, df=df_slice)

            if self._on_progress and total > 0:
                self._on_progress((i - self.start_idx + 1) / total)

        yield EngineStopEvent(reason="data_exhausted")

    def stop(self) -> None:
        self._stopped = True

    # Optional progress callback — set by BacktestEngine if on_progress is provided
    _on_progress = None
