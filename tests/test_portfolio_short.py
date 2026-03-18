"""
tests/test_portfolio_short.py
Tests for PortfolioManager SHORT trade handling.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from decimal import Decimal
from datetime import datetime

from app.backtest.mock_exchange import MockExchange
from app.core.portfolio import PortfolioManager, Position
from app.core.events import SignalEvent


SYMBOL = "BTC/USDT"
NOW = datetime(2024, 1, 1, 12, 0, 0)


def make_exchange(balance=10000.0):
    ex = MockExchange(initial_balance=balance, leverage=1)
    ex.current_prices[SYMBOL] = {"price": Decimal("50000"), "time": NOW}
    return ex


def make_portfolio(exchange, extra_risk=None):
    risk = {"leverage": 1, "risk_per_trade_pct": 0.02, "tp1_close_pct": 0.5, "tp2_close_pct": 0.5}
    if extra_risk:
        risk.update(extra_risk)
    config = {
        "risk": risk,
        "backtest": {"initial_balance": 10000},
        "symbols": [SYMBOL],
    }
    return PortfolioManager(exchange, config)


def make_short_signal(price=50000, sl=52000, tp1=48000, tp2=46000, tp3=44000):
    return SignalEvent(
        symbol=SYMBOL,
        signal_type="SELL",
        price=Decimal(str(price)),
        timestamp=NOW,
        reason="SHORT_ENTRY",
        sl_price=Decimal(str(sl)),
        soft_sl_price=Decimal(str(sl)),
        tp1_price=Decimal(str(tp1)),
        tp2_price=Decimal(str(tp2)),
        tp3_price=Decimal(str(tp3)),
    )


class TestShortEntry:
    def test_short_entry_creates_sell_order(self):
        """market SELL + BUY-side SL/TP orders placed"""
        ex = make_exchange()
        pm = make_portfolio(ex)
        signal = make_short_signal()

        result = pm.on_signal(signal)

        assert result is not None
        # Entry order is a market SELL
        assert result["side"] == "SELL"
        assert result["type"] == "market"
        # Position is tracked with negative amount
        assert SYMBOL in pm.positions
        pos = pm.positions[SYMBOL]
        assert pos.side == "SELL"
        assert pos.amount < Decimal("0"), "Short position should have negative amount"

    def test_short_tp_orders_buy_side(self):
        """TP limit orders placed as BUY with reduceOnly"""
        ex = make_exchange()
        pm = make_portfolio(ex)
        signal = make_short_signal()
        pm.on_signal(signal)

        # Check pending TP orders
        tp_orders = [
            o for o in ex.pending_orders.values()
            if o.get("order_subtype") == "limit"
        ]
        assert len(tp_orders) > 0, "No TP limit orders placed"
        for order in tp_orders:
            assert order["side"] == "BUY", f"TP order side should be BUY, got {order['side']}"
            assert order.get("reduce_only") is True, "TP order should be reduceOnly"

    def test_short_sl_order_buy_side(self):
        """SL stop_market placed as BUY with reduceOnly"""
        ex = make_exchange()
        pm = make_portfolio(ex)
        signal = make_short_signal()
        pm.on_signal(signal)

        sl_orders = [
            o for o in ex.pending_orders.values()
            if o.get("order_subtype") == "stop_market"
        ]
        assert len(sl_orders) == 1, f"Expected 1 SL order, got {len(sl_orders)}"
        sl = sl_orders[0]
        assert sl["side"] == "BUY", f"Short SL should be BUY side, got {sl['side']}"
        assert sl.get("reduce_only") is True, "SL order should be reduceOnly"

    def test_short_position_negative_amount(self):
        """Position amount is negative for short trades"""
        ex = make_exchange()
        pm = make_portfolio(ex)
        signal = make_short_signal()
        pm.on_signal(signal)

        pos = pm.positions[SYMBOL]
        assert pos.amount < Decimal("0")

    def test_no_entry_when_position_exists(self):
        """Strategy should not open a second position while one is open.

        The PortfolioManager correctly blocks double entry in _handle_entry_signal
        when the symbol is already in positions. A BUY signal when already long/short
        will be blocked.
        """
        ex = make_exchange()
        pm = make_portfolio(ex)
        pm.on_signal(make_short_signal())
        assert SYMBOL in pm.positions
        pos_before = pm.positions[SYMBOL]

        # BUY entry signal should be blocked (position already exists)
        buy_signal = SignalEvent(
            symbol=SYMBOL,
            signal_type="BUY",
            price=Decimal("49000"),
            timestamp=NOW,
            sl_price=Decimal("46000"),
        )
        result = pm.on_signal(buy_signal)
        assert result is None, "Should not open a BUY when SHORT is open"
        # Short position still exists unchanged
        assert SYMBOL in pm.positions
        assert pm.positions[SYMBOL].side == "SELL"


class TestShortPartialClose:
    def test_short_partial_close_tp1_reduces_negative_amount(self):
        """TP1 fill reduces negative amount toward zero"""
        ex = make_exchange()
        pm = make_portfolio(ex)
        signal = make_short_signal()
        pm.on_signal(signal)

        pos = pm.positions[SYMBOL]
        initial_amount = pos.amount  # negative
        assert initial_amount < Decimal("0")

        # Execute partial close TP1
        pm.execute_partial_close(SYMBOL, "TP1")

        # Amount should be closer to zero (less negative)
        remaining = pm.positions.get(SYMBOL)
        if remaining is not None:
            assert remaining.amount > initial_amount, (
                f"Amount should increase toward zero after TP1: was {initial_amount}, now {remaining.amount}"
            )
            assert remaining.amount < Decimal("0"), "Should still be short after TP1"

    def test_short_tp1_hit_flag(self):
        """tp1_hit flag is set after TP1 partial close"""
        ex = make_exchange()
        pm = make_portfolio(ex)
        pm.on_signal(make_short_signal())
        pm.execute_partial_close(SYMBOL, "TP1")

        pos = pm.positions.get(SYMBOL)
        if pos:
            assert pos.tp1_hit is True


class TestShortLockProfit:
    def test_short_lock_profit_moves_sl(self):
        """After TP1 hit, SL can be moved to lock profit below entry"""
        ex = make_exchange()
        pm = make_portfolio(ex)
        signal = make_short_signal(price=50000, sl=52000)
        pm.on_signal(signal)

        # Move SL to lock-profit price (below entry for short = profit locked)
        lock_price = Decimal("49500")  # below entry, locks profit
        result = pm.move_stop_loss(SYMBOL, lock_price)

        assert result is True
        # The new stop_market order should be at the lock_price
        sl_orders = [
            o for o in ex.pending_orders.values()
            if o.get("order_subtype") == "stop_market" and o.get("symbol") == SYMBOL
        ]
        assert len(sl_orders) == 1
        assert sl_orders[0]["triggerPrice"] == lock_price

    def test_move_sl_updates_pending_order(self):
        """Moving SL cancels old order and places new BUY stop_market"""
        ex = make_exchange()
        pm = make_portfolio(ex)
        pm.on_signal(make_short_signal(price=50000, sl=52000))

        old_sl_orders = [
            o for o in ex.pending_orders.values()
            if o.get("order_subtype") == "stop_market"
        ]
        assert len(old_sl_orders) == 1

        pm.move_stop_loss(SYMBOL, Decimal("49800"))

        new_sl_orders = [
            o for o in ex.pending_orders.values()
            if o.get("order_subtype") == "stop_market"
        ]
        assert len(new_sl_orders) == 1
        assert new_sl_orders[0]["side"] == "BUY"


class TestShortFullExit:
    def test_short_full_exit_cancel_orders_market_buy(self):
        """Full exit: cancel all orders, market BUY to close short"""
        ex = make_exchange()
        pm = make_portfolio(ex)
        initial_balance = ex.balance
        pm.on_signal(make_short_signal())

        # Ensure orders and position were created
        assert len(ex.pending_orders) > 0
        assert SYMBOL in pm.positions
        balance_after_entry = ex.balance

        # Full exit — close_position returns None (by design), not the order
        pm.close_position(SYMBOL, reason="MANUAL")

        # Position should be removed
        assert SYMBOL not in pm.positions
        # All pending orders should be cancelled
        remaining = [o for o in ex.pending_orders.values() if o.get("symbol") == SYMBOL]
        assert len(remaining) == 0
        # Trade history should have a BUY exit order
        buy_exits = [t for t in ex.trade_history if t.get("side") == "BUY" and t.get("symbol") == SYMBOL]
        assert len(buy_exits) > 0, "Should have a BUY order in trade history for short exit"

    def test_short_exit_not_called_when_no_position(self):
        """close_position does nothing if no position exists"""
        ex = make_exchange()
        pm = make_portfolio(ex)
        result = pm.close_position(SYMBOL, reason="MANUAL")
        assert result is None


class TestSLExitReason:
    def test_sl_exit_reason_stop_loss_above_entry(self):
        """SL above entry for short = STOP_LOSS"""
        reason = PortfolioManager._sl_exit_reason(
            sl_price=Decimal("52000"),
            entry_price=Decimal("50000"),
            position_side="SELL",
        )
        assert reason == "STOP_LOSS"

    def test_sl_exit_reason_lock_profit_below_entry(self):
        """SL below entry for short = LOCK_PROFIT"""
        reason = PortfolioManager._sl_exit_reason(
            sl_price=Decimal("49000"),
            entry_price=Decimal("50000"),
            position_side="SELL",
        )
        assert reason == "LOCK_PROFIT"

    def test_sl_exit_reason_breakeven(self):
        """SL at entry = BREAKEVEN"""
        reason = PortfolioManager._sl_exit_reason(
            sl_price=Decimal("50000"),
            entry_price=Decimal("50000"),
            position_side="SELL",
        )
        assert reason == "BREAKEVEN"
