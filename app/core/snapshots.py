"""
Read-only snapshots passed to stateless analyze().

PositionSnapshot  — Portfolio provides this; describes current position state.
ContextSnapshot   — Runner stores and passes this; holds strategy state machine
                    data (state phase + active trade metadata).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class PositionSnapshot:
    """Read-only view of current position state from Portfolio."""
    has_position: bool
    symbol: str
    side: str = "BUY"
    entry_price: Decimal = Decimal("0")
    current_sl: Decimal = Decimal("0")
    soft_sl: Optional[Decimal] = None
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    lock_profit_triggered: bool = False
    unrealized_pnl: Optional[Decimal] = None


@dataclass(frozen=True)
class ContextSnapshot:
    """
    Read-only view of strategy state machine + active trade metadata.

    state         — "SCANNING" or "CONFIRMING"
    soft_sl_price — current soft SL price (updated when SL is moved)
    meta          — arbitrary strategy-owned data:
                    entry_price, sl_price, original_soft_sl, disaster_sl_price,
                    tp1/2/3_price, moved_sl_to_entry, pending_candle_sl,
                    lock_profit_price, tp_allocations, etc.
    """
    state: str = "SCANNING"
    soft_sl_price: Optional[Decimal] = None
    meta: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.meta is None:
            object.__setattr__(self, "meta", {})
