"""
Typed action objects returned by Strategy.analyze().
Each action is self-describing and carries all data needed for execution.
Runner reads .actions from AnalysisResult and applies them to Portfolio.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional, Union


# ── Side constants ──────────────────────────────────────────────────
# Use these instead of raw "BUY"/"SELL" strings to avoid typos.
SIDE_BUY = "BUY"    # Long entry / short exit
SIDE_SELL = "SELL"   # Short entry / long exit


def opposite_side(side: str) -> str:
    """Return the opposite side (BUY↔SELL)."""
    return SIDE_BUY if side.upper() == SIDE_SELL else SIDE_SELL


# ── Exit reason constants ───────────────────────────────────────────
EXIT_STOP_LOSS = "STOP_LOSS"
EXIT_SOFT_SL = "SOFT_SL"
EXIT_BREAKEVEN = "BREAKEVEN"
EXIT_LOCK_PROFIT = "LOCK_PROFIT"
EXIT_LIQUIDATION = "LIQUIDATION"
EXIT_TP1 = "TP1"
EXIT_TP2 = "TP2"
EXIT_TP3 = "TP3"
EXIT_MANUAL = "MANUAL"
EXIT_CLOSE_BY_CANDLE_SL = "CLOSE_BY_CANDLE_SL"

# ── Default fee rates (Binance futures) ────────────────────────────
DEFAULT_TAKER_FEE = 0.0005   # 0.05%
DEFAULT_MAKER_FEE = 0.0002   # 0.02%


@dataclass(frozen=True)
class OpenPosition:
    """Open a new position (long or short).

    side = SIDE_BUY  → long entry  (exit orders will be SELL)
    side = SIDE_SELL → short entry (exit orders will be BUY)
    """
    symbol: str
    side: str          # SIDE_BUY for long, SIDE_SELL for short
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
