from pathlib import Path
import json
import os
import sys

# Determine paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_DIR)))
OVERRIDE_DIR = Path(PROJECT_ROOT) / "config" / "strategy_overrides"

def load_strategy_config(strategy_name: str, strategy_class) -> dict:
    """Load merged strategy config."""
    # 1. Get DEFAULT_CONFIG from strategy class
    default = getattr(strategy_class, 'DEFAULT_CONFIG', {})
    
    # 2. Load override if exists
    override_path = OVERRIDE_DIR / f"{strategy_name}.json"
    override = {}
    if override_path.exists():
        try:
            with open(override_path) as f:
                override = json.load(f)
        except Exception as e:
            print(f"Error loading override for {strategy_name}: {e}")
    
    # 3. Merge (override takes precedence)
    merged = {**default, **override}
    
    return {
        "default": default,
        "override": override,
        "merged": merged
    }

def save_strategy_override(strategy_name: str, config: dict) -> str:
    """Save strategy override to JSON."""
    OVERRIDE_DIR.mkdir(parents=True, exist_ok=True)
    path = OVERRIDE_DIR / f"{strategy_name}.json"
    
    with open(path, 'w') as f:
        json.dump(config, f, indent=2)
    
    return str(path)

def reset_strategy_override(strategy_name: str) -> bool:
    """Delete override file, reverting to defaults."""
    path = OVERRIDE_DIR / f"{strategy_name}.json"
    if path.exists():
        path.unlink()
        return True
    return False
