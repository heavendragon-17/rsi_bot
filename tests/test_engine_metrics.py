"""Tests for BacktestEngine metric computation functions."""

import pandas as pd

from app.backtest.engine.metrics import (
    _get_highest_exit_reason,
    build_round_trips,
    calculate_drawdown,
    calculate_metrics,
    calculate_monthly_returns,
    calculate_risk_metrics,
    create_round_trip,
    max_consecutive,
)


def _entry(side="BUY", price=100.0, amount=1.0, symbol="BTC", time="2024-01-01"):
    return {
        "symbol": symbol,
        "side": side,
        "price": price,
        "amount": amount,
        "time": time,
        "margin": 100.0,
        "notional": 100.0,
        "leverage": 1,
        "info": {},
    }


def _exit(price=110, amount=1.0, pnl=10, reason="TP1", time="2024-01-01T01:00:00", symbol="BTC"):
    return {
        "symbol": symbol,
        "price": price,
        "amount": amount,
        "pnl": pnl,
        "time": time,
        "info": {"exit_reason": reason},
    }


class TestBuildRoundTrips:
    def test_empty(self):
        out = build_round_trips(pd.DataFrame())
        assert out.empty

    def test_pair_entry_exit(self):
        trades = pd.DataFrame([_entry(), _exit()])
        rt = build_round_trips(trades)
        assert len(rt) == 1
        assert rt.iloc[0]["pnl"] == 10.0
        assert rt.iloc[0]["side"] == "LONG"

    def test_grouped_by_symbol(self):
        trades = pd.DataFrame([
            _entry(symbol="BTC"),
            _exit(symbol="BTC"),
            _entry(symbol="ETH"),
            _exit(symbol="ETH"),
        ])
        rt = build_round_trips(trades)
        assert len(rt) == 2
        # Both symbols appear
        assert set(rt["symbol"]) == {"BTC", "ETH"}

    def test_orphan_entry_no_exits_logs_warning(self):
        trades = pd.DataFrame([_entry(), _entry()])
        rt = build_round_trips(trades)
        assert rt.empty


class TestCreateRoundTrip:
    def test_builds_round_trip_dict(self):
        entry = _entry(side="BUY", price=100)
        exits = [_exit(price=110, amount=1, pnl=10, reason="TP1")]
        rt = create_round_trip(entry, exits, total_pnl=10, total_exit_amount=1)
        assert rt["side"] == "LONG"
        assert rt["entry_price"] == 100
        assert rt["exit_reason"] == "TP1"
        assert rt["num_partial_exits"] == 1
        assert rt["pnl"] == 10

    def test_short_side(self):
        entry = _entry(side="SELL", price=100)
        exits = [_exit()]
        rt = create_round_trip(entry, exits, 10, 1)
        assert rt["side"] == "SHORT"


class TestGetHighestExitReason:
    def test_no_reasons(self):
        assert _get_highest_exit_reason([]) == "UNKNOWN"

    def test_tp3_only(self):
        assert _get_highest_exit_reason(["TP3"]) == "TP3"

    def test_sl_only(self):
        assert _get_highest_exit_reason(["SL"]) == "SL"

    def test_tp_then_sl_combined(self):
        assert _get_highest_exit_reason(["TP2", "SL"]) == "TP2+SL"

    def test_multiple_tps_picks_highest(self):
        assert _get_highest_exit_reason(["TP1", "TP3"]) == "TP3"


class TestMaxConsecutive:
    def test_counts_ones(self):
        assert max_consecutive([0, 1, 1, 0, 1, 1, 1], 1) == 3

    def test_no_match(self):
        assert max_consecutive([1, 1, 1], 0) == 0


class TestCalculateMetrics:
    def test_empty_rt(self):
        assert calculate_metrics(pd.DataFrame()) == {}

    def test_basic_metrics(self):
        rt = pd.DataFrame([
            {"pnl": 100, "pnl_pct": 10, "hold_duration_hours": 2.0,
             "hit_tp1": True, "hit_tp2": False, "hit_tp3": False, "hit_sl": False, "exit_reason": "TP1"},
            {"pnl": -50, "pnl_pct": -5, "hold_duration_hours": 1.0,
             "hit_tp1": False, "hit_tp2": False, "hit_tp3": False, "hit_sl": True, "exit_reason": "SL"},
            {"pnl": 25, "pnl_pct": 2.5, "hold_duration_hours": 3.0,
             "hit_tp1": True, "hit_tp2": False, "hit_tp3": False, "hit_sl": False, "exit_reason": "TP1"},
        ])
        m = calculate_metrics(rt)
        assert m["total_trades"] == 3
        assert m["win_count"] == 2
        assert m["loss_count"] == 1
        assert m["tp1_count"] == 2
        assert m["sl_count"] == 1
        assert m["profit_factor"] > 0
        assert m["max_consec_wins"] >= 1


class TestCalculateDrawdown:
    def test_empty(self):
        out = calculate_drawdown(pd.DataFrame(), 1000)
        assert out["max_drawdown_pct"] == 0

    def test_computes_curve(self):
        rt = pd.DataFrame({"pnl": [100, -150, 50]})
        out = calculate_drawdown(rt, 1000)
        assert len(out["equity_curve"]) == 4
        assert out["max_drawdown_pct"] > 0
        assert out["max_dd_duration"] >= 1

    def test_monotonic_no_drawdown(self):
        rt = pd.DataFrame({"pnl": [100, 100, 100]})
        out = calculate_drawdown(rt, 1000)
        assert out["max_drawdown_pct"] == 0


class TestCalculateRiskMetrics:
    def test_empty(self):
        out = calculate_risk_metrics(pd.DataFrame(), {}, 1000)
        assert out["sharpe_ratio"] == 0

    def test_computes(self):
        rt = pd.DataFrame({"pnl": [100, -50, 200, -30, 150], "pnl_pct": [1, -0.5, 2, -0.3, 1.5]})
        out = calculate_risk_metrics(rt, {"max_drawdown_pct": 5}, 1000)
        assert out["volatility"] > 0
        assert "sharpe_ratio" in out
        assert "calmar_ratio" in out

    def test_single_trade(self):
        rt = pd.DataFrame({"pnl": [100], "pnl_pct": [1.0]})
        out = calculate_risk_metrics(rt, {}, 1000)
        assert out["sharpe_ratio"] == 0


class TestMonthlyReturns:
    def test_empty(self):
        assert calculate_monthly_returns(pd.DataFrame()) == {}

    def test_groups_by_month(self):
        rt = pd.DataFrame([
            {"exit_time": "2024-01-15", "pnl": 100},
            {"exit_time": "2024-01-20", "pnl": -50},
            {"exit_time": "2024-02-01", "pnl": 25},
        ])
        out = calculate_monthly_returns(rt)
        assert "2024-01" in out
        assert "2024-02" in out
        assert out["2024-01"]["trades"] == 2
        assert out["2024-01"]["pnl"] == 50
