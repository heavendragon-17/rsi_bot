"""
Centralized constants for the RSI bot.

All magic numbers that were previously scattered across the codebase
are collected here. Import from this module instead of hardcoding values.
"""

# ── Warmup / data limits ─────────────────────────────────────────────
WARMUP = 220                # Candles to skip before strategy analysis begins
MAX_CANDLES_IN_RAM = 6000   # Max candles held per symbol in MarketDataStore

# ── Default fee rates (Binance futures) ──────────────────────────────
DEFAULT_TAKER_FEE = 0.0005  # 0.05%
DEFAULT_MAKER_FEE = 0.0002  # 0.02%
