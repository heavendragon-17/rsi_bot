import unittest
import os
import json
import shutil
from pathlib import Path

# Add project root to path
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.strategy_loader import load_strategy_config, save_strategy_override, reset_strategy_override
from app.config.global_loader import load_global_config, save_global_config
from app.config.schema import get_parameter_schema
from app.strategies.rsi_wma_retest import RsiWmaRetestStrategy

class TestConfigSystem(unittest.TestCase):
    def setUp(self):
        # Create temp config dirs
        self.override_dir = Path("config/strategy_overrides")
        self.config_path = Path("config/config.yaml")
        
        # Backup existing config.yaml if exists
        self.backup_config = False
        if self.config_path.exists():
            shutil.copy(self.config_path, "config/config.yaml.bak")
            self.backup_config = True
        
        # Ensure clean state for overrides
        reset_strategy_override("rsi_wma_retest")

    def tearDown(self):
        # Cleanup overrides
        reset_strategy_override("rsi_wma_retest")
        
        # Restore config.yaml
        if self.backup_config:
            shutil.move("config/config.yaml.bak", "config/config.yaml")

    def test_save_and_load_strategy_override(self):
        strategy_name = "rsi_wma_retest"
        new_config = {"rsi_period": 99, "nr_tp1_rr": 5.0}
        
        # Save override
        path = save_strategy_override(strategy_name, new_config)
        self.assertTrue(os.path.exists(path))
        
        # Load config
        loaded = load_strategy_config(strategy_name, RsiWmaRetestStrategy)
        self.assertEqual(loaded['override']['rsi_period'], 99)
        self.assertEqual(loaded['merged']['rsi_period'], 99)
        self.assertEqual(loaded['merged']['nr_tp1_rr'], 5.0)
        # Check default preserved
        self.assertEqual(loaded['default']['rsi_period'], RsiWmaRetestStrategy.DEFAULT_CONFIG['rsi_period'])

    def test_schema_generation(self):
        schema = get_parameter_schema(RsiWmaRetestStrategy)
        self.assertTrue(len(schema) > 0)
        
        # Check specific param
        rsi_period = next(p for p in schema if p['key'] == 'rsi_period')
        self.assertEqual(rsi_period['type'], 'number')
        self.assertEqual(rsi_period['group'], 'indicators')
        self.assertEqual(rsi_period['min'], 1)

    def test_global_config_validation(self):
        # Valid config
        valid_config = {
            "strategy": "rsi_wma_retest",
            "backtest": {"initial_balance": 5000, "leverage": 5}
        }
        try:
            save_global_config(valid_config)
        except ValueError:
            self.fail("save_global_config raised ValueError unexpectedly!")
            
        # Invalid config
        invalid_config = {
            "strategy": "rsi_wma_retest",
            "backtest": {"initial_balance": -100}
        }
        with self.assertRaises(ValueError):
            save_global_config(invalid_config)

if __name__ == "__main__":
    unittest.main()
