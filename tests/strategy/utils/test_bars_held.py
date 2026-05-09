"""Unit tests for the shared bars_held / max-holding utility."""

from __future__ import annotations

from decimal import Decimal

from app.core.actions import EXIT_MAX_HOLDING_PERIOD, ClosePosition
from app.core.context import SCANNING
from app.trading.strategy.utils.bars_held import (
    increment_bars_held,
    maybe_force_close_max_holding,
)
from app.trading.strategy.utils.trade_state import TradeState


# ── increment_bars_held ────────────────────────────────────────────────────


def test_increment_starts_at_one_when_zero() -> None:
    ts = TradeState()
    assert ts.bars_held == 0
    new_count = increment_bars_held(ts)
    assert new_count == 1
    assert ts.bars_held == 1


def test_increment_continues_count() -> None:
    ts = TradeState(bars_held=5)
    new_count = increment_bars_held(ts)
    assert new_count == 6
    assert ts.bars_held == 6
    new_count = increment_bars_held(ts)
    assert new_count == 7
    assert ts.bars_held == 7


# ── maybe_force_close_max_holding ──────────────────────────────────────────


def test_force_close_returns_none_when_disabled() -> None:
    result = maybe_force_close_max_holding(
        symbol="BTC/USDT",
        bars_held=1000,
        max_bars=0,
        close_price=Decimal("100"),
    )
    assert result is None


def test_force_close_returns_none_when_no_close_price() -> None:
    result = maybe_force_close_max_holding(
        symbol="BTC/USDT",
        bars_held=200,
        max_bars=96,
        close_price=None,
    )
    assert result is None


def test_force_close_returns_none_below_threshold() -> None:
    result = maybe_force_close_max_holding(
        symbol="BTC/USDT",
        bars_held=95,
        max_bars=96,
        close_price=Decimal("100"),
    )
    assert result is None


def test_force_close_returns_close_at_threshold() -> None:
    result = maybe_force_close_max_holding(
        symbol="BTC/USDT",
        bars_held=96,
        max_bars=96,
        close_price=Decimal("100"),
    )
    assert result is not None
    assert len(result.actions) == 1
    action = result.actions[0]
    assert isinstance(action, ClosePosition)
    assert action.reason == EXIT_MAX_HOLDING_PERIOD
    assert result.new_context.state == SCANNING


def test_force_close_returns_close_above_threshold() -> None:
    result = maybe_force_close_max_holding(
        symbol="ETH/USDT",
        bars_held=200,
        max_bars=96,
        close_price=Decimal("3000"),
    )
    assert result is not None
    action = result.actions[0]
    assert isinstance(action, ClosePosition)
    assert action.reason == EXIT_MAX_HOLDING_PERIOD


def test_force_close_uses_close_price_in_action() -> None:
    close_price = Decimal("12345.67")
    result = maybe_force_close_max_holding(
        symbol="BTC/USDT",
        bars_held=96,
        max_bars=96,
        close_price=close_price,
    )
    assert result is not None
    action = result.actions[0]
    assert isinstance(action, ClosePosition)
    assert action.symbol == "BTC/USDT"
    assert action.price == close_price
