from app.core.events import MarketEvent, Candle, EventType
from datetime import datetime
import pandas as pd

class DataNormalizer:
    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """
        Normalize symbol to base asset (e.g. BTC/USDT -> BTC, BTCUSDT -> BTC).
        """
        symbol = symbol.upper().replace('/', '')
        # Order matters: longer suffixes first to avoid partial matches (e.g. BUSD matching USD)
        for quote in ['USDT', 'USDC', 'BUSD', 'USD']:
            if symbol.endswith(quote):
                return symbol[:-len(quote)]
        return symbol

    @staticmethod
    def normalize_binance(raw_data) -> MarketEvent:
        """
        Convert raw Binance kline stream format to MarketEvent
        raw_data: {'e': 'kline', 'E': 123456789, 's': 'BTCUSDT', 'k': {...}}
        """
        kline = raw_data['k']
        raw_symbol = raw_data['s']
        symbol = DataNormalizer._normalize_symbol(raw_symbol)
        is_closed = kline['x']
        
        event_type = EventType.KLINE_CLOSE if is_closed else EventType.TICK_UPDATE
        
        candle = Candle(
            symbol=symbol,
            timestamp=pd.to_datetime(kline['t'], unit='ms'),
            open=float(kline['o']),
            high=float(kline['h']),
            low=float(kline['l']),
            close=float(kline['c']),
            volume=float(kline['v']),
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
        Convert CCXT OHLCV list to Candle object
        ohlcv: [timestamp, open, high, low, close, volume]
        """
        normalized_symbol = DataNormalizer._normalize_symbol(symbol)
        timestamp = pd.to_datetime(ohlcv[0], unit='ms')

        return Candle(
            symbol=normalized_symbol,
            timestamp=timestamp,
            open=float(ohlcv[1]),
            high=float(ohlcv[2]),
            low=float(ohlcv[3]),
            close=float(ohlcv[4]),
            volume=float(ohlcv[5]),
            closed=True  # Historical data is always closed
        )
    
    @staticmethod
    def normalize_hyperliquid(raw_data) -> MarketEvent:
        # Placeholder for Hyperliquid normalization logic
        pass
