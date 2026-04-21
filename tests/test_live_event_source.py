"""Unit tests for LiveEventSource queue / thread-safety glue."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from app.core.events import Candle, CandleCloseEvent, EngineStopEvent
from app.data.live_event_source import LiveEventSource


def _mk_candle(symbol="BTC"):
    return Candle(
        symbol=symbol,
        timestamp=datetime(2024, 1, 1),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=Decimal("1"),
        closed=True,
    )


def test_on_kline_close_enqueues_event():
    stream = MagicMock()
    store = MagicMock()
    store.get_dataframe.return_value = "df-sentinel"

    src = LiveEventSource(stream, store, ["BTC"])
    src._on_kline_close(_mk_candle())

    evt = src._event_queue.get_nowait()
    assert isinstance(evt, CandleCloseEvent)
    assert evt.df == "df-sentinel"


def test_on_kline_close_drops_when_queue_full():
    stream = MagicMock()
    store = MagicMock()
    store.get_dataframe.return_value = None
    src = LiveEventSource(stream, store, ["BTC"], queue_size=1)
    # Fill the queue
    src._event_queue.put_nowait(CandleCloseEvent(candle=_mk_candle()))
    # Second call should log warning instead of raising
    src._on_kline_close(_mk_candle())


def test_stop_sets_flag_and_enqueues_stop_event():
    stream = MagicMock()
    store = MagicMock()
    src = LiveEventSource(stream, store, ["BTC"])

    src.stop()

    assert src._stopped.is_set()
    # The stop() implementation also enqueues an EngineStopEvent to unblock queue.get
    evt = src._event_queue.get_nowait()
    assert isinstance(evt, EngineStopEvent)


def test_events_yields_and_exits_on_stop():
    stream = MagicMock()
    store = MagicMock()
    src = LiveEventSource(stream, store, ["BTC"])

    # Prime queue with a normal event followed by stop
    src._event_queue.put_nowait(CandleCloseEvent(candle=_mk_candle()))
    src._event_queue.put_nowait(EngineStopEvent(reason="done"))

    seen = []
    for evt in src.events():
        seen.append(evt)
        if isinstance(evt, EngineStopEvent):
            break

    assert len(seen) == 2
    assert isinstance(seen[-1], EngineStopEvent)
    # stream_manager callback should be wired
    assert stream.on_kline_close == src._on_kline_close
