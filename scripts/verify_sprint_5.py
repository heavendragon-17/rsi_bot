import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ui.api.backtest import BacktestAPI
from app.db.connection import get_cursor
from app.db.repositories.runs import RunsRepository

def create_dummy_data():
    """Create a dummy CSV file for testing."""
    data_dir = os.path.join("app", "backtest", "data")
    os.makedirs(data_dir, exist_ok=True)
    
    file_path = os.path.join(data_dir, "BTCUSDT_1h.csv")
    
    # Always create new data to ensure sufficient length
    print(f"Creating dummy data at {file_path}")
    dates = pd.date_range(end=datetime.now(), periods=500, freq='1h') # Increased to 500
    
    # Create a simple trend for RSI to trigger
    # prices = np.linspace(50000, 60000, 500) + np.random.normal(0, 100, 500)
    
    df = pd.DataFrame({
        'timestamp': dates,
        'open': np.random.rand(500) * 100 + 50000,
        'high': np.random.rand(500) * 100 + 50100,
        'low': np.random.rand(500) * 100 + 49900,
        'close': np.random.rand(500) * 100 + 50050,
        'volume': np.random.rand(500) * 1000,
        'closed': [True] * 500 # Ensure 'closed' execution
    })
    df.to_csv(file_path, index=False)
    return file_path

def test_integration():
    print("Starting Integration Test...")
    
    # 1. Setup Data
    file_path = create_dummy_data()
    
    # 2. Test BacktestAPI.get_data_files
    api = BacktestAPI()
    files_res = api.get_data_files()
    if not files_res['success'] or len(api.get_data_files()['data']) == 0:
        print("FAIL: get_data_files returned empty or error")
        return False
    print("PASS: get_data_files found CSVs")

    # 3. Test BacktestAPI.run_backtest
    params = {
        "strategy_name": "rsi_wma_retest",
        "data_file": file_path,
        "initial_balance": 10000
    }
    
    print(f"Running backtest with {params['strategy_name']}...")
    res = api.run_backtest(params)
    
    if not res['success']:
        print(f"FAIL: run_backtest failed: {res.get('error')}")
        # Print actual error
        if 'error' in res:
             print(res['error'])
        if 'traceback' in res:
             print(res['traceback'])
        return False
        
    run_id = res['data']['run_id']
    metrics = res['data']['metrics']
    print(f"PASS: Backtest completed. Run ID: {run_id}")
    print(f"Metrics: {metrics}")

    # 4. Verify DB persistence
    repo = RunsRepository()
    with get_cursor() as cursor:
        run = repo.get_run(cursor, run_id)
        if not run:
            print("FAIL: Run not found in DB")
            return False
        
        if run['status'] != 'completed':
            print(f"FAIL: Run status is {run['status']}")
            return False
            
    print("PASS: Run persisted to DB correctly")
    return True

if __name__ == "__main__":
    success = test_integration()
    sys.exit(0 if success else 1)
