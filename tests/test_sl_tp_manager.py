"""Tests for SLTPManager edge cases (M12 coverage gap)."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.core.actions import EXIT_BREAKEVEN, EXIT_LOCK_PROFIT, EXIT_STOP_LOSS, SIDE_BUY, SIDE_SELL
from app.core.events import SignalEvent
from app.trading.portfolio.models import Position
from app.trading.portfolio.sl_tp_manager import SLTPManager


@pytest.fixture
def mock_exchange():
    ex = MagicMock()
    ex.create_order.return_value = {"id": "order-1"}
    ex.cancel_order.return_value = True
    return ex


@pytest.fixture
def manager(mock_exchange):
    config = {"risk": {"tp1_close_pct": 0.50, "tp2_close_pct": 0.50}}
    return SLTPManager(mock_exchange, config)


def _make_signal(
    symbol="BTC/USDT", tp1=Decimal("110"), tp2=Decimal("120"), tp3=Decimal("130"), sl=Decimal("90"), allocs=None
):
    return SignalEvent(
        symbol=symbol,
        signal_type="BUY",
        price=Decimal("100"),
        timestamp=datetime.now(),
        tp1_price=tp1,
        tp2_price=tp2,
        tp3_price=tp3,
        sl_price=sl,
        tp_allocations=allocs,
    )


def _make_position(symbol="BTC/USDT", amount=Decimal("10"), side=SIDE_BUY, entry=Decimal("100"), sl_order_id=None):
    return Position(
        symbol=symbol,
        amount=amount,
        entry_price=entry,
        side=side,
        timestamp=datetime.now(),
        sl_order_id=sl_order_id,
    )


class TestSLExitReason:
    def test_breakeven(self):
        assert SLTPManager.sl_exit_reason(Decimal("100"), Decimal("100")) == EXIT_BREAKEVEN

    def test_lock_profit_long(self):
        assert SLTPManager.sl_exit_reason(Decimal("105"), Decimal("100"), SIDE_BUY) == EXIT_LOCK_PROFIT

    def test_stop_loss_short(self):
        # For SHORT: sl > entry means loss (price moved against us)
        assert SLTPManager.sl_exit_reason(Decimal("105"), Decimal("100"), SIDE_SELL) == EXIT_STOP_LOSS

    def test_lock_profit_short(self):
        assert SLTPManager.sl_exit_reason(Decimal("95"), Decimal("100"), SIDE_SELL) == EXIT_LOCK_PROFIT


class TestPlaceTPOrders:
    def test_short_position_tp_uses_buy_side(self, manager, mock_exchange):
        signal = _make_signal()
        manager.place_tp_orders(signal, Decimal("10"), position_side=SIDE_SELL)
        # All TP orders should use BUY (opposite of SELL position)
        for c in mock_exchange.create_order.call_args_list:
            assert c.kwargs["side"] == SIDE_BUY

    def test_default_allocations_consume_full_amount(self, manager, mock_exchange):
        signal = _make_signal()
        manager.place_tp_orders(signal, Decimal("10"), position_side=SIDE_BUY)
        # With tp1=50%, tp2=50% of remaining, tp3=100% of remaining
        assert mock_exchange.create_order.call_count == 3

    def test_custom_allocations(self, manager, mock_exchange):
        signal = _make_signal(allocs={"TP1": 0.3, "TP2": 0.3, "TP3": 1.0})
        manager.place_tp_orders(signal, Decimal("10"), position_side=SIDE_BUY)
        amounts = [c.kwargs["amount"] for c in mock_exchange.create_order.call_args_list]
        assert amounts[0] == Decimal("10") * Decimal("0.3")  # TP1: 3.0


class TestMoveSL:
    def test_zero_distance_sl_places_order(self, manager, mock_exchange):
        """SL at entry price should still place a stop_market order."""
        positions = {"BTC/USDT": _make_position(sl_order_id="old-sl")}
        result = manager.move_sl("BTC/USDT", positions, new_price=Decimal("100"))
        assert result is True
        mock_exchange.create_order.assert_called_once()
        assert mock_exchange.create_order.call_args.kwargs["order_type"] == "stop_market"


class TestCleanup:
    def test_cleanup_cancels_all_orders(self, manager, mock_exchange):
        pos = _make_position(sl_order_id="sl-1")
        pos.tp_order_ids = {"TP1": "tp-1", "TP2": "tp-2"}
        positions = {"BTC/USDT": pos}

        manager.cleanup_position("BTC/USDT", positions)

        assert "BTC/USDT" not in positions
        # Should have cancelled sl-1, tp-1, tp-2
        assert mock_exchange.cancel_order.call_count == 3
