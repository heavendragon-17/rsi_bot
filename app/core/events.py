from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

class EventType(Enum):
    TICK_UPDATE = "TICK_UPDATE"   # Nến đang chạy (Real-time)
    KLINE_CLOSE = "KLINE_CLOSE"   # Nến vừa đóng cửa (Confirmed)

@dataclass
class Candle:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    closed: bool

@dataclass
class MarketEvent:
    type: EventType
    exchange: str
    payload: Candle
    received_at: datetime = field(default_factory=datetime.now)

@dataclass
class SignalEvent:
    symbol: str
    signal_type: str # BUY, SELL
    price: float
    timestamp: datetime
    reason: str = ""

@dataclass
class OrderEvent:
    symbol: str
    order_type: str # MARKET, LIMIT
    side: str # BUY, SELL
    amount: float
    price: float = None
