"""Tests for BinanceStreamManager — WebSocket stream manager."""

import json
from unittest.mock import MagicMock, patch

from app.data.stream_manager import BinanceStreamManager


def _mk_mgr(symbols=("BTC/USDT",), timeframe="5m"):
    with patch("app.data.stream_manager.ccxt") as MockCcxt:
        mock_exchange = MagicMock()
        MockCcxt.binanceusdm.return_value = mock_exchange
        store = MagicMock()
        mgr = BinanceStreamManager(list(symbols), timeframe, store)
        return mgr, store, mock_exchange


class TestSymbolHelpers:
    def test_to_stream_symbol_slash(self):
        mgr, _, _ = _mk_mgr()
        assert mgr._to_stream_symbol("BTC/USDT") == "btcusdt"

    def test_to_stream_symbol_no_slash(self):
        mgr, _, _ = _mk_mgr()
        assert mgr._to_stream_symbol("BTCUSDT") == "btcusdt"

    def test_to_stream_symbol_empty(self):
        mgr, _, _ = _mk_mgr()
        assert mgr._to_stream_symbol("") == ""

    def test_to_ccxt_symbol_with_colon(self):
        mgr, _, _ = _mk_mgr()
        assert mgr._to_ccxt_symbol("BTC/USDT:USDT") == "BTC/USDT:USDT"

    def test_to_ccxt_symbol_slash(self):
        mgr, _, _ = _mk_mgr()
        assert mgr._to_ccxt_symbol("BTC/USDT") == "BTC/USDT:USDT"

    def test_to_ccxt_symbol_no_slash(self):
        mgr, _, _ = _mk_mgr()
        assert mgr._to_ccxt_symbol("BTCUSDT") == "BTC/USDT:USDT"

    def test_to_ccxt_symbol_empty(self):
        mgr, _, _ = _mk_mgr()
        assert mgr._to_ccxt_symbol("") == ""

    def test_to_ccxt_symbol_custom_pair(self):
        mgr, _, _ = _mk_mgr()
        # Pair not ending in USDT — returns as-is uppercased
        assert mgr._to_ccxt_symbol("BTC/BUSD") == "BTC/BUSD"


class TestInitialization:
    def test_constructs_stream_url(self):
        mgr, _, _ = _mk_mgr(symbols=["BTC/USDT", "ETHUSDT"], timeframe="1h")
        assert "btcusdt@kline_1h" in mgr.url
        assert "ethusdt@kline_1h" in mgr.url

    def test_keep_running_true_after_init(self):
        mgr, _, _ = _mk_mgr()
        assert mgr.keep_running is True


class TestFetchInitialData:
    def test_disabled(self):
        with patch("app.data.stream_manager.ccxt") as MockCcxt:
            MockCcxt.binanceusdm.return_value = MagicMock()
            store = MagicMock()
            mgr = BinanceStreamManager(["BTC/USDT"], "5m", store, enable_history=False)
            mgr.fetch_initial_data()
            store.update_candle.assert_not_called()

    def test_fetches_and_stores(self):
        mgr, store, exchange = _mk_mgr()
        exchange.fetch_ohlcv.return_value = [
            [1_700_000_000_000, 100, 110, 90, 105, 1.0],
            [1_700_000_300_000, 105, 112, 95, 108, 1.5],
        ]
        mgr.fetch_initial_data()
        assert store.update_candle.call_count == 2

    def test_fetch_error_is_logged_and_swallowed(self):
        mgr, store, exchange = _mk_mgr()
        exchange.fetch_ohlcv.side_effect = RuntimeError("api fail")
        # Should not raise
        mgr.fetch_initial_data()
        store.update_candle.assert_not_called()

    def test_history_does_not_fire_live_callbacks(self):
        """History ingest must not invoke on_tick / on_kline_close — those
        callbacks are for live WS events only, per LiveEventSource semantics."""
        mgr, _, exchange = _mk_mgr()
        exchange.fetch_ohlcv.return_value = [
            [1_700_000_000_000, 100, 110, 90, 105, 1.0],
            [1_700_000_300_000, 105, 112, 95, 108, 1.5],
        ]
        mgr.on_tick = MagicMock()
        mgr.on_kline_close = MagicMock()
        mgr.fetch_initial_data()
        mgr.on_tick.assert_not_called()
        mgr.on_kline_close.assert_not_called()


class TestOnMessage:
    def test_invalid_json(self):
        mgr, store, _ = _mk_mgr()
        mgr.on_message(None, "not json")
        store.update_candle.assert_not_called()

    def test_no_data_field(self):
        mgr, store, _ = _mk_mgr()
        mgr.on_message(None, json.dumps({}))
        store.update_candle.assert_not_called()

    def test_closed_kline_invokes_callback(self):
        mgr, store, _ = _mk_mgr()
        mgr.on_kline_close = MagicMock()
        mgr.on_tick = MagicMock()
        msg = {
            "data": {
                "e": "kline",
                "s": "BTCUSDT",
                "k": {
                    "t": 1_700_000_000_000,
                    "o": "1", "h": "2", "l": "0.5", "c": "1.5", "v": "10",
                    "x": True,
                },
            }
        }
        mgr.on_message(None, json.dumps(msg))
        store.update_candle.assert_called_once()
        mgr.on_tick.assert_called_once()
        mgr.on_kline_close.assert_called_once()

    def test_open_kline_no_close_callback(self):
        mgr, store, _ = _mk_mgr()
        mgr.on_kline_close = MagicMock()
        mgr.on_tick = MagicMock()
        msg = {
            "data": {
                "e": "kline",
                "s": "BTCUSDT",
                "k": {
                    "t": 1_700_000_000_000,
                    "o": "1", "h": "2", "l": "0.5", "c": "1.5", "v": "10",
                    "x": False,
                },
            }
        }
        mgr.on_message(None, json.dumps(msg))
        mgr.on_tick.assert_called_once()
        mgr.on_kline_close.assert_not_called()

    def test_normalizer_error_logged_and_swallowed(self):
        mgr, store, _ = _mk_mgr()
        msg = {"data": {"e": "kline", "s": "BTCUSDT", "k": {}}}  # missing fields
        mgr.on_message(None, json.dumps(msg))
        # Should not crash


class TestLifecycle:
    def test_on_open_on_close_on_error(self):
        mgr, _, _ = _mk_mgr()
        mgr.on_open(None)
        mgr.on_error(None, RuntimeError("x"))
        mgr.on_close(None, 1000, "closed")
        # These are logging-only — just ensure no crash

    def test_stop_sets_flag(self):
        mgr, _, _ = _mk_mgr()
        mgr.stop()
        assert mgr.keep_running is False

    def test_stop_closes_ws(self):
        mgr, _, _ = _mk_mgr()
        mgr.ws = MagicMock()
        mgr.stop()
        mgr.ws.close.assert_called_once()
