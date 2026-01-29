"""
Core Event Types for RSI Trading Bot
=====================================
All price fields use Decimal for financial precision.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class EventType(Enum):
    """Market data event types."""
    TICK_UPDATE = "TICK_UPDATE"   # Nến đang chạy (Real-time)
    KLINE_CLOSE = "KLINE_CLOSE"   # Nến vừa đóng cửa (Confirmed)


@dataclass
class Candle:
    """
    OHLCV candle data with Decimal precision for price fields.
    Prevents floating-point errors in financial calculations.
    """
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    closed: bool


@dataclass
class MarketEvent:
    """Event emitted when market data is received."""
    type: EventType
    exchange: str
    payload: Candle
    received_at: datetime = field(default_factory=datetime.now)


@dataclass
class SignalEvent:
    """
    Signal emitted by strategy layer.
    Contains entry information and TP/SL metadata.
    
    LONG ONLY strategy - signal_type is always 'BUY' for entry.
    """
    symbol: str
    signal_type: str  # BUY for entry, SELL for exit
    price: Decimal
    timestamp: datetime
    reason: str = ""
    
    # TP levels (prices calculated from RSI levels)
    tp1_price: Optional[Decimal] = None  # R60 level
    tp2_price: Optional[Decimal] = None  # R70 level
    tp3_price: Optional[Decimal] = None  # R80 level
    
    # SL levels (dual SL system)
    sl_price: Optional[Decimal] = None        # Disaster SL: hard limit order at 3x distance
    soft_sl_price: Optional[Decimal] = None   # Soft SL: candle-close exit level (R40 - buffer)
    lock_profit_price: Optional[Decimal] = None # Price to move SL to after TP1 (e.g. 0.2R)
    
    # Signal quality classification
    # 1 = optimal (WMA45 in 40-46 range)
    # 2 = acceptable (WMA45 in 30-50 range)
    signal_class: int = 2


@dataclass
class OrderEvent:
    """Order event to be executed by exchange."""
    symbol: str
    order_type: str  # MARKET, LIMIT
    side: str        # BUY, SELL
    amount: Decimal
    price: Optional[Decimal] = None


@dataclass 
class TPSLEvent:
    """Take profit or stop loss trigger event."""
    symbol: str
    event_type: str  # TP1, TP2, TP3, SL
    trigger_price: Decimal
    close_percentage: Decimal  # How much of position to close (0.0 - 1.0)
    timestamp: datetime
