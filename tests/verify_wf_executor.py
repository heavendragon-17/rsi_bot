"""
Verification script for WalkForwardExecutor
"""
import asyncio
import os
import sys
import json
import sqlite3

# Add root to path
sys.path.append(os.getcwd())

from app.db.schema import init_db, seed_defaults
from app.api.sse import get_queue
from app.engine.walk_forward_executor import run_walk_forward

async def test_wf_executor():
    db_path = "test_wf_executor.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    # Initialize DB
    init_db(db_path)
    seed_defaults(db_path)
    
    # Session ID
    session_id = "test_wf_session"
    
    # From ui/src/stores/walkForwardStore.ts pattern
    base_config = {
        "symbol": "1INCH/USDT",
        "timeframe": "15m",
        "strategy": "rsi_no_retest",
        "capital": 10000,
        "leverage": 1,
        "riskPercent": 2,
        "params": {
            "rsi_period": 14,
            "rsi_ema_length": 9,
            "rsi_wma_length": 45,
            "price_ema_fast": 21,
            "price_ema_slow": 200,
            "nr_lookback": 30,
            "nr_max_above_ema21": 1,
            "nr_rsi_spread_min": 1.5,
            "nr_sl_mode": "lowest_close",
            "sl_buffer_pct": 0.0,
            "disaster_sl_multiplier": 3.0,
            "nr_tp1_rr": 1.0,
            "nr_tp2_rr": 2.0,
            "nr_tp3_rr": 3.0,
            "tp1_close_pct": 0.50,
            "tp2_close_pct": 0.50,
            "nr_move_sl_rr": 0.5,
            "nr_lock_profit_rr": 0.2
        }
    }
    
    wf_config = {
        "param_to_optimize": "rsi_period",
        "param_min": 14,
        "param_max": 18,
        "param_step": 2,
        "is_window_days": 30,
        "oos_window_days": 10,
        "step_size_days": 30,
        "optimize_metric": "sharpe"
    }
    
    # Create session to satisfy foreign key
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO sessions (id, mode_type, strategy_id, config_snapshot) VALUES (?, ?, ?, ?)",
                     (session_id, "single", 1, "{}"))
    
    print("Starting walk-forward...")
    run_id, total = await run_walk_forward(session_id, base_config, wf_config, db_path=db_path)
    print(f"Run started: ID={run_id}, Total Windows={total}")
    
    # Monitor SSE queue
    queue = get_queue(run_id)
    
    while True:
        event = await queue.get()
        event_type = event.get("event")
        data = event.get("data", {})
        
        if event_type == "progress":
            print(f"Progress: {data.get('pct')}% - {data.get('message')}")
        elif event_type == "done":
            print("\nWalk-forward completed successfully!")
            print(f"Summary: {data}")
            break
        elif event_type == "error":
            print(f"\nError: {data.get('message')}")
            break

if __name__ == "__main__":
    asyncio.run(test_wf_executor())
