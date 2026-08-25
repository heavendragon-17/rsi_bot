"""Tests for the multi-TF constructor path of BinanceStreamManager."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.data.stream_manager import BinanceStreamManager


def _mk_multi(targets=None):
    targets = targets or {("BTC/USDT", "1m")}
    with patch("app.data.stream_manager.ccxt") as MockCcxt:
        MockCcxt.binanceusdm.return_value = MagicMock()
        mux = MagicMock()
        mgr = BinanceStreamManager(
            targets=targets,
            multiplexer=mux,
            enable_history=False,
        )
        return mgr, mux, MockCcxt.binanceusdm.return_value


class TestCtorValidation:
    def test_both_forms_rejected(self):
        with patch("app.data.stream_manager.ccxt"):
            with pytest.raises(ValueError):
                BinanceStreamManager(
                    symbols=["BTC/USDT"],
                    timeframe="1m",
                    store=MagicMock(),
                    targets={("ETH/USDT", "5m")},
                    multiplexer=MagicMock(),
                )

    def test_neither_form_rejected(self):
        with patch("app.data.stream_manager.ccxt"):
            with pytest.raises(ValueError):
                BinanceStreamManager()

    def test_partial_legacy_rejected(self):
        with patch("app.data.stream_manager.ccxt"):
            with pytest.raises(ValueError):
                BinanceStreamManager(symbols=["BTC/USDT"], timeframe="1m")

    def test_partial_multi_rejected(self):
        with patch("app.data.stream_manager.ccxt"):
            with pytest.raises(ValueError):
                BinanceStreamManager(targets={("BTC/USDT", "1m")})


class TestUrlConstruction:
    def test_multi_tf_url_has_all_streams(self):
        mgr, _, _ = _mk_multi(
            targets={("BTC/USDT", "1m"), ("ETH/USDT", "5m")},
        )
        assert "btcusdt@kline_1m" in mgr.url
        assert "ethusdt@kline_5m" in mgr.url

    def test_url_handles_multiple_tfs_same_pair(self):
        mgr, _, _ = _mk_multi(
            targets={("BTC/USDT", "1m"), ("BTC/USDT", "1h")},
        )
        assert "btcusdt@kline_1m" in mgr.url
        assert "btcusdt@kline_1h" in mgr.url


class TestOnMessage:
    def _msg(self, raw_symbol="BTCUSDT", interval="1m", closed=True):
        return {
            "data": {
                "e": "kline",
                "s": raw_symbol,
                "k": {
                    "t": 1_700_000_000_000,
                    "i": interval,
                    "o": "1", "h": "2", "l": "0.5", "c": "1.5", "v": "10",
                    "x": closed,
                },
            }
        }

    def test_routes_to_multiplexer(self):
        mgr, mux, _ = _mk_multi(targets={("BTC/USDT", "1m")})
        mgr.on_message(None, json.dumps(self._msg()))

        mux.on_kline_event.assert_called_once()
        args = mux.on_kline_event.call_args.args
        assert args[0] == "BTC/USDT"
        assert args[1] == "1m"
        assert args[2].timeframe == "1m"
        assert args[2].closed is True

    def test_separates_tfs_for_same_pair(self):
        mgr, mux, _ = _mk_multi(
            targets={("BTC/USDT", "1m"), ("BTC/USDT", "5m")},
        )
        mgr.on_message(None, json.dumps(self._msg(interval="1m")))
        mgr.on_message(None, json.dumps(self._msg(interval="5m")))

        assert mux.on_kline_event.call_count == 2
        tfs = [call.args[1] for call in mux.on_kline_event.call_args_list]
        assert sorted(tfs) == ["1m", "5m"]

    def test_drops_untargeted_pair(self):
        mgr, mux, _ = _mk_multi(targets={("BTC/USDT", "1m")})
        mgr.on_message(None, json.dumps(self._msg(raw_symbol="DOGEUSDT")))
        mux.on_kline_event.assert_not_called()

    def test_drops_untargeted_interval(self):
        mgr, mux, _ = _mk_multi(targets={("BTC/USDT", "1m")})
        mgr.on_message(None, json.dumps(self._msg(interval="1h")))
        mux.on_kline_event.assert_not_called()

    def test_open_candle_still_routes(self):
        mgr, mux, _ = _mk_multi(targets={("BTC/USDT", "1m")})
        mgr.on_message(None, json.dumps(self._msg(closed=False)))
        mux.on_kline_event.assert_called_once()
        assert mux.on_kline_event.call_args.args[2].closed is False


class TestFetchInitialData:
    def test_fetches_each_pair_tf(self):
        with patch("app.data.stream_manager.ccxt") as MockCcxt:
            exchange = MagicMock()
            MockCcxt.binanceusdm.return_value = exchange
            exchange.fetch_ohlcv.return_value = [
                [1_700_000_000_000, 100, 110, 90, 105, 1.0],
            ]
            mux = MagicMock()

            mgr = BinanceStreamManager(
                targets={("BTC/USDT", "1m"), ("ETH/USDT", "5m")},
                multiplexer=mux,
                enable_history=True,
                history_limit=10,
            )
            mgr.fetch_initial_data()

            assert exchange.fetch_ohlcv.call_count == 2
            tfs_used = sorted(call.args[1] for call in exchange.fetch_ohlcv.call_args_list)
            assert tfs_used == ["1m", "5m"]
            # Both rows get routed into the multiplexer.
            assert mux.on_kline_event.call_count == 2

    def test_disabled_skips_fetch(self):
        mgr, mux, exchange = _mk_multi(targets={("BTC/USDT", "1m")})
        mgr.fetch_initial_data()
        exchange.fetch_ohlcv.assert_not_called()
        mux.on_kline_event.assert_not_called()

    def test_fetch_error_swallowed(self):
        with patch("app.data.stream_manager.ccxt") as MockCcxt:
            exchange = MagicMock()
            MockCcxt.binanceusdm.return_value = exchange
            exchange.fetch_ohlcv.side_effect = RuntimeError("api fail")
            mux = MagicMock()

            mgr = BinanceStreamManager(
                targets={("BTC/USDT", "1m")},
                multiplexer=mux,
                enable_history=True,
            )
            # Must not raise
            mgr.fetch_initial_data()
            mux.on_kline_event.assert_not_called()


class TestHistoryCompleteCallback:
    def test_default_callback_is_none_and_start_unchanged(self):
        mgr, mux, _ = _mk_multi()
        assert mgr.history_complete_callback is None

        with patch("app.data.stream_manager.threading.Thread") as MockThread:
            MockThread.return_value = MagicMock()
            mgr.start()
        MockThread.assert_called_once()

    def test_callback_fires_once_after_all_fetches_before_ws_thread(self):
        events: list[str] = []

        with patch("app.data.stream_manager.ccxt") as MockCcxt:
            exchange = MagicMock()
            MockCcxt.binanceusdm.return_value = exchange

            def _record_fetch(*args, **kwargs):
                events.append("fetch")
                return [[1_700_000_000_000, 1, 2, 0.5, 1.5, 1.0]]

            exchange.fetch_ohlcv.side_effect = _record_fetch

            with patch("app.data.stream_manager.threading.Thread") as MockThread:
                MockThread.return_value = MagicMock()

                mgr = BinanceStreamManager(
                    targets={("BTC/USDT", "1m"), ("ETH/USDT", "5m")},
                    multiplexer=MagicMock(),
                    enable_history=True,
                    history_complete_callback=lambda: events.append("callback"),
                )
                mgr.start()

        # Order locked by spec §11: every fetch attempt → callback once → WS.
        assert events == ["fetch", "fetch", "callback"]
        MockThread.assert_called_once()  # WS loop starts after the hook

    def test_callback_fires_exactly_once_when_a_fetch_fails(self):
        calls: list[int] = []

        with patch("app.data.stream_manager.ccxt") as MockCcxt:
            exchange = MagicMock()
            MockCcxt.binanceusdm.return_value = exchange
            exchange.fetch_ohlcv.side_effect = [
                RuntimeError("first target fails"),
                [[1_700_000_000_000, 1, 2, 0.5, 1.5, 1.0]],
            ]

            with patch("app.data.stream_manager.threading.Thread") as MockThread:
                MockThread.return_value = MagicMock()
                mgr = BinanceStreamManager(
                    targets={("BTC/USDT", "1m"), ("ETH/USDT", "5m")},
                    multiplexer=MagicMock(),
                    enable_history=True,
                    history_complete_callback=lambda: calls.append(1),
                )
                # Must not raise despite the failed target.
                mgr.start()

        assert len(calls) == 1

    def test_callback_exception_is_isolated(self):
        with patch("app.data.stream_manager.ccxt"):
            with patch("app.data.stream_manager.threading.Thread") as MockThread:
                MockThread.return_value = MagicMock()
                mgr = BinanceStreamManager(
                    targets={("BTC/USDT", "1m")},
                    multiplexer=MagicMock(),
                    enable_history=False,
                    history_complete_callback=lambda: (_ for _ in ()).throw(
                        RuntimeError("hook boom")
                    ),
                )
                # Must not raise; WS loop still starts.
                mgr.start()
        MockThread.assert_called_once()
