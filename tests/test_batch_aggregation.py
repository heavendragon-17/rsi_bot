"""Tests for batch_aggregation: portfolio curves + aggregation."""

import pandas as pd

from app.backtest.batch_aggregation import (
    aggregate_batch_results,
    build_batch_portfolio_curves,
)


def _mk_batch_result(symbol, profit, equity=None, round_trips=None, metrics=None):
    return {
        "symbol": symbol,
        "profit": profit,
        "trades": 2,
        "equity_curve": equity or [],
        "round_trips": round_trips if round_trips is not None else [],
        "metrics": metrics or {"win_count": 1, "loss_count": 1, "gross_profit": 100.0, "gross_loss": 50.0},
        "risk_metrics": {"sharpe_ratio": 1.2},
    }


class TestBuildBatchPortfolioCurves:
    def test_empty_returns_empties(self):
        eq, dd, disp, stats = build_batch_portfolio_curves([], 1000)
        assert eq == [] and dd == [] and disp == []

    def test_zero_capital_skips_symbol(self):
        r = _mk_batch_result("BTC", 100, equity=[{"date": "2024-01-01", "balance": 1100}])
        eq, dd, disp, _ = build_batch_portfolio_curves([r], 0)
        assert eq == []

    def test_multi_symbol_combines(self):
        r1 = _mk_batch_result("BTC", 100, equity=[
            {"date": "2024-01-01", "balance": 1100},
            {"date": "2024-01-02", "balance": 1200},
        ])
        r2 = _mk_batch_result("ETH", -50, equity=[
            {"date": "2024-01-01", "balance": 950},
            {"date": "2024-01-02", "balance": 900},
        ])
        eq, dd, disp, _ = build_batch_portfolio_curves([r1, r2], 1000)
        assert len(eq) == 2
        assert len(disp) == 2
        # Avg of +10% and -5% = +2.5% on Day 1
        assert 1020 < eq[0]["balance"] < 1030

    def test_time_key_fallback(self):
        # Equity curve with "time" key instead of "date"
        r = _mk_batch_result("BTC", 100, equity=[
            {"time": "2024-01-01", "balance": 1100},
        ])
        eq, _, _, _ = build_batch_portfolio_curves([r], 1000)
        assert len(eq) == 1

    def test_forward_fill_after_last(self):
        r1 = _mk_batch_result("BTC", 100, equity=[
            {"date": "2024-01-01", "balance": 1100},
        ])
        r2 = _mk_batch_result("ETH", -50, equity=[
            {"date": "2024-01-01", "balance": 950},
            {"date": "2024-01-02", "balance": 900},
        ])
        eq, _, _, _ = build_batch_portfolio_curves([r1, r2], 1000)
        # On Day 2 BTC is forward-filled at its last value (1100)
        assert len(eq) == 2


class TestAggregateBatchResults:
    def test_empty_returns_defaults(self):
        out = aggregate_batch_results([], 1000)
        assert out["net_profit"] == 0
        assert out["metrics"] == {}

    def test_aggregates_profits_and_metrics(self):
        batch = [
            _mk_batch_result("BTC", 100, equity=[{"date": "2024-01-01", "balance": 1100}]),
            _mk_batch_result("ETH", -30, equity=[{"date": "2024-01-01", "balance": 970}]),
        ]
        out = aggregate_batch_results(batch, 1000)
        assert out["net_profit"] == 70
        assert out["metrics"]["total_trades"] == 4
        assert out["metrics"]["win_count"] == 2

    def test_round_trips_as_dataframe(self):
        rt_df = pd.DataFrame([{"pnl": 10}, {"pnl": -5}])
        batch = [_mk_batch_result("BTC", 10, round_trips=rt_df)]
        out = aggregate_batch_results(batch, 1000)
        assert len(out["round_trips"]) == 2
        assert out["round_trips"][0]["symbol"] == "BTC"

    def test_round_trips_as_list(self):
        rt = [{"pnl": 5}, {"pnl": -5, "symbol": "OTHER"}]
        batch = [_mk_batch_result("BTC", 10, round_trips=rt)]
        out = aggregate_batch_results(batch, 1000)
        assert len(out["round_trips"]) == 2
        assert out["round_trips"][0]["symbol"] == "BTC"
        # Existing symbol preserved
        assert out["round_trips"][1]["symbol"] == "OTHER"
