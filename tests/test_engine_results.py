"""
Tests for BacktestEngine.run() results dict contract.

Verifies that run() returns a dict with the canonical structure expected by
BacktestReporter and the DB layer, regardless of whether trades occurred.
"""
import os
import pytest

from app.backtest.engine import BacktestEngine
from app.trading.strategy.rsi_no_retest import RsiNoRetestStrategy

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "small_btc.csv")

REQUIRED_KEYS = {
    "metrics",
    "risk_metrics",
    "drawdown",
    "monthly_returns",
    "equity_curve",
    "drawdown_curve",
    "round_trips",
    "initial_balance",
    "final_balance",
    "net_profit",
    "net_profit_pct",
}

REQUIRED_RISK_KEYS = {"sharpe_ratio", "sortino_ratio", "calmar_ratio", "volatility", "var_95"}
REQUIRED_DRAWDOWN_KEYS = {"max_drawdown_pct", "max_drawdown_value", "max_dd_duration", "avg_drawdown_pct"}

BASE_CONFIG = {
    "symbols": ["BTC/USDT"],
    "timeframe": "15m",
    "bot": {"timeframe": "15m"},
    "strategy": "rsi_no_retest",
    "backtest": {"initial_balance": 10000},
    "risk": {"leverage": 10, "risk_per_trade_pct": 0.02},
}


@pytest.fixture(scope="module")
def results():
    engine = BacktestEngine(
        data_path=DATA_PATH,
        strategy_class=RsiNoRetestStrategy,
        config=BASE_CONFIG,
    )
    return engine.run()


def test_returns_dict(results):
    assert isinstance(results, dict)


def test_has_required_keys(results):
    missing = REQUIRED_KEYS - results.keys()
    assert not missing, f"Missing keys: {missing}"


def test_initial_balance_float(results):
    assert isinstance(results["initial_balance"], float)
    assert results["initial_balance"] == 10000.0


def test_final_balance_float(results):
    assert isinstance(results["final_balance"], float)


def test_net_profit_float(results):
    assert isinstance(results["net_profit"], float)
    assert isinstance(results["net_profit_pct"], float)


def test_round_trips_is_list(results):
    assert isinstance(results["round_trips"], list)


def test_equity_curve_structure(results):
    """equity_curve must be a list of {date, balance} dicts (may be empty)."""
    ec = results["equity_curve"]
    assert isinstance(ec, list)
    for pt in ec:
        assert "date" in pt, "equity_curve point missing 'date'"
        assert "balance" in pt, "equity_curve point missing 'balance'"
        assert isinstance(pt["balance"], float)


def test_drawdown_curve_structure(results):
    """drawdown_curve must be a list of {date, drawdown} dicts (may be empty)."""
    dc = results["drawdown_curve"]
    assert isinstance(dc, list)
    for pt in dc:
        assert "date" in pt
        assert "drawdown" in pt


def test_risk_metrics_keys(results):
    missing = REQUIRED_RISK_KEYS - results["risk_metrics"].keys()
    assert not missing, f"risk_metrics missing: {missing}"


def test_drawdown_keys(results):
    missing = REQUIRED_DRAWDOWN_KEYS - results["drawdown"].keys()
    assert not missing, f"drawdown missing: {missing}"


def test_monthly_returns_is_dict(results):
    assert isinstance(results["monthly_returns"], dict)


def test_on_progress_callback():
    """on_progress callback receives dicts with pct/candle/total; last call has pct=100."""
    calls = []

    engine = BacktestEngine(
        data_path=DATA_PATH,
        strategy_class=RsiNoRetestStrategy,
        config=BASE_CONFIG,
    )
    engine.run(on_progress=lambda d: calls.append(d))

    assert calls, "on_progress was never called"
    last = calls[-1]
    assert last["pct"] == 100
    for call in calls:
        assert "pct" in call
        assert "candle" in call
        assert "total" in call
        assert 0 <= call["pct"] <= 100
