"""Tests for trade-level IC computation.

Five tests:
  1. test_realized_ic_on_synthetic_data    — known Spearman, pure computation
  2. test_fwd_ic_on_synthetic_data         — known Spearman, fwd-return variant
  3. test_returns_none_below_min_trades    — 10 trades → None
  4. test_reproduces_phase2_eth_finding    — regression: ETH run 35 IC ≈ +0.093
  5. test_reproduces_phase2_arb_finding    — regression: ARB run 35 IC ≈ -0.014
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pandas as pd
import pytest
from scipy import stats

from app.backtest.audit.constants import MIN_TRADES_FOR_TRADE_LEVEL_IC
from app.backtest.audit.information_coefficient import (
    TradeLevelICResult,
    compute_trade_level_fwd_ic,
    compute_trade_level_realized_ic,
)
from app.backtest.audit.signal_panel import SignalPanel
from app.backtest.audit.trade_log import TradeLog
from app.core.actions import SIDE_BUY


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_signal_panel(rsi_values: list[float], fwd_values: list[float]) -> SignalPanel:
    """Build a minimal SignalPanel with `rsi_14` and `fwd_logret_4` columns."""
    n = len(rsi_values)
    timestamps = [datetime(2024, 1, 1) + timedelta(minutes=15 * i) for i in range(n)]
    df = pd.DataFrame(
        {
            "close": [100.0] * n,
            "rsi_14": rsi_values,
            "rsi_ema9": [50.0] * n,
            "rsi_wma45": [50.0] * n,
            "fwd_logret_1": fwd_values,
            "fwd_logret_4": fwd_values,
            "fwd_logret_16": fwd_values,
            "fwd_logret_96": fwd_values,
        },
        index=pd.DatetimeIndex(timestamps),
    )
    return SignalPanel(df=df, symbol="TEST/USDT", timeframe="15m")


def _make_trade_log(
    rsi_values: list[float],
    ret_values: list[float],
    symbol: str = "TEST/USDT",
    side: str = SIDE_BUY,
    panel: SignalPanel | None = None,
) -> TradeLog:
    """Build a TradeLog whose entry_time lines up with the panel timestamps."""
    n = len(rsi_values)
    if panel is not None:
        timestamps = list(panel.df.index[:n])
    else:
        timestamps = [datetime(2024, 1, 1) + timedelta(minutes=15 * i) for i in range(n)]

    df = pd.DataFrame(
        {
            "entry_time": pd.DatetimeIndex(timestamps),
            "exit_time": pd.DatetimeIndex(
                [t + timedelta(hours=1) for t in timestamps]
            ),
            "side": [side] * n,
            "symbol": [symbol] * n,
            "entry_price": [100.0] * n,
            "exit_price": [101.0] * n,
            "qty": [1.0] * n,
            "ret_pct": ret_values,
            "ret_abs": ret_values,
            "holding_hours": [1.0] * n,
            "exit_reason": ["TP1"] * n,
            "run_id": [99] * n,
        }
    )
    return TradeLog(df=df, run_id=99, dropped_open_count=0)


# ── tests ─────────────────────────────────────────────────────────────────────


def test_realized_ic_on_synthetic_data():
    """Spearman(RSI@entry, ret_pct) must match scipy.stats.spearmanr directly."""
    import random

    random.seed(42)
    n = 60
    rsi_vals = [random.uniform(20, 80) for _ in range(n)]
    # ret positively correlated with RSI so we get a meaningful IC
    ret_vals = [r * 0.001 + random.uniform(-0.005, 0.005) for r in rsi_vals]

    panel = _make_signal_panel(rsi_vals, ret_vals)
    tl = _make_trade_log(rsi_vals, ret_vals, panel=panel)

    result = compute_trade_level_realized_ic(
        trade_log=tl, signal_panel=panel, symbol="TEST/USDT", side=SIDE_BUY,
    )

    assert result is not None
    assert isinstance(result, TradeLevelICResult)
    assert result.sample_type == "realized"
    assert result.n_trades == n
    assert result.horizon is None

    expected_ic, expected_p = stats.spearmanr(rsi_vals, ret_vals)
    assert abs(result.ic - float(expected_ic)) < 1e-9
    assert abs(result.p_value - float(expected_p)) < 1e-9


def test_fwd_ic_on_synthetic_data():
    """Spearman(RSI@entry, fwd_logret_4) must match scipy.stats.spearmanr directly."""
    import random

    random.seed(7)
    n = 50
    rsi_vals = [random.uniform(30, 70) for _ in range(n)]
    fwd_vals = [random.uniform(-0.02, 0.02) for _ in range(n)]

    panel = _make_signal_panel(rsi_vals, fwd_vals)
    tl = _make_trade_log(rsi_vals, fwd_vals, panel=panel)

    result = compute_trade_level_fwd_ic(
        trade_log=tl, signal_panel=panel, symbol="TEST/USDT", horizon=4,
    )

    assert result is not None
    assert result.sample_type == "fwd"
    assert result.horizon == 4
    assert result.n_trades == n

    expected_ic, expected_p = stats.spearmanr(rsi_vals, fwd_vals)
    assert abs(result.ic - float(expected_ic)) < 1e-9
    assert abs(result.p_value - float(expected_p)) < 1e-9


def test_returns_none_below_min_trades():
    """Fewer than MIN_TRADES_FOR_TRADE_LEVEL_IC (30) trades → None."""
    n = MIN_TRADES_FOR_TRADE_LEVEL_IC - 1  # 29 trades
    rsi_vals = [float(i) for i in range(n)]
    ret_vals = [0.001 * i for i in range(n)]

    panel = _make_signal_panel(rsi_vals, ret_vals)
    tl = _make_trade_log(rsi_vals, ret_vals, panel=panel)

    realized = compute_trade_level_realized_ic(
        trade_log=tl, signal_panel=panel, symbol="TEST/USDT", side=SIDE_BUY,
    )
    fwd = compute_trade_level_fwd_ic(
        trade_log=tl, signal_panel=panel, symbol="TEST/USDT",
    )

    assert realized is None
    assert fwd is None


@pytest.mark.slow
def test_reproduces_phase2_eth_finding():
    """Regression: ETH/USDT trade-realized IC on run 35 ≈ +0.093 (within 0.01)."""
    from app.backtest.audit.signal_panel import build_signal_panel
    from app.backtest.audit.trade_log import build_trade_log

    tl = build_trade_log(35)
    panel = build_signal_panel("ETH/USDT", "15m")

    result = compute_trade_level_realized_ic(
        trade_log=tl, signal_panel=panel, symbol="ETH/USDT", side=SIDE_BUY,
    )

    assert result is not None, "ETH/USDT has 366 trades — should not be None"
    assert abs(result.ic - 0.093) <= 0.01, (
        f"ETH trade-realized IC {result.ic:.4f} deviates from Phase 2 baseline "
        f"0.093 by more than 0.01"
    )
    assert not math.isnan(result.p_value)
    assert result.n_trades >= 30


@pytest.mark.slow
def test_reproduces_phase2_arb_finding():
    """Regression: ARB/USDT trade-realized IC on run 35 ≈ -0.014 (within 0.01)."""
    from app.backtest.audit.signal_panel import build_signal_panel
    from app.backtest.audit.trade_log import build_trade_log

    tl = build_trade_log(35)
    panel = build_signal_panel("ARB/USDT", "15m")

    result = compute_trade_level_realized_ic(
        trade_log=tl, signal_panel=panel, symbol="ARB/USDT", side=SIDE_BUY,
    )

    assert result is not None, "ARB/USDT has 242 trades — should not be None"
    assert abs(result.ic - (-0.014)) <= 0.01, (
        f"ARB trade-realized IC {result.ic:.4f} deviates from Phase 2 baseline "
        f"-0.014 by more than 0.01"
    )
    assert not math.isnan(result.p_value)
    assert result.n_trades >= 30
