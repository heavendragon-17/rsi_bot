"""Tests for strategy loader — config → strategy class/instance."""

import pytest

from app.trading.strategy.loader import (
    STRATEGY_MAP,
    get_available_strategies,
    load_strategy,
    load_strategy_instance,
)


class TestLoader:
    def test_available_strategies(self):
        out = get_available_strategies()
        assert "rsi_no_retest" in out
        assert "rsi_momentum" in out
        assert "rsi_wma_retest" in out

    def test_load_default_strategy(self):
        cls = load_strategy({})
        assert cls is STRATEGY_MAP["rsi_wma_retest"]

    def test_load_named_strategy(self):
        cls = load_strategy({"strategy": "rsi_no_retest"})
        assert cls is STRATEGY_MAP["rsi_no_retest"]

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError, match="Unknown strategy"):
            load_strategy({"strategy": "nonexistent"})

    def test_load_instance(self):
        inst = load_strategy_instance({"strategy": "rsi_momentum"})
        assert isinstance(inst, STRATEGY_MAP["rsi_momentum"])
