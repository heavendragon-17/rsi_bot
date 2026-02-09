from app.config.global_loader import load_global_config, save_global_config
from app.config.strategy_loader import load_strategy_config, save_strategy_override
from app.config.schema import get_parameter_schema
# Import strategies to get DEFAULT_CONFIG for schema generation
from app.strategies.rsi_wma_retest import RsiWmaRetestStrategy
from app.strategies.rsi_no_retest import RsiNoRetestStrategy

STRATEGY_MAP = {
    "rsi_wma_retest": RsiWmaRetestStrategy,
    "rsi_no_retest": RsiNoRetestStrategy,
}

class ConfigAPI:
    def get_global_config(self):
        """Get global configuration."""
        try:
            config = load_global_config()
            return {"success": True, "data": config}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_global_config(self, config):
        """Save global configuration."""
        try:
            save_global_config(config)
            return {"success": True}
        except ValueError as e:
             return {"success": False, "error": str(e), "error_code": "VALIDATION_ERROR"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_strategies(self):
        """Get list of available strategies."""
        try:
            strategies = []
            for name, cls in STRATEGY_MAP.items():
                strategies.append({
                    "name": name,
                    "display_name": name.replace("_", " ").title(),
                    "description": cls.__doc__.strip() if cls.__doc__ else "No description",
                    # has_override check could go here
                })
            return {"success": True, "data": strategies}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_strategy_config(self, strategy_name):
        """Get strategy configuration and schema."""
        if strategy_name not in STRATEGY_MAP:
             return {"success": False, "error": f"Unknown strategy: {strategy_name}", "error_code": "STRATEGY_NOT_FOUND"}
            
        try:
            strategy_class = STRATEGY_MAP[strategy_name]
            config = load_strategy_config(strategy_name, strategy_class)
            schema = get_parameter_schema(strategy_class)
            
            return {
                "success": True, 
                "data": {
                    **config,
                    "schema": schema
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_strategy_config(self, strategy_name, config):
        """Save strategy configuration override."""
        if strategy_name not in STRATEGY_MAP:
             return {"success": False, "error": f"Unknown strategy: {strategy_name}", "error_code": "STRATEGY_NOT_FOUND"}
             
        try:
            path = save_strategy_override(strategy_name, config)
            return {"success": True, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e)}
