"""Position model for portfolio tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime
from typing import Dict, Optional

from app.core.actions import SIDE_BUY, opposite_side


@dataclass
class Position:
    """
    Represents an open position with TP/SL tracking.
    """
    symbol: str
    amount: Decimal
    entry_price: Decimal
    side: str  # SIDE_BUY (Long) or SIDE_SELL (Short)
    timestamp: datetime

    # TP/SL prices (from SignalEvent)
    tp1_price: Optional[Decimal] = None
    tp2_price: Optional[Decimal] = None
    tp3_price: Optional[Decimal] = None
    sl_price: Optional[Decimal] = None
    lock_profit_price: Optional[Decimal] = None
    tp_allocations: Optional[dict] = None

    # Order tracking
    sl_order_id: Optional[str] = None
    tp_order_ids: Dict[str, str] = field(default_factory=dict)  # {"TP1": order_id, ...}

    # TP hit flags
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False

    def is_long(self) -> bool:
        return self.side == SIDE_BUY

    @property
    def exit_side(self) -> str:
        return opposite_side(self.side)
