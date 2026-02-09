from pathlib import Path
import yaml
import os

# Determine paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_DIR)))
CONFIG_PATH = Path(PROJECT_ROOT) / "config" / "config.yaml"

def get_default_global_config() -> dict:
    """Return default global config."""
    return {
        "strategy": "rsi_wma_retest",
        "symbols": ["XPL/USDT"],
        "timeframe": "5m",
        "exchange": "binance",
        "backtest": {
            "initial_balance": 10000,
            "leverage": 10
        }
    }

def load_global_config() -> dict:
    """Load global config from YAML."""
    if not CONFIG_PATH.exists():
        return get_default_global_config()
    
    try:
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or get_default_global_config()
    except Exception as e:
        print(f"Error loading global config: {e}")
        return get_default_global_config()

def validate_global_config(config: dict) -> None:
    """Validate global config. Raises ValueError on error."""
    # Balance must be positive
    balance = config.get("backtest", {}).get("initial_balance", 0)
    if isinstance(balance, (int, float)) and balance <= 0:
        raise ValueError("initial_balance must be positive")
    
    # Leverage must be reasonable
    leverage = config.get("backtest", {}).get("leverage", 1)
    if isinstance(leverage, (int, float)) and (leverage < 1 or leverage > 125):
        raise ValueError("leverage must be 1-125")

def save_global_config(config: dict) -> None:
    """Save global config to YAML."""
    # Validate before saving
    validate_global_config(config)
    
    # Ensure directory exists
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with open(CONFIG_PATH, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
