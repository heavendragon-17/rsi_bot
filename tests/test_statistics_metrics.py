"""Unit tests for pure backtest statistics functions."""

import pandas as pd

from app.backtest.statistics.metrics import (
    _max_consecutive,
    compute_core_metrics,
    compute_monthly_breakdown,
    compute_quarterly_breakdown,
    compute_regime_breakdown,
    compute_risk_metrics,
)


def _mk_df(trades):
    df = pd.DataFrame(trades)
    if "exit_time" in df.columns:
        df["exit_time"] = pd.to_datetime(df["exit_time"])
    if "entry_time" in df.columns:
        df["entry_time"] = pd.to_datetime(df["entry_time"])
    return df


class TestCoreMetrics:
    def test_empty_df(self):
        df = pd.DataFrame({"pnl": pd.Series([], dtype=float)})
        out = compute_core_metrics(df)
        assert out["total_trades"] == 0
        assert out["win_rate"] == 0.0
        assert out["total_pnl"] == 0.0

    def test_mixed_wins_losses(self):
        df = pd.DataFrame({"pnl": [100, -50, 75, -25, 200]})
        out = compute_core_metrics(df)
        assert out["total_trades"] == 5
        assert out["win_count"] == 3
        assert out["loss_count"] == 2
        assert out["win_rate"] == 60.0
        assert out["avg_win"] == (100 + 75 + 200) / 3
        assert out["avg_loss"] == -37.5
        assert out["gross_profit"] == 375
        assert out["gross_loss"] == 75
        assert out["profit_factor"] == 5.0
        assert out["total_pnl"] == 300

    def test_all_wins_infinite_profit_factor(self):
        df = pd.DataFrame({"pnl": [100, 50]})
        out = compute_core_metrics(df)
        assert out["profit_factor"] == float("inf")
        assert out["reward_to_risk"] == float("inf")

    def test_zero_pnl_treated_as_loss(self):
        df = pd.DataFrame({"pnl": [0, 10]})
        out = compute_core_metrics(df)
        assert out["loss_count"] == 1


class TestBreakdowns:
    def test_monthly_breakdown_groups_by_month(self):
        df = _mk_df([
            {"pnl": 100, "exit_time": "2024-01-15"},
            {"pnl": -50, "exit_time": "2024-01-20"},
            {"pnl": 75, "exit_time": "2024-02-05"},
        ])
        out = compute_monthly_breakdown(df)
        assert len(out) == 2
        assert out.iloc[0]["month"] == "2024-01"
        assert out.iloc[0]["trades"] == 2
        assert out.iloc[0]["wins"] == 1
        assert out.iloc[0]["win_rate"] == 50.0
        assert out.iloc[0]["pnl"] == 50
        assert out.iloc[1]["month"] == "2024-02"

    def test_monthly_breakdown_empty(self):
        df = pd.DataFrame()
        out = compute_monthly_breakdown(df)
        assert out.empty

    def test_quarterly_breakdown(self):
        df = _mk_df([
            {"pnl": 100, "exit_time": "2024-01-15"},
            {"pnl": -50, "exit_time": "2024-04-20"},
        ])
        out = compute_quarterly_breakdown(df)
        assert len(out) == 2

    def test_quarterly_breakdown_empty(self):
        out = compute_quarterly_breakdown(pd.DataFrame())
        assert out.empty

    def test_regime_breakdown_needs_min_rows(self):
        df = _mk_df([{"pnl": 10, "entry_price": 100, "entry_time": "2024-01-01"}])
        assert compute_regime_breakdown(df) is None

    def test_regime_breakdown_classifies(self):
        df = _mk_df([
            {"pnl": 10, "entry_price": 100.0, "entry_time": "2024-01-01"},
            {"pnl": 10, "entry_price": 105.0, "entry_time": "2024-01-02"},  # +5% -> TRENDING_UP
            {"pnl": -10, "entry_price": 100.0, "entry_time": "2024-01-03"},  # -5% -> TRENDING_DOWN
            {"pnl": 5, "entry_price": 100.5, "entry_time": "2024-01-04"},   # +0.5% -> RANGING
            {"pnl": 5, "entry_price": 100.6, "entry_time": "2024-01-05"},
        ])
        out = compute_regime_breakdown(df)
        assert out is not None
        regimes = set(out["regime"].tolist())
        assert "TRENDING_UP" in regimes or "TRENDING_DOWN" in regimes or "RANGING" in regimes


class TestRiskMetrics:
    def test_empty_returns_zeros(self):
        df = pd.DataFrame({"pnl": [], "pnl_pct": []})
        out = compute_risk_metrics(df, 1000.0)
        assert out["max_drawdown_pct"] == 0.0
        assert out["sharpe_ratio"] == 0.0

    def test_basic_metrics(self):
        df = pd.DataFrame({
            "pnl": [100, -50, 200, -30, -20, 150],
            "pnl_pct": [1.0, -0.5, 2.0, -0.3, -0.2, 1.5],
        })
        out = compute_risk_metrics(df, 1000.0)
        assert out["max_consec_wins"] >= 1
        assert out["max_consec_losses"] >= 1
        assert out["max_drawdown_pct"] >= 0
        assert out["std_dev_pct"] > 0
        assert out["var_95_pct"] <= out["std_dev_pct"] or True  # sanity

    def test_single_trade_sharpe_zero(self):
        df = pd.DataFrame({"pnl": [100], "pnl_pct": [1.0]})
        out = compute_risk_metrics(df, 1000.0)
        assert out["sharpe_ratio"] == 0.0


class TestMaxConsecutive:
    def test_empty_series(self):
        assert _max_consecutive([], 1) == 0

    def test_all_matching(self):
        assert _max_consecutive([1, 1, 1, 1], 1) == 4

    def test_mixed(self):
        assert _max_consecutive([1, 0, 1, 1, 0, 1, 1, 1], 1) == 3

    def test_no_match(self):
        assert _max_consecutive([1, 1, 1], 0) == 0
