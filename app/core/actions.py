"""
Typed action objects returned by Strategy.analyze().
Each action is self-describing and carries all data needed for execution.
Runner reads .actions from AnalysisResult and applies them to Portfolio.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional, Union


@dataclass(frozen=True)
class OpenPosition:
    """Open a new position (long or short).

    side = "BUY"  → long entry  (exit orders will be SELL)
    side = "SELL" → short entry (exit orders will be BUY)
    """
    symbol: str
    side: str          # "BUY" for long, "SELL" for short
    entry_price: Decimal
    sl_price: Decimal  # hard/disaster SL (placed as stop_market on exchange)
    soft_sl_price: Optional[Decimal]
    tp_prices: List[Decimal]       # [tp1, tp2, tp3] — only non-None entries
    tp_allocations: Optional[dict]
    lock_profit_price: Optional[Decimal]
    signal_class: int
    reason: str


@dataclass(frozen=True)
class ClosePosition:
    """Close the current position (full exit)."""
    symbol: str
    reason: str
    price: Optional[Decimal] = None  # None = market; set for candle-close exits


@dataclass(frozen=True)
class MoveSL:
    """Move the stop loss to a new price level."""
    symbol: str
    new_sl_price: Decimal
    reason: str


@dataclass(frozen=True)
class PartialClose:
    """Partially close position at a TP level."""
    symbol: str
    tp_level: str           # "TP1", "TP2", "TP3"
    price: Decimal
    reason: str
    new_sl_price: Optional[Decimal] = None  # move SL after partial close (e.g. TP1)


@dataclass(frozen=True)
class DoNothing:
    """Explicit no-op. Makes the return type non-optional."""
    pass


# Union type for type checking
Action = Union[OpenPosition, ClosePosition, MoveSL, PartialClose, DoNothing]
