"""
Layer 1: Data Ingestion - DataNormalizer
=========================================
Normalizes raw exchange data into Candle objects with Decimal precision.
"""
from app.core.events import MarketEvent, Candle, EventType
from datetime import datetime
from decimal import Decimal
import pandas as pd


class DataNormalizer:
    """
    Normalizes raw exchange data to standardized Candle objects.
    All prices are converted to Decimal for financial precision.
    """
    
    @staticmethod
    def _to_decimal(value) -> Decimal:
        """
        Convert any numeric value to Decimal for price precision.
        Handles strings, floats, ints, and existing Decimals.
        """
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """
        Normalize symbol to base asset (e.g. BTC/USDT -> BTC, BTCUSDT -> BTC).
        """
        symbol = symbol.upper().replace('/', '')
        # Order matters: longer suffixes first to avoid partial matches
        for quote in ['USDT', 'USDC', 'BUSD', 'USD']:
            if symbol.endswith(quote):
                return symbol[:-len(quote)]
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
        kline = raw_data['k']
        raw_symbol = raw_data['s']
        symbol = DataNormalizer._normalize_symbol(raw_symbol)
        is_closed = kline['x']
        
        event_type = EventType.KLINE_CLOSE if is_closed else EventType.TICK_UPDATE
        
        candle = Candle(
            symbol=symbol,
            timestamp=pd.to_datetime(kline['t'], unit='ms'),
            open=DataNormalizer._to_decimal(kline['o']),
            high=DataNormalizer._to_decimal(kline['h']),
            low=DataNormalizer._to_decimal(kline['l']),
            close=DataNormalizer._to_decimal(kline['c']),
            volume=DataNormalizer._to_decimal(kline['v']),
            closed=is_closed
        )
        
        return MarketEvent(
            type=event_type,
            exchange="binance",
            payload=candle
        )

    @staticmethod
    def normalize_ccxt(symbol: str, ohlcv: list) -> Candle:
        """
        Convert CCXT OHLCV list to Candle object.
        
        Args:
            symbol: Trading pair symbol (e.g. 'BTC/USDT')
            ohlcv: [timestamp, open, high, low, close, volume]
        
        Returns:
            Candle with Decimal price fields
        """
        normalized_symbol = DataNormalizer._normalize_symbol(symbol)
        timestamp = pd.to_datetime(ohlcv[0], unit='ms')

        return Candle(
            symbol=normalized_symbol,
            timestamp=timestamp,
            open=DataNormalizer._to_decimal(ohlcv[1]),
            high=DataNormalizer._to_decimal(ohlcv[2]),
            low=DataNormalizer._to_decimal(ohlcv[3]),
            close=DataNormalizer._to_decimal(ohlcv[4]),
            volume=DataNormalizer._to_decimal(ohlcv[5]),
            closed=True  # Historical data is always closed
        )
    
    @staticmethod
    def normalize_hyperliquid(raw_data) -> MarketEvent:
        """Placeholder for Hyperliquid normalization logic."""
        # TODO: Implement when needed
        pass
