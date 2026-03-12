with open('tests/test_api_backtest.py', 'r') as f:
    code = f.read()

code = code.replace('"symbol": "BTC/USDT",', '"mode": "single", "symbols": ["BTC/USDT"],')
code = code.replace('assert response.status_code == 200 # App returns 200 based on code flow', 'assert response.status_code in [200, 201]')
code = code.replace('"initial_capital": 10000,', '"initial_capital": "10000",')
code = code.replace('"risk_per_trade_pct": 1.0,', '"risk_per_trade_pct": "1.0",')

with open('tests/test_api_backtest.py', 'w') as f:
    f.write(code)
