# Quick test for exchange factory
import sys
sys.path.insert(0, '.')

from app.trading.exchange.factory import create_exchange

# Test mock mode
config = {
    'bot': {'mode': 'mock'},
    'backtest': {'initial_balance': 10000},
    'risk': {'leverage': 10}
}

try:
    ex = create_exchange(config)
    print(f"SUCCESS: Created {type(ex).__name__}")
    balance = ex.fetch_balance()
    print(f"Balance USDT: {balance['free']['USDT']}")
except Exception as e:
    print(f"ERROR: {e}")
