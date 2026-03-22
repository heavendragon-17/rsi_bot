# tests/test_sim_exchange.py
"""
Unit tests for SimExchange order simulation engine.

Tests are isolated — each creates a fresh SimExchange with a mocked notifier
so no Telegram or network calls are made.
"""

from __future__ import annotations

import time
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import OrderRejectedError
from app.trading.exchange.sim.sim_exchange import MAKER_FEE, TAKER_FEE, SimExchange
from app.trading.exchange.sim.sim_state import SimTradeState

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _config(balance: float = 10_000) -> dict:
    return {
        "bot": {"mode": "sim"},
        "sim": {
            "initial_balance": balance,
            "telegram_token": "",
        },
        "risk": {"leverage": 10},
    }


@pytest.fixture()
def exchange():
    """SimExchange with notifications fully mocked out."""
    return _make_exchange()


def _make_exchange(balance: float = 10_000) -> SimExchange:
    """Construct SimExchange without any Telegram calls."""
    cfg = _config(balance)
    ex = SimExchange.__new__(SimExchange)
    ex._config = cfg
    ex._last_prices = {}
    ex._sim_time = None
    ex.state = SimTradeState(Decimal(str(balance)))
    ex._notification_service = MagicMock()
    return ex


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _open_position(ex: SimExchange, symbol="BTC/USDT", amount="0.01", entry="95000"):
    """Place a market BUY and immediately fill it via on_kline_open."""
    ex.create_order(symbol, "market", "BUY", Decimal(amount))
    ex.on_kline_open(symbol, Decimal(entry))


# ---------------------------------------------------------------------------
# 1. Market entry fills at next candle open (pending_open lifecycle)
# ---------------------------------------------------------------------------


class TestMarketEntryFill:
    def test_entry_queued_as_pending_open(self):
        ex = _make_exchange()
        ex.create_order("BTC/USDT", "market", "BUY", Decimal("0.01"))
        assert len(ex.state.pending_orders) == 1
        order = next(iter(ex.state.pending_orders.values()))
        assert order.status == "pending_open"

    def test_entry_does_not_fill_before_kline_open(self):
        ex = _make_exchange()
        ex.create_order("BTC/USDT", "market", "BUY", Decimal("0.01"))
        # on_tick should not fill a pending_open order
        ex.on_tick("BTC/USDT", Decimal("95000"), time.time())
        assert len(ex.state.pending_orders) == 1  # still pending

    def test_entry_fills_at_kline_open_price(self):
        ex = _make_exchange()
        ex.create_order("BTC/USDT", "market", "BUY", Decimal("0.01"))
        ex.on_kline_open("BTC/USDT", Decimal("95420"))
        # Order removed from pending, position created
        assert len(ex.state.pending_orders) == 0
        assert "BTC/USDT" in ex.state.positions
        pos = ex.state.positions["BTC/USDT"]
        assert pos.entry_price == Decimal("95420")
        assert pos.amount == Decimal("0.01")

    def test_entry_fee_deducted_from_balance(self):
        ex = _make_exchange(10_000)
        ex.create_order("BTC/USDT", "market", "BUY", Decimal("0.01"))
        ex.on_kline_open("BTC/USDT", Decimal("100000"))
        # fee = 100000 * 0.01 * 0.0005 = 0.50 USDT
        expected_fee = Decimal("100000") * Decimal("0.01") * TAKER_FEE
        assert ex.state.balance == Decimal("10000") - expected_fee

    def test_entry_wrong_symbol_not_filled(self):
        ex = _make_exchange()
        ex.create_order("BTC/USDT", "market", "BUY", Decimal("0.01"))
        ex.on_kline_open("ETH/USDT", Decimal("3000"))  # different symbol
        assert len(ex.state.pending_orders) == 1  # BTC order still pending


# ---------------------------------------------------------------------------
# 2. Soft SL — market reduceOnly fills immediately at latest tick price
# ---------------------------------------------------------------------------


class TestSoftSL:
    def test_soft_sl_fills_immediately(self):
        ex = _make_exchange()
        _open_position(ex, entry="100000")
        ex._last_prices["BTC/USDT"] = Decimal("99000")
        ex.create_order("BTC/USDT", "market", "SELL", Decimal("0.01"), params={"reduceOnly": True})
        # Position should be closed
        assert "BTC/USDT" not in ex.state.positions

    def test_soft_sl_skipped_if_no_tick_price(self):
        ex = _make_exchange()
        _open_position(ex, entry="100000")
        # No last price set → raises OrderRejectedError (cannot fill without price)
        with pytest.raises(OrderRejectedError):
            ex.create_order("BTC/USDT", "market", "SELL", Decimal("0.01"), params={"reduceOnly": True})

    def test_reduce_only_skipped_if_no_position(self):
        ex = _make_exchange()
        ex._last_prices["BTC/USDT"] = Decimal("95000")
        result = ex.create_order(
            "BTC/USDT", "stop_market", "SELL", Decimal("0.01"), params={"stopPrice": "94000", "reduceOnly": True}
        )
        assert result is None
        assert len(ex.state.pending_orders) == 0


# ---------------------------------------------------------------------------
# 3. Limit TP fills on tick
# ---------------------------------------------------------------------------


class TestLimitTPFill:
    def test_tp_fills_when_tick_at_or_above_price(self):
        ex = _make_exchange()
        _open_position(ex, entry="95000", amount="0.03")
        tp_id = ex.create_order(
            "BTC/USDT",
            "limit",
            "SELL",
            Decimal("0.01"),
            price=Decimal("97000"),
            params={"reduceOnly": True},
        )["id"]
        assert tp_id in ex.state.pending_orders
        ex.on_tick("BTC/USDT", Decimal("97000"), time.time())
        assert tp_id not in ex.state.pending_orders  # filled

    def test_tp_does_not_fill_below_price(self):
        ex = _make_exchange()
        _open_position(ex, entry="95000", amount="0.03")
        tp_id = ex.create_order(
            "BTC/USDT",
            "limit",
            "SELL",
            Decimal("0.01"),
            price=Decimal("97000"),
            params={"reduceOnly": True},
        )["id"]
        ex.on_tick("BTC/USDT", Decimal("96999"), time.time())
        assert tp_id in ex.state.pending_orders  # not yet filled

    def test_tp_fill_uses_maker_fee(self):
        ex = _make_exchange(10_000)
        _open_position(ex, entry="100000", amount="0.01")
        balance_after_entry = ex.state.balance
        ex.create_order(
            "BTC/USDT",
            "limit",
            "SELL",
            Decimal("0.01"),
            price=Decimal("102000"),
            params={"reduceOnly": True},
        )
        ex.on_tick("BTC/USDT", Decimal("102000"), time.time())
        # pnl_gross = (102000 - 100000) * 0.01 = 20
        # fee = 102000 * 0.01 * 0.0002 = 0.204
        pnl_gross = (Decimal("102000") - Decimal("100000")) * Decimal("0.01")
        fee = Decimal("102000") * Decimal("0.01") * MAKER_FEE
        expected_balance = balance_after_entry + pnl_gross - fee
        assert abs(ex.state.balance - expected_balance) < Decimal("0.001")

    def test_tp_fill_reduces_position_amount(self):
        ex = _make_exchange()
        _open_position(ex, entry="95000", amount="0.03")
        ex.create_order(
            "BTC/USDT",
            "limit",
            "SELL",
            Decimal("0.01"),
            price=Decimal("97000"),
            params={"reduceOnly": True},
        )
        ex.on_tick("BTC/USDT", Decimal("97000"), time.time())
        pos = ex.state.positions.get("BTC/USDT")
        assert pos is not None
        assert abs(pos.amount - Decimal("0.02")) < Decimal("0.000001")


# ---------------------------------------------------------------------------
# 4. Stop-market SL fills on tick
# ---------------------------------------------------------------------------


class TestStopMarketSLFill:
    def test_sl_fills_when_tick_at_or_below_stop(self):
        ex = _make_exchange()
        _open_position(ex, entry="95000")
        sl_id = ex.create_order(
            "BTC/USDT",
            "stop_market",
            "SELL",
            Decimal("0.01"),
            params={"stopPrice": "94000", "reduceOnly": True},
        )["id"]
        ex.on_tick("BTC/USDT", Decimal("94000"), time.time())
        assert sl_id not in ex.state.pending_orders
        assert "BTC/USDT" not in ex.state.positions

    def test_sl_does_not_fill_above_stop(self):
        ex = _make_exchange()
        _open_position(ex, entry="95000")
        sl_id = ex.create_order(
            "BTC/USDT",
            "stop_market",
            "SELL",
            Decimal("0.01"),
            params={"stopPrice": "94000", "reduceOnly": True},
        )["id"]
        ex.on_tick("BTC/USDT", Decimal("94001"), time.time())
        assert sl_id in ex.state.pending_orders

    def test_sl_fill_price_is_stop_price_not_tick(self):
        """SL fills at stop_price, not the tick price (which may gap below)."""
        ex = _make_exchange(10_000)
        _open_position(ex, entry="100000", amount="0.01")
        balance_after_entry = ex.state.balance
        ex.create_order(
            "BTC/USDT",
            "stop_market",
            "SELL",
            Decimal("0.01"),
            params={"stopPrice": "94000", "reduceOnly": True},
        )
        # Tick gaps below stop price
        ex.on_tick("BTC/USDT", Decimal("90000"), time.time())
        pnl_gross = (Decimal("94000") - Decimal("100000")) * Decimal("0.01")
        fee = Decimal("94000") * Decimal("0.01") * TAKER_FEE
        expected = balance_after_entry + pnl_gross - fee
        assert abs(ex.state.balance - expected) < Decimal("0.001")

    def test_sl_fill_uses_taker_fee(self):
        ex = _make_exchange(10_000)
        _open_position(ex, entry="100000", amount="0.01")
        balance_after_entry = ex.state.balance
        ex.create_order(
            "BTC/USDT",
            "stop_market",
            "SELL",
            Decimal("0.01"),
            params={"stopPrice": "98000", "reduceOnly": True},
        )
        ex.on_tick("BTC/USDT", Decimal("97000"), time.time())
        fee = Decimal("98000") * Decimal("0.01") * TAKER_FEE
        pnl_gross = (Decimal("98000") - Decimal("100000")) * Decimal("0.01")
        expected = balance_after_entry + pnl_gross - fee
        assert abs(ex.state.balance - expected) < Decimal("0.001")


# ---------------------------------------------------------------------------
# 5. Cancel / cancel_all
# ---------------------------------------------------------------------------


class TestCancelOrders:
    def test_cancel_single_order(self):
        ex = _make_exchange()
        _open_position(ex)
        result = ex.create_order(
            "BTC/USDT",
            "stop_market",
            "SELL",
            Decimal("0.01"),
            params={"stopPrice": "94000", "reduceOnly": True},
        )
        order_id = result["id"]
        assert ex.cancel_order(order_id, "BTC/USDT") is True
        assert order_id not in ex.state.pending_orders

    def test_cancel_nonexistent_returns_false(self):
        ex = _make_exchange()
        assert ex.cancel_order("nonexistent-id", "BTC/USDT") is False

    def test_cancel_all_orders_for_symbol(self):
        ex = _make_exchange()
        _open_position(ex, amount="0.03")
        ex.create_order(
            "BTC/USDT", "stop_market", "SELL", Decimal("0.01"), params={"stopPrice": "94000", "reduceOnly": True}
        )
        ex.create_order(
            "BTC/USDT", "limit", "SELL", Decimal("0.01"), price=Decimal("97000"), params={"reduceOnly": True}
        )
        count = ex.cancel_all_orders("BTC/USDT")
        assert count == 2
        assert len(ex.state.pending_orders) == 0


# ---------------------------------------------------------------------------
# 6. R-multiple calculation
# ---------------------------------------------------------------------------


class TestRMultiple:
    def test_r_multiple_on_full_close(self):
        ex = _make_exchange(10_000)
        # Open at 100000, SL at 99000 → initial_risk = (100000-99000)*0.01 = 10 USDT
        _open_position(ex, entry="100000", amount="0.01")
        ex.create_order(
            "BTC/USDT", "stop_market", "SELL", Decimal("0.01"), params={"stopPrice": "99000", "reduceOnly": True}
        )
        # Close at 102000 → pnl_gross = 20, fee(maker) ≈ 0.204 → r ≈ 1.98R
        ex.create_order(
            "BTC/USDT", "limit", "SELL", Decimal("0.01"), price=Decimal("102000"), params={"reduceOnly": True}
        )
        ex.on_tick("BTC/USDT", Decimal("102000"), time.time())
        trade = ex.state.closed_trades[-1]
        # Verify: r_multiple == pnl_net / initial_risk (both computed by exchange)
        assert trade.r_multiple > Decimal("1"), f"Expected r > 1 for profitable trade, got {trade.r_multiple}"
        assert trade.pnl_net > Decimal("0")

    def test_negative_r_on_sl(self):
        ex = _make_exchange(10_000)
        _open_position(ex, entry="100000", amount="0.01")
        ex.create_order(
            "BTC/USDT", "stop_market", "SELL", Decimal("0.01"), params={"stopPrice": "99000", "reduceOnly": True}
        )
        ex.on_tick("BTC/USDT", Decimal("99000"), time.time())
        trade = ex.state.closed_trades[-1]
        assert trade.pnl_net < Decimal("0")
        # r_multiple = pnl_net / initial_risk (computed inside _execute_fill)
        # If initial_risk > 0 it should be negative; if 0 it stays 0
        assert trade.r_multiple <= Decimal("0"), f"Expected r_multiple ≤ 0 on SL hit, got {trade.r_multiple}"


# ---------------------------------------------------------------------------
# 7. Pause / toggle
# ---------------------------------------------------------------------------


class TestPauseBehavior:
    def test_is_paused_returns_state(self):
        ex = _make_exchange()
        assert ex.is_paused() is False
        ex.state.is_paused = True
        assert ex.is_paused() is True

    def test_pause_does_not_stop_tick_scanner(self):
        """Tick scanner must still run when paused (positions still monitored)."""
        ex = _make_exchange()
        _open_position(ex, entry="100000", amount="0.01")
        sl_id = ex.create_order(
            "BTC/USDT",
            "stop_market",
            "SELL",
            Decimal("0.01"),
            params={"stopPrice": "94000", "reduceOnly": True},
        )["id"]
        ex.state.is_paused = True
        # on_tick should still fire and fill the SL
        ex.on_tick("BTC/USDT", Decimal("93000"), time.time())
        assert sl_id not in ex.state.pending_orders


# ---------------------------------------------------------------------------
# 8. Reset
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_restores_balance(self):
        ex = _make_exchange(10_000)
        _open_position(ex, entry="100000", amount="0.01")
        ex.state.balance -= Decimal("500")
        ex.state.reset()
        assert ex.state.balance == Decimal("10000")

    def test_reset_clears_positions_and_orders(self):
        ex = _make_exchange()
        _open_position(ex)
        ex.create_order(
            "BTC/USDT", "stop_market", "SELL", Decimal("0.01"), params={"stopPrice": "94000", "reduceOnly": True}
        )
        ex.state.reset()
        assert len(ex.state.positions) == 0
        assert len(ex.state.pending_orders) == 0
        assert len(ex.state.closed_trades) == 0


# ---------------------------------------------------------------------------
# 9. fetch_balance / fetch_positions
# ---------------------------------------------------------------------------


class TestQueryMethods:
    def test_fetch_balance_returns_ccxt_format(self):
        ex = _make_exchange(10_000)
        bal = ex.fetch_balance()
        assert "USDT" in bal
        assert bal["USDT"]["free"] == pytest.approx(10_000, rel=1e-3)

    def test_fetch_positions_returns_open_positions(self):
        ex = _make_exchange()
        _open_position(ex, entry="95000", amount="0.01")
        positions = ex.fetch_positions()
        assert len(positions) == 1
        assert positions[0]["symbol"] == "BTC/USDT"
        assert positions[0]["contracts"] == pytest.approx(0.01)

    def test_fetch_positions_empty_when_no_trades(self):
        ex = _make_exchange()
        assert ex.fetch_positions() == []
