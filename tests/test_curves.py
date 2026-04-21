"""Unit tests for equity / drawdown curve builders."""

from datetime import datetime

from app.backtest.engine.curves import (
    build_drawdown_curve_dated,
    build_equity_curve_dated,
    calculate_portfolio_drawdown,
)


class TestEquityCurve:
    def test_empty_trades(self):
        curve = build_equity_curve_dated([], 1000.0)
        assert curve == []

    def test_cumulative_balance(self):
        trades = [
            {"pnl": 100, "exit_time": datetime(2024, 1, 1)},
            {"pnl": -50, "exit_time": datetime(2024, 1, 2)},
            {"pnl": 25, "exit_time": datetime(2024, 1, 3)},
        ]
        curve = build_equity_curve_dated(trades, 1000.0)
        assert len(curve) == 3
        assert curve[0]["balance"] == 1100.0
        assert curve[1]["balance"] == 1050.0
        assert curve[2]["balance"] == 1075.0
        assert curve[0]["date"] == "2024-01-01T00:00:00"

    def test_missing_pnl_treated_as_zero(self):
        trades = [{"pnl": None, "exit_time": datetime(2024, 1, 1)}]
        curve = build_equity_curve_dated(trades, 500.0)
        assert curve[0]["balance"] == 500.0

    def test_exit_time_as_string(self):
        trades = [{"pnl": 10, "exit_time": "2024-01-01"}]
        curve = build_equity_curve_dated(trades, 100)
        assert curve[0]["date"] == "2024-01-01"

    def test_exit_time_none(self):
        trades = [{"pnl": 10}]
        curve = build_equity_curve_dated(trades, 100)
        assert curve[0]["date"] == ""


class TestDrawdownCurve:
    def test_builds_drawdown_points(self):
        equity = [
            {"date": "2024-01-01", "balance": 1100},
            {"date": "2024-01-02", "balance": 1000},
            {"date": "2024-01-03", "balance": 1200},
        ]
        dd = build_drawdown_curve_dated(equity, 1000.0)
        assert len(dd) == 3
        assert dd[0]["drawdown"] == 0.0  # balance above peak
        # peak 1100, balance 1000 -> dd = 100/1100 = 9.09...%
        assert abs(dd[1]["drawdown"] - 9.0909) < 0.01
        # new peak
        assert dd[2]["drawdown"] == 0.0


class TestPortfolioDrawdown:
    def test_empty_returns_zeros(self):
        result = calculate_portfolio_drawdown([], 1000.0)
        assert result["max_drawdown_pct"] == 0
        assert result["drawdown_curve"] == []

    def test_tracks_max_and_avg(self):
        equity = [
            {"date": "2024-01-01", "balance": 1100},
            {"date": "2024-01-02", "balance": 900},
            {"date": "2024-01-03", "balance": 1000},
            {"date": "2024-01-04", "balance": 1300},
            {"date": "2024-01-05", "balance": 1200},
        ]
        result = calculate_portfolio_drawdown(equity, 1000.0)
        # Peak went 1000 -> 1100 (peak), down to 900 (dd 200/1100 = 18.18%)
        assert result["max_drawdown_pct"] > 15
        assert result["max_drawdown_value"] > 0
        assert len(result["drawdown_curve"]) == 5
        assert result["max_dd_duration"] >= 1
        assert result["avg_drawdown_pct"] > 0

    def test_monotonic_equity_no_drawdown(self):
        equity = [
            {"date": "2024-01-01", "balance": 1100},
            {"date": "2024-01-02", "balance": 1200},
        ]
        result = calculate_portfolio_drawdown(equity, 1000.0)
        assert result["max_drawdown_pct"] == 0
        assert result["avg_drawdown_pct"] == 0
