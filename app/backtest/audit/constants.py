"""Numeric thresholds and configuration constants for the Phase 1 audit pipeline.

All constants live here per CLAUDE.md's no-magic-numbers rule. Audit test
modules import what they need; never hardcode a threshold inside a test.
"""

from __future__ import annotations

# ── Information Coefficient (information_coefficient.py) ──────────────────────
IC_MIN_ABS = 0.02
IC_MAX_PVALUE = 0.01
IC_HORIZONS = [1, 4, 16, 96]
IC_ROLLING_WINDOW_MONTHS = 6

# ── Bootstrap CI (bootstrap_ci.py) ────────────────────────────────────────────
BOOTSTRAP_REPS = 10_000
BOOTSTRAP_CI_PCT = 95
BOOTSTRAP_SHARPE_LB_MIN = 0.0
BOOTSTRAP_PROFIT_FACTOR_LB_MIN = 1.0

# ── Deflated Sharpe Ratio (deflated_sharpe.py) ────────────────────────────────
DSR_PASS_THRESHOLD = 0.95

# ── Probability of Backtest Overfitting (pbo.py) ──────────────────────────────
PBO_FAIL_THRESHOLD = 0.20
PBO_BLOCK_COUNT = 16

# ── Sanity checks (sanity.py) ─────────────────────────────────────────────────
SANITY_TOP_TRADE_SHARE_MAX = 0.50
SANITY_TOP_TRADE_COUNT = 5
SANITY_COST_STRESS_FEE_MULTIPLIER = 2
SANITY_COST_STRESS_EXTRA_SLIPPAGE_TICKS = 1

# ── Strategy direction flags ──────────────────────────────────────────────────
# Used by the API route to set `single_direction` when building run_audit()
# calls. Not consumed by the audit module itself — placed here so the
# canonical mapping has one home.
STRATEGY_DIRECTION_FLAG = {
    "rsi_no_retest": True,
    "rsi_no_retest_short": True,
    "rsi_no_retest_fade": True,
    "rsi_momentum": True,
    "rsi_wma_retest": False,
}

# Strategy direction side — used by report.py to detect direction-vs-IC
# mismatches. Keys are strategy slugs as stored in the `strategies.name`
# column. "long" / "short" / "both" describe which side the strategy
# trades; mixed-direction strategies map to "both".
STRATEGY_DIRECTION_SIDE = {
    "rsi_no_retest": "long",
    "rsi_no_retest_short": "short",
    "rsi_no_retest_fade": "short",
    "rsi_momentum": "short",
    "rsi_wma_retest": "long",
}

# IC horizon used for direction-mismatch checks (matches the typical
# strategy holding period at the 15m timeframe).
IC_DIRECTION_MISMATCH_HORIZON = 4

# Multi-symbol IC aggregation policy (v1 = MAJORITY).
# TODO(audit-ic-aggregation-v2): make configurable per-strategy or
# per-run. v1 hardcodes majority because most batches are one-strategy
# applied to many symbols and a single-symbol veto is too strict.
IC_AGGREGATE_POLICY = "majority"
