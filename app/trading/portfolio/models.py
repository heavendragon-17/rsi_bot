"""Position model for portfolio tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

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
    tp1_price: Decimal | None = None
    tp2_price: Decimal | None = None
    tp3_price: Decimal | None = None
    sl_price: Decimal | None = None
    lock_profit_price: Decimal | None = None
    tp_allocations: dict | None = None

    # Order tracking
    sl_order_id: str | None = None
    tp_order_ids: dict[str, str] = field(default_factory=dict)  # {"TP1": order_id, ...}

    # TP hit flags
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False

    def is_long(self) -> bool:
        return self.side == SIDE_BUY

    @property
    def exit_side(self) -> str:
        return opposite_side(self.side)
