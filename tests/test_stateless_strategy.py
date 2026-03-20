"""
Tests verifying the stateless property of RsiNoRetestStrategy.analyze().

Key invariants:
- Same inputs → same outputs (no hidden mutable state on self)
- Calling analyze() never modifies self.context
- Returns AnalysisResult (not None, not SignalEvent)
- new_context is a frozen ContextSnapshot
"""
import pytest
import pandas as pd
from decimal import Decimal
from datetime import datetime

from app.trading.strategy.rsi_no_retest import RsiNoRetestStrategy
from app.core.snapshots import ContextSnapshot, PositionSnapshot
from app.core.analysis_result import AnalysisResult
from app.core.actions import DoNothing
from app.utils.indicators import Indicators


CONFIG = {
    "strategy_params": {"use_active_trades": True, "nr_tp_count": 3},
    "risk": {"leverage": 1},
    "bot": {"timeframe": "15m"},
    "backtest": {"initial_balance": 1000},
    "symbols": ["BTC/USDT"],
}


def _make_df(n: int = 220) -> pd.DataFrame:
    timestamps = [pd.Timestamp.now() - pd.Timedelta(minutes=15 * i) for i in range(n)]
    timestamps.reverse()
    rows = [
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0,
         "rsi": 50.0, "rsi_ema9": 50.0, "rsi_wma45": 50.0,
         "ema21": 100.0, "ema200": 100.0, "closed": True}
        for _ in range(n)
    ]
    return pd.DataFrame(rows, index=timestamps)


@pytest.fixture
def strategy():
    return RsiNoRetestStrategy(CONFIG)


def test_analyze_returns_analysis_result(strategy, monkeypatch):
    """analyze() must always return an AnalysisResult, never None."""
    df = _make_df()
    last = {"close": 100.0, "high": 100.0, "low": 100.0, "open": 100.0,
            "ema21": 100.0, "rsi_ema9": 50.0, "rsi_wma45": 50.0}
    monkeypatch.setattr(strategy.indicators, "compute", lambda *a, **kw: df)
    monkeypatch.setattr(Indicators, "last", staticmethod(lambda df: last))

    ctx = ContextSnapshot(state="SCANNING")
    result = strategy.analyze("BTC/USDT", df, context=ctx)

    assert isinstance(result, AnalysisResult), (
        f"analyze() must return AnalysisResult, got {type(result)}"
    )


def test_analyze_does_not_mutate_self_context(strategy, monkeypatch):
    """Calling analyze() must not mutate strategy.context."""
    df = _make_df()
    last = {"close": 100.0, "high": 100.0, "low": 100.0, "open": 100.0,
            "ema21": 100.0, "rsi_ema9": 50.0, "rsi_wma45": 50.0}
    monkeypatch.setattr(strategy.indicators, "compute", lambda *a, **kw: df)
    monkeypatch.setattr(Indicators, "last", staticmethod(lambda df: last))

    # Capture the context object identity before the call
    original_context = strategy.context
    ctx = ContextSnapshot(state="SCANNING")

    strategy.analyze("BTC/USDT", df, context=ctx)
    strategy.analyze("BTC/USDT", df, context=ctx)
    strategy.analyze("BTC/USDT", df, context=ctx)

    assert strategy.context is original_context, (
        "analyze() must not replace self.context"
    )


def test_same_inputs_same_outputs(strategy, monkeypatch):
    """Calling analyze() twice with identical inputs must produce identical outputs."""
    df = _make_df()
    last = {"close": 100.0, "high": 100.0, "low": 100.0, "open": 100.0,
            "ema21": 100.0, "rsi_ema9": 50.0, "rsi_wma45": 50.0}
    monkeypatch.setattr(strategy.indicators, "compute", lambda *a, **kw: df)
    monkeypatch.setattr(Indicators, "last", staticmethod(lambda df: last))

    ctx = ContextSnapshot(state="SCANNING")
    r1 = strategy.analyze("BTC/USDT", df, context=ctx)
    r2 = strategy.analyze("BTC/USDT", df, context=ctx)

    assert type(r1.actions[0]) == type(r2.actions[0]), (
        "Same inputs must produce same action type"
    )
    assert r1.new_context.state == r2.new_context.state, (
        "Same inputs must produce same new_context state"
    )


def test_new_context_is_frozen(strategy, monkeypatch):
    """new_context must be a frozen ContextSnapshot."""
    df = _make_df()
    last = {"close": 100.0, "high": 100.0, "low": 100.0, "open": 100.0,
            "ema21": 100.0, "rsi_ema9": 50.0, "rsi_wma45": 50.0}
    monkeypatch.setattr(strategy.indicators, "compute", lambda *a, **kw: df)
    monkeypatch.setattr(Indicators, "last", staticmethod(lambda df: last))

    ctx = ContextSnapshot(state="SCANNING")
    result = strategy.analyze("BTC/USDT", df, context=ctx)

    assert isinstance(result.new_context, ContextSnapshot)
    with pytest.raises(Exception):
        result.new_context.state = "CONFIRMING"  # type: ignore[misc]


def test_no_position_returns_do_nothing_or_scanning(strategy, monkeypatch):
    """With no position and market in SCANNING, strategy returns DoNothing."""
    df = _make_df()
    last = {"close": 100.0, "high": 100.0, "low": 100.0, "open": 100.0,
            "ema21": 100.0, "rsi_ema9": 50.0, "rsi_wma45": 50.0}
    monkeypatch.setattr(strategy.indicators, "compute", lambda *a, **kw: df)
    monkeypatch.setattr(Indicators, "last", staticmethod(lambda df: last))

    ctx = ContextSnapshot(state="SCANNING")
    result = strategy.analyze("BTC/USDT", df, position=None, context=ctx)

    assert any(isinstance(a, DoNothing) for a in result.actions), (
        "No open position in SCANNING state should produce DoNothing"
    )
