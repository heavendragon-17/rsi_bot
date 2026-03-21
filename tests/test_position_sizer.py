"""Tests for PositionSizer edge cases (M12 coverage gap)."""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from app.trading.portfolio.position_sizer import PositionSizer


def _make_config(
    risk_pct=0.02, max_pct=0.99, leverage=10, min_sl=0.01, initial=10000
):
    return {
        "risk": {
            "risk_per_trade_pct": risk_pct,
            "max_position_size_pct": max_pct,
            "use_risk_based_sizing": True,
            "min_sl_distance_pct": min_sl,
            "leverage": leverage,
            "use_initial_capital_for_risk": True,
        },
        "backtest": {"initial_balance": initial},
    }


@pytest.fixture
def mock_exchange():
    ex = MagicMock()
    ex.fetch_balance.return_value = {"total": {"USDT": 10000}}
    return ex


@pytest.fixture
def sizer(mock_exchange):
    return PositionSizer(_make_config(), mock_exchange)


class TestZeroBalance:
    def test_zero_balance_returns_zero_size(self, mock_exchange):
        """Zero balance → max_amount = 0, so result is 0."""
        s = PositionSizer(_make_config(initial=0), mock_exchange)
        # With use_initial_capital_for_risk, cap_balance=0 → max_notional=0
        result = s.calculate(Decimal("0"), Decimal("100"), Decimal("95"))
        assert result == Decimal("0")


class TestMaxPositionCap:
    def test_caps_at_max_position_size(self, mock_exchange):
        """Wide SL should still be capped by max_position_size_pct."""
        s = PositionSizer(_make_config(max_pct=0.10, leverage=10), mock_exchange)
        # max_margin = 10000 * 0.10 = 1000, max_notional = 10000, max_amount = 100
        # Risk-based: risk=200, SL=2%, notional=10000, size=100 → exactly at cap
        result = s.calculate(Decimal("10000"), Decimal("100"), Decimal("98"))
        max_amount = Decimal("10000") * Decimal("0.10") * Decimal("10") / Decimal("100")
        assert result <= max_amount


class TestSmallBalanceHighLeverage:
    def test_very_small_balance_high_leverage(self, mock_exchange):
        """Balance=1 with leverage=100 should not crash."""
        s = PositionSizer(_make_config(initial=1, leverage=100), mock_exchange)
        result = s.calculate(Decimal("1"), Decimal("100"), Decimal("95"))
        assert result >= Decimal("0")
        assert isinstance(result, Decimal)


class TestNoSL:
    def test_no_sl_returns_max_amount(self, sizer):
        """No SL → falls through to max_amount."""
        result = sizer.calculate(Decimal("10000"), Decimal("100"), None)
        expected_max = Decimal("10000") * Decimal("0.99") * Decimal("10") / Decimal("100")
        assert result == expected_max

    def test_sl_price_zero_returns_max_amount(self, sizer):
        """sl_price=0 is treated same as no SL (condition on line 62)."""
        result = sizer.calculate(Decimal("10000"), Decimal("100"), Decimal("0"))
        expected_max = Decimal("10000") * Decimal("0.99") * Decimal("10") / Decimal("100")
        assert result == expected_max


class TestSyncBalance:
    def test_sync_balance_reads_from_exchange(self, sizer, mock_exchange):
        mock_exchange.fetch_balance.return_value = {"total": {"USDT": 5000}}
        result = sizer.sync_balance()
        assert result == Decimal("5000")
        mock_exchange.fetch_balance.assert_called_once()
