"""
Risk Types
==========
Core types for strategy risk configuration per REFACTOR_SPEC.md.
"""
from enum import Enum
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List


class ExitTrigger(Enum):
    """Trigger type for SL/TP exits."""
    CANDLE_CLOSE = "candle_close"  # Check on candle close
    LIMIT_ORDER = "limit_order"    # Place as limit order on exchange
    WICK = "wick"                  # Check intra-candle (wicks)


@dataclass
class TPLevel:
    """Take-profit level configuration."""
    percentage: Decimal      # Price distance as percentage (e.g., Decimal('0.01') for 1%)
    trigger: ExitTrigger = ExitTrigger.LIMIT_ORDER


@dataclass
class RiskParams:
    """Strategy risk parameters."""
    sl_trigger: ExitTrigger
    tp_trigger: ExitTrigger
    sl_distance_pct: Decimal  # SL distance as percentage from entry
    tp_levels: List[TPLevel] = field(default_factory=list)
