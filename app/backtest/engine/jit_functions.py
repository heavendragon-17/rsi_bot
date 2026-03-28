"""
Numba JIT-compiled numeric functions for backtest hot paths.
=============================================================
Phase 1.3 optimization: applies @numba.njit to the two most-called
numeric functions in the backtest loop.

1. ``check_fills_jit`` — order vs candle wick comparison (fill matching)
2. ``calculate_equity_jit`` — per-candle equity = balance + margin + unrealized PnL

Both functions operate on pre-extracted float64 arrays, avoiding all Python
object overhead. They are called from their respective callers via thin
wrappers that handle the Decimal ↔ float64 conversion at the boundary.

Graceful degradation: if numba is not installed, the module exports pure-Python
fallbacks with identical signatures.
"""

from __future__ import annotations

import numpy as np

try:
    from numba import njit

    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False

    def njit(*args, **kwargs):  # type: ignore[misc]
        """No-op decorator when numba is unavailable."""
        if args and callable(args[0]):
            return args[0]
        return lambda fn: fn


# ── Order type / side constants for JIT (no strings allowed) ─────────

# Side encoding: 1 = SELL, 2 = BUY
SIDE_SELL_I = np.int8(1)
SIDE_BUY_I = np.int8(2)

# Order type encoding:
OT_STOP_MARKET = np.int8(1)
OT_LIMIT = np.int8(2)
OT_STOP_LIMIT = np.int8(3)
# trailing_stop is not JIT'd (complex peak tracking logic, rare)

SIDE_MAP = {"SELL": SIDE_SELL_I, "BUY": SIDE_BUY_I}
OT_MAP = {
    "stop_market": OT_STOP_MARKET,
    "limit": OT_LIMIT,
    "stop_limit": OT_STOP_LIMIT,
}


# ── 1. Fill matching (JIT) ──────────────────────────────────────────


@njit(cache=True)
def check_fills_jit(
    trigger_prices: np.ndarray,  # float64[N]
    limit_prices: np.ndarray,  # float64[N] (for stop_limit)
    sides: np.ndarray,  # int8[N]
    order_types: np.ndarray,  # int8[N]
    candle_high: float,
    candle_low: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Check which pending orders trigger against a candle's high/low.

    Returns:
        filled: bool[N] — True for orders that triggered.
        fill_prices: float64[N] — fill price for triggered orders (0 otherwise).
    """
    n = len(trigger_prices)
    filled = np.zeros(n, dtype=np.bool_)
    fill_prices = np.zeros(n, dtype=np.float64)

    for i in range(n):
        tp = trigger_prices[i]
        side = sides[i]
        ot = order_types[i]

        if side == SIDE_SELL_I:
            if ot == OT_STOP_MARKET:
                if candle_low <= tp:
                    filled[i] = True
                    fill_prices[i] = tp
            elif ot == OT_LIMIT:
                if candle_high >= tp:
                    filled[i] = True
                    fill_prices[i] = tp
            elif ot == OT_STOP_LIMIT:
                if candle_low <= tp:
                    filled[i] = True
                    fill_prices[i] = limit_prices[i]

        elif side == SIDE_BUY_I:
            if ot == OT_LIMIT:
                if candle_low <= tp:
                    filled[i] = True
                    fill_prices[i] = tp
            elif ot == OT_STOP_MARKET:
                if candle_high >= tp:
                    filled[i] = True
                    fill_prices[i] = tp

    return filled, fill_prices


# ── 2. Equity calculation (JIT) ─────────────────────────────────────


@njit(cache=True)
def calculate_equity_jit(
    position_amounts: np.ndarray,  # float64[S] — signed position sizes
    entry_prices: np.ndarray,  # float64[S]
    current_prices: np.ndarray,  # float64[S]
    margin_used: np.ndarray,  # float64[S]
    balance: float,
) -> float:
    """Calculate total portfolio equity.

    equity = balance + sum(margin_used) + sum(unrealized_pnl)
    unrealized_pnl[i] = (current_price[i] - entry_price[i]) * position_amount[i]
    """
    total_margin = 0.0
    total_upnl = 0.0
    n = len(position_amounts)

    for i in range(n):
        if position_amounts[i] != 0.0:
            total_margin += margin_used[i]
            total_upnl += (current_prices[i] - entry_prices[i]) * position_amounts[i]

    return balance + total_margin + total_upnl
