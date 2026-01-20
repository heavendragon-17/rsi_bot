import unittest
from decimal import Decimal
from datetime import datetime
from app.core.portfolio import PortfolioManager
from app.backtest.mock_exchange import MockExchange
from app.core.events import SignalEvent

class TestConfigEntryMode(unittest.TestCase):
    def test_string_strategy_config(self):
        """Test that PortfolioManager handles config['strategy'] as a string."""
        config = {
            "strategy": "SomeStrategyName",
            "strategy_params": {
                "some_param": 123
            },
            "risk": {},
            "backtest": {}
        }
        exchange = MockExchange()
        pm = PortfolioManager(exchange, config)

        signal = SignalEvent(
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            signal_type="BUY",
            price=Decimal("50000"),
            reason="TEST"
        )

        # Should not raise AttributeError
        exchange.current_prices["BTC/USDT"] = {"price": Decimal("50000"), "time": datetime.now()}
        pm.on_signal(signal)

    def test_strategy_params_override(self):
        """Test that strategy_params can override entry_mode."""
        config = {
            "strategy": "SomeStrategyName",
            "strategy_params": {
                "entry_mode": "LIMIT"
            },
            "risk": {},
            "backtest": {}
        }
        exchange = MockExchange()
        pm = PortfolioManager(exchange, config)

        signal = SignalEvent(
            timestamp=datetime.now(),
            symbol="BTC/USDT",
            signal_type="BUY",
            price=Decimal("50000"),
            reason="TEST"
        )

        exchange.current_prices["BTC/USDT"] = {"price": Decimal("50000"), "time": datetime.now()}
        order = pm.on_signal(signal)

        self.assertIsNotNone(order)
        # Should be pending because LIMIT mode was active
        self.assertTrue(pm.has_pending_entry("BTC/USDT"))

if __name__ == '__main__':
    unittest.main()
