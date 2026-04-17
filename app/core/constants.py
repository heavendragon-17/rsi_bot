"""
Centralized constants for the RSI bot.

All magic numbers and shared defaults live here.
Import from this module instead of hardcoding values.
"""

import tempfile
from decimal import Decimal
from pathlib import Path

_TMP = Path(tempfile.gettempdir())

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

# ── Bot status file (read by deploy listener) ────────────────────────
STATUS_FILE_PATH = str(_TMP / "rsi_bot_status.json")
DEPLOY_STATE_PATH = str(_TMP / "rsi_bot_deploy_state.json")
FORCE_DEPLOY_FLAG = str(_TMP / "rsi_bot_force_deploy")
CANCEL_DEPLOY_FLAG = str(_TMP / "rsi_bot_cancel_deploy")
STATUS_WRITE_INTERVAL = 30  # seconds

# ── Equity curve sampling (Phase 2.2) ─────────────────────────────────
# Adaptive sampling: normal interval, high-res interval, and drawdown threshold
EQUITY_SAMPLE_INTERVAL = 3  # candles between samples (normal mode)
EQUITY_SAMPLE_HIGH_RES = 1  # every candle when drawdown is steep
EQUITY_SAMPLE_LOW_RES = 6  # relaxed interval when flat/steady
EQUITY_DRAWDOWN_THRESHOLD = 2.0  # % drawdown to trigger high-res mode
