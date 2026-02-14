"""
Verification script for WalkForwardRepo
"""
import sqlite3
import os
import sys

# Add root to path
sys.path.append(os.getcwd())

from app.db.schema import init_db
from app.db.repositories import walk_forward_repo, run_repo, session_repo

def test_wf_repo():
    db_path = "test_wf.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    init_db(db_path)
    
    # Use a real connection for testing (bypassing connection manager for :memory: simplicity)
    conn = sqlite3.connect(db_path)
    
    # Needs a session and a strategy and a run to follow foreign keys
    # Actually schema.py seeds 1 strategy
    strategy_id = 1
    session_id = "test_wf_session"
    
    # Create session
    conn.execute("INSERT INTO sessions (id, mode_type, strategy_id, config_snapshot) VALUES (?, ?, ?, ?)",
                 (session_id, "single", strategy_id, "{}"))
    
    # Create run
    run_id = run_repo.create_run(conn, strategy_id=strategy_id, session_id=session_id, run_type="walk_forward")
    
    # 1. Test save_result
    result1 = {
        "window_index": 1,
        "is_start_date": "2024-01-01",
        "is_end_date": "2024-01-30",
        "oos_start_date": "2024-01-31",
        "oos_end_date": "2024-02-15",
        "best_param": "rsi_period",
        "best_param_value": 14.0,
        "is_metric_value": 1.5,
        "oos_return_pct": 2.5,
        "is_positive": True
    }
    
    row_id = walk_forward_repo.save_result(conn, run_id, session_id, result1)
    print(f"Inserted row {row_id}")
    
    # 2. Test get_results
    results = walk_forward_repo.get_results(conn, run_id)
    assert len(results) == 1
    assert results[0]["window_index"] == 1
    assert results[0]["oos_return_pct"] == 2.5
    print("get_results passed")
    
    # 3. Test save_results_batch
    results_batch = [
        {
            "window_index": 2,
            "is_start_date": "2024-02-01",
            "is_end_date": "2024-03-01",
            "oos_start_date": "2024-03-02",
            "oos_end_date": "2024-03-15",
            "best_param": "rsi_period",
            "best_param_value": 16.0,
            "is_metric_value": 1.8,
            "oos_return_pct": -0.5,
            "is_positive": False
        },
        {
            "window_index": 3,
            "is_start_date": "2024-03-01",
            "is_end_date": "2024-04-01",
            "oos_start_date": "2024-04-02",
            "oos_end_date": "2024-04-15",
            "best_param": "rsi_period",
            "best_param_value": 12.0,
            "is_metric_value": 2.1,
            "oos_return_pct": 1.2,
            "is_positive": True
        }
    ]
    
    walk_forward_repo.save_results_batch(conn, run_id, session_id, results_batch)
    
    results = walk_forward_repo.get_results(conn, run_id)
    assert len(results) == 3
    assert results[1]["window_index"] == 2
    assert results[2]["window_index"] == 3
    print("save_results_batch passed")
    
    # 4. Test get_results_by_session
    session_results = walk_forward_repo.get_results_by_session(conn, session_id)
    assert len(session_results) == 3
    print("get_results_by_session passed")
    
    conn.close()
    print("\nAll WalkForwardRepo tests passed!")

if __name__ == "__main__":
    test_wf_repo()
