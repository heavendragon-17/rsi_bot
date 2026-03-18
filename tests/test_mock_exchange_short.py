"""
tests/test_mock_exchange_short.py
Tests for MockExchange SHORT trade handling.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from decimal import Decimal
from datetime import datetime, timedelta

from app.backtest.mock_exchange import MockExchange


SYMBOL = "BTC/USDT"
NOW = datetime(2024, 1, 1, 12, 0, 0)


def make_exchange(balance=10000.0, leverage=1):
    ex = MockExchange(initial_balance=balance, leverage=leverage)
    ex.current_prices[SYMBOL] = {"price": Decimal("50000"), "time": NOW}
    return ex


def open_short(ex, price=50000, amount=0.1):
    """Helper to open a short position via SELL market order."""
    ex.current_prices[SYMBOL] = {"price": Decimal(str(price)), "time": NOW}
    order = ex.create_order(
        symbol=SYMBOL,
        order_type="market",
        side="SELL",
        amount=Decimal(str(amount)),
    )
    return order


class TestShortEntry:
    def test_short_entry_negative_amount(self):
        """SELL market creates negative position amount"""
        ex = make_exchange()
        open_short(ex, price=50000, amount=0.1)

        pos = ex.positions.get(SYMBOL)
        assert pos is not None
        assert pos < Decimal("0"), f"Short position should be negative, got {pos}"
        assert pos == Decimal("-0.1")

    def test_short_entry_deducts_margin(self):
        """Margin is deducted from balance on short entry"""
        ex = make_exchange(balance=10000, leverage=1)
        initial_balance = ex.balance
        open_short(ex, price=50000, amount=0.1)

        # Notional = 50000 * 0.1 = 5000; margin = 5000 / 1 = 5000
        margin = Decimal("5000")
        assert ex.balance == initial_balance - margin
        assert ex.margin_used.get(SYMBOL) == margin

    def test_short_entry_records_entry_price(self):
        """Entry price is recorded for PnL calculation"""
        ex = make_exchange()
        open_short(ex, price=50000, amount=0.1)

        assert ex.entry_prices.get(SYMBOL) == Decimal("50000")


class TestShortPnL:
    def test_short_pnl_positive_when_price_drops(self):
        """amount * (exit - entry) with negative amount = positive PnL when price drops"""
        ex = make_exchange(balance=10000)
        open_short(ex, price=50000, amount=0.1)

        # Price drops to 48000 — short should profit
        exit_time = NOW + timedelta(hours=1)
        ex.current_prices[SYMBOL] = {"price": Decimal("48000"), "time": exit_time}

        result = ex.create_order(
            symbol=SYMBOL,
            order_type="market",
            side="BUY",
            amount=Decimal("0.1"),
            params={"reduceOnly": True},
        )

        assert result is not None
        assert result["pnl"] is not None
        assert result["pnl"] > 0, f"PnL should be positive when price drops, got {result['pnl']}"
        # Expected: (50000 - 48000) * 0.1 = 200 (minus fees)
        assert result["pnl"] > 100, "PnL should be substantial (≈200 before fees)"

    def test_short_pnl_negative_when_price_rises(self):
        """Negative PnL when price rises against short"""
        ex = make_exchange(balance=10000)
        open_short(ex, price=50000, amount=0.1)

        # Price rises to 52000 — short should lose
        exit_time = NOW + timedelta(hours=1)
        ex.current_prices[SYMBOL] = {"price": Decimal("52000"), "time": exit_time}

        result = ex.create_order(
            symbol=SYMBOL,
            order_type="market",
            side="BUY",
            amount=Decimal("0.1"),
            params={"reduceOnly": True},
        )

        assert result is not None
        assert result["pnl"] is not None
        assert result["pnl"] < 0, f"PnL should be negative when price rises, got {result['pnl']}"

    def test_short_pnl_zero_at_entry_price(self):
        """Zero PnL (before fees) when exit price equals entry"""
        ex = make_exchange(balance=10000, leverage=1)
        # Set zero fees to test pure PnL
        ex.taker_fee = Decimal("0")
        ex.maker_fee = Decimal("0")
        open_short(ex, price=50000, amount=0.1)

        # Exit at same price
        ex.current_prices[SYMBOL] = {"price": Decimal("50000"), "time": NOW}
        result = ex.create_order(
            symbol=SYMBOL, order_type="market", side="BUY",
            amount=Decimal("0.1"), params={"reduceOnly": True},
        )
        assert result["pnl"] == pytest.approx(0.0, abs=1e-6)


class TestShortOrderTriggers:
    def test_short_sl_triggers_on_high(self):
        """BUY stop_market (SL for short) triggers when high >= stopPrice"""
        ex = make_exchange()
        open_short(ex, price=50000, amount=0.1)

        # Place BUY stop_market SL at 52000
        ex.create_order(
            symbol=SYMBOL,
            order_type="stop_market",
            side="BUY",
            amount=Decimal("0.1"),
            params={"stopPrice": Decimal("52000"), "reduceOnly": True},
        )
        assert len(ex.pending_orders) == 1

        # Candle with high >= 52000 → SL should trigger
        executed = ex.update_candle(
            symbol=SYMBOL,
            open_=50500, high=52100, low=50400, close=51000,
            timestamp=NOW + timedelta(hours=1),
        )

        assert len(executed) == 1, "SL should have triggered"
        assert executed[0]["side"] == "BUY"
        assert len(ex.pending_orders) == 0

    def test_short_sl_does_not_trigger_below_stop(self):
        """BUY stop_market does NOT trigger when high < stopPrice"""
        ex = make_exchange()
        open_short(ex, price=50000, amount=0.1)

        ex.create_order(
            symbol=SYMBOL, order_type="stop_market", side="BUY",
            amount=Decimal("0.1"),
            params={"stopPrice": Decimal("52000"), "reduceOnly": True},
        )

        # Candle with high < 52000 → SL should NOT trigger
        executed = ex.update_candle(
            symbol=SYMBOL,
            open_=50000, high=51500, low=49800, close=50200,
            timestamp=NOW + timedelta(hours=1),
        )

        assert len(executed) == 0
        assert len(ex.pending_orders) == 1  # Still pending

    def test_short_tp_triggers_on_low(self):
        """BUY limit (TP for short) triggers when low <= price"""
        ex = make_exchange()
        open_short(ex, price=50000, amount=0.1)

        # Place BUY limit TP at 48000
        ex.create_order(
            symbol=SYMBOL,
            order_type="limit",
            side="BUY",
            amount=Decimal("0.1"),
            price=Decimal("48000"),
            params={"reduceOnly": True},
        )
        assert len(ex.pending_orders) == 1

        # Candle with low <= 48000 → TP should trigger
        executed = ex.update_candle(
            symbol=SYMBOL,
            open_=49500, high=49600, low=47900, close=48200,
            timestamp=NOW + timedelta(hours=1),
        )

        assert len(executed) == 1, "TP should have triggered"
        assert executed[0]["side"] == "BUY"
        pnl = executed[0]["pnl"]
        assert pnl > 0, f"TP hit should have positive PnL, got {pnl}"

    def test_short_tp_does_not_trigger_above_price(self):
        """BUY limit TP does NOT trigger when low > price"""
        ex = make_exchange()
        open_short(ex, price=50000, amount=0.1)

        ex.create_order(
            symbol=SYMBOL, order_type="limit", side="BUY",
            amount=Decimal("0.1"), price=Decimal("48000"),
            params={"reduceOnly": True},
        )

        # Candle that doesn't reach TP
        executed = ex.update_candle(
            symbol=SYMBOL,
            open_=49500, high=50000, low=49000, close=49500,
            timestamp=NOW + timedelta(hours=1),
        )

        assert len(executed) == 0
        assert len(ex.pending_orders) == 1  # Still pending


class TestShortLiquidation:
    def test_short_liquidation_when_price_spikes_up(self):
        """Equity <= 0 when price spikes up enough to consume margin"""
        # Use leverage 10 with small balance to make liquidation easier to trigger
        ex = make_exchange(balance=1000, leverage=10)
        ex.current_prices[SYMBOL] = {"price": Decimal("50000"), "time": NOW}
        open_short(ex, price=50000, amount=0.2)  # margin = 50000*0.2/10 = 1000

        # Simulate extreme price spike that would wipe margin
        # With leverage 10, a 10% move wipes the margin
        # At entry 50000, margin = 1000. Loss at 55000 = (55000-50000)*0.2 = 1000
        ex.current_prices[SYMBOL] = {"price": Decimal("55001"), "time": NOW}

        liquidated = ex.check_liquidation(NOW)
        assert liquidated is True, "Should be liquidated when price spikes up"

    def test_no_liquidation_when_price_drops(self):
        """No liquidation when price drops (short is profitable)"""
        ex = make_exchange(balance=10000, leverage=5)
        ex.current_prices[SYMBOL] = {"price": Decimal("50000"), "time": NOW}
        open_short(ex, price=50000, amount=0.1)

        # Price drops — short is profitable, no liquidation
        ex.current_prices[SYMBOL] = {"price": Decimal("45000"), "time": NOW}

        liquidated = ex.check_liquidation(NOW)
        assert liquidated is False


class TestShortMarginAccounting:
    def test_short_margin_deducted_on_entry(self):
        """Margin is correctly deducted from free balance"""
        ex = make_exchange(balance=10000, leverage=2)
        ex.current_prices[SYMBOL] = {"price": Decimal("50000"), "time": NOW}
        open_short(ex, price=50000, amount=0.1)

        # notional = 50000 * 0.1 = 5000; margin = 5000/2 = 2500
        expected_margin = Decimal("2500")
        assert ex.margin_used.get(SYMBOL) == expected_margin
        assert ex.balance == Decimal("10000") - expected_margin

    def test_short_margin_returned_on_exit(self):
        """Margin returned to balance when short is closed"""
        ex = make_exchange(balance=10000, leverage=2)
        ex.taker_fee = Decimal("0")  # no fees for clarity
        ex.current_prices[SYMBOL] = {"price": Decimal("50000"), "time": NOW}
        open_short(ex, price=50000, amount=0.1)

        balance_after_entry = ex.balance
        margin_held = ex.margin_used.get(SYMBOL, Decimal("0"))
        assert margin_held > 0

        # Close at lower price (profit)
        ex.current_prices[SYMBOL] = {"price": Decimal("48000"), "time": NOW}
        ex.create_order(
            symbol=SYMBOL, order_type="market", side="BUY",
            amount=Decimal("0.1"), params={"reduceOnly": True},
        )

        # After close: margin freed + PnL added
        assert SYMBOL not in ex.margin_used or ex.margin_used.get(SYMBOL) == Decimal("0")
        # Balance should be back plus profit
        assert ex.balance > balance_after_entry


class TestReduceOnly:
    def test_reduce_only_caps_at_position(self):
        """BUY reduceOnly can't exceed abs(short position)"""
        ex = make_exchange()
        open_short(ex, price=50000, amount=0.1)  # position = -0.1

        # Try to close MORE than position with reduceOnly
        result = ex.create_order(
            symbol=SYMBOL,
            order_type="market",
            side="BUY",
            amount=Decimal("0.5"),  # More than 0.1 position
            params={"reduceOnly": True},
        )

        assert result is not None
        # Should only close 0.1 (capped at position size)
        assert float(result["amount"]) == pytest.approx(0.1)
        # Position should be fully closed
        assert ex.positions.get(SYMBOL) is None or abs(ex.positions.get(SYMBOL)) < Decimal("1e-8")

    def test_reduce_only_buy_no_position(self):
        """BUY reduceOnly returns None when no short position exists"""
        ex = make_exchange()
        # No position opened

        result = ex.create_order(
            symbol=SYMBOL,
            order_type="market",
            side="BUY",
            amount=Decimal("0.1"),
            params={"reduceOnly": True},
        )
        assert result is None

    def test_reduce_only_enforced_in_pending_orders(self):
        """reduceOnly pending BUY order is skipped if position was already closed"""
        ex = make_exchange()
        open_short(ex, price=50000, amount=0.1)

        # Place reduceOnly pending limit order (TP)
        ex.create_order(
            symbol=SYMBOL, order_type="limit", side="BUY",
            amount=Decimal("0.1"), price=Decimal("48000"),
            params={"reduceOnly": True},
        )

        # Manually close position first
        ex.create_order(
            symbol=SYMBOL, order_type="market", side="BUY",
            amount=Decimal("0.1"), params={"reduceOnly": True},
        )
        assert SYMBOL not in ex.positions

        # Candle that would trigger TP (but position is gone)
        executed = ex.update_candle(
            symbol=SYMBOL,
            open_=49500, high=49600, low=47500, close=48000,
            timestamp=NOW + timedelta(hours=1),
        )
        # Should not execute because position is gone (reduceOnly enforcement)
        assert len(executed) == 0
