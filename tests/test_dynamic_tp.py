"""
Verification tests for Dynamic TP allocation logic.

Tests that strategy produces correct tp_allocations based on nr_tp_count config.
Uses monkeypatch fixture to safely patch Indicators.last per-test.
"""

from datetime import datetime
from decimal import Decimal

import pandas as pd
import pytest

from app.backtest.exchange.mock_exchange import MockExchange
from app.core.actions import OpenPosition
from app.core.events import SignalEvent
from app.core.snapshots import ContextSnapshot
from app.data.indicators import Indicators
from app.trading.portfolio.manager import PortfolioManager
from app.trading.strategy.rsi_no_retest import RsiNoRetestStrategy


def _create_mock_data():
    """Create 220 candles worth of mock data for strategy warmup."""
    timestamps = [pd.Timestamp.now() - pd.Timedelta(hours=i) for i in range(220)]
    timestamps.reverse()
    rows = []
    for _ in range(220):
        rows.append(
            {
                "date": timestamps[0],
                "open": 100.0,
                "high": 100.0,
                "low": 100.0,
                "close": 100.0,
                "rsi_14": 50.0,
                "rsi_ema9": 50.0,
                "rsi_wma45": 50.0,
                "ema21": 100.0,
                "closed": True,
            }
        )
    return pd.DataFrame(rows, index=timestamps)


def test_tp_count_1(monkeypatch):
    """With nr_tp_count=1, TP1 allocation should be 100% and close the full position."""
    config = {
        "strategy_params": {
            "nr_tp_count": 1,
            "nr_tp1_rr": 1.0,
            "use_active_trades": True,
        },
        "risk": {"tp1_close_pct": 0.5},
        "bot": {"timeframe": "1h"},
        "backtest": {"initial_balance": 1000},
        "symbols": ["BTC/USDT"],
    }
    strategy = RsiNoRetestStrategy(config)

    df = _create_mock_data()
    df.iloc[-1, df.columns.get_loc("close")] = 105.0
    df.iloc[-1, df.columns.get_loc("ema21")] = 104.0

    last = {
        "close": 105.0,
        "high": 105.0,
        "low": 105.0,
        "open": 105.0,
        "ema21": 104.0,
        "rsi_ema9": 60.0,
        "rsi_wma45": 50.0,
        "ts": datetime.now(),
    }

    monkeypatch.setattr(strategy.indicators, "compute", lambda *a, **kw: df)
    monkeypatch.setattr(Indicators, "last", staticmethod(lambda df, **kw: last))

    ctx = ContextSnapshot(state="CONFIRMING")
    result = strategy.analyze("BTC/USDT", df, context=ctx)

    open_pos = next((a for a in result.actions if isinstance(a, OpenPosition)), None)
    assert open_pos is not None, "Should generate an OpenPosition action"

    allocs = open_pos.tp_allocations
    assert allocs is not None, "tp_allocations must be present"
    assert allocs.get("TP1") == 1.0, f"TP1 allocation should be 1.0, got {allocs.get('TP1')}"

    # --- portfolio execution phase ---
    exchange = MockExchange()
    pm = PortfolioManager(exchange, config)
    exchange.fetch_balance = lambda: {"total": {"USDT": 1000}}
    exchange.update_candle(
        "BTC/USDT",
        Decimal("105"),
        Decimal("105"),
        Decimal("105"),
        Decimal("105"),
        datetime.now(),
    )

    tp_prices = open_pos.tp_prices or []
    signal = SignalEvent(
        symbol=open_pos.symbol,
        signal_type="BUY",
        price=open_pos.entry_price,
        timestamp=datetime.now(),
        reason=open_pos.reason,
        sl_price=open_pos.sl_price,
        soft_sl_price=open_pos.soft_sl_price,
        tp1_price=tp_prices[0] if len(tp_prices) > 0 else None,
        tp2_price=tp_prices[1] if len(tp_prices) > 1 else None,
        tp3_price=tp_prices[2] if len(tp_prices) > 2 else None,
        signal_class=open_pos.signal_class,
        lock_profit_price=open_pos.lock_profit_price,
        tp_allocations=open_pos.tp_allocations,
    )

    exchange.update_candle(
        "BTC/USDT",
        Decimal("105"),
        Decimal("105"),
        Decimal("105"),
        Decimal("105"),
        datetime.now(),
    )
    pm.on_signal(signal)

    pos = pm.positions.get("BTC/USDT")
    assert pos is not None, "Position must be created after BUY signal"
    assert pos.tp_allocations["TP1"] == 1.0, "Position must inherit TP1=1.0 allocation"

    # TP1 hit → should close 100%
    sell_signal = SignalEvent(
        symbol="BTC/USDT",
        signal_type="SELL",
        price=Decimal("110"),
        timestamp=datetime.now(),
        reason="TP1 hit",
        sl_price=Decimal("100"),
    )
    pm.on_signal(sell_signal)

    assert "BTC/USDT" not in pm.positions, "Position must be fully closed after TP1 (100% alloc)"


def test_tp_count_2(monkeypatch):
    """With nr_tp_count=2 and tp1_close_pct=0.4, TP1=40%, TP2=100%."""
    config = {
        "strategy_params": {
            "nr_tp_count": 2,
            "nr_tp1_rr": 1.0,
            "nr_tp2_rr": 2.0,
            "tp1_close_pct": 0.4,
        },
        "risk": {},
        "bot": {"timeframe": "1h"},
        "backtest": {"initial_balance": 1000},
        "symbols": ["BTC/USDT"],
    }
    strategy = RsiNoRetestStrategy(config)
    df = _create_mock_data()

    last = {
        "close": 105.0,
        "high": 105.0,
        "low": 105.0,
        "open": 105.0,
        "ema21": 104.0,
        "rsi_ema9": 60.0,
        "rsi_wma45": 50.0,
        "ts": datetime.now(),
    }
    monkeypatch.setattr(strategy.indicators, "compute", lambda *a, **kw: df)
    monkeypatch.setattr(Indicators, "last", staticmethod(lambda df, **kw: last))

    ctx = ContextSnapshot(state="CONFIRMING")
    result = strategy.analyze("BTC/USDT", df, context=ctx)

    open_pos = next((a for a in result.actions if isinstance(a, OpenPosition)), None)
    assert open_pos is not None, "Should generate an OpenPosition action"

    allocs = open_pos.tp_allocations
    assert allocs is not None, "tp_allocations must be present"
    assert allocs["TP1"] == pytest.approx(0.4), f"TP1 should be 0.4, got {allocs['TP1']}"
    assert allocs["TP2"] == pytest.approx(1.0), f"TP2 should be 1.0, got {allocs['TP2']}"
