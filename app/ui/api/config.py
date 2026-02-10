import os
import json
import yaml
from app.db.repository import BacktestRepository
from app.strategies.loader import load_strategy

class ConfigAPIMixin:
    """Methods related to configuration and themes."""

    def get_strategy_config(self, strategy_name: str) -> dict:
        """Get strategy config (defaults + overrides)."""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

        # 1. Load DEFAULT_CONFIG from Strategy Class
        default_config = {}
        try:
            # We create a dummy config with the strategy name to use the loader
            dummy_config = {"strategy": strategy_name}
            strategy_class = load_strategy(dummy_config)
            if hasattr(strategy_class, "DEFAULT_CONFIG"):
                default_config = strategy_class.DEFAULT_CONFIG
        except Exception as e:
            print(f"Error loading default config for {strategy_name}: {e}")

        # 2. Load Overrides from JSON
        override_path = os.path.join(base_dir, "config", "strategy_overrides", f"{strategy_name}.json")
        override = {}
        if os.path.exists(override_path):
            try:
                with open(override_path, "r") as f:
                    override = json.load(f)
            except Exception as e:
                print(f"Error loading strategy override: {e}")

        # 3. Merge Configs (Override > Default)
        merged = default_config.copy()
        merged.update(override)

        return {
            "default": default_config,
            "override": override,
            "merged": merged,
            "schema": [] # TODO: Generate schema from dataclass if available
        }

    def save_strategy_config(self, strategy_name: str, config: dict) -> dict:
        """Save strategy config override."""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        override_dir = os.path.join(base_dir, "config", "strategy_overrides")

        if not os.path.exists(override_dir):
            os.makedirs(override_dir)

        path = os.path.join(override_dir, f"{strategy_name}.json")
        try:
            with open(path, "w") as f:
                json.dump(config, f, indent=2)
            return {"success": True, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_global_config(self) -> dict:
        """Get global config.yaml."""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        config_path = os.path.join(base_dir, "config.yaml")

        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                print(f"Error loading config.yaml: {e}")
                return {}
        return {}

    def save_global_config(self, config: dict) -> dict:
        """Save global config.yaml."""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        config_path = os.path.join(base_dir, "config.yaml")

        try:
            with open(config_path, "w") as f:
                yaml.dump(config, f)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_themes(self) -> list[dict]:
        """Get all themes."""
        repo = BacktestRepository()
        return repo.get_themes()

    def get_active_theme(self) -> dict:
        """Get active theme."""
        repo = BacktestRepository()
        theme = repo.get_active_theme()
        if theme:
            return theme
        # Fallback if no active theme found
        return {"name": "default", "colors": {}}

    def set_active_theme(self, theme_name: str) -> bool:
        """Set active theme."""
        repo = BacktestRepository()
        try:
            repo.set_active_theme(theme_name)
            return True
        except Exception as e:
            print(f"Error setting theme: {e}")
            return False
