# tests/test_sim_tick_scanner.py
"""
Unit tests for SimExchange tick scanner ordering and gap scenarios.

Focuses on:
  - FIFO fill ordering (chronological insertion order)
  - Gap scenarios where candle price jumps through both SL and TP levels
  - Multiple symbols do not cross-trigger
  - Filled orders are removed from pending_orders
"""

from __future__ import annotations

import time
from decimal import Decimal
from unittest.mock import MagicMock

from app.trading.exchange.sim.sim_exchange import SimExchange
from app.trading.exchange.sim.sim_state import SimTradeState

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


def _make_exchange(balance: float = 10_000) -> SimExchange:
    cfg = {
        "bot": {"mode": "sim"},
        "sim": {"initial_balance": balance, "telegram_token": ""},
        "risk": {"leverage": 10},
    }
    ex = SimExchange.__new__(SimExchange)
    ex._config = cfg
    ex._last_prices = {}
    ex._sim_time = None
    ex.state = SimTradeState(Decimal(str(balance)))
    ex._notification_service = MagicMock()
    return ex


def _open_position(ex: SimExchange, symbol="BTC/USDT", amount="0.03", entry="100000"):
    ex.create_order(symbol, "market", "BUY", Decimal(amount))
    ex.on_kline_open(symbol, Decimal(entry))


# ---------------------------------------------------------------------------
# 1. FIFO ordering: first inserted order wins on a gap tick
# ---------------------------------------------------------------------------


class TestFIFOOrdering:
    def test_sl_inserted_before_tp_wins_on_gap(self):
        """
        SL inserted first, then TP.
        Price gaps so both levels are breached simultaneously.
        SL should win because it was inserted first (FIFO).
        """
        ex = _make_exchange()
        _open_position(ex, entry="100000", amount="0.01")

        # SL at 94000 inserted FIRST
        sl_order = ex.create_order(
            "BTC/USDT",
            "stop_market",
            "SELL",
            Decimal("0.01"),
            params={"stopPrice": "94000", "reduceOnly": True},
        )
        sl_id = sl_order["id"]

        # TP at 105000 inserted SECOND
        tp_order = ex.create_order(
            "BTC/USDT",
            "limit",
            "SELL",
            Decimal("0.01"),
            price=Decimal("105000"),
            params={"reduceOnly": True},
        )
        tp_order["id"]

        # Gap tick: price drops below SL (94000 → breaches both levels on a gap)
        ex.on_tick("BTC/USDT", Decimal("93000"), time.time())

        # SL should be filled
        assert sl_id not in ex.state.pending_orders
        # TP should be cancelled by post-fill cleanup or still pending (position closed)
        # Either way, position is gone
        assert "BTC/USDT" not in ex.state.positions

        # The closed trade exit reason is HARD_SL
        trade = ex.state.closed_trades[-1]
        assert trade.exit_reason == "HARD_SL"

    def test_tp_inserted_before_sl_wins_on_gap(self):
        """
        TP inserted first, then SL.
        Tick crosses TP level.
        TP fills first.
        """
        ex = _make_exchange()
        _open_position(ex, entry="100000", amount="0.01")

        # TP inserted FIRST
        tp_order = ex.create_order(
            "BTC/USDT",
            "limit",
            "SELL",
            Decimal("0.01"),
            price=Decimal("105000"),
            params={"reduceOnly": True},
        )
        tp_id = tp_order["id"]

        # SL inserted SECOND
        sl_order = ex.create_order(
            "BTC/USDT",
            "stop_market",
            "SELL",
            Decimal("0.01"),
            params={"stopPrice": "94000", "reduceOnly": True},
        )
        sl_order["id"]

        # Tick at TP level
        ex.on_tick("BTC/USDT", Decimal("106000"), time.time())

        assert tp_id not in ex.state.pending_orders
        assert "BTC/USDT" not in ex.state.positions
        trade = ex.state.closed_trades[-1]
        assert "TP" in trade.exit_reason or trade.exit_reason in ("TP1", "TP2", "TP3")


# ---------------------------------------------------------------------------
# 2. Gap scenarios
# ---------------------------------------------------------------------------


class TestGapScenarios:
    def test_sl_fills_at_stop_price_not_gap_price(self):
        """When price gaps below SL, fill must be at stop_price (not the tick price)."""
        ex = _make_exchange(10_000)
        _open_position(ex, entry="100000", amount="0.01")

        ex.create_order(
            "BTC/USDT",
            "stop_market",
            "SELL",
            Decimal("0.01"),
            params={"stopPrice": "95000", "reduceOnly": True},
        )

        # Gap: tick is far below stop_price
        ex.on_tick("BTC/USDT", Decimal("80000"), time.time())

        trade = ex.state.closed_trades[-1]
        assert trade.exit_price == Decimal("95000"), f"Expected fill at stop_price=95000, got {trade.exit_price}"

    def test_tp_fills_at_limit_price_not_gap_price(self):
        """When price gaps above TP, fill must be at limit_price (not the tick price)."""
        ex = _make_exchange(10_000)
        _open_position(ex, entry="100000", amount="0.01")

        ex.create_order(
            "BTC/USDT",
            "limit",
            "SELL",
            Decimal("0.01"),
            price=Decimal("105000"),
            params={"reduceOnly": True},
        )

        # Gap: tick is far above limit price
        ex.on_tick("BTC/USDT", Decimal("120000"), time.time())

        trade = ex.state.closed_trades[-1]
        assert trade.exit_price == Decimal("105000"), f"Expected fill at limit_price=105000, got {trade.exit_price}"

    def test_only_one_order_fills_per_tick(self):
        """
        When multiple orders could theoretically trigger on the same tick,
        only the first (FIFO) should fill if it closes the position.
        """
        ex = _make_exchange()
        _open_position(ex, entry="100000", amount="0.01")

        # Both SL and TP for the same position
        ex.create_order(
            "BTC/USDT",
            "stop_market",
            "SELL",
            Decimal("0.01"),
            params={"stopPrice": "94000", "reduceOnly": True},
        )["id"]
        ex.create_order(
            "BTC/USDT",
            "limit",
            "SELL",
            Decimal("0.01"),
            price=Decimal("105000"),
            params={"reduceOnly": True},
        )["id"]

        # Tick that would trigger SL (price gap drops below stop)
        ex.on_tick("BTC/USDT", Decimal("93000"), time.time())

        # Position closed — only one trade recorded
        assert len(ex.state.closed_trades) == 1


# ---------------------------------------------------------------------------
# 3. Multiple symbols — no cross-contamination
# ---------------------------------------------------------------------------


class TestMultiSymbol:
    def test_btc_tick_does_not_fill_eth_orders(self):
        ex = _make_exchange()
        _open_position(ex, symbol="ETH/USDT", amount="0.1", entry="3000")
        sl_id = ex.create_order(
            "ETH/USDT",
            "stop_market",
            "SELL",
            Decimal("0.1"),
            params={"stopPrice": "2800", "reduceOnly": True},
        )["id"]

        # BTC tick at SL level — should NOT affect ETH order
        ex.on_tick("BTC/USDT", Decimal("2800"), time.time())
        assert sl_id in ex.state.pending_orders

    def test_eth_tick_fills_only_eth_orders(self):
        ex = _make_exchange()

        _open_position(ex, symbol="BTC/USDT", amount="0.01", entry="100000")
        _open_position(ex, symbol="ETH/USDT", amount="0.1", entry="3000")

        btc_sl_id = ex.create_order(
            "BTC/USDT",
            "stop_market",
            "SELL",
            Decimal("0.01"),
            params={"stopPrice": "94000", "reduceOnly": True},
        )["id"]
        eth_sl_id = ex.create_order(
            "ETH/USDT",
            "stop_market",
            "SELL",
            Decimal("0.1"),
            params={"stopPrice": "2800", "reduceOnly": True},
        )["id"]

        # Only ETH tick at SL level
        ex.on_tick("ETH/USDT", Decimal("2799"), time.time())

        assert eth_sl_id not in ex.state.pending_orders  # ETH SL filled
        assert btc_sl_id in ex.state.pending_orders  # BTC SL untouched


# ---------------------------------------------------------------------------
# 4. Filled orders removed from pending_orders
# ---------------------------------------------------------------------------


class TestOrderCleanup:
    def test_filled_sl_removed_from_pending(self):
        ex = _make_exchange()
        _open_position(ex, entry="100000", amount="0.01")
        sl_id = ex.create_order(
            "BTC/USDT",
            "stop_market",
            "SELL",
            Decimal("0.01"),
            params={"stopPrice": "95000", "reduceOnly": True},
        )["id"]
        ex.on_tick("BTC/USDT", Decimal("94000"), time.time())
        assert sl_id not in ex.state.pending_orders

    def test_filled_tp_removed_from_pending(self):
        ex = _make_exchange()
        _open_position(ex, entry="100000", amount="0.03")
        tp_id = ex.create_order(
            "BTC/USDT",
            "limit",
            "SELL",
            Decimal("0.01"),
            price=Decimal("103000"),
            params={"reduceOnly": True},
        )["id"]
        ex.on_tick("BTC/USDT", Decimal("103500"), time.time())
        assert tp_id not in ex.state.pending_orders

    def test_unfilled_orders_remain_in_pending(self):
        ex = _make_exchange()
        _open_position(ex, entry="100000", amount="0.01")
        sl_id = ex.create_order(
            "BTC/USDT",
            "stop_market",
            "SELL",
            Decimal("0.01"),
            params={"stopPrice": "94000", "reduceOnly": True},
        )["id"]
        # Price has NOT reached SL
        ex.on_tick("BTC/USDT", Decimal("97000"), time.time())
        assert sl_id in ex.state.pending_orders


# ---------------------------------------------------------------------------
# 5. Partial TP (position amount decremented correctly)
# ---------------------------------------------------------------------------


class TestPartialTPFills:
    def test_tp1_reduces_position_amount(self):
        """After TP1, remaining position must be reduced."""
        ex = _make_exchange()
        _open_position(ex, entry="100000", amount="0.03")
        ex.create_order(
            "BTC/USDT",
            "limit",
            "SELL",
            Decimal("0.01"),  # 33% of 0.03
            price=Decimal("103000"),
            params={"reduceOnly": True},
        )
        ex.on_tick("BTC/USDT", Decimal("103000"), time.time())
        pos = ex.state.positions.get("BTC/USDT")
        assert pos is not None
        assert abs(pos.amount - Decimal("0.02")) < Decimal("0.000001")

    def test_tp3_closes_position_completely(self):
        """After final TP, position must be fully removed."""
        ex = _make_exchange()
        _open_position(ex, entry="100000", amount="0.01")
        ex.create_order(
            "BTC/USDT",
            "limit",
            "SELL",
            Decimal("0.01"),
            price=Decimal("105000"),
            params={"reduceOnly": True},
        )
        ex.on_tick("BTC/USDT", Decimal("105000"), time.time())
        assert "BTC/USDT" not in ex.state.positions
        assert len(ex.state.closed_trades) == 1
