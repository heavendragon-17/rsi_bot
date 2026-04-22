"""
Core Event Types for RSI Trading Bot
=====================================
All price fields use Decimal for financial precision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


class EventType(Enum):
    """Market data event types."""

    TICK_UPDATE = "TICK_UPDATE"  # Nến đang chạy (Real-time)
    KLINE_CLOSE = "KLINE_CLOSE"  # Nến vừa đóng cửa (Confirmed)


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
    timeframe: str = ""


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
    tp1_price: Decimal | None = None  # R60 level
    tp2_price: Decimal | None = None  # R70 level
    tp3_price: Decimal | None = None  # R80 level

    # SL levels (dual SL system)
    sl_price: Decimal | None = None  # Disaster SL: hard limit order at 3x distance
    soft_sl_price: Decimal | None = None  # Soft SL: candle-close exit level (R40 - buffer)

    # Signal quality classification
    # 1 = optimal (WMA45 in 40-46 range)
    # 2 = acceptable (WMA45 in 30-50 range)
    signal_class: int = 2

    # Lock Profit Level (e.g. 0.2R)
    lock_profit_price: Decimal | None = None

    # Dynamic TP Allocations (e.g. {"TP1": 0.5, "TP2": 1.0})
    # If None, PortfolioManager uses default config
    tp_allocations: dict | None = field(default=None)

    # Indicator snapshot at signal time (rsi_ema9, rsi_wma45, spread, above_ema21)
    indicators: dict[str, float] | None = field(default=None)


@dataclass
class OrderEvent:
    """Order event to be executed by exchange."""

    symbol: str
    order_type: str  # MARKET, LIMIT
    side: str  # BUY, SELL
    amount: Decimal
    price: Decimal | None = None


@dataclass
class TPSLEvent:
    """Take profit or stop loss trigger event."""

    symbol: str
    event_type: str  # TP1, TP2, TP3, SL
    trigger_price: Decimal
    close_percentage: Decimal  # How much of position to close (0.0 - 1.0)
    timestamp: datetime


# ============================================
# Engine Event Types (PR7: Unified Engine)
# ============================================


@dataclass
class TickEvent:
    """Real-time price tick (from WebSocket or historical replay)."""

    symbol: str
    price: Decimal
    timestamp: datetime
    volume: Decimal | None = None


@dataclass
class CandleCloseEvent:
    """
    A candle has closed. Contains full OHLCV Candle data.

    The optional ``df`` field carries a pre-built DataFrame with indicators
    already computed (used by BacktestEventSource). When ``df`` is None the
    Engine is responsible for fetching the DataFrame from its data store.

    Phase 1.1 optimization: ``current_index`` enables zero-copy backtest mode.
    When set, ``df`` is the *full* pre-computed DataFrame (not a slice) and
    ``current_index`` indicates which row is the "current" candle. Strategies
    use ``current_index`` instead of ``df.iloc[-1]``.  When ``current_index``
    is None, behaviour is unchanged (``df`` may be a slice or None).
    """

    candle: Candle
    df: pd.DataFrame | None = None  # type: ignore[type-arg]
    current_index: int | None = None


@dataclass
class EngineStopEvent:
    """Signals the engine to stop processing."""

    reason: str = "normal"


# Union of all engine-level events
EngineEvent = TickEvent | CandleCloseEvent | EngineStopEvent
