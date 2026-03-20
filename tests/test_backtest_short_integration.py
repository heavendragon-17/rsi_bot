"""
tests/test_backtest_short_integration.py
End-to-end integration test for the SHORT trade flow:
  RsiMomentumStrategy → PortfolioManager → MockExchange

Approach: Build a synthetic OHLCV DataFrame with pre-set indicator columns
that satisfy all 5 entry conditions (S1-S5), then run the full chain:
  strategy.analyze() → OpenPosition → PortfolioManager.on_signal() → MockExchange orders

Then simulate price movement via MockExchange.update_candle() to exercise
SL/TP execution and verify PnL and trade closure.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
import numpy as np
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import patch

from app.strategies.rsi_momentum import RsiMomentumStrategy
from app.backtest.mock_exchange import MockExchange
from app.trading.portfolio.manager import PortfolioManager
from app.core.snapshots import ContextSnapshot, PositionSnapshot
from app.core.actions import OpenPosition, DoNothing
from app.core.context import SCANNING


SYMBOL = "BTC/USDT"
NOW = datetime(2024, 1, 1, 12, 0, 0)

BASE_CONFIG = {
    "symbols": [SYMBOL],
    "strategy": "rsi_momentum",
    "timeframe": "15m",
    "backtest": {"initial_balance": 10000},
    "risk": {
        "leverage": 1,
        "risk_per_trade_pct": 0.02,
        "tp1_close_pct": 0.5,
        "tp2_close_pct": 0.5,
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_short_signal_df(
    n: int = 100,
    entry_close: float = 50000.0,
    rsi: float = 42.0,
    ema9: float = 50.0,
    wma45: float = 55.0,
    inject_divergence: bool = True,
) -> pd.DataFrame:
    """
    Build an n-row OHLCV DataFrame with pre-injected indicator values
    that satisfy all SHORT entry conditions:

      S1: EMA9 crossed below WMA45 (crossover on last 2 candles)
      S2: RSI < EMA9
      S3: EMA9 < WMA45
      S4: (WMA45 - EMA9) > 2.5
      S5: Bearish divergence in last 30 candles (pivot A and B injected)
    """
    ts = pd.date_range("2024-01-01", periods=n, freq="15min")
    closes = [entry_close] * n

    # Inject high values for divergence
    # Pivot A: higher price lower RSI (earlier, within last 30 candles)
    # Pivot B: highest price, even lower RSI (later, within last 30 candles)
    highs = [entry_close * 1.001] * n
    rsis = [rsi] * n
    emas = [ema9] * n
    wmas = [wma45] * n

    if inject_divergence:
        N = 5  # pivot strength
        # Pivot A: price high at n-22, RSI high = 70
        pa = n - 22
        highs[pa] = entry_close * 1.06   # Higher high
        rsis[pa] = 70.0
        for i in range(max(0, pa - N), pa):
            highs[i] = entry_close * 0.99
            rsis[i] = rsi
        for i in range(pa + 1, min(pa + N + 1, n)):
            highs[i] = entry_close * 0.99
            rsis[i] = rsi

        # Pivot B: price even higher at n-9, RSI lower = 62 (bearish divergence)
        pb = n - 9
        highs[pb] = entry_close * 1.08   # Even Higher High in price
        rsis[pb] = 62.0                  # But Lower RSI High → divergence
        for i in range(max(0, pb - N), pb):
            if highs[i] < entry_close * 0.995:
                highs[i] = entry_close * 0.995
            rsis[i] = rsi
        for i in range(pb + 1, min(pb + N + 1, n)):
            highs[i] = entry_close * 0.995
            rsis[i] = rsi

    # Build previous candle with EMA9 >= WMA45 for crossover detection (S1)
    prev_ema = wma45 + 0.5  # EMA9 was above WMA45 on previous candle
    emas_col = [prev_ema] * n
    emas_col[-1] = ema9  # current candle: EMA9 crossed below WMA45

    df = pd.DataFrame({
        "open": [entry_close] * n,
        "high": highs,
        "low": [entry_close * 0.999] * n,
        "close": closes,
        "volume": [1000.0] * n,
        "closed": [True] * n,
        "rsi_14": rsis,
        "rsi_ema9": emas_col,
        "rsi_wma45": [wma45] * n,
    }, index=ts)

    return df


def _make_exchange(balance=10000):
    ex = MockExchange(initial_balance=balance, leverage=1)
    ex.current_prices[SYMBOL] = {"price": Decimal("50000"), "time": NOW}
    return ex


def _make_portfolio(ex):
    return PortfolioManager(ex, BASE_CONFIG)


def _make_strategy():
    return RsiMomentumStrategy(BASE_CONFIG)


def _open_position_to_signal(action: OpenPosition) -> "SignalEvent":
    """Mirror what Engine._action_to_signal does."""
    from app.core.events import SignalEvent
    tp = action.tp_prices or []
    return SignalEvent(
        symbol=action.symbol,
        signal_type=action.side,
        price=action.entry_price,
        timestamp=NOW,
        reason=action.reason,
        sl_price=action.sl_price,
        soft_sl_price=action.soft_sl_price,
        tp1_price=tp[0] if len(tp) > 0 else None,
        tp2_price=tp[1] if len(tp) > 1 else None,
        tp3_price=tp[2] if len(tp) > 2 else None,
        lock_profit_price=action.lock_profit_price,
        tp_allocations=action.tp_allocations,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestShortIntegrationEntry:
    def test_short_signal_fires_on_all_conditions_met(self):
        """
        When all 5 entry conditions are met, strategy returns OpenPosition(side='SELL').
        """
        strategy = _make_strategy()
        df = _make_short_signal_df()

        # Patch compute to return our pre-loaded DataFrame (indicators already set)
        with patch.object(strategy.indicators, "compute", return_value=df):
            result = strategy.analyze(
                symbol=SYMBOL,
                df=df,
                position=PositionSnapshot(has_position=False, symbol=SYMBOL),
                context=ContextSnapshot(state=SCANNING),
            )

        assert len(result.actions) == 1
        action = result.actions[0]
        assert isinstance(action, OpenPosition), f"Expected OpenPosition, got {type(action)}"
        assert action.side == "SELL", f"Expected SELL, got {action.side}"

    def test_short_action_has_sl_above_entry(self):
        """SL for SHORT is ABOVE the entry price (highest high lookback)."""
        strategy = _make_strategy()
        df = _make_short_signal_df(entry_close=50000.0)

        with patch.object(strategy.indicators, "compute", return_value=df):
            result = strategy.analyze(
                symbol=SYMBOL,
                df=df,
                position=PositionSnapshot(has_position=False, symbol=SYMBOL),
                context=ContextSnapshot(state=SCANNING),
            )

        action = result.actions[0]
        assert isinstance(action, OpenPosition)
        # For a short: SL must be above entry price (highest high)
        assert action.sl_price > action.entry_price, (
            f"Short SL {action.sl_price} should be > entry {action.entry_price}"
        )
        # soft_sl also above entry
        assert action.soft_sl_price > action.entry_price

    def test_short_action_has_tps_below_entry(self):
        """TP levels for SHORT are BELOW the entry price."""
        strategy = _make_strategy()
        df = _make_short_signal_df(entry_close=50000.0)

        with patch.object(strategy.indicators, "compute", return_value=df):
            result = strategy.analyze(
                symbol=SYMBOL,
                df=df,
                position=PositionSnapshot(has_position=False, symbol=SYMBOL),
                context=ContextSnapshot(state=SCANNING),
            )

        action = result.actions[0]
        assert isinstance(action, OpenPosition)
        tp_prices = action.tp_prices
        assert len(tp_prices) >= 2
        assert tp_prices[0] < action.entry_price, "TP1 should be below entry for SHORT"
        assert tp_prices[1] < tp_prices[0], "TP2 should be below TP1 for SHORT"


class TestShortIntegrationPortfolioExchange:
    def test_full_chain_entry_creates_short_position(self):
        """
        strategy.analyze() → OpenPosition → PortfolioManager → MockExchange:
        Verify short position is opened with negative amount.
        """
        strategy = _make_strategy()
        ex = _make_exchange()
        pm = _make_portfolio(ex)
        df = _make_short_signal_df(entry_close=50000.0)

        # Set exchange price to match entry
        ex.current_prices[SYMBOL] = {"price": Decimal("50000"), "time": NOW}

        with patch.object(strategy.indicators, "compute", return_value=df):
            result = strategy.analyze(
                symbol=SYMBOL,
                df=df,
                position=PositionSnapshot(has_position=False, symbol=SYMBOL),
                context=ContextSnapshot(state=SCANNING),
            )

        action = result.actions[0]
        assert isinstance(action, OpenPosition)

        # Simulate what engine does with OpenPosition action
        signal = _open_position_to_signal(action)
        pm.on_signal(signal)

        assert SYMBOL in pm.positions, "Position should be tracked"
        pos = pm.positions[SYMBOL]
        assert pos.side == "SELL", "Position side should be SELL"
        assert pos.amount < Decimal("0"), "Short position should have negative amount"

        # Verify orders were placed
        sl_orders = [o for o in ex.pending_orders.values() if o.get("order_subtype") == "stop_market"]
        tp_orders = [o for o in ex.pending_orders.values() if o.get("order_subtype") == "limit"]
        assert len(sl_orders) == 1, f"Expected 1 SL order, got {len(sl_orders)}"
        assert len(tp_orders) > 0, "Expected TP orders"
        assert sl_orders[0]["side"] == "BUY", "Short SL should be BUY"
        for tpo in tp_orders:
            assert tpo["side"] == "BUY", "Short TP should be BUY"

    def test_short_closes_at_tp_with_positive_pnl(self):
        """
        After opening a short, price drops to TP1 → trade closes with positive PnL.
        """
        strategy = _make_strategy()
        ex = _make_exchange()
        pm = _make_portfolio(ex)
        entry_price = Decimal("50000")
        df = _make_short_signal_df(entry_close=float(entry_price))

        ex.current_prices[SYMBOL] = {"price": entry_price, "time": NOW}

        with patch.object(strategy.indicators, "compute", return_value=df):
            result = strategy.analyze(
                symbol=SYMBOL,
                df=df,
                position=PositionSnapshot(has_position=False, symbol=SYMBOL),
                context=ContextSnapshot(state=SCANNING),
            )

        action = result.actions[0]
        assert isinstance(action, OpenPosition)
        tp1 = action.tp_prices[0]
        assert tp1 < entry_price, "TP1 must be below entry for short"

        # Route through portfolio
        signal = _open_position_to_signal(action)
        pm.on_signal(signal)

        initial_balance = ex.balance

        # Simulate a candle that hits TP1 (low <= tp1_price)
        t1 = NOW + timedelta(hours=1)
        executed = ex.update_candle(
            symbol=SYMBOL,
            open_=float(entry_price * Decimal("0.998")),
            high=float(entry_price * Decimal("0.999")),
            low=float(tp1 * Decimal("0.998")),   # low below TP1
            close=float(tp1),
            timestamp=t1,
        )

        # TP1 should have triggered
        tp_fills = [e for e in executed if e.get("side") == "BUY"]
        assert len(tp_fills) > 0, "TP1 should have triggered"
        pnl = tp_fills[0].get("pnl")
        assert pnl is not None and pnl > 0, f"TP1 hit should be profitable, pnl={pnl}"

    def test_short_closes_at_sl_with_negative_pnl(self):
        """
        After opening a short, price rises to SL → trade closes with negative PnL.
        """
        strategy = _make_strategy()
        ex = _make_exchange()
        pm = _make_portfolio(ex)
        entry_price = Decimal("50000")
        df = _make_short_signal_df(entry_close=float(entry_price))

        ex.current_prices[SYMBOL] = {"price": entry_price, "time": NOW}

        with patch.object(strategy.indicators, "compute", return_value=df):
            result = strategy.analyze(
                symbol=SYMBOL,
                df=df,
                position=PositionSnapshot(has_position=False, symbol=SYMBOL),
                context=ContextSnapshot(state=SCANNING),
            )

        action = result.actions[0]
        sl = action.sl_price  # disaster SL, above entry

        signal = _open_position_to_signal(action)
        pm.on_signal(signal)

        t1 = NOW + timedelta(hours=1)
        executed = ex.update_candle(
            symbol=SYMBOL,
            open_=float(entry_price * Decimal("1.001")),
            high=float(sl * Decimal("1.001")),   # high above SL
            low=float(entry_price),
            close=float(sl),
            timestamp=t1,
        )

        sl_fills = [e for e in executed if e.get("side") == "BUY"]
        assert len(sl_fills) > 0, "SL should have triggered"
        pnl = sl_fills[0].get("pnl")
        assert pnl is not None and pnl < 0, f"SL hit should be a loss, pnl={pnl}"

    def test_round_trip_side_in_trade_history(self):
        """
        After a complete short trade, trade history entry has side='SELL'.
        """
        ex = _make_exchange()
        pm = _make_portfolio(ex)
        strategy = _make_strategy()
        entry_price = Decimal("50000")
        df = _make_short_signal_df(entry_close=float(entry_price))

        ex.current_prices[SYMBOL] = {"price": entry_price, "time": NOW}

        with patch.object(strategy.indicators, "compute", return_value=df):
            result = strategy.analyze(
                symbol=SYMBOL,
                df=df,
                position=PositionSnapshot(has_position=False, symbol=SYMBOL),
                context=ContextSnapshot(state=SCANNING),
            )

        action = result.actions[0]
        signal = _open_position_to_signal(action)
        pm.on_signal(signal)

        # Close via SL
        sl = action.sl_price
        executed = ex.update_candle(
            symbol=SYMBOL,
            open_=float(entry_price),
            high=float(sl * Decimal("1.001")),
            low=float(entry_price),
            close=float(sl),
            timestamp=NOW + timedelta(hours=1),
        )

        # The entry order should be in trade history with side='SELL'
        entry_orders = [t for t in ex.trade_history if t.get("side") == "SELL"]
        assert len(entry_orders) > 0, "Should have a SELL trade in history"
        # Exit order should be BUY
        exit_orders = [t for t in ex.trade_history if t.get("side") == "BUY"]
        assert len(exit_orders) > 0, "Should have a BUY exit in history"


class TestEngineRoundTripBuilder:
    """Test that BacktestEngine._build_round_trips correctly handles SHORT trades."""

    def test_short_round_trip_has_sell_side(self):
        """SELL entry + BUY exits produces a round trip with side='SHORT'."""
        from app.backtest.engine import BacktestEngine

        # Simulate trade history for a short trade
        trades = pd.DataFrame([
            {
                "side": "SELL",  # short entry
                "symbol": SYMBOL,
                "time": "2024-01-01 10:00",
                "price": 50000.0,
                "amount": 0.1,
                "pnl": None,
                "margin": 5000.0,
                "notional": 5000.0,
                "leverage": 1.0,
                "info": {"exit_reason": ""},
            },
            {
                "side": "BUY",  # short exit (TP)
                "symbol": SYMBOL,
                "time": "2024-01-01 14:00",
                "price": 48000.0,  # lower price = profit for short
                "amount": 0.1,
                "pnl": 200.0,
                "margin": 5000.0,
                "notional": 4800.0,
                "leverage": 1.0,
                "info": {"exit_reason": "TP1"},
            },
        ])

        round_trips = BacktestEngine._build_round_trips(trades)

        assert not round_trips.empty, "Should have 1 round trip"
        assert len(round_trips) == 1
        rt = round_trips.iloc[0]
        assert rt["side"] == "SHORT", f"Round trip side should be SHORT, got {rt['side']}"
        assert rt["pnl"] == pytest.approx(200.0)

    def test_long_round_trip_has_buy_side(self):
        """BUY entry + SELL exits produces a round trip with side='LONG'."""
        from app.backtest.engine import BacktestEngine

        trades = pd.DataFrame([
            {
                "side": "BUY",
                "symbol": SYMBOL,
                "time": "2024-01-01 10:00",
                "price": 50000.0,
                "amount": 0.1,
                "pnl": None,
                "margin": 5000.0,
                "notional": 5000.0,
                "leverage": 1.0,
                "info": {"exit_reason": ""},
            },
            {
                "side": "SELL",
                "symbol": SYMBOL,
                "time": "2024-01-01 14:00",
                "price": 52000.0,
                "amount": 0.1,
                "pnl": 200.0,
                "margin": 5000.0,
                "notional": 5200.0,
                "leverage": 1.0,
                "info": {"exit_reason": "TP1"},
            },
        ])

        round_trips = BacktestEngine._build_round_trips(trades)

        assert not round_trips.empty
        rt = round_trips.iloc[0]
        assert rt["side"] == "LONG", f"Long round trip should have side LONG, got {rt['side']}"

    def test_mixed_long_short_round_trips(self):
        """Mixed LONG and SHORT trades produce correct round trips with correct sides."""
        from app.backtest.engine import BacktestEngine

        trades = pd.DataFrame([
            # Short trade
            {"side": "SELL", "symbol": SYMBOL, "time": "2024-01-01 08:00", "price": 50000.0, "amount": 0.1, "pnl": None, "margin": 5000.0, "notional": 5000.0, "leverage": 1.0, "info": {"exit_reason": ""}},
            {"side": "BUY",  "symbol": SYMBOL, "time": "2024-01-01 10:00", "price": 49000.0, "amount": 0.1, "pnl": 100.0, "margin": 0.0, "notional": 4900.0, "leverage": 1.0, "info": {"exit_reason": "TP1"}},
            # Long trade
            {"side": "BUY",  "symbol": SYMBOL, "time": "2024-01-01 12:00", "price": 49500.0, "amount": 0.1, "pnl": None, "margin": 4950.0, "notional": 4950.0, "leverage": 1.0, "info": {"exit_reason": ""}},
            {"side": "SELL", "symbol": SYMBOL, "time": "2024-01-01 14:00", "price": 51000.0, "amount": 0.1, "pnl": 150.0, "margin": 0.0, "notional": 5100.0, "leverage": 1.0, "info": {"exit_reason": "TP1"}},
        ])

        round_trips = BacktestEngine._build_round_trips(trades)

        assert len(round_trips) == 2
        sides = set(round_trips["side"].tolist())
        assert "SHORT" in sides, "Should have SHORT round trip"
        assert "LONG" in sides, "Should have LONG round trip"
