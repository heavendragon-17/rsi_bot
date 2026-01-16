from enum import Enum
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

class ExitTrigger(Enum):
    CANDLE_CLOSE = "CANDLE_CLOSE"
    LIMIT_ORDER = "LIMIT_ORDER"
    WICK = "WICK"

@dataclass
class TPLevel:
    price: Decimal
    percentage: Decimal  # 0.0 - 1.0

@dataclass
class RiskParams:
    sl_price: Optional[Decimal]
    tp_levels: List[TPLevel] = field(default_factory=list)
    sl_trigger: ExitTrigger = ExitTrigger.LIMIT_ORDER
    tp_trigger: ExitTrigger = ExitTrigger.WICK
    disaster_sl_price: Optional[Decimal] = None
