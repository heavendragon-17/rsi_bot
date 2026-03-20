"""
Tests for the unified Engine event processing (PR7).

Verifies:
- Engine processes CandleCloseEvent and dispatches typed actions
- Engine stores and updates per-symbol ContextSnapshot
- EngineStopEvent stops the event loop
- BacktestEventSource yields the expected number of events
"""
import pytest
import pandas as pd
from decimal import Decimal
from datetime import datetime
from unittest.mock import MagicMock, call

from app.trading.engine import Engine
from app.trading.event_source import IEventSource
from app.core.events import (
    Candle, CandleCloseEvent, EngineStopEvent, TickEvent,
)
from app.core.snapshots import ContextSnapshot, PositionSnapshot
from app.core.analysis_result import AnalysisResult
from app.core.actions import DoNothing, OpenPosition
from app.backtest.backtest_event_source import BacktestEventSource


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------

def _make_candle(symbol="BTC/USDT", close=100.0) -> Candle:
    return Candle(
        symbol=symbol,
        timestamp=datetime.now(),
        open=Decimal(str(close)),
        high=Decimal(str(close)),
        low=Decimal(str(close)),
        close=Decimal(str(close)),
        volume=Decimal("1"),
        closed=True,
    )


def _make_df(n: int = 10) -> pd.DataFrame:
    timestamps = [pd.Timestamp.now() - pd.Timedelta(minutes=i) for i in range(n)]
    timestamps.reverse()
    rows = [
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0,
         "ema21": 100.0, "rsi_ema9": 50.0, "rsi_wma45": 50.0, "closed": True}
        for _ in range(n)
    ]
    return pd.DataFrame(rows, index=timestamps)


class _FixedEventSource(IEventSource):
    """Emits a fixed list of events then stops."""

    def __init__(self, events):
        self._events = list(events)

    def events(self):
        yield from self._events

    def stop(self):
        pass


class _DoNothingStrategy:
    """Stub strategy that always returns DoNothing."""

    def analyze(self, symbol, df, position=None, context=None):
        ctx = context or ContextSnapshot(state="SCANNING")
        return AnalysisResult(actions=[DoNothing()], new_context=ctx)


class _MockPortfolio:
    def __init__(self):
        self.signals = []
        self.closes = []

    def get_position_snapshot(self, symbol):
        return PositionSnapshot(has_position=False, symbol=symbol)

    def on_signal(self, signal):
        self.signals.append(signal)

    def close_position(self, symbol, **kw):
        self.closes.append(symbol)

    def move_stop_loss(self, symbol, new_sl):
        pass

    def execute_partial_close(self, symbol, tp_level, **kw):
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_engine_stop_event_ends_loop():
    """EngineStopEvent must terminate the event loop."""
    source = _FixedEventSource([EngineStopEvent(reason="test")])
    strategy = _DoNothingStrategy()
    portfolio = _MockPortfolio()
    exchange = MagicMock()

    engine = Engine(
        event_source=source,
        strategy=strategy,
        portfolio=portfolio,
        exchange=exchange,
        symbols=["BTC/USDT"],
    )
    result = engine.run()  # should return immediately
    assert result is None


def test_candle_close_event_calls_analyze():
    """Engine calls strategy.analyze() for each CandleCloseEvent."""
    df = _make_df(60)  # more than 50 rows → engine won't skip
    candle = _make_candle()
    event = CandleCloseEvent(candle=candle, df=df)
    source = _FixedEventSource([event, EngineStopEvent()])

    strategy = MagicMock()
    strategy.analyze.return_value = AnalysisResult(
        actions=[DoNothing()],
        new_context=ContextSnapshot(state="SCANNING"),
    )

    portfolio = _MockPortfolio()
    engine = Engine(
        event_source=source,
        strategy=strategy,
        portfolio=portfolio,
        exchange=MagicMock(),
        symbols=["BTC/USDT"],
    )
    engine.run()

    strategy.analyze.assert_called_once()


def test_engine_stores_context_per_symbol():
    """Engine must update self.contexts with new_context after each analyze()."""
    df = _make_df(60)
    candle = _make_candle()
    source = _FixedEventSource([
        CandleCloseEvent(candle=candle, df=df),
        EngineStopEvent(),
    ])

    new_ctx = ContextSnapshot(state="CONFIRMING")
    strategy = MagicMock()
    strategy.analyze.return_value = AnalysisResult(
        actions=[DoNothing()], new_context=new_ctx
    )

    engine = Engine(
        event_source=source,
        strategy=strategy,
        portfolio=_MockPortfolio(),
        exchange=MagicMock(),
        symbols=["BTC/USDT"],
    )
    engine.run()

    assert engine.contexts.get("BTC/USDT") is new_ctx


def test_engine_skips_df_below_50_rows():
    """Engine must skip CandleCloseEvent when df has fewer than 50 rows."""
    df = _make_df(10)  # only 10 rows → should skip
    candle = _make_candle()
    source = _FixedEventSource([
        CandleCloseEvent(candle=candle, df=df),
        EngineStopEvent(),
    ])

    strategy = MagicMock()

    engine = Engine(
        event_source=source,
        strategy=strategy,
        portfolio=_MockPortfolio(),
        exchange=MagicMock(),
        symbols=["BTC/USDT"],
    )
    engine.run()

    strategy.analyze.assert_not_called()


def test_engine_skips_none_df():
    """Engine must skip CandleCloseEvent when df is None."""
    candle = _make_candle()
    source = _FixedEventSource([
        CandleCloseEvent(candle=candle, df=None),
        EngineStopEvent(),
    ])

    strategy = MagicMock()

    engine = Engine(
        event_source=source,
        strategy=strategy,
        portfolio=_MockPortfolio(),
        exchange=MagicMock(),
        symbols=["BTC/USDT"],
    )
    engine.run()

    strategy.analyze.assert_not_called()


# ---------------------------------------------------------------------------
# BacktestEventSource tests
# ---------------------------------------------------------------------------

def _make_full_df(n: int = 300) -> pd.DataFrame:
    """Create a DataFrame large enough for realistic backtest slicing."""
    timestamps = [pd.Timestamp.now() - pd.Timedelta(minutes=i) for i in range(n)]
    timestamps.reverse()
    rows = [
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0,
         "volume": 1.0, "closed": True}
        for _ in range(n)
    ]
    return pd.DataFrame(rows, index=pd.DatetimeIndex(timestamps))


def test_backtest_event_source_yields_correct_count():
    """BacktestEventSource should yield (n - start_idx) CandleCloseEvents + 1 EngineStopEvent."""
    n = 300
    start = 220
    df = _make_full_df(n)
    source = BacktestEventSource(df, symbol="BTC/USDT", start_idx=start)

    events = list(source.events())
    candle_events = [e for e in events if isinstance(e, CandleCloseEvent)]
    stop_events = [e for e in events if isinstance(e, EngineStopEvent)]

    assert len(candle_events) == n - start
    assert len(stop_events) == 1
    assert stop_events[0].reason == "data_exhausted"


def test_backtest_event_source_df_slice_grows():
    """Each successive CandleCloseEvent's df must be one row longer than the previous."""
    n = 225
    start = 220
    df = _make_full_df(n)
    source = BacktestEventSource(df, symbol="BTC/USDT", start_idx=start)

    events = [e for e in source.events() if isinstance(e, CandleCloseEvent)]
    lengths = [len(e.df) for e in events]

    for i in range(1, len(lengths)):
        assert lengths[i] == lengths[i - 1] + 1, (
            f"df slice at event {i} should be one longer than event {i-1}"
        )


def test_backtest_event_source_stop():
    """Calling stop() should cause events() to emit EngineStopEvent early."""
    df = _make_full_df(300)
    source = BacktestEventSource(df, symbol="BTC/USDT", start_idx=220)

    collected = []
    for event in source.events():
        collected.append(event)
        if len(collected) == 3:
            source.stop()

    stop_events = [e for e in collected if isinstance(e, EngineStopEvent)]
    assert stop_events, "stop() must cause an EngineStopEvent to be emitted"
    assert stop_events[0].reason == "cancelled"
