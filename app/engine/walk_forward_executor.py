"""
Walk-Forward Executor
=====================
Runs rolling window optimization and validation.

Flow:
  1. Generate rolling windows (IS, OOS, Step) from CSV range
  2. For each window:
     a. IS OPTIMIZATION: Run param range in parallel via ProcessPoolExecutor
     b. Find best param by metric
     c. OOS VALIDATION: Run single backtest with best param on OOS period
     d. Save window result to walk_forward_results
     e. Publish SSE progress
  3. Final summary + done event
"""
import asyncio
import os
import copy
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed

from app.db.connection import get_connection
from app.db.repositories import run_repo, walk_forward_repo
from app.api.sse import publish_from_thread, get_queue


# ─────────────────────────────────────────────
# Top-level worker function (must be picklable)
# ─────────────────────────────────────────────

def _run_wf_backtest(combo_config: dict) -> dict:
    """
    Worker for a single backtest within a window (IS or OOS).
    Runs in a subprocess.
    """
    param_name = combo_config.get("param_to_optimize")
    param_value = combo_config.get("param_value")
    
    base_result = {
        "param_name": param_name,
        "param_value": param_value,
    }

    try:
        from app.engine.executor import resolve_data_path, build_engine_config
        from app.backtest.engine import BacktestEngine
        from app.backtest.reporting import BacktestReporter
        from app.strategies.loader import load_strategy

        # Build engine config (respects startDate/endDate in combo_config)
        engine_config = build_engine_config(combo_config)

        # Resolve data path
        symbol = combo_config.get("symbol", "BTC/USDT")
        timeframe = combo_config.get("timeframe", "15m")
        data_path = resolve_data_path(symbol, timeframe)

        if not os.path.exists(data_path):
            base_result["error"] = f"Data file not found: {data_path}"
            return base_result

        # Load strategy class
        strategy_class = load_strategy(engine_config)

        # Run backtest
        engine = BacktestEngine(data_path, strategy_class, engine_config)
        engine.run()

        # Calculate metrics
        trades = engine.exchange.trade_history
        if not trades:
            base_result.update({
                "net_pnl_pct": 0.0,
                "sharpe_ratio": 0.0,
                "profit_factor": 0.0,
                "sortino_ratio": 0.0,
                "trade_count": 0,
            })
            return base_result

        df = pd.DataFrame(trades)
        initial_balance = float(combo_config.get("capital", 10000))
        reporter = BacktestReporter(
            engine.exchange,
            engine_config,
            initial_balance=initial_balance,
            symbol=engine_config["symbols"][0],
            timeframe=timeframe,
            strategy_name=combo_config.get("strategy", "rsi_no_retest"),
        )

        round_trips = reporter._build_round_trips(df)
        metrics = reporter._calculate_metrics(round_trips)
        drawdown = reporter._calculate_drawdown(round_trips)
        risk_metrics = reporter._calculate_risk_metrics(round_trips, drawdown)

        realized_pnl = float(round_trips["pnl"].sum()) if not round_trips.empty else 0.0
        net_pnl_pct = (realized_pnl / initial_balance) * 100

        base_result.update({
            "net_pnl_pct": net_pnl_pct,
            "sharpe_ratio": risk_metrics.get("sharpe_ratio", 0.0),
            "profit_factor": metrics.get("profit_factor", 0.0),
            "sortino_ratio": risk_metrics.get("sortino_ratio", 0.0),
            "trade_count": metrics.get("total_trades", 0),
        })
        return base_result

    except Exception as exc:
        base_result["error"] = str(exc)
        return base_result


# ─────────────────────────────────────────────
# Window generator
# ─────────────────────────────────────────────

def _generate_windows(data_path: str, is_days: int, oos_days: int, step_days: int) -> list[dict]:
    """
    Read CSV to find data date range, then generate rolling windows.
    """
    df = pd.read_csv(data_path, usecols=['timestamp'], nrows=1)
    first_ts = df['timestamp'].iloc[0]
    
    # Get last row timestamp
    # A bit slow for huge files, but safe. Alternatively read last N bytes.
    # For now, let's read the whole timestamp col if needed, or just use tail(1)
    df_last = pd.read_csv(data_path, usecols=['timestamp']).tail(1)
    last_ts = df_last['timestamp'].iloc[0]
    
    def to_dt(ts):
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts / 1000.0)
        return pd.to_datetime(ts).to_pydatetime()

    start_date = to_dt(first_ts)
    end_date = to_dt(last_ts)
    
    windows = []
    current_is_start = start_date
    window_idx = 1
    
    while True:
        is_end = current_is_start + timedelta(days=is_days)
        oos_start = is_end # No gap
        oos_end = oos_start + timedelta(days=oos_days)
        
        if oos_end > end_date:
            break
            
        windows.append({
            "window_index": window_idx,
            "is_start": current_is_start.strftime("%Y-%m-%d"),
            "is_end": is_end.strftime("%Y-%m-%d"),
            "oos_start": oos_start.strftime("%Y-%m-%d"),
            "oos_end": oos_end.strftime("%Y-%m-%d"),
        })
        
        current_is_start += timedelta(days=step_days)
        window_idx += 1
        
    return windows


# ─────────────────────────────────────────────
# Synchronous orchestrator
# ─────────────────────────────────────────────

def _run_walk_forward_sync(
    run_id: int,
    session_id: str,
    base_config: dict,
    wf_config: dict,
    loop: asyncio.AbstractEventLoop,
    db_path: str = None,
) -> dict:
    """
    Blocking orchestrator.
    """
    def emit(event_type: str, data: dict) -> None:
        publish_from_thread(run_id, event_type, data, loop)

    try:
        from app.engine.executor import resolve_data_path
        
        with get_connection(db_path) as conn:
            run_repo.update_run_status(conn, run_id, "running")

        emit("progress", {"pct": 0, "message": "Generating windows..."})
        
        symbol = base_config.get("symbol", "BTC/USDT")
        timeframe = base_config.get("timeframe", "15m")
        data_path = resolve_data_path(symbol, timeframe)
        
        is_days = int(wf_config["is_window_days"])
        oos_days = int(wf_config["oos_window_days"])
        step_days = int(wf_config["step_size_days"])
        
        windows = _generate_windows(data_path, is_days, oos_days, step_days)
        total_windows = len(windows)
        
        if total_windows == 0:
            raise ValueError("Not enough data for the configured windows.")

        emit("progress", {"pct": 5, "completed": 0, "total": total_windows, "message": f"Generated {total_windows} windows."})

        # Process each window sequentially
        window_results = []
        param_to_optimize = wf_config["param_to_optimize"]
        p_min = float(wf_config["param_min"])
        p_max = float(wf_config["param_max"])
        p_step = float(wf_config["param_step"])
        metric_key = wf_config.get("optimize_metric", "sharpe")
        
        # UI/Engine metric mapping (reused from grid search)
        metric_map = {
            "net_pnl": "net_pnl_pct",
            "sharpe": "sharpe_ratio",
            "profit_factor": "profit_factor",
            "sortino": "sortino_ratio",
        }
        target_metric = metric_map.get(metric_key, "sharpe_ratio")

        max_workers = os.cpu_count() or 4
        
        for w_idx, w in enumerate(windows):
            pct = int((w_idx / total_windows) * 90) + 5
            emit("progress", {
                "pct": pct, 
                "completed": w_idx, 
                "total": total_windows, 
                "message": f"Window {w_idx+1}/{total_windows}: IS optimization..."
            })
            
            # 1. Generate combos for IS
            combos = []
            val = p_min
            while val <= p_max + 1e-9:
                combo = copy.deepcopy(base_config)
                combo["params"] = combo.get("params", {})
                combo["params"][param_to_optimize] = round(val, 6)
                combo["startDate"] = w["is_start"]
                combo["endDate"] = w["is_end"]
                combo["param_to_optimize"] = param_to_optimize
                combo["param_value"] = round(val, 6)
                combos.append(combo)
                val += p_step
            
            # 2. Run IS combos in parallel
            is_results = []
            with ProcessPoolExecutor(max_workers=min(max_workers, len(combos))) as executor:
                futures = [executor.submit(_run_wf_backtest, c) for c in combos]
                for future in as_completed(futures):
                    is_results.append(future.result())
            
            # 3. Find best param
            valid_is = [r for r in is_results if "error" not in r]
            if not valid_is:
                best_p = p_min # Fallback
                is_metric = 0.0
            else:
                best_res = max(valid_is, key=lambda r: r.get(target_metric, 0))
                best_p = best_res["param_value"]
                is_metric = best_res[target_metric]
            
            # 4. Run OOS validation
            emit("progress", {
                "pct": pct + 2, 
                "completed": w_idx, 
                "total": total_windows, 
                "message": f"Window {w_idx+1}/{total_windows}: OOS validation..."
            })
            
            oos_config = copy.deepcopy(base_config)
            oos_config["params"] = oos_config.get("params", {})
            oos_config["params"][param_to_optimize] = best_p
            oos_config["startDate"] = w["oos_start"]
            oos_config["endDate"] = w["oos_end"]
            oos_config["param_to_optimize"] = param_to_optimize
            oos_config["param_value"] = best_p
            
            oos_res = _run_wf_backtest(oos_config)
            
            # 5. Record result
            final_w_res = {
                "window_index": w["window_index"],
                "is_start_date": w["is_start"],
                "is_end_date": w["is_end"],
                "oos_start_date": w["oos_start"],
                "oos_end_date": w["oos_end"],
                "best_param": param_to_optimize,
                "best_param_value": best_p,
                "is_metric_value": is_metric,
                "oos_return_pct": oos_res.get("net_pnl_pct", 0.0),
                "is_positive": oos_res.get("net_pnl_pct", 0.0) > 0,
            }
            window_results.append(final_w_res)
            
            # Save to DB immediately so partial results persist
            with get_connection(db_path) as conn:
                walk_forward_repo.save_result(conn, run_id, session_id, final_w_res)

        # Mark done
        with get_connection(db_path) as conn:
            run_repo.update_run_status(conn, run_id, "completed")
            
        emit("progress", {"pct": 100, "completed": total_windows, "total": total_windows, "message": "Verification complete."})
        
        summary = {
            "run_id": run_id,
            "status": "completed",
            "total_windows": total_windows,
        }
        emit("done", summary)
        return summary

    except Exception as exc:
        error_msg = str(exc)
        try:
            with get_connection(db_path) as conn:
                run_repo.update_run_status(conn, run_id, "failed")
        except: pass
        emit("error", {"message": error_msg, "run_id": run_id})
        return {"error": error_msg, "run_id": run_id}


# ─────────────────────────────────────────────
# Async entry point
# ─────────────────────────────────────────────

async def run_walk_forward(session_id: str, base_config: dict, wf_config: dict, db_path: str = None) -> tuple[int, int]:
    """
    Returns (run_id, estimated_total_windows).
    """
    loop = asyncio.get_running_loop()
    
    strategy_name = base_config.get("strategy", "rsi_no_retest")
    with get_connection(db_path) as conn:
        cursor = conn.execute("SELECT id FROM strategies WHERE name = ? LIMIT 1", (strategy_name,))
        row = cursor.fetchone()
        strategy_id = row[0] if row else 1
        
        run_id = run_repo.create_run(
            conn,
            strategy_id=strategy_id,
            session_id=session_id,
            run_type="walk_forward"
        )
    
    # Pre-calculate windows to return total to UI
    from app.engine.executor import resolve_data_path
    data_path = resolve_data_path(base_config.get("symbol"), base_config.get("timeframe"))
    temp_windows = _generate_windows(
        data_path, 
        int(wf_config["is_window_days"]), 
        int(wf_config["oos_window_days"]), 
        int(wf_config["step_size_days"])
    )
    total = len(temp_windows)
    
    get_queue(run_id)
    
    loop.run_in_executor(
        None,
        _run_walk_forward_sync,
        run_id,
        session_id,
        base_config,
        wf_config,
        loop,
        db_path,
    )
    
    return run_id, total
