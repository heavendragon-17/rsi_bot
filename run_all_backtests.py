"""Run all 3 backtests and save results."""
import subprocess
import sys

symbols = ['BTC', 'ETH', 'BNB']
results = {}

for sym in symbols:
    data_file = f'data/{sym}USDT_5m.csv'
    print(f"\n{'='*50}")
    print(f"BACKTEST: {sym}/USDT")
    print('='*50)
    
    try:
        result = subprocess.run(
            [sys.executable, 'backtest.py', '--data', data_file, '--balance', '10000'],
            capture_output=True,
            text=True,
            timeout=300
        )
        print(result.stdout)
        if result.stderr:
            print(f"Errors: {result.stderr[-500:]}")
    except Exception as e:
        print(f"Error running {sym}: {e}")

print("\n" + "="*50)
print("ALL BACKTESTS COMPLETE")
print("="*50)
