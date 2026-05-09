"""Shared TradeState for strategies that track position state in ContextSnapshot.meta."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class TradeState:
    """Typed trade state stored in ContextSnapshot.meta.

    Replaces raw dict access with explicit fields to prevent typos
    and make the meta schema discoverable.
    """

    entry_price: Decimal | None = None
    sl_price: Decimal | None = None
    soft_sl_price: Decimal | None = None
    original_soft_sl: Decimal | None = None
    disaster_sl_price: Decimal | None = None
    lock_profit_price: Decimal | None = None
    move_trigger: Decimal | None = None
    moved_sl_to_entry: bool = False
    pending_candle_sl: bool = False
    crossover_detected: bool = False
    tp_allocations: dict | None = field(default_factory=dict)
    bars_held: int = 0

    def to_meta(self) -> dict[str, Any]:
        """Serialize to a plain dict for ContextSnapshot.meta."""
        return {
            "entry_price": self.entry_price,
            "sl_price": self.sl_price,
            "soft_sl_price": self.soft_sl_price,
            "original_soft_sl": self.original_soft_sl,
            "disaster_sl_price": self.disaster_sl_price,
            "lock_profit_price": self.lock_profit_price,
            "move_trigger": self.move_trigger,
            "moved_sl_to_entry": self.moved_sl_to_entry,
            "pending_candle_sl": self.pending_candle_sl,
            "crossover_detected": self.crossover_detected,
            "tp_allocations": self.tp_allocations,
            "bars_held": self.bars_held,
        }

    @classmethod
    def from_meta(cls, meta: dict[str, Any] | None) -> TradeState:
        """Deserialize from ContextSnapshot.meta dict."""
        if not meta:
            return cls()
        return cls(
            entry_price=meta.get("entry_price"),
            sl_price=meta.get("sl_price"),
            soft_sl_price=meta.get("soft_sl_price"),
            original_soft_sl=meta.get("original_soft_sl"),
            disaster_sl_price=meta.get("disaster_sl_price"),
            lock_profit_price=meta.get("lock_profit_price"),
            move_trigger=meta.get("move_trigger"),
            moved_sl_to_entry=bool(meta.get("moved_sl_to_entry", False)),
            pending_candle_sl=bool(meta.get("pending_candle_sl", False)),
            crossover_detected=bool(meta.get("crossover_detected", False)),
            tp_allocations=meta.get("tp_allocations"),
            bars_held=int(meta.get("bars_held", 0) or 0),
        )
