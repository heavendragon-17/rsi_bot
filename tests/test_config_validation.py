import pytest
import sys
import os

# Ensure app is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.validators import validate_config

def test_valid_config():
    config = {
        'bot': {'mode': 'paper'},
        'exchange': {'name': 'binance'},
        'symbols': ['BTC/USDT', 'ETH/USDT'],
        'timeframe': '15m'
    }
    # Should not raise exception
    validate_config(config)

def test_missing_keys():
    config = {
        'bot': {'mode': 'paper'},
        # Missing exchange
        'symbols': ['BTC/USDT'],
        'timeframe': '15m'
    }
    with pytest.raises(ValueError, match="Missing required config key: exchange"):
        validate_config(config)

def test_invalid_mode():
    config = {
        'bot': {'mode': 'invalid_mode'},
        'exchange': {'name': 'binance'},
        'symbols': ['BTC/USDT'],
        'timeframe': '15m'
    }
    with pytest.raises(ValueError, match="Invalid bot mode"):
        validate_config(config)

def test_invalid_exchange():
    config = {
        'bot': {'mode': 'live'},
        'exchange': {'name': 'unsupported'},
        'symbols': ['BTC/USDT'],
        'timeframe': '15m'
    }
    with pytest.raises(ValueError, match="Invalid exchange"):
        validate_config(config)

def test_empty_symbols():
    config = {
        'bot': {'mode': 'paper'},
        'exchange': {'name': 'binance'},
        'symbols': [],
        'timeframe': '15m'
    }
    with pytest.raises(ValueError, match="Symbols list cannot be empty"):
        validate_config(config)

def test_invalid_symbols_type():
    config = {
        'bot': {'mode': 'paper'},
        'exchange': {'name': 'binance'},
        'symbols': "BTC/USDT", # Not a list
        'timeframe': '15m'
    }
    with pytest.raises(ValueError, match="Symbols must be a list"):
        validate_config(config)
