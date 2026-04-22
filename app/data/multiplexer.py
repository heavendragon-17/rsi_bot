"""
Layer 1: Data Ingestion - TimeframeMultiplexer
===============================================
Thread-safe in-memory storage for candles across many ``(symbol, timeframe)``
pairs, used by the signal-bot path. The live bot continues to use
:class:`app.data.store.MarketDataStore` (single-timeframe).

Callers own the symbol format. The multiplexer is a dumb router: whatever
string the caller registers as a target is the string that must be passed to
:meth:`on_kline_event` and :meth:`get_dataframe`.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

import pandas as pd
import structlog

from app.core.constants import MAX_CANDLES_IN_RAM, MAX_CANDLES_IN_RAM_PER_TF
from app.core.events import Candle
from app.data._candle_row import candle_to_row, last_row_to_decimal_dict

logger = structlog.get_logger()

CloseCallback = Callable[[str, str, Candle], None]


class TimeframeMultiplexer:
    """Thread-safe in-memory store keyed by ``(symbol, timeframe)``.

    Close callbacks fire after the per-pair lock is released, so a slow or
    crashing subscriber cannot block data ingest for other pairs. Callback
    exceptions are logged and isolated — one bad subscriber never stops the
    others.
    """

    def __init__(
        self,
        targets: set[tuple[str, str]],
        max_candles_per_tf: dict[str, int] | None = None,
    ) -> None:
        self._targets: frozenset[tuple[str, str]] = frozenset(targets)
        self._caps: dict[str, int] = (
            dict(max_candles_per_tf)
            if max_candles_per_tf is not None
            else dict(MAX_CANDLES_IN_RAM_PER_TF)
        )

        self._data: dict[tuple[str, str], pd.DataFrame] = {}
        self._locks: dict[tuple[str, str], threading.Lock] = {}
        self._global_lock = threading.Lock()
        self._callbacks: list[CloseCallback] = []

    @property
    def targets(self) -> frozenset[tuple[str, str]]:
        return self._targets

    def register_close_callback(self, cb: CloseCallback) -> None:
        self._callbacks.append(cb)

    def on_kline_event(self, symbol: str, timeframe: str, candle: Candle) -> None:
        key = (symbol, timeframe)
        if key not in self._targets:
            logger.debug(
                "multiplexer_untargeted_event",
                symbol=symbol,
                timeframe=timeframe,
            )
            return

        with self._get_lock(key):
            self._upsert(key, timeframe, candle)

        if candle.closed:
            self._fire_callbacks(symbol, timeframe, candle)

    def get_dataframe(self, symbol: str, timeframe: str) -> pd.DataFrame | None:
        key = (symbol, timeframe)
        with self._get_lock(key):
            df = self._data.get(key)
            if df is None:
                return None
            return df.copy()

    def get_last_candle(self, symbol: str, timeframe: str) -> dict | None:
        return last_row_to_decimal_dict(self.get_dataframe(symbol, timeframe))

    def _get_lock(self, key: tuple[str, str]) -> threading.Lock:
        with self._global_lock:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock

    def _cap_for(self, timeframe: str) -> int:
        return self._caps.get(timeframe, MAX_CANDLES_IN_RAM)

    def _upsert(self, key: tuple[str, str], timeframe: str, candle: Candle) -> None:
        new_row = candle_to_row(candle)
        df = self._data.get(key)

        if df is None:
            new_df = pd.DataFrame([new_row])
            new_df.set_index("timestamp", inplace=True)
            self._data[key] = new_df
            return

        last_time = df.index[-1]
        new_time = new_row["timestamp"]

        if new_time == last_time:
            for col, value in new_row.items():
                if col != "timestamp":
                    df.at[last_time, col] = value
        else:
            new_df = pd.DataFrame([new_row])
            new_df.set_index("timestamp", inplace=True)
            df = pd.concat([df, new_df])
            self._data[key] = df

        cap = self._cap_for(timeframe)
        if len(self._data[key]) > cap:
            self._data[key] = self._data[key].tail(cap)

    def _fire_callbacks(self, symbol: str, timeframe: str, candle: Candle) -> None:
        for cb in self._callbacks:
            try:
                cb(symbol, timeframe, candle)
            except Exception as e:
                logger.exception(
                    "multiplexer_callback_error",
                    symbol=symbol,
                    timeframe=timeframe,
                    error=str(e),
                )
