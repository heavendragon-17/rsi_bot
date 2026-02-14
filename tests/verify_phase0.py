"""Quick verification script for Phase 0"""
import sys
import os

# Add project root to path (one level up from tests/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from app.db.schema import init_db, seed_defaults
from app.db.connection import get_connection
from app.db.repositories import session_repo, run_repo

print("Testing Phase 0 components...")

# Test 1: Schema initialization
print("\n1. Initializing schema...")
init_db('test_phase0.db')
seed_defaults('test_phase0.db')
print("   ✓ Schema initialized")

# Test 2: Session CRUD
print("\n2. Testing session CRUD...")
with get_connection('test_phase0.db') as conn:
    session_id = session_repo.create_session(
        conn, 'single', 1, {'symbol': 'BTC/USDT'}
    )
    print(f"   ✓ Created session: {session_id}")
    
    session = session_repo.get_session(conn, session_id)
    assert session['mode_type'] == 'single'
    print(f"   ✓ Retrieved session")
    
    sessions = session_repo.list_sessions(conn)
    assert len(sessions) == 1
    print(f"   ✓ Listed sessions: {len(sessions)}")

# Test 3: Run CRUD with version chaining
print("\n3. Testing run CRUD with version chaining...")
with get_connection('test_phase0.db') as conn:
    run_v1 = run_repo.create_run(conn, 1, session_id, 'grid_search', version_number=1)
    print(f"   ✓ Created run v1: {run_v1}")
    
    run_v2 = run_repo.create_run(conn, 1, session_id, 'grid_search', version_number=2, parent_run_id=run_v1)
    print(f"   ✓ Created run v2: {run_v2}")
    
    versions = run_repo.get_run_versions(conn, session_id, 'grid_search')
    assert len(versions) == 2
    assert versions[1]['parent_run_id'] == run_v1
    print(f"   ✓ Version chaining works")

# Test 4: Save run data
print("\n4. Testing run data persistence...")
with get_connection('test_phase0.db') as conn:
    config = {
        'symbol': 'BTC/USDT',
        'timeframe': '15m',
        'start_date': '2025-01-01',
        'end_date': '2025-03-31',
        'initial_capital': '10000.00',
        'params': {'rsi_period': 21}
    }
    run_repo.save_run_config(conn, run_v1, config)
    print(f"   ✓ Saved run config")
    
    results = {
        'net_profit': '1234.56789',
        'sharpe_ratio': 1.85,
        'total_trades': 42
    }
    run_repo.save_run_results(conn, run_v1, results)
    print(f"   ✓ Saved run results")
    
    equity_curve = [
        {'date': '2025-01-01', 'balance': '10000.00'},
        {'date': '2025-01-02', 'balance': '10123.45'}
    ]
    run_repo.save_run_timeseries(conn, run_v1, equity_curve)
    print(f"   ✓ Saved timeseries (compressed)")

print("\n" + "="*50)
print("✓ ALL PHASE 0 TESTS PASSED!")
print("="*50)

# Cleanup
os.remove('test_phase0.db')
print("\nTest database cleaned up.")
