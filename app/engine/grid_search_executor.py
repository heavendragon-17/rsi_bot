"""
Grid Search Executor
====================
Runs N parameter combinations in parallel using ProcessPoolExecutor.

Flow:
  1. Create ONE parent run record (run_type="grid_search")
  2. Generate all (x, y) combinations
  3. Run combos via ProcessPoolExecutor + as_completed()
  4. Publish SSE progress after each combo completes
  5. Persist all results to grid_search_results table

Usage (async, from FastAPI route):
    run_id, total = await run_grid_search(session_id, base_config, grid_config)
"""
import asyncio
import os
import copy
from concurrent.futures import ProcessPoolExecutor, as_completed

from app.db.connection import get_connection
from app.db.repositories import run_repo
from app.db.repositories import grid_search_repo
from app.api.sse import publish_from_thread, get_queue


# ─────────────────────────────────────────────
# Top-level worker function (must be picklable)
# ─────────────────────────────────────────────

def _run_single_combo(combo_config: dict) -> dict:
    """
    Run one backtest for a single parameter combination.
    Runs in a subprocess via ProcessPoolExecutor.

    Args:
        combo_config: {
            symbol, timeframe, strategy, capital, leverage, riskPercent,
            params, x_param, x_value, y_param, y_value
        }

    Returns:
        dict with x_param, x_value, y_param, y_value + all metrics
        OR { "error": str, x_param, x_value, y_param, y_value }
    """
    x_param = combo_config["x_param"]
    x_value = combo_config["x_value"]
    y_param = combo_config["y_param"]
    y_value = combo_config["y_value"]

    base_result = {
        "x_param": x_param,
        "x_value": x_value,
        "y_param": y_param,
        "y_value": y_value,
    }

    try:
        # Import inside subprocess to avoid pickling issues
        import pandas as pd
        from app.engine.executor import normalize_symbol, resolve_data_path, build_engine_config
        from app.backtest.engine import BacktestEngine
        from app.backtest.reporting import BacktestReporter
        from app.strategies.loader import load_strategy

        # Build engine config from the combo config
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

        # Check for trades
        trades = engine.exchange.trade_history
        if not trades:
            base_result.update({
                "net_pnl": "0",
                "net_pnl_pct": 0.0,
                "sharpe_ratio": 0.0,
                "profit_factor": 0.0,
                "win_rate": 0.0,
                "max_drawdown_pct": 0.0,
                "trade_count": 0,
                "calmar_ratio": 0.0,
                "sortino_ratio": 0.0,
                "above_threshold": False,
            })
            return base_result

        # Calculate metrics via reporter internals
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

        sharpe = risk_metrics.get("sharpe_ratio", 0.0)

        base_result.update({
            "net_pnl": str(realized_pnl),
            "net_pnl_pct": net_pnl_pct,
            "sharpe_ratio": sharpe,
            "profit_factor": metrics.get("profit_factor", 0.0),
            "win_rate": metrics.get("win_rate", 0.0),
            "max_drawdown_pct": drawdown.get("max_drawdown_pct", 0.0),
            "trade_count": metrics.get("total_trades", 0),
            "calmar_ratio": risk_metrics.get("calmar_ratio", 0.0),
            "sortino_ratio": risk_metrics.get("sortino_ratio", 0.0),
            "above_threshold": sharpe > 0,
        })
        return base_result

    except Exception as exc:
        base_result["error"] = str(exc)
        return base_result


# ─────────────────────────────────────────────
# Combination generator
# ─────────────────────────────────────────────

def _generate_combinations(base_config: dict, grid_config: dict) -> list[dict]:
    """
    Generate all (x, y) parameter combinations.

    Args:
        base_config: The user's base config (symbol, timeframe, strategy, capital, etc.)
        grid_config: {
            x_param, x_min, x_max, x_step,
            y_param, y_min, y_max, y_step,
            metric
        }

    Returns:
        List of combo_config dicts, each ready for _run_single_combo().
    """
    x_param = grid_config["x_param"]
    y_param = grid_config["y_param"]
    x_min = float(grid_config["x_min"])
    x_max = float(grid_config["x_max"])
    x_step = float(grid_config["x_step"])
    y_min = float(grid_config["y_min"])
    y_max = float(grid_config["y_max"])
    y_step = float(grid_config["y_step"])

    combos = []
    x_val = x_min
    while x_val <= x_max + 1e-9:
        y_val = y_min
        while y_val <= y_max + 1e-9:
            # Deep copy base config and override the two grid params
            combo = copy.deepcopy(base_config)
            params = combo.get("params", {})
            params[x_param] = round(x_val, 6)
            params[y_param] = round(y_val, 6)
            combo["params"] = params

            # Attach grid metadata
            combo["x_param"] = x_param
            combo["x_value"] = round(x_val, 6)
            combo["y_param"] = y_param
            combo["y_value"] = round(y_val, 6)

            combos.append(combo)
            y_val += y_step
        x_val += x_step

    return combos


# ─────────────────────────────────────────────
# Synchronous orchestrator (runs in thread pool)
# ─────────────────────────────────────────────

def _run_grid_search_sync(
    run_id: int,
    session_id: str,
    base_config: dict,
    grid_config: dict,
    loop: asyncio.AbstractEventLoop,
) -> dict:
    """
    Blocking grid search orchestrator. Runs inside a thread pool executor.

    Args:
        run_id: Pre-created parent run ID
        session_id: Session ID
        base_config: Base backtest config from UI
        grid_config: Grid search parameters
        loop: Event loop for SSE publishing

    Returns:
        dict with status, run_id, total_combos, best result
    """

    def emit(event_type: str, data: dict) -> None:
        publish_from_thread(run_id, event_type, data, loop)

    try:
        # Mark running
        with get_connection() as conn:
            run_repo.update_run_status(conn, run_id, "running")

        emit("progress", {"pct": 0, "completed": 0, "total": 0, "message": "Generating combinations..."})

        # Generate all combinations
        combos = _generate_combinations(base_config, grid_config)
        total = len(combos)

        if total == 0:
            with get_connection() as conn:
                run_repo.update_run_status(conn, run_id, "completed")
            emit("done", {"run_id": run_id, "status": "completed", "total_combos": 0, "best": None})
            return {"run_id": run_id, "status": "completed", "total_combos": 0}

        # Update run with grid search total
        with get_connection() as conn:
            conn.execute(
                "UPDATE runs SET is_grid_search = TRUE, grid_search_total = ?, grid_search_completed = 0 WHERE id = ?",
                (total, run_id),
            )

        emit("progress", {"pct": 2, "completed": 0, "total": total, "message": f"Starting {total} combinations..."})

        # Run combos in parallel
        max_workers = min(os.cpu_count() or 4, total)
        all_results = []
        completed = 0

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_run_single_combo, combo): combo
                for combo in combos
            }

            for future in as_completed(futures):
                combo = futures[future]
                completed += 1

                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "x_param": combo["x_param"],
                        "x_value": combo["x_value"],
                        "y_param": combo["y_param"],
                        "y_value": combo["y_value"],
                        "error": str(exc),
                    }

                all_results.append(result)

                # Update grid_search_completed count
                with get_connection() as conn:
                    conn.execute(
                        "UPDATE runs SET grid_search_completed = ? WHERE id = ?",
                        (completed, run_id),
                    )

                pct = int((completed / total) * 95) + 2  # 2-97% range
                x_val = result.get("x_value", "?")
                y_val = result.get("y_value", "?")
                msg = f"Completed {completed}/{total} (X={x_val}, Y={y_val})"
                if "error" in result:
                    msg += f" [ERROR: {result['error'][:50]}]"
                emit("progress", {"pct": pct, "completed": completed, "total": total, "message": msg})

        emit("progress", {"pct": 97, "completed": total, "total": total, "message": "Saving results to database..."})

        # Filter out errors and persist valid results
        valid_results = [r for r in all_results if "error" not in r]

        with get_connection() as conn:
            if valid_results:
                grid_search_repo.save_results_batch(conn, run_id, session_id, valid_results)
            run_repo.update_run_status(conn, run_id, "completed")

        # Find best result
        metric_key = grid_config.get("metric", "net_pnl")
        best = _find_best_result(valid_results, metric_key)

        summary = {
            "run_id": run_id,
            "status": "completed",
            "total_combos": total,
            "valid_combos": len(valid_results),
            "error_combos": len(all_results) - len(valid_results),
            "best": best,
        }

        emit("done", summary)
        return summary

    except Exception as exc:
        error_msg = str(exc)
        try:
            with get_connection() as conn:
                run_repo.update_run_status(conn, run_id, "failed")
        except Exception:
            pass
        emit("error", {"message": error_msg, "run_id": run_id})
        return {"error": error_msg, "run_id": run_id}


def _find_best_result(results: list[dict], metric_key: str) -> dict | None:
    """Find the best result based on the optimization metric."""
    if not results:
        return None

    # Map UI metric names to result dict keys
    metric_map = {
        "net_pnl": "net_pnl_pct",
        "sharpe": "sharpe_ratio",
        "profit_factor": "profit_factor",
        "win_rate": "win_rate",
        "max_dd": "max_drawdown_pct",
        "calmar": "calmar_ratio",
        "sortino": "sortino_ratio",
    }

    key = metric_map.get(metric_key, "net_pnl_pct")
    reverse = metric_key != "max_dd"  # For max_dd, lower is better

    def get_val(r):
        v = r.get(key, 0)
        if isinstance(v, str):
            try:
                return float(v)
            except (ValueError, TypeError):
                return 0.0
        return float(v) if v is not None else 0.0

    best = max(results, key=get_val) if reverse else min(results, key=get_val)

    return {
        "x_param": best.get("x_param"),
        "x_value": best.get("x_value"),
        "y_param": best.get("y_param"),
        "y_value": best.get("y_value"),
        "metric_value": get_val(best),
    }


# ─────────────────────────────────────────────
# Async entry point (called from FastAPI route)
# ─────────────────────────────────────────────

async def run_grid_search(
    session_id: str,
    base_config: dict,
    grid_config: dict,
) -> tuple[int, int]:
    """
    Create a run record and launch grid search in a thread pool.
    Returns (run_id, total_combinations) immediately.

    Args:
        session_id: Session ID
        base_config: Base backtest config (symbol, timeframe, strategy, params, etc.)
        grid_config: Grid search config (x_param, x_min, x_max, x_step, y_param, ...)

    Returns:
        (run_id, total_combinations)
    """
    loop = asyncio.get_running_loop()

    # Look up strategy_id
    strategy_name = base_config.get("strategy", "rsi_no_retest")
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT id FROM strategies WHERE name = ? LIMIT 1", (strategy_name,)
        )
        row = cursor.fetchone()
        strategy_id = row[0] if row else 1

    # Create parent run record
    with get_connection() as conn:
        run_id = run_repo.create_run(
            conn,
            strategy_id=strategy_id,
            session_id=session_id,
            run_type="grid_search",
        )

    # Calculate total combinations
    combos = _generate_combinations(base_config, grid_config)
    total = len(combos)

    # Create SSE queue before launching thread
    get_queue(run_id)

    # Launch in thread pool (non-blocking)
    loop.run_in_executor(
        None,
        _run_grid_search_sync,
        run_id,
        session_id,
        base_config,
        grid_config,
        loop,
    )

    return run_id, total
