"""Unit tests for TimeframeMultiplexer — multi-TF in-memory routing.

Upsert/append semantics and per-frame capping behavior are covered by
``tests/test_store.py`` via the shared helpers in ``app/data/_candle_row.py``.
These tests focus on multiplexer-specific logic: target routing, per-TF cap
isolation, and close-callback fan-out.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from app.core.events import Candle
from app.data.multiplexer import TimeframeMultiplexer


def _mk_candle(ts=None, close="100", closed=True):
    return Candle(
        symbol="BTC",
        timestamp=ts or datetime(2024, 1, 1, 0, 0, 0),
        open=Decimal("99"),
        high=Decimal("101"),
        low=Decimal("98"),
        close=Decimal(close),
        volume=Decimal("10"),
        closed=closed,
    )


class TestRouting:
    def test_empty_get_returns_none(self):
        mux = TimeframeMultiplexer(targets={("BTC/USDT", "1m")})
        assert mux.get_dataframe("BTC/USDT", "1m") is None

    def test_routes_to_correct_pair_and_tf(self):
        mux = TimeframeMultiplexer(
            targets={("BTC/USDT", "1m"), ("BTC/USDT", "5m"), ("ETH/USDT", "1m")},
        )
        mux.on_kline_event("BTC/USDT", "1m", _mk_candle(close="100"))
        mux.on_kline_event("BTC/USDT", "5m", _mk_candle(close="200"))
        mux.on_kline_event("ETH/USDT", "1m", _mk_candle(close="300"))

        assert mux.get_dataframe("BTC/USDT", "1m").iloc[0]["close"] == 100.0
        assert mux.get_dataframe("BTC/USDT", "5m").iloc[0]["close"] == 200.0
        assert mux.get_dataframe("ETH/USDT", "1m").iloc[0]["close"] == 300.0

    def test_non_target_event_ignored(self):
        mux = TimeframeMultiplexer(targets={("BTC/USDT", "1m")})
        fired: list = []
        mux.register_close_callback(lambda s, t, c: fired.append((s, t)))

        mux.on_kline_event("DOGE/USDT", "1m", _mk_candle())

        assert mux.get_dataframe("DOGE/USDT", "1m") is None
        assert fired == []

    def test_get_dataframe_returns_copy(self):
        mux = TimeframeMultiplexer(targets={("BTC/USDT", "1m")})
        mux.on_kline_event("BTC/USDT", "1m", _mk_candle(close="100"))

        df = mux.get_dataframe("BTC/USDT", "1m")
        df.iloc[0, df.columns.get_loc("close")] = 999.0

        assert mux.get_dataframe("BTC/USDT", "1m").iloc[0]["close"] == 100.0

    def test_get_last_candle_returns_decimal_dict(self):
        mux = TimeframeMultiplexer(targets={("BTC/USDT", "1m")})
        mux.on_kline_event("BTC/USDT", "1m", _mk_candle(close="123.45"))

        last = mux.get_last_candle("BTC/USDT", "1m")
        assert last["close"] == Decimal("123.45")
        assert bool(last["closed"]) is True

    def test_get_last_candle_empty_returns_none(self):
        mux = TimeframeMultiplexer(targets={("BTC/USDT", "1m")})
        assert mux.get_last_candle("BTC/USDT", "1m") is None


class TestCallbacks:
    def test_callback_fires_only_on_closed_candle(self):
        mux = TimeframeMultiplexer(targets={("BTC/USDT", "1m")})
        fired: list = []
        mux.register_close_callback(lambda s, t, c: fired.append(c.close))

        mux.on_kline_event("BTC/USDT", "1m", _mk_candle(close="100", closed=False))
        assert fired == []

        mux.on_kline_event("BTC/USDT", "1m", _mk_candle(close="101", closed=True))
        assert fired == [Decimal("101")]

    def test_callback_receives_sym_tf_candle_triple(self):
        mux = TimeframeMultiplexer(targets={("ETH/USDT", "15m")})
        received: list = []
        mux.register_close_callback(lambda s, t, c: received.append((s, t, c)))

        candle = _mk_candle(close="42", closed=True)
        mux.on_kline_event("ETH/USDT", "15m", candle)

        assert received == [("ETH/USDT", "15m", candle)]

    def test_multiple_callbacks_fire_in_registration_order(self):
        mux = TimeframeMultiplexer(targets={("BTC/USDT", "1m")})
        order: list = []
        mux.register_close_callback(lambda s, t, c: order.append("a"))
        mux.register_close_callback(lambda s, t, c: order.append("b"))
        mux.register_close_callback(lambda s, t, c: order.append("c"))

        mux.on_kline_event("BTC/USDT", "1m", _mk_candle(closed=True))
        assert order == ["a", "b", "c"]

    def test_callback_exception_does_not_break_others(self):
        mux = TimeframeMultiplexer(targets={("BTC/USDT", "1m")})
        fired: list = []

        def bad(sym, tf, candle):
            raise RuntimeError("boom")

        mux.register_close_callback(bad)
        mux.register_close_callback(lambda s, t, c: fired.append("ok"))

        mux.on_kline_event("BTC/USDT", "1m", _mk_candle(closed=True))
        assert fired == ["ok"]


class TestCaps:
    def test_per_tf_cap_applied(self):
        mux = TimeframeMultiplexer(
            targets={("BTC/USDT", "1h")},
            max_candles_per_tf={"1h": 3},
        )
        base = datetime(2024, 1, 1)
        for i in range(6):
            mux.on_kline_event(
                "BTC/USDT",
                "1h",
                _mk_candle(ts=base + timedelta(hours=i), close=str(100 + i)),
            )

        df = mux.get_dataframe("BTC/USDT", "1h")
        assert list(df["close"]) == [103.0, 104.0, 105.0]

    def test_unknown_tf_falls_back_to_default(self, monkeypatch):
        monkeypatch.setattr("app.data.multiplexer.MAX_CANDLES_IN_RAM", 2)
        mux = TimeframeMultiplexer(
            targets={("BTC/USDT", "3m")},
            max_candles_per_tf={},
        )
        base = datetime(2024, 1, 1)
        for i in range(5):
            mux.on_kline_event(
                "BTC/USDT",
                "3m",
                _mk_candle(ts=base + timedelta(minutes=3 * i)),
            )

        assert len(mux.get_dataframe("BTC/USDT", "3m")) == 2

    def test_caps_isolated_between_timeframes(self):
        mux = TimeframeMultiplexer(
            targets={("BTC/USDT", "1m"), ("BTC/USDT", "5m")},
            max_candles_per_tf={"1m": 2, "5m": 4},
        )
        base = datetime(2024, 1, 1)
        for i in range(6):
            mux.on_kline_event(
                "BTC/USDT",
                "1m",
                _mk_candle(ts=base + timedelta(minutes=i)),
            )
            mux.on_kline_event(
                "BTC/USDT",
                "5m",
                _mk_candle(ts=base + timedelta(minutes=5 * i)),
            )

        assert len(mux.get_dataframe("BTC/USDT", "1m")) == 2
        assert len(mux.get_dataframe("BTC/USDT", "5m")) == 4


class TestTargets:
    def test_targets_exposes_registered_pairs(self):
        pairs = {("BTC/USDT", "1m"), ("ETH/USDT", "5m")}
        mux = TimeframeMultiplexer(targets=pairs)
        assert mux.targets == frozenset(pairs)
