import os
import sqlite3
import sys
from pathlib import Path

def verify_db():
    db_path = Path("data/backtest.db")
    if not db_path.exists():
        print("❌ Database file not found")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    tables = [
        "strategies", "themes", "runs", "run_configs", 
        "run_results", "run_timeseries", "trades", "tags", "comparisons"
    ]
    
    missing = []
    for table in tables:
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
        if not cursor.fetchone():
            missing.append(table)
            
    conn.close()
    
    if missing:
        print(f"❌ Missing tables: {missing}")
        return False
        
    print("✅ Database verification passed")
    return True

def verify_ui_launch():
    # We can't easily verify UI launch headless without logic in main_ui.py to exit
    # But main_ui.py has --test arg
    import subprocess
    try:
        result = subprocess.run(
            [sys.executable, "main_ui.py", "--test"], 
            capture_output=True, 
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print("✅ UI launch verification passed (test mode)")
            return True
        else:
            print(f"❌ UI launch failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ UI launch exception: {e}")
        return False

if __name__ == "__main__":
    db_ok = verify_db()
    ui_ok = verify_ui_launch()
    
    if db_ok and ui_ok:
        print("🎉 Sprint 1 Verification Passed!")
        sys.exit(0)
    else:
        print("💥 Sprint 1 Verification Failed!")
        sys.exit(1)
