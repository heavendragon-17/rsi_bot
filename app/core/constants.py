"""
Centralized constants for the RSI bot.

All magic numbers and shared defaults live here.
Import from this module instead of hardcoding values.
"""

from decimal import Decimal

# ── Warmup ──────────────────────────────────────────────────────────
# Number of candles to skip before strategy analysis begins.
WARMUP = 220

# ── Memory limits ───────────────────────────────────────────────────
MAX_CANDLES_IN_RAM = 6000

# ── Fee defaults (Binance futures) ──────────────────────────────────
DEFAULT_TAKER_FEE = 0.0005  # 0.05 %
DEFAULT_MAKER_FEE = 0.0002  # 0.02 %

# Decimal variants for modules that require exact arithmetic.
DEFAULT_TAKER_FEE_DECIMAL = Decimal("0.0005")
DEFAULT_MAKER_FEE_DECIMAL = Decimal("0.0002")
