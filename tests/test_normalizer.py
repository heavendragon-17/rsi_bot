"""Unit tests for DataNormalizer — pure candle transforms."""

from decimal import Decimal

import pytest

from app.core.events import EventType
from app.data.normalizer import DataNormalizer


class TestSymbolNormalize:
    def test_binance_usdt(self):
        assert DataNormalizer._normalize_symbol("BTCUSDT") == "BTC"

    def test_slash_pair(self):
        assert DataNormalizer._normalize_symbol("ETH/USDT") == "ETH"

    def test_usdc(self):
        assert DataNormalizer._normalize_symbol("SOLUSDC") == "SOL"

    def test_busd(self):
        assert DataNormalizer._normalize_symbol("XRPBUSD") == "XRP"

    def test_usd(self):
        assert DataNormalizer._normalize_symbol("ADAUSD") == "ADA"

    def test_no_known_quote_returns_as_is(self):
        assert DataNormalizer._normalize_symbol("BTCETH") == "BTCETH"

    def test_lowercase_uppercases(self):
        assert DataNormalizer._normalize_symbol("btcusdt") == "BTC"


class TestNormalizeBinance:
    def test_closed_candle_returns_kline_close(self):
        raw = {
            "e": "kline",
            "s": "BTCUSDT",
            "k": {
                "t": 1_700_000_000_000,
                "o": "50000.0",
                "h": "51000.0",
                "l": "49500.0",
                "c": "50500.0",
                "v": "123.45",
                "x": True,
            },
        }
        evt = DataNormalizer.normalize_binance(raw)
        assert evt.type == EventType.KLINE_CLOSE
        assert evt.exchange == "binance"
        assert evt.payload.symbol == "BTC"
        assert evt.payload.open == Decimal("50000.0")
        assert evt.payload.high == Decimal("51000.0")
        assert evt.payload.low == Decimal("49500.0")
        assert evt.payload.close == Decimal("50500.0")
        assert evt.payload.volume == Decimal("123.45")
        assert evt.payload.closed is True

    def test_open_candle_returns_tick_update(self):
        raw = {
            "e": "kline",
            "s": "ETHUSDT",
            "k": {
                "t": 1_700_000_000_000,
                "o": "2000",
                "h": "2010",
                "l": "1990",
                "c": "2005",
                "v": "10",
                "x": False,
            },
        }
        evt = DataNormalizer.normalize_binance(raw)
        assert evt.type == EventType.TICK_UPDATE
        assert evt.payload.closed is False


class TestNormalizeCcxt:
    def test_ohlcv_list_to_candle(self):
        ohlcv = [1_700_000_000_000, 100.0, 110.0, 90.0, 105.0, 1000.0]
        candle = DataNormalizer.normalize_ccxt("BTC/USDT", ohlcv)
        assert candle.symbol == "BTC"
        assert candle.open == Decimal("100.0")
        assert candle.high == Decimal("110.0")
        assert candle.low == Decimal("90.0")
        assert candle.close == Decimal("105.0")
        assert candle.volume == Decimal("1000.0")
        assert candle.closed is True


class TestNormalizeHyperliquid:
    def test_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            DataNormalizer.normalize_hyperliquid({})
