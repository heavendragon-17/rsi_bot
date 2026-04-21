"""Unit tests for thread-safe MarketDataStore."""

from datetime import datetime
from decimal import Decimal

from app.core.events import Candle
from app.data.store import MarketDataStore


def _mk_candle(symbol="BTC", ts=None, close="100"):
    return Candle(
        symbol=symbol,
        timestamp=ts or datetime(2024, 1, 1, 0, 0, 0),
        open=Decimal("99"),
        high=Decimal("101"),
        low=Decimal("98"),
        close=Decimal(close),
        volume=Decimal("10"),
        closed=True,
    )


class TestStore:
    def test_empty_get_returns_none(self):
        store = MarketDataStore()
        assert store.get_dataframe("BTC") is None

    def test_update_and_get(self):
        store = MarketDataStore()
        store.update_candle(_mk_candle())
        df = store.get_dataframe("BTC")
        assert df is not None
        assert len(df) == 1
        assert df.iloc[0]["close"] == 100.0

    def test_update_same_timestamp_overwrites(self):
        store = MarketDataStore()
        ts = datetime(2024, 1, 1)
        store.update_candle(_mk_candle(ts=ts, close="100"))
        store.update_candle(_mk_candle(ts=ts, close="200"))
        df = store.get_dataframe("BTC")
        assert len(df) == 1
        assert df.iloc[0]["close"] == 200.0

    def test_new_timestamp_appends(self):
        store = MarketDataStore()
        store.update_candle(_mk_candle(ts=datetime(2024, 1, 1), close="100"))
        store.update_candle(_mk_candle(ts=datetime(2024, 1, 2), close="110"))
        df = store.get_dataframe("BTC")
        assert len(df) == 2

    def test_get_last_candle_empty_returns_none(self):
        store = MarketDataStore()
        assert store.get_last_candle("BTC") is None

    def test_get_last_candle_returns_decimal_dict(self):
        store = MarketDataStore()
        store.update_candle(_mk_candle(close="123.45"))
        last = store.get_last_candle("BTC")
        assert last is not None
        assert last["close"] == Decimal("123.45")
        assert bool(last["closed"]) is True

    def test_lock_reused_per_symbol(self):
        store = MarketDataStore()
        lock1 = store._get_lock("BTC")
        lock2 = store._get_lock("BTC")
        assert lock1 is lock2
        lock3 = store._get_lock("ETH")
        assert lock3 is not lock1


class TestStoreCap:
    def test_capped_at_max_candles(self, monkeypatch):
        # Use a small cap for testing
        monkeypatch.setattr("app.data.store.MAX_CANDLES_IN_RAM", 3)
        store = MarketDataStore()
        for i in range(10):
            store.update_candle(_mk_candle(ts=datetime(2024, 1, 1 + i)))
        df = store.get_dataframe("BTC")
        assert len(df) == 3
