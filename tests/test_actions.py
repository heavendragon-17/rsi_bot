"""
Tests for typed action objects (app/core/actions.py).

Verifies that actions are frozen dataclasses with the expected fields,
and that the Action union type covers all action classes.
"""
import pytest
from decimal import Decimal
from app.core.actions import (
    Action, ClosePosition, DoNothing, MoveSL, OpenPosition, PartialClose,
)


def test_open_position_fields():
    action = OpenPosition(
        symbol="BTC/USDT",
        side="BUY",
        entry_price=Decimal("100"),
        sl_price=Decimal("95"),
        soft_sl_price=Decimal("96"),
        tp_prices=[Decimal("110"), Decimal("120"), Decimal("130")],
        tp_allocations={"TP1": 0.33, "TP2": 0.5, "TP3": 1.0},
        lock_profit_price=Decimal("102"),
        signal_class=1,
        reason="EMA21 reclaim",
    )
    assert action.symbol == "BTC/USDT"
    assert action.entry_price == Decimal("100")
    assert len(action.tp_prices) == 3


def test_open_position_is_frozen():
    action = OpenPosition(
        symbol="BTC/USDT", side="BUY", entry_price=Decimal("100"),
        sl_price=Decimal("95"), soft_sl_price=None,
        tp_prices=[], tp_allocations=None, lock_profit_price=None,
        signal_class=2, reason="test",
    )
    with pytest.raises(Exception):
        action.symbol = "ETH/USDT"  # type: ignore[misc]


def test_close_position_optional_price():
    market_close = ClosePosition(symbol="BTC/USDT", reason="SL_HIT")
    assert market_close.price is None

    candle_close = ClosePosition(symbol="BTC/USDT", reason="CLOSE_BY_CANDLE_SL", price=Decimal("94"))
    assert candle_close.price == Decimal("94")


def test_move_sl_fields():
    action = MoveSL(symbol="BTC/USDT", new_sl_price=Decimal("102"), reason="LOCK_PROFIT")
    assert action.new_sl_price == Decimal("102")
    assert action.reason == "LOCK_PROFIT"


def test_partial_close_fields():
    action = PartialClose(
        symbol="BTC/USDT", tp_level="TP1", price=Decimal("110"),
        reason="TP1 hit", new_sl_price=Decimal("102"),
    )
    assert action.tp_level == "TP1"
    assert action.new_sl_price == Decimal("102")


def test_partial_close_new_sl_optional():
    action = PartialClose(
        symbol="BTC/USDT", tp_level="TP2", price=Decimal("120"), reason="TP2 hit",
    )
    assert action.new_sl_price is None


def test_do_nothing_is_singleton_like():
    """DoNothing carries no data — two instances are equal."""
    a = DoNothing()
    b = DoNothing()
    assert a == b


def test_action_union_covers_all():
    """All action classes must appear in the Action union."""
    import typing
    args = typing.get_args(Action)
    assert OpenPosition in args
    assert ClosePosition in args
    assert MoveSL in args
    assert PartialClose in args
    assert DoNothing in args
