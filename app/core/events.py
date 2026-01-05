from dataclasses import dataclass
from datetime import datetime

@dataclass
class MarketEvent:
    symbol: str
    timestamp: datetime
    data: dict
    event_type: str = "TICK"

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
