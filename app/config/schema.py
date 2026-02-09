def _infer_type(value):
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        # Extend this list as needed
        KNOWN_SELECTS = ["lowest_close", "fixed_pct", "variable", "none"]
        return "select" if value in KNOWN_SELECTS else "text"
    return "text"

def _infer_group(key: str) -> str:
    key_lower = key.lower()
    if any(x in key_lower for x in ["rsi", "ema", "wma", "period", "length"]):
        return "indicators"
    if any(x in key_lower for x in ["sl", "tp", "close_pct", "stop_loss", "take_profit"]):
        return "exits"
    if any(x in key_lower for x in ["buffer", "multiplier", "risk", "leverage"]):
        return "risk"
    return "general"

def _key_to_label(key: str) -> str:
    """Convert snake_case key to Title Case Label."""
    return key.replace("_", " ").title()

def _get_numeric_constraints(key: str) -> dict:
    """Heuristic for numeric constraints."""
    key_lower = key.lower()
    constraints = {}
    
    if "pct" in key_lower or "ratio" in key_lower:
        constraints["step"] = 0.01
    else:
        constraints["step"] = 1
        
    if "period" in key_lower or "length" in key_lower:
        constraints["min"] = 1
        
    return constraints

def get_parameter_schema(strategy_class) -> list:
    """Generate form schema from DEFAULT_CONFIG."""
    config = getattr(strategy_class, 'DEFAULT_CONFIG', {})
    
    schema = []
    for key, value in config.items():
        param = {
            "key": key,
            "type": _infer_type(value),
            "label": _key_to_label(key),
            "group": _infer_group(key),
            "default": value
        }
        
        # Add constraints
        if param["type"] == "number":
            param.update(_get_numeric_constraints(key))
            
        # Add options for selects
        if param["type"] == "select":
             # This is a bit manual, but safer for now. 
             # Could be improved by inspecting Strategy class or comments.
             if "sl_mode" in key:
                 param["options"] = ["lowest_close", "fixed"]
             elif "slippage_model" in key:
                 param["options"] = ["none", "fixed_pct", "variable"]
        
        schema.append(param)
    
    return schema
