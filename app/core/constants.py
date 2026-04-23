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

# Per-timeframe RAM cap for the signal-bot multi-TF path.
# Higher resolution keeps more history; lower resolution needs less.
# Keys must be Binance-compatible timeframe strings.
MAX_CANDLES_IN_RAM_PER_TF: dict[str, int] = {
    "1m": 6000,
    "5m": 6000,
    "15m": 6000,
    "1h": 3000,
    "4h": 1500,
    "1d": 500,
}

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

# ── Sim state persistence (survives bot restarts / deploys) ──────────
# JSON snapshot of balance + session-anchor + cumulative fees so a deploy
# doesn't reset the user's running session P&L back to the configured
# initial_balance. Open positions are NOT persisted — they roll over
# naturally via cleanup_on_startup.
SIM_STATE_FILE_PATH = str(_TMP / "rsi_bot_sim_state.json")

# ── Equity curve sampling (Phase 2.2) ─────────────────────────────────
# Adaptive sampling: normal interval, high-res interval, and drawdown threshold
EQUITY_SAMPLE_INTERVAL = 3  # candles between samples (normal mode)
EQUITY_SAMPLE_HIGH_RES = 1  # every candle when drawdown is steep
EQUITY_SAMPLE_LOW_RES = 6  # relaxed interval when flat/steady
EQUITY_DRAWDOWN_THRESHOLD = 2.0  # % drawdown to trigger high-res mode

# ── Concurrency ──────────────────────────────────────────────────────
DEFAULT_MAX_WORKERS = 2  # concurrent backtest jobs
MAX_WORKERS_UPPER_BOUND = 8  # hard cap on concurrent workers

# ── Signal runner ────────────────────────────────────────────────────
# Default age cap for virtual positions before auto-expiry.
SIGNAL_MAX_VP_AGE_CANDLES = 50

# Timeframe string → whole seconds. Used by the exit monitor's age check
# and anywhere else that needs to convert a Binance-style timeframe into
# elapsed time. Keys must match the timeframe strings Binance uses.
TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "1d": 86400,
}
