"""
Layer 1: Data Ingestion - DataNormalizer
=========================================
Normalizes raw exchange data into Candle objects with Decimal precision.
"""

import pandas as pd

from app.core.events import Candle, EventType, MarketEvent
from app.core.utils import to_decimal


class DataNormalizer:
    """
    Normalizes raw exchange data to standardized Candle objects.
    All prices are converted to Decimal for financial precision.
    """

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """
        Normalize symbol to base asset (e.g. BTC/USDT -> BTC, BTCUSDT -> BTC).
        """
        symbol = symbol.upper().replace("/", "")
        # Order matters: longer suffixes first to avoid partial matches
        for quote in ["USDT", "USDC", "BUSD", "USD"]:
            if symbol.endswith(quote):
                return symbol[: -len(quote)]
        return symbol

    @staticmethod
    def normalize_binance(raw_data) -> MarketEvent:
        """
        Convert raw Binance kline stream format to MarketEvent.

        Args:
            raw_data: {'e': 'kline', 'E': 123456789, 's': 'BTCUSDT', 'k': {...}}

        Returns:
            MarketEvent with Decimal price fields
        """
        kline = raw_data["k"]
        raw_symbol = raw_data["s"]
        symbol = DataNormalizer._normalize_symbol(raw_symbol)
        is_closed = kline["x"]

        event_type = EventType.KLINE_CLOSE if is_closed else EventType.TICK_UPDATE

        candle = Candle(
            symbol=symbol,
            timestamp=pd.to_datetime(kline["t"], unit="ms") + pd.Timedelta(hours=7),
            open=to_decimal(kline["o"]),
            high=to_decimal(kline["h"]),
            low=to_decimal(kline["l"]),
            close=to_decimal(kline["c"]),
            volume=to_decimal(kline["v"]),
            closed=is_closed,
            timeframe=kline.get("i", ""),
        )

        return MarketEvent(type=event_type, exchange="binance", payload=candle)

    @staticmethod
    def normalize_ccxt(symbol: str, ohlcv: list, timeframe: str = "") -> Candle:
        """
        Convert CCXT OHLCV list to Candle object.

        Args:
            symbol: Trading pair symbol (e.g. 'BTC/USDT')
            ohlcv: [timestamp, open, high, low, close, volume]
            timeframe: Optional timeframe string (e.g. '15m'). Empty when unknown.

        Returns:
            Candle with Decimal price fields
        """
        normalized_symbol = DataNormalizer._normalize_symbol(symbol)
        timestamp = pd.to_datetime(ohlcv[0], unit="ms") + pd.Timedelta(hours=7)

        return Candle(
            symbol=normalized_symbol,
            timestamp=timestamp,
            open=to_decimal(ohlcv[1]),
            high=to_decimal(ohlcv[2]),
            low=to_decimal(ohlcv[3]),
            close=to_decimal(ohlcv[4]),
            volume=to_decimal(ohlcv[5]),
            closed=True,  # Historical data is always closed
            timeframe=timeframe,
        )

    @staticmethod
    def normalize_hyperliquid(raw_data) -> MarketEvent:
        """Placeholder for Hyperliquid normalization logic."""
        # TODO: Implement when needed
        raise NotImplementedError("Hyperliquid normalization not yet implemented")
