def validate_config(config):
    """
    Validates the configuration dictionary.
    Raises ValueError if the configuration is invalid.
    """
    if not isinstance(config, dict):
        raise ValueError("Config must be a dictionary")

    # Required keys
    required_keys = ['bot', 'exchange', 'symbols', 'timeframe']
    for key in required_keys:
        if key not in config:
            raise ValueError(f"Missing required config key: {key}")

    # Validate 'bot' section
    if not isinstance(config['bot'], dict):
        raise ValueError("Config key 'bot' must be a dictionary")

    if 'mode' not in config['bot']:
        raise ValueError("Missing 'mode' in 'bot' config")

    if config['bot']['mode'] not in ['paper', 'live']:
        raise ValueError(f"Invalid bot mode: {config['bot']['mode']}. Must be 'paper' or 'live'")

    # Validate 'exchange' section
    if not isinstance(config['exchange'], dict):
        raise ValueError("Config key 'exchange' must be a dictionary")

    if 'name' not in config['exchange']:
        raise ValueError("Missing 'name' in 'exchange' config")

    if config['exchange']['name'] not in ['binance', 'hyperliquid']:
        raise ValueError(f"Invalid exchange: {config['exchange']['name']}. Must be 'binance' or 'hyperliquid'")

    # Validate 'symbols'
    if not isinstance(config['symbols'], list):
        raise ValueError("Symbols must be a list")

    if len(config['symbols']) == 0:
        raise ValueError("Symbols list cannot be empty")

    for symbol in config['symbols']:
        if not isinstance(symbol, str):
            raise ValueError(f"Invalid symbol: {symbol}. Must be a string")

    # Validate 'timeframe'
    if not isinstance(config['timeframe'], str):
        raise ValueError("Timeframe must be a string")
