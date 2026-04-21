"""Unit tests for build_symbol_dispersion — per-symbol cumulative PnL range."""

from datetime import datetime

from app.backtest.engine.portfolio_dispersion import build_symbol_dispersion


class TestDispersion:
    def test_empty_round_trips(self):
        assert build_symbol_dispersion([], [{"date": "2024-01-01", "balance": 1000}], 1000) == []

    def test_empty_equity(self):
        assert build_symbol_dispersion(
            [{"symbol": "BTC", "exit_time": datetime(2024, 1, 1), "pnl": 10}],
            [],
            1000,
        ) == []

    def test_zero_initial(self):
        assert build_symbol_dispersion(
            [{"symbol": "BTC", "exit_time": datetime(2024, 1, 1), "pnl": 10}],
            [{"date": "2024-01-01", "balance": 0}],
            0,
        ) == []

    def test_single_symbol_returns_empty(self):
        rt = [{"symbol": "BTC", "exit_time": datetime(2024, 1, 1), "pnl": 10}]
        equity = [{"date": "2024-01-01", "balance": 1010}]
        assert build_symbol_dispersion(rt, equity, 1000) == []

    def test_multi_symbol_dispersion(self):
        rt = [
            {"symbol": "BTC", "exit_time": datetime(2024, 1, 1), "pnl": 100},
            {"symbol": "ETH", "exit_time": datetime(2024, 1, 1), "pnl": -50},
            {"symbol": "BTC", "exit_time": datetime(2024, 1, 2), "pnl": 50},
        ]
        equity = [
            {"date": "2024-01-01", "balance": 1050},
            {"date": "2024-01-02", "balance": 1100},
        ]
        out = build_symbol_dispersion(rt, equity, 1000)
        assert len(out) == 2
        # Day 1: BTC +10%, ETH -5% → min=-5, max=10
        assert out[0]["min"] == -5.0
        assert out[0]["max"] == 10.0
        # Day 2: BTC +15%, ETH -5% → min=-5, max=15
        assert out[1]["min"] == -5.0
        assert out[1]["max"] == 15.0

    def test_missing_symbol_or_time_skipped(self):
        rt = [
            {"symbol": "", "exit_time": datetime(2024, 1, 1), "pnl": 10},
            {"symbol": "BTC", "exit_time": None, "pnl": 10},
            {"symbol": "BTC", "exit_time": datetime(2024, 1, 1), "pnl": 10},
            {"symbol": "ETH", "exit_time": datetime(2024, 1, 1), "pnl": -10},
        ]
        equity = [{"date": "2024-01-01", "balance": 1000}]
        out = build_symbol_dispersion(rt, equity, 1000)
        assert len(out) == 1
