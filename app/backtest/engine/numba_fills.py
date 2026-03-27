"""
Numba JIT-compiled numeric functions for backtest hot paths.

These functions extract the pure numeric logic from FillSimulator and
PortfolioEngine into forms that Numba can compile to machine code.
Fallback to pure-Python if numba is not available.
"""

from __future__ import annotations

import numpy as np

try:
    from numba import njit

    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False

    def njit(func=None, **kwargs):
        """No-op decorator when numba is not installed."""
        if func is not None:
            return func
        return lambda f: f


# ── Fill matching (wick-based) ──────────────────────────────────────
# Order arrays layout: each row is one pending order
# Columns: [trigger_price, limit_price, side_code, type_code, peak_price, callback_rate]
#   side_code:  0=SELL, 1=BUY
#   type_code:  0=stop_market, 1=limit, 2=stop_limit, 3=trailing_stop

SIDE_SELL = 0
SIDE_BUY = 1
TYPE_STOP_MARKET = 0
TYPE_LIMIT = 1
TYPE_STOP_LIMIT = 2
TYPE_TRAILING_STOP = 3


@njit(cache=True)
def check_fills_numeric(
    trigger_prices: np.ndarray,
    limit_prices: np.ndarray,
    side_codes: np.ndarray,
    type_codes: np.ndarray,
    peak_prices: np.ndarray,
    callback_rates: np.ndarray,
    high: float,
    low: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Check which orders trigger against a candle's high/low.

    Returns:
        filled_mask: boolean array — True for orders that triggered
        fill_prices: float array — fill price for each triggered order
        new_peaks:   float array — updated peak prices (for trailing stops)
    """
    n = len(trigger_prices)
    filled_mask = np.zeros(n, dtype=np.bool_)
    fill_prices = np.zeros(n, dtype=np.float64)
    new_peaks = peak_prices.copy()

    for i in range(n):
        tp = trigger_prices[i]
        side = side_codes[i]
        otype = type_codes[i]

        if side == SIDE_SELL:
            if otype == TYPE_STOP_MARKET:
                if low <= tp:
                    filled_mask[i] = True
                    fill_prices[i] = tp
            elif otype == TYPE_LIMIT:
                if high >= tp:
                    filled_mask[i] = True
                    fill_prices[i] = tp
            elif otype == TYPE_STOP_LIMIT:
                if low <= tp:
                    filled_mask[i] = True
                    fill_prices[i] = limit_prices[i] if limit_prices[i] != 0.0 else tp
            elif otype == TYPE_TRAILING_STOP:
                cb = callback_rates[i] if callback_rates[i] != 0.0 else 1.0
                peak = peak_prices[i] if peak_prices[i] != 0.0 else high
                if high > peak:
                    peak = high
                    new_peaks[i] = peak
                trigger_level = peak * (1.0 - cb / 100.0)
                if low <= trigger_level:
                    filled_mask[i] = True
                    fill_prices[i] = trigger_level

        elif side == SIDE_BUY:
            if otype == TYPE_LIMIT:
                if low <= tp:
                    filled_mask[i] = True
                    fill_prices[i] = tp
            elif otype == TYPE_STOP_MARKET:
                if high >= tp:
                    filled_mask[i] = True
                    fill_prices[i] = tp

    return filled_mask, fill_prices, new_peaks


# ── Equity calculation ──────────────────────────────────────────────


@njit(cache=True)
def calculate_equity_numeric(
    balance: float,
    margin_used_total: float,
    position_amounts: np.ndarray,
    entry_prices: np.ndarray,
    current_prices: np.ndarray,
) -> float:
    """Calculate total portfolio equity from positions.

    equity = free_cash + used_margin + sum(unrealized_pnl)
    unrealized_pnl = (current_price - entry_price) * amount
    """
    total_upnl = 0.0
    for i in range(len(position_amounts)):
        amt = position_amounts[i]
        if amt != 0.0:
            total_upnl += (current_prices[i] - entry_prices[i]) * amt
    return balance + margin_used_total + total_upnl
