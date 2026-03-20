# tests/test_position_sizing.py
"""
Tests for PortfolioManager._calculate_position_size
Focus: Verify tight SL does NOT trigger max leverage behavior
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock

# We need to create a minimal test setup since PortfolioManager requires exchange
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.trading.portfolio.manager import PortfolioManager


class MockExchange:
    """Minimal mock for testing PortfolioManager initialization."""
    def fetch_balance(self):
        return {"total": {"USDT": Decimal("10000")}, "free": {"USDT": Decimal("10000")}}
    
    def fetch_positions(self):
        return []


@pytest.fixture
def portfolio_manager():
    """Create PortfolioManager with test config."""
    config = {
        "risk": {
            "max_position_size_pct": 0.99,
            "risk_per_trade_pct": 0.02,  # 2% risk per trade
            "use_risk_based_sizing": True,
            "min_sl_distance_pct": 0.01,  # 1% minimum SL distance
            "leverage": 10,
            "use_initial_capital_for_risk": True,
        },
        "backtest": {
            "initial_balance": 10000,
        }
    }
    exchange = MockExchange()
    return PortfolioManager(exchange, config)


class TestTightSLBehavior:
    """Tests for when SL distance is below min_sl_distance_pct threshold."""
    
    def test_tight_sl_does_not_max_leverage(self, portfolio_manager):
        """
        BUG: When SL distance < min_sl_distance_pct (1%), 
        the code currently returns max_amount (max leverage).
        
        EXPECTED: Should return a risk-capped amount or zero, NOT max leverage.
        
        Scenario:
        - Entry: $100
        - SL: $99.50 (0.5% distance, below 1% threshold)
        - Risk: 2% of $10k = $200
        - Max amount with 10x leverage on 99% capital: huge position
        
        Current behavior: Returns max_amount (dangerous!)
        Expected behavior: Returns safe amount or rejects trade
        """
        balance = Decimal("10000")
        entry_price = Decimal("100")
        sl_price = Decimal("99.50")  # 0.5% SL distance (below 1% min)
        
        result = portfolio_manager._calculate_position_size(balance, entry_price, sl_price)
        
        # Calculate what max_amount would be (the BAD behavior)
        max_margin = balance * Decimal("0.99")  # 99% of balance
        max_notional = max_margin * Decimal("10")  # 10x leverage
        max_amount = max_notional / entry_price  # ~990 units
        
        # Calculate what risk-based sizing SHOULD give us
        # At 0.5% SL distance, to risk $200: notional = $200 / 0.005 = $40,000
        # Size = $40,000 / $100 = 400 units
        # But this would be capped at max_amount anyway...
        
        # The KEY assertion: result should NOT be max_amount
        # It should be the risk-calculated amount (capped if needed)
        # OR it should be zero/rejected
        
        # For now, we expect it to NOT equal max_amount
        # The fix should apply risk-based calculation even for tight SLs
        assert result < max_amount, (
            f"Tight SL returned max_amount ({result} >= {max_amount}). "
            f"Risk controls were bypassed!"
        )
    
    def test_sl_exactly_at_min_threshold(self, portfolio_manager):
        """
        When SL distance is exactly at min_sl_distance_pct (1%),
        normal risk calculation should apply.
        """
        balance = Decimal("10000")
        entry_price = Decimal("100")
        sl_price = Decimal("99")  # Exactly 1% SL distance
        
        result = portfolio_manager._calculate_position_size(balance, entry_price, sl_price)
        
        # Should use risk-based sizing
        # Risk: 2% of $10k = $200
        # SL distance: 1%
        # Notional = $200 / 0.01 = $20,000
        # Size = $20,000 / $100 = 200 units
        expected = Decimal("200")
        
        # Allow some tolerance for Decimal precision
        assert abs(result - expected) < Decimal("1"), (
            f"Expected ~{expected}, got {result}"
        )


class TestEdgeCases:
    """Tests for edge cases that could cause errors or undefined behavior."""
    
    def test_zero_sl_distance(self, portfolio_manager):
        """
        When SL = Entry (impossible trade), should return 0 or raise error.
        """
        balance = Decimal("10000")
        entry_price = Decimal("100")
        sl_price = Decimal("100")  # SL = Entry (0% distance)
        
        result = portfolio_manager._calculate_position_size(balance, entry_price, sl_price)
        
        # Should NOT return a giant position due to division by zero
        max_amount = balance * Decimal("0.99") * Decimal("10") / entry_price
        
        assert result <= Decimal("0") or result < max_amount, (
            f"Zero SL distance returned {result}, expected 0 or safe fallback"
        )
    
    def test_negative_sl_distance_for_long(self, portfolio_manager):
        """
        When SL > Entry for a LONG position (invalid), should handle gracefully.
        """
        balance = Decimal("10000")
        entry_price = Decimal("100")
        sl_price = Decimal("105")  # SL above entry (invalid for LONG)
        
        result = portfolio_manager._calculate_position_size(balance, entry_price, sl_price)
        
        # Should return 0 or a safe value, not a negative/weird position
        assert result >= Decimal("0"), f"Got negative position size: {result}"
        
        # Should not return max leverage just because abs() makes it look valid
        max_amount = balance * Decimal("0.99") * Decimal("10") / entry_price
        assert result < max_amount, (
            f"Invalid SL returned max_amount ({result} >= {max_amount})"
        )


class TestNormalOperation:
    """Tests for normal, happy-path scenarios."""
    
    def test_normal_sl_distance(self, portfolio_manager):
        """
        Normal SL distance (5%) should use risk-based sizing correctly.
        """
        balance = Decimal("10000")
        entry_price = Decimal("100")
        sl_price = Decimal("95")  # 5% SL distance
        
        result = portfolio_manager._calculate_position_size(balance, entry_price, sl_price)
        
        # Risk: 2% of $10k = $200
        # SL distance: 5%
        # Notional = $200 / 0.05 = $4,000
        # Size = $4,000 / $100 = 40 units
        expected = Decimal("40")
        
        assert abs(result - expected) < Decimal("1"), (
            f"Expected ~{expected}, got {result}"
        )
    
    def test_no_sl_provided_uses_max_position(self, portfolio_manager):
        """
        When no SL is provided, should fall back to max position size.
        """
        balance = Decimal("10000")
        entry_price = Decimal("100")
        sl_price = None
        
        result = portfolio_manager._calculate_position_size(balance, entry_price, sl_price)
        
        # Should use max_amount fallback
        max_amount = balance * Decimal("0.99") * Decimal("10") / entry_price
        
        assert abs(result - max_amount) < Decimal("1"), (
            f"Expected max_amount ~{max_amount}, got {result}"
        )
