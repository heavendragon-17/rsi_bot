"""
Risk Management Types
=====================
Core types for strategy-specific risk management.

ExitTrigger: How SL/TP orders are executed
RiskParams: Complete risk configuration per strategy
TPLevel: Take profit level configuration
"""
from enum import Enum
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional


class ExitTrigger(Enum):
    """How exit orders (SL/TP) should be executed."""
    CANDLE_CLOSE = "candle_close"   # Check on candle close, execute market order
    LIMIT_ORDER = "limit_order"     # Place limit order on exchange immediately
    WICK = "wick"                   # Check intra-candle (high/low)


@dataclass
class TPLevel:
    """Take profit level configuration."""
    price_pct: Decimal          # Distance from entry (e.g., 0.01 for 1%)
    size_pct: Decimal           # Portion to close (e.g., 0.33 for 33%)
    trigger: ExitTrigger = ExitTrigger.CANDLE_CLOSE
    executed: bool = False
    
    def __post_init__(self):
        """Ensure Decimal types."""
        if not isinstance(self.price_pct, Decimal):
            self.price_pct = Decimal(str(self.price_pct))
        if not isinstance(self.size_pct, Decimal):
            self.size_pct = Decimal(str(self.size_pct))


@dataclass
class RiskParams:
    """
    Strategy-specific risk parameters.
    
    Each strategy defines its own RiskParams - no config override.
    
    Example for RSI strategy:
        RISK_CONFIG = RiskParams(
            sl_type='percentage',
            sl_value=Decimal('0.02'),  # 2% SL
            sl_trigger=ExitTrigger.CANDLE_CLOSE,
            tp_levels=[
                TPLevel(price_pct=Decimal('0.01'), size_pct=Decimal('0.33')),
                TPLevel(price_pct=Decimal('0.02'), size_pct=Decimal('0.33')),
                TPLevel(price_pct=Decimal('0.03'), size_pct=Decimal('0.34')),
            ],
            tp_trigger=ExitTrigger.CANDLE_CLOSE,
        )
    """
    # Stop Loss configuration
    sl_type: str                    # 'percentage', 'price', 'atr'
    sl_value: Decimal               # Value based on sl_type
    sl_trigger: ExitTrigger         # How SL is executed
    
    # Take Profit configuration
    tp_levels: List[TPLevel] = field(default_factory=list)
    tp_trigger: ExitTrigger = ExitTrigger.CANDLE_CLOSE
    
    # Disaster SL (placed on exchange as backup)
    disaster_sl_multiplier: float = 3.0  # 3x normal SL distance
    
    # Trailing Stop Loss
    trailing_sl: bool = False
    trailing_distance_pct: float = 0.02     # Trail 2% behind max price
    trailing_activation_pct: float = 0.01   # Activate after 1% profit
    
    def __post_init__(self):
        """Ensure Decimal types."""
        if not isinstance(self.sl_value, Decimal):
            self.sl_value = Decimal(str(self.sl_value))
