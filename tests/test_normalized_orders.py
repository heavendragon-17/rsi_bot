"""
Tests for normalized order type vocabulary.
Validates MockExchange handles all order types correctly,
reduceOnly enforcement, and full TP/SL lifecycle.
"""
import pytest
from decimal import Decimal
from datetime import datetime

from app.backtest.mock_exchange import MockExchange
from app.trading.portfolio.manager import PortfolioManager, Position
from app.core.events import SignalEvent


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def exchange():
    """Fresh MockExchange with 10k balance, 10x leverage."""
    ex = MockExchange(initial_balance=10000, leverage=10)
    ex.update_candle("BTC/USDT", 50000, 50100, 49900, 50000, datetime(2025, 1, 1))
    return ex


@pytest.fixture
def portfolio(exchange):
    """PortfolioManager with standard config."""
    config = {
        "risk": {
            "max_position_size_pct": 0.99,
            "risk_per_trade_pct": 0.02,
            "use_risk_based_sizing": True,
            "min_sl_distance_pct": 0.003,
            "leverage": 10,
            "tp1_close_pct": 0.33,
            "tp2_close_pct": 0.50,
        },
        "backtest": {"initial_balance": 10000},
    }
    return PortfolioManager(exchange, config)


def _buy_signal(symbol="BTC/USDT", price=50000, sl=48000, tp1=51000, tp2=52000, tp3=53000):
    return SignalEvent(
        symbol=symbol,
        signal_type="BUY",
        price=Decimal(str(price)),
        timestamp=datetime(2025, 1, 1),
        reason="TEST_BUY",
        tp1_price=Decimal(str(tp1)),
        tp2_price=Decimal(str(tp2)),
        tp3_price=Decimal(str(tp3)),
        sl_price=Decimal(str(sl)),
        soft_sl_price=Decimal(str(sl + 500)),
    )


# ==============================================================================
# Test: MockExchange handles stop_market correctly
# ==============================================================================

class TestMockStopMarket:
    def test_create_order_stop_market_places_pending(self, exchange):
        """stop_market order should be pending, not immediately executed."""
        # First buy a position
        exchange.create_order("BTC/USDT", "market", "BUY", Decimal("0.1"), Decimal("50000"))

        # Place stop_market SL
        result = exchange.create_order(
            "BTC/USDT", "stop_market", "SELL", Decimal("0.1"),
            params={"stopPrice": Decimal("48000"), "reduceOnly": True},
        )

        assert result is not None
        assert result["status"] == "open"
        assert result["type"] == "stop_market"
        assert len(exchange.pending_orders) == 1

    def test_stop_market_triggers_on_low(self, exchange):
        """stop_market SL should trigger when candle low <= stopPrice."""
        exchange.create_order("BTC/USDT", "market", "BUY", Decimal("0.1"), Decimal("50000"))
        exchange.create_order(
            "BTC/USDT", "stop_market", "SELL", Decimal("0.1"),
            params={"stopPrice": Decimal("48000"), "reduceOnly": True},
        )

        # Candle that doesn't trigger SL (low = 49000)
        executed = exchange.update_candle("BTC/USDT", 50000, 50500, 49000, 50200, datetime(2025, 1, 2))
        assert len(executed) == 0
        assert len(exchange.pending_orders) == 1

        # Candle that triggers SL (low = 47500 <= 48000)
        executed = exchange.update_candle("BTC/USDT", 50200, 50300, 47500, 48500, datetime(2025, 1, 3))
        assert len(executed) == 1
        assert executed[0]["side"] == "SELL"
        assert float(executed[0]["price"]) == 48000.0
        assert len(exchange.pending_orders) == 0

    def test_stop_market_does_not_trigger_on_high(self, exchange):
        """stop_market SL should NOT trigger just because high is above stopPrice."""
        exchange.create_order("BTC/USDT", "market", "BUY", Decimal("0.1"), Decimal("50000"))
        exchange.create_order(
            "BTC/USDT", "stop_market", "SELL", Decimal("0.1"),
            params={"stopPrice": Decimal("48000"), "reduceOnly": True},
        )

        # Candle with high well above stop but low above stop — should NOT trigger
        executed = exchange.update_candle("BTC/USDT", 50000, 55000, 49000, 54000, datetime(2025, 1, 2))
        assert len(executed) == 0


# ==============================================================================
# Test: MockExchange handles limit TP correctly
# ==============================================================================

class TestMockLimitTP:
    def test_limit_tp_triggers_on_high(self, exchange):
        """Limit SELL (TP) should trigger when candle high >= price."""
        exchange.create_order("BTC/USDT", "market", "BUY", Decimal("0.1"), Decimal("50000"))
        exchange.create_order(
            "BTC/USDT", "limit", "SELL", Decimal("0.05"),
            price=Decimal("52000"),
            params={"reduceOnly": True, "exit_reason": "TP1"},
        )

        # Candle that triggers TP (high = 52500 >= 52000)
        executed = exchange.update_candle("BTC/USDT", 50500, 52500, 50000, 51000, datetime(2025, 1, 2))
        assert len(executed) == 1
        assert float(executed[0]["price"]) == 52000.0
        assert executed[0]["info"]["exit_reason"] == "TP1"

    def test_limit_tp_does_not_trigger_below(self, exchange):
        """Limit SELL (TP) should NOT trigger when high < price."""
        exchange.create_order("BTC/USDT", "market", "BUY", Decimal("0.1"), Decimal("50000"))
        exchange.create_order(
            "BTC/USDT", "limit", "SELL", Decimal("0.05"),
            price=Decimal("52000"),
            params={"reduceOnly": True},
        )

        executed = exchange.update_candle("BTC/USDT", 50500, 51500, 50000, 51000, datetime(2025, 1, 2))
        assert len(executed) == 0


# ==============================================================================
# Test: reduceOnly enforcement
# ==============================================================================

class TestReduceOnly:
    def test_reduce_only_prevents_short(self, exchange):
        """reduceOnly market SELL on zero position should return None."""
        result = exchange.create_order(
            "BTC/USDT", "market", "SELL", Decimal("1.0"),
            params={"reduceOnly": True},
        )
        assert result is None

    def test_reduce_only_caps_at_position(self, exchange):
        """reduceOnly should cap sell amount at current position size."""
        exchange.create_order("BTC/USDT", "market", "BUY", Decimal("0.1"), Decimal("50000"))

        result = exchange.create_order(
            "BTC/USDT", "market", "SELL", Decimal("0.5"),  # Trying to sell 5x position
            params={"reduceOnly": True},
        )
        assert result is not None
        assert float(result["amount"]) == pytest.approx(0.1, abs=1e-6)

    def test_reduce_only_cancels_pending_on_zero_position(self, exchange):
        """reduceOnly pending order should be cancelled if position is zero when triggered."""
        # Place stop_market without a position
        exchange.create_order(
            "BTC/USDT", "stop_market", "SELL", Decimal("0.1"),
            params={"stopPrice": Decimal("48000"), "reduceOnly": True},
        )

        # Trigger — should cancel, not execute
        executed = exchange.update_candle("BTC/USDT", 49000, 49500, 47000, 47500, datetime(2025, 1, 2))
        assert len(executed) == 0
        assert len(exchange.pending_orders) == 0  # Order was removed

    def test_reduce_only_caps_pending_order(self, exchange):
        """reduceOnly pending order should fill at most the current position."""
        exchange.create_order("BTC/USDT", "market", "BUY", Decimal("0.1"), Decimal("50000"))
        # SL for 0.5 (more than position)
        exchange.create_order(
            "BTC/USDT", "stop_market", "SELL", Decimal("0.5"),
            params={"stopPrice": Decimal("48000"), "reduceOnly": True},
        )

        executed = exchange.update_candle("BTC/USDT", 49000, 49500, 47000, 47500, datetime(2025, 1, 3))
        assert len(executed) == 1
        assert float(executed[0]["amount"]) == pytest.approx(0.1, abs=1e-6)


# ==============================================================================
# Test: Full TP/SL lifecycle
# ==============================================================================

class TestTPSLLifecycle:
    def test_buy_places_sl_and_tps(self, exchange, portfolio):
        """BUY signal should place market entry + stop_market SL + limit TPs."""
        signal = _buy_signal()
        order = portfolio.on_signal(signal)

        assert order is not None
        assert "BTC/USDT" in portfolio.positions

        pos = portfolio.positions["BTC/USDT"]
        # SL order placed
        assert pos.sl_order_id is not None
        # TP orders placed
        assert "TP1" in pos.tp_order_ids
        assert "TP2" in pos.tp_order_ids
        assert "TP3" in pos.tp_order_ids

        # Verify SL is stop_market type
        sl_order = exchange.pending_orders.get(pos.sl_order_id)
        assert sl_order is not None
        assert sl_order["order_subtype"] == "stop_market"
        assert sl_order["reduce_only"] is True

        # Verify TP1 is limit type
        tp1_order = exchange.pending_orders.get(pos.tp_order_ids["TP1"])
        assert tp1_order is not None
        assert tp1_order["order_subtype"] == "limit"
        assert tp1_order["reduce_only"] is True

    def test_tp1_fill_moves_sl_to_breakeven(self, exchange, portfolio):
        """After TP1 fills, SL should be moved to entry price (breakeven)."""
        signal = _buy_signal()
        portfolio.on_signal(signal)

        pos = portfolio.positions["BTC/USDT"]
        initial_amount = pos.amount
        old_sl_id = pos.sl_order_id

        # Candle triggers TP1 (high >= 51000)
        exchange.update_candle("BTC/USDT", 50500, 51500, 50000, 51200, datetime(2025, 1, 2))

        # Sync TP fills
        portfolio.sync_tp_fills("BTC/USDT")

        assert pos.tp1_hit is True
        assert pos.amount < initial_amount  # Position reduced
        assert "TP1" not in pos.tp_order_ids  # TP1 order removed

        # SL should have been replaced (new order ID)
        assert pos.sl_order_id is not None
        assert pos.sl_order_id != old_sl_id

        # New SL should be at entry price (breakeven)
        new_sl = exchange.pending_orders.get(pos.sl_order_id)
        assert new_sl is not None
        assert float(new_sl["triggerPrice"]) == 50000.0

    def test_sl_fires_cancels_remaining_tps(self, exchange, portfolio):
        """When SL triggers, position closes and remaining TP orders should be cancellable."""
        signal = _buy_signal()
        portfolio.on_signal(signal)

        pos = portfolio.positions["BTC/USDT"]
        tp_ids = dict(pos.tp_order_ids)

        # Candle triggers SL (low <= 48000)
        exchange.update_candle("BTC/USDT", 49000, 49500, 47500, 48000, datetime(2025, 1, 2))

        # Position should be gone from exchange
        assert "BTC/USDT" not in exchange.positions

        # sync_from_exchange should clean up portfolio
        portfolio.sync_from_exchange()
        assert "BTC/USDT" not in portfolio.positions

    def test_full_lifecycle_tp1_tp2(self, exchange, portfolio):
        """Full lifecycle: BUY → TP1 fills → TP2 fills → position closes."""
        signal = _buy_signal()
        portfolio.on_signal(signal)

        pos = portfolio.positions["BTC/USDT"]
        initial_amount = pos.amount

        # TP1 triggers
        exchange.update_candle("BTC/USDT", 50500, 51500, 50000, 51200, datetime(2025, 1, 2))
        portfolio.sync_tp_fills("BTC/USDT")
        assert pos.tp1_hit is True
        amount_after_tp1 = pos.amount
        assert amount_after_tp1 < initial_amount

        # TP2 triggers
        exchange.update_candle("BTC/USDT", 51500, 52500, 51000, 52200, datetime(2025, 1, 3))
        portfolio.sync_tp_fills("BTC/USDT")
        assert pos.tp2_hit is True
        amount_after_tp2 = pos.amount
        assert amount_after_tp2 < amount_after_tp1

        # TP3 triggers — full close
        exchange.update_candle("BTC/USDT", 52500, 53500, 52000, 53200, datetime(2025, 1, 4))
        portfolio.sync_tp_fills("BTC/USDT")
        # Position should be fully closed
        assert "BTC/USDT" not in portfolio.positions


# ==============================================================================
# Test: Soft SL race condition
# ==============================================================================

class TestSoftSLRaceCondition:
    def test_soft_sl_after_hard_sl_no_double_sell(self, exchange, portfolio):
        """If hard SL already fired, soft SL signal should not create a short."""
        signal = _buy_signal()
        portfolio.on_signal(signal)

        # Hard SL triggers
        exchange.update_candle("BTC/USDT", 49000, 49500, 47500, 48000, datetime(2025, 1, 2))
        assert "BTC/USDT" not in exchange.positions

        # Soft SL signal arrives
        soft_sl_signal = SignalEvent(
            symbol="BTC/USDT",
            signal_type="SELL",
            price=Decimal("48500"),
            timestamp=datetime(2025, 1, 2),
            reason="SOFT_SL",
        )
        result = portfolio.on_signal(soft_sl_signal)

        # Should not execute (position already gone)
        assert result is None
        assert "BTC/USDT" not in portfolio.positions
        # No short position should exist
        assert exchange.positions.get("BTC/USDT", Decimal("0")) <= Decimal("0")


# ==============================================================================
# Test: Startup cleanup
# ==============================================================================

class TestStartupCleanup:
    def test_cleanup_closes_orphan_positions(self, exchange):
        """Runner startup should close orphan positions."""
        from app.trading.runner import MultiSymbolRunner
        from unittest.mock import MagicMock

        # Create orphan position
        exchange.create_order("BTC/USDT", "market", "BUY", Decimal("0.1"), Decimal("50000"))
        assert "BTC/USDT" in exchange.positions

        # Create a minimal runner (mock what we can't instantiate)
        runner = MultiSymbolRunner.__new__(MultiSymbolRunner)
        runner.exchange = exchange
        runner.telegram = None
        runner.config = {"risk": {"leverage": 10}}
        runner.symbols = ["BTC/USDT"]

        runner._cleanup_on_startup()

        # Position should be closed
        assert "BTC/USDT" not in exchange.positions


# ==============================================================================
# Test: cancel_all_orders / fetch_open_orders
# ==============================================================================

class TestOrderManagement:
    def test_cancel_all_orders(self, exchange):
        """cancel_all_orders should remove all pending orders for a symbol."""
        exchange.create_order("BTC/USDT", "market", "BUY", Decimal("0.1"), Decimal("50000"))
        exchange.create_order("BTC/USDT", "stop_market", "SELL", Decimal("0.1"),
                              params={"stopPrice": Decimal("48000"), "reduceOnly": True})
        exchange.create_order("BTC/USDT", "limit", "SELL", Decimal("0.05"),
                              price=Decimal("52000"), params={"reduceOnly": True})

        assert len(exchange.pending_orders) == 2
        cancelled = exchange.cancel_all_orders("BTC/USDT")
        assert cancelled == 2
        assert len(exchange.pending_orders) == 0

    def test_fetch_open_orders(self, exchange):
        """fetch_open_orders should return all pending orders for a symbol."""
        exchange.create_order("BTC/USDT", "market", "BUY", Decimal("0.1"), Decimal("50000"))
        exchange.create_order("BTC/USDT", "stop_market", "SELL", Decimal("0.1"),
                              params={"stopPrice": Decimal("48000")})
        exchange.create_order("BTC/USDT", "limit", "SELL", Decimal("0.05"),
                              price=Decimal("52000"))

        orders = exchange.fetch_open_orders("BTC/USDT")
        assert len(orders) == 2
        types = {o["type"] for o in orders}
        assert "stop_market" in types
        assert "limit" in types

    def test_fetch_order_pending(self, exchange):
        """fetch_order on pending order should return status=open."""
        exchange.create_order("BTC/USDT", "market", "BUY", Decimal("0.1"), Decimal("50000"))
        result = exchange.create_order("BTC/USDT", "stop_market", "SELL", Decimal("0.1"),
                                        params={"stopPrice": Decimal("48000")})

        fetched = exchange.fetch_order(result["id"], "BTC/USDT")
        assert fetched["status"] == "open"

    def test_fetch_order_filled(self, exchange):
        """fetch_order on filled order should return status=closed."""
        exchange.create_order("BTC/USDT", "market", "BUY", Decimal("0.1"), Decimal("50000"))
        result = exchange.create_order("BTC/USDT", "stop_market", "SELL", Decimal("0.1"),
                                        params={"stopPrice": Decimal("48000"), "reduceOnly": True})

        order_id = result["id"]
        exchange.update_candle("BTC/USDT", 49000, 49500, 47000, 47500, datetime(2025, 1, 2))

        fetched = exchange.fetch_order(order_id, "BTC/USDT")
        assert fetched["status"] == "closed"
