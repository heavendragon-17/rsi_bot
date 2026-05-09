"""
Typed action objects returned by Strategy.analyze().
Each action is self-describing and carries all data needed for execution.
Runner reads .actions from AnalysisResult and applies them to Portfolio.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# ── Side constants ──────────────────────────────────────────────────
# Use these instead of raw "BUY"/"SELL" strings to avoid typos.
SIDE_BUY = "BUY"  # Long entry / short exit
SIDE_SELL = "SELL"  # Short entry / long exit


def opposite_side(side: str) -> str:
    """Return the opposite side (BUY↔SELL)."""
    return SIDE_BUY if side.upper() == SIDE_SELL else SIDE_SELL


# ── Exit reason constants ───────────────────────────────────────────
# STOP_LOSS:  exit_reason stamped on a hard stop_market order when it is placed
# SOFT_SL:    signal reason emitted when a candle closes beyond the soft SL level
# MOVED_SL:   fill reason when a stop_market that has been relocated (lock-profit
#             / trailing) triggers — always at-or-above entry by construction
# HARD_SL (string only, see sim fill handler) is the fill reason for an un-moved
# stop_market; it isn't exported as a constant because nothing imports it.
EXIT_STOP_LOSS = "STOP_LOSS"
EXIT_SOFT_SL = "SOFT_SL"
EXIT_MOVED_SL = "MOVED_SL"
EXIT_BREAKEVEN = "BREAKEVEN"
EXIT_LOCK_PROFIT = "LOCK_PROFIT"
EXIT_LIQUIDATION = "LIQUIDATION"
EXIT_TP1 = "TP1"
EXIT_TP2 = "TP2"
EXIT_TP3 = "TP3"
EXIT_MANUAL = "MANUAL"
EXIT_CLOSE_BY_CANDLE_SL = "CLOSE_BY_CANDLE_SL"
EXIT_MAX_HOLDING_PERIOD = "MAX_HOLDING_PERIOD"

# ── Default fee rates (Binance futures) ────────────────────────────
# Canonical values in app.core.constants; re-exported here for compatibility.


@dataclass(frozen=True)
class OpenPosition:
    """Open a new position (long or short).

    side = SIDE_BUY  → long entry  (exit orders will be SELL)
    side = SIDE_SELL → short entry (exit orders will be BUY)
    """

    symbol: str
    side: str  # SIDE_BUY for long, SIDE_SELL for short
    entry_price: Decimal
    sl_price: Decimal  # hard/disaster SL (placed as stop_market on exchange)
    soft_sl_price: Decimal | None
    tp_prices: list[Decimal]  # [tp1, tp2, tp3] — only non-None entries
    tp_allocations: dict | None
    lock_profit_price: Decimal | None
    signal_class: int
    reason: str
    indicators: dict[str, float] | None = None  # rsi_ema9, rsi_wma45, spread, above_ema21


@dataclass(frozen=True)
class ClosePosition:
    """Close the current position (full exit)."""

    symbol: str
    reason: str
    price: Decimal | None = None  # None = market; set for candle-close exits


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
    tp_level: str  # "TP1", "TP2", "TP3"
    price: Decimal
    reason: str
    new_sl_price: Decimal | None = None  # move SL after partial close (e.g. TP1)


@dataclass(frozen=True)
class DoNothing:
    """Explicit no-op. Makes the return type non-optional."""

    pass


# Union type for type checking
Action = OpenPosition | ClosePosition | MoveSL | PartialClose | DoNothing
