"""
Event Source Abstraction (PR7: Unified Engine)
===============================================
Both live and backtest provide the same EngineEvent types through this
interface. The Engine is agnostic to whether events come from a WebSocket
stream or a replayed historical CSV.
"""
from abc import ABC, abstractmethod
from typing import Iterator

from app.core.events import EngineEvent


class IEventSource(ABC):
    """Yields EngineEvents for the Engine to process."""

    @abstractmethod
    def events(self) -> Iterator[EngineEvent]:
        """
        Yield events one at a time.

        - LiveEventSource  : blocks until next WebSocket message, yields in real-time.
        - BacktestEventSource: iterates historical data, yields instantly.

        Must yield an EngineStopEvent when the stream ends or stop() is called.
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """Signal the event source to stop producing events."""
        pass
