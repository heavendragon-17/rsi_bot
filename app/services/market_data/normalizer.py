from app.core.events import MarketEvent, Candle, EventType
from datetime import datetime
import pandas as pd

class DataNormalizer:
    @staticmethod
    def normalize_binance(raw_data) -> MarketEvent:
        """
        Convert raw Binance kline stream format to MarketEvent
        raw_data: {'e': 'kline', 'E': 123456789, 's': 'BTCUSDT', 'k': {...}}
        """
        kline = raw_data['k']
        symbol = raw_data['s']
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
    def normalize_hyperliquid(raw_data) -> MarketEvent:
        # Placeholder for Hyperliquid normalization logic
        pass
