"""
Live Event Source (PR7: Unified Engine with Event Source Pattern)
=================================================================
Wraps BinanceStreamManager and converts closed-candle callbacks into
CandleCloseEvents on a thread-safe queue so the unified Engine can consume
them through the standard IEventSource interface.

The attached MarketDataStore is queried on each kline-close to attach the
full indicator-ready DataFrame to the event (same DataFrame the runner
currently reads via store.get_dataframe).

Usage:
    live_source = LiveEventSource(stream_manager, store, symbols)
    engine = Engine(event_source=live_source, ...)
    engine.run()           # blocks until stop() is called
"""
from __future__ import annotations

import queue
import threading
from typing import Iterator, List

import structlog

from app.trading.event_source import IEventSource
from app.core.events import CandleCloseEvent, EngineEvent, EngineStopEvent

logger = structlog.get_logger()


class LiveEventSource(IEventSource):
    """
    Produces CandleCloseEvents from a running BinanceStreamManager.

    The stream manager's ``on_kline_close`` callback is set to push closed
    candles (plus their current store DataFrame) onto a bounded queue.
    The ``events()`` generator blocks on that queue, yielding events as
    they arrive from the WebSocket thread.
    """

    def __init__(
        self,
        stream_manager,     # BinanceStreamManager
        store,              # MarketDataStore
        symbols: List[str],
        queue_size: int = 500,
    ) -> None:
        self.stream_manager = stream_manager
        self.store = store
        self.symbols = symbols
        self._event_queue: queue.Queue[EngineEvent] = queue.Queue(maxsize=queue_size)
        self._stopped = threading.Event()

    # ------------------------------------------------------------------
    # IEventSource
    # ------------------------------------------------------------------

    def events(self) -> Iterator[EngineEvent]:
        """
        Register callbacks on the stream manager then yield events as
        they arrive. Blocks on queue.get with a 1-second timeout so the
        stop flag can be checked cleanly.
        """
        self.stream_manager.on_kline_close = self._on_kline_close

        while not self._stopped.is_set():
            try:
                event = self._event_queue.get(timeout=1.0)
                yield event
                if isinstance(event, EngineStopEvent):
                    break
            except queue.Empty:
                continue

    def stop(self) -> None:
        self._stopped.set()
        # Unblock the generator in case it's waiting on queue.get
        self._event_queue.put(EngineStopEvent(reason="stopped"))

    # ------------------------------------------------------------------
    # Internal callback (called from WebSocket thread)
    # ------------------------------------------------------------------

    def _on_kline_close(self, candle) -> None:
        """
        Called by BinanceStreamManager when a kline closes.
        Fetches the current DataFrame from the store and enqueues the event.
        """
        symbol = candle.symbol
        df = self.store.get_dataframe(symbol)
        try:
            self._event_queue.put_nowait(CandleCloseEvent(candle=candle, df=df))
        except queue.Full:
            logger.warning("live_event_queue_full", symbol=symbol)
