"""
Pure metric computation functions for backtest statistical analysis.

All functions take a DataFrame of round-trip trades and return dicts or DataFrames.
No I/O or side effects — purely computational.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ── Core Metrics ──────────────────────────────────────────────────────────────


def compute_core_metrics(df: pd.DataFrame) -> dict:
    """Win rate, EV, reward-to-risk, profit factor, expectancy."""
    total = len(df)
    wins = df[df["pnl"] > 0]
    losses = df[df["pnl"] <= 0]

    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total * 100) if total > 0 else 0.0

    avg_win = float(wins["pnl"].mean()) if win_count > 0 else 0.0
    avg_loss = float(losses["pnl"].mean()) if loss_count > 0 else 0.0

    # EV = (win_rate * avg_win) - (loss_rate * |avg_loss|)
    loss_rate = 1 - (win_rate / 100)
    ev_per_trade = (win_rate / 100 * avg_win) + (loss_rate * avg_loss)

    # Reward-to-Risk = avg_win / |avg_loss|
    reward_to_risk = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

    gross_profit = float(wins["pnl"].sum()) if win_count > 0 else 0.0
    gross_loss = abs(float(losses["pnl"].sum())) if loss_count > 0 else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    return {
        "total_trades": total,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "ev_per_trade": ev_per_trade,
        "reward_to_risk": reward_to_risk,
        "profit_factor": profit_factor,
        "expectancy": ev_per_trade,
        "total_pnl": float(df["pnl"].sum()),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
    }


# ── Time-Period Breakdowns ────────────────────────────────────────────────────


def compute_monthly_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Win rate and PnL grouped by calendar month."""
    if df.empty or "exit_time" not in df.columns:
        return pd.DataFrame(columns=["month", "trades", "wins", "win_rate", "pnl"])

    tmp = df.copy()
    tmp["_month"] = tmp["exit_time"].dt.to_period("M")

    rows = []
    for period, grp in tmp.groupby("_month", sort=True):
        wins = int((grp["pnl"] > 0).sum())
        total = len(grp)
        rows.append(
            {
                "month": str(period),
                "trades": total,
                "wins": wins,
                "win_rate": (wins / total * 100) if total > 0 else 0.0,
                "pnl": float(grp["pnl"].sum()),
            }
        )
    return pd.DataFrame(rows)


def compute_quarterly_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Win rate and PnL grouped by calendar quarter."""
    if df.empty or "exit_time" not in df.columns:
        return pd.DataFrame(columns=["quarter", "trades", "wins", "win_rate", "pnl"])

    tmp = df.copy()
    tmp["_quarter"] = tmp["exit_time"].dt.to_period("Q")

    rows = []
    for period, grp in tmp.groupby("_quarter", sort=True):
        wins = int((grp["pnl"] > 0).sum())
        total = len(grp)
        rows.append(
            {
                "quarter": str(period),
                "trades": total,
                "wins": wins,
                "win_rate": (wins / total * 100) if total > 0 else 0.0,
                "pnl": float(grp["pnl"].sum()),
            }
        )
    return pd.DataFrame(rows)


def compute_regime_breakdown(df: pd.DataFrame) -> pd.DataFrame | None:
    """Classify trades into market regimes based on entry-to-exit price movement.

    Regime heuristic (per-trade):
      - TRENDING UP: entry_price rose >1% from 10 candles prior (approximated by
        comparing each trade's entry price to the previous trade's entry price)
      - TRENDING DOWN: entry_price fell >1%
      - RANGING: otherwise

    Returns None if insufficient data for meaningful regime classification.
    """
    if len(df) < 5 or "entry_price" not in df.columns:
        return None

    tmp = df.copy().sort_values("entry_time").reset_index(drop=True)
    prev_price = tmp["entry_price"].shift(1)
    pct_change = (tmp["entry_price"] - prev_price) / prev_price * 100

    conditions = [pct_change > 1.0, pct_change < -1.0]
    choices = ["TRENDING_UP", "TRENDING_DOWN"]
    tmp["regime"] = np.select(conditions, choices, default="RANGING")
    # First trade has no prior reference
    tmp.loc[0, "regime"] = "RANGING"

    rows = []
    for regime, grp in tmp.groupby("regime", sort=False):
        wins = int((grp["pnl"] > 0).sum())
        total = len(grp)
        rows.append(
            {
                "regime": regime,
                "trades": total,
                "wins": wins,
                "win_rate": (wins / total * 100) if total > 0 else 0.0,
                "pnl": float(grp["pnl"].sum()),
            }
        )
    return pd.DataFrame(rows)


# ── Risk Metrics ──────────────────────────────────────────────────────────────


def compute_risk_metrics(df: pd.DataFrame, initial_balance: float) -> dict:
    """Max consecutive losses, max drawdown, std dev, Sharpe, Sortino, VaR."""
    zeros = {
        "max_consec_losses": 0,
        "max_consec_wins": 0,
        "max_drawdown_pct": 0.0,
        "max_drawdown_value": 0.0,
        "std_dev_pct": 0.0,
        "sharpe_ratio": 0.0,
        "sortino_ratio": 0.0,
        "var_95_pct": 0.0,
    }
    if df.empty:
        return zeros

    # Consecutive wins/losses
    is_win = (df["pnl"] > 0).astype(int)
    max_consec_wins = _max_consecutive(is_win, 1)
    max_consec_losses = _max_consecutive(is_win, 0)

    # Equity curve → drawdown
    equity = [initial_balance]
    for pnl in df["pnl"]:
        equity.append(equity[-1] + pnl)

    peak = equity[0]
    max_dd = max_dd_val = 0.0
    for val in equity:
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
            max_dd_val = peak - val

    # Return distribution
    returns_pct = df["pnl_pct"].values
    std_dev = float(np.std(returns_pct, ddof=1)) if len(returns_pct) > 1 else 0.0
    mean_ret = float(np.mean(returns_pct))

    sharpe = mean_ret / std_dev if std_dev > 0 else 0.0

    neg_returns = returns_pct[returns_pct < 0]
    downside_std = float(np.std(neg_returns, ddof=1)) if len(neg_returns) > 1 else 0.0
    sortino = mean_ret / downside_std if downside_std > 0 else 0.0

    var_95 = float(np.percentile(returns_pct, 5)) if len(returns_pct) >= 5 else float(min(returns_pct))

    return {
        "max_consec_losses": max_consec_losses,
        "max_consec_wins": max_consec_wins,
        "max_drawdown_pct": max_dd * 100,
        "max_drawdown_value": max_dd_val,
        "std_dev_pct": std_dev,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "var_95_pct": var_95,
    }


def _max_consecutive(series, value: int) -> int:
    """Count the longest streak of `value` in a series."""
    max_count = current = 0
    for v in series:
        if v == value:
            current += 1
            max_count = max(max_count, current)
        else:
            current = 0
    return max_count
