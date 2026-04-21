"""Tests for PortfolioEventSource — heap-merge of symbol DataFrames."""

import pandas as pd

from app.backtest.engine.portfolio_event_source import PortfolioEventSource
from app.core.events import CandleCloseEvent, EngineStopEvent


def _mk_df(n, start="2024-01-01"):
    ts = pd.date_range(start, periods=n, freq="5min")
    return pd.DataFrame({
        "open": [100.0 + i for i in range(n)],
        "high": [101.0 + i for i in range(n)],
        "low": [99.0 + i for i in range(n)],
        "close": [100.5 + i for i in range(n)],
        "volume": [10.0] * n,
    }, index=ts)


class TestPortfolioEventSource:
    def test_merges_two_symbols_in_order(self):
        df1 = _mk_df(5, "2024-01-01 00:00:00")
        df2 = _mk_df(5, "2024-01-01 00:02:30")  # staggered
        src = PortfolioEventSource({"BTC": df1, "ETH": df2}, start_idx=0)

        events = list(src.events())
        candle_events = [e for e in events if isinstance(e, CandleCloseEvent)]
        stops = [e for e in events if isinstance(e, EngineStopEvent)]
        assert len(candle_events) == 10
        assert len(stops) == 1
        # Timestamps must be monotonic
        timestamps = [e.candle.timestamp for e in candle_events]
        assert timestamps == sorted(timestamps)

    def test_start_idx_skips(self):
        df = _mk_df(10)
        src = PortfolioEventSource({"BTC": df}, start_idx=3)
        candle_events = [e for e in src.events() if isinstance(e, CandleCloseEvent)]
        assert len(candle_events) == 7

    def test_start_idx_larger_than_df_yields_nothing(self):
        df = _mk_df(3)
        src = PortfolioEventSource({"BTC": df}, start_idx=10)
        events = list(src.events())
        assert all(isinstance(e, EngineStopEvent) for e in events)
        # Stop reason should be data_exhausted
        assert events[0].reason == "data_exhausted"

    def test_stop_mid_iteration(self):
        df = _mk_df(10)
        src = PortfolioEventSource({"BTC": df}, start_idx=0)
        out = []
        for i, e in enumerate(src.events()):
            out.append(e)
            if i >= 2:
                src.stop()
        # Once stop() is called the source yields a cancelled EngineStopEvent
        assert any(
            isinstance(e, EngineStopEvent) and e.reason == "cancelled" for e in out
        )

    def test_current_index_exposed(self):
        df = _mk_df(3)
        src = PortfolioEventSource({"BTC": df}, start_idx=0)
        first = next(src.events())
        assert isinstance(first, CandleCloseEvent)
        assert first.current_index == 0

    def test_no_volume_column(self):
        df = _mk_df(2).drop(columns=["volume"])
        src = PortfolioEventSource({"BTC": df}, start_idx=0)
        events = [e for e in src.events() if isinstance(e, CandleCloseEvent)]
        # Volume defaults to Decimal("0")
        assert events[0].candle.volume == 0
