"""
Run Repository
==============
CRUD operations for runs table with version chaining support.
"""
import json
import zlib
from datetime import datetime
from typing import Optional


def create_run(
    conn,
    strategy_id: int,
    session_id: str,
    run_type: str = "backtest",
    version_number: int = 1,
    parent_run_id: int = None,
    git_hash: str = None,
    version: str = None,
    auto_quant_config: dict = None
) -> int:
    """
    Create a new run. Returns the run_id (auto-incremented integer).

    Args:
        conn: SQLite connection
        strategy_id: Foreign key to strategies table
        session_id: Foreign key to sessions table
        run_type: "backtest" | "grid_search" | "walk_forward" | "sensitivity"
        version_number: Version number for version chaining
        parent_run_id: Optional parent run ID for version chaining
        git_hash: Optional git commit hash
        version: Optional semantic version
        auto_quant_config: Optional dict of auto-triggered quant tools

    Returns:
        int: Run ID
    """
    now = datetime.now().isoformat()

    cursor = conn.execute("""
        INSERT INTO runs (strategy_id, session_id, run_type, version_number, parent_run_id,
                         auto_quant_config, created_at, status, git_hash, version)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
    """, (strategy_id, session_id, run_type, version_number, parent_run_id,
          json.dumps(auto_quant_config) if auto_quant_config else None,
          now, git_hash, version))

    return cursor.lastrowid


def update_run_status(conn, run_id: int, status: str, completed_at: str = None) -> None:
    """
    Update run status (pending → running → completed|failed|partial).

    Args:
        conn: SQLite connection
        run_id: Run ID to update
        status: New status value
        completed_at: Optional completion timestamp
    """
    if status == "running":
        now = datetime.now().isoformat()
        conn.execute("""
            UPDATE runs
            SET status = ?, started_at = ?
            WHERE id = ?
        """, (status, now, run_id))
    elif status in ("completed", "failed", "partial"):
        completed = completed_at or datetime.now().isoformat()
        conn.execute("""
            UPDATE runs
            SET status = ?, completed_at = ?
            WHERE id = ?
        """, (status, completed, run_id))
    else:
        conn.execute("""
            UPDATE runs
            SET status = ?
            WHERE id = ?
        """, (status, run_id))


def get_run(conn, run_id: int) -> Optional[dict]:
    """
    Get a single run by ID.

    Args:
        conn: SQLite connection
        run_id: Run ID to retrieve

    Returns:
        dict: Run data with parsed JSON fields, or None
    """
    cursor = conn.execute("""
        SELECT id, strategy_id, session_id, run_type, version_number, parent_run_id,
               auto_quant_config, created_at, started_at, completed_at, status,
               git_hash, version, is_grid_search, grid_search_parent_id,
               grid_search_total, grid_search_completed
        FROM runs
        WHERE id = ?
    """, (run_id,))

    row = cursor.fetchone()
    if not row:
        return None

    return {
        "id": row[0],
        "strategy_id": row[1],
        "session_id": row[2],
        "run_type": row[3],
        "version_number": row[4],
        "parent_run_id": row[5],
        "auto_quant_config": json.loads(row[6]) if row[6] else None,
        "created_at": row[7],
        "started_at": row[8],
        "completed_at": row[9],
        "status": row[10],
        "git_hash": row[11],
        "version": row[12],
        "is_grid_search": row[13],
        "grid_search_parent_id": row[14],
        "grid_search_total": row[15],
        "grid_search_completed": row[16]
    }


def get_runs_by_session(
    conn,
    session_id: str,
    run_type: str = None
) -> list[dict]:
    """
    Get all runs in a session, optionally filtered by type.

    Args:
        conn: SQLite connection
        session_id: Session ID to filter by
        run_type: Optional run type filter

    Returns:
        list[dict]: List of run dicts
    """
    query = """
        SELECT id, strategy_id, session_id, run_type, version_number, parent_run_id,
               auto_quant_config, created_at, started_at, completed_at, status,
               git_hash, version, is_grid_search, grid_search_parent_id,
               grid_search_total, grid_search_completed
        FROM runs
        WHERE session_id = ?
    """
    params = [session_id]

    if run_type:
        query += " AND run_type = ?"
        params.append(run_type)

    query += " ORDER BY created_at DESC"

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()

    return [
        {
            "id": row[0],
            "strategy_id": row[1],
            "session_id": row[2],
            "run_type": row[3],
            "version_number": row[4],
            "parent_run_id": row[5],
            "auto_quant_config": json.loads(row[6]) if row[6] else None,
            "created_at": row[7],
            "started_at": row[8],
            "completed_at": row[9],
            "status": row[10],
            "git_hash": row[11],
            "version": row[12],
            "is_grid_search": row[13],
            "grid_search_parent_id": row[14],
            "grid_search_total": row[15],
            "grid_search_completed": row[16]
        }
        for row in rows
    ]


def get_run_versions(conn, session_id: str, run_type: str) -> list[dict]:
    """
    Get all versions of a specific run type within a session.
    Ordered by version_number ASC.
    Used for version comparison UI.

    Args:
        conn: SQLite connection
        session_id: Session ID
        run_type: Run type to filter by

    Returns:
        list[dict]: List of run versions ordered by version_number
    """
    cursor = conn.execute("""
        SELECT id, strategy_id, session_id, run_type, version_number, parent_run_id,
               auto_quant_config, created_at, started_at, completed_at, status,
               git_hash, version
        FROM runs
        WHERE session_id = ? AND run_type = ?
        ORDER BY version_number ASC
    """, (session_id, run_type))

    rows = cursor.fetchall()

    return [
        {
            "id": row[0],
            "strategy_id": row[1],
            "session_id": row[2],
            "run_type": row[3],
            "version_number": row[4],
            "parent_run_id": row[5],
            "auto_quant_config": json.loads(row[6]) if row[6] else None,
            "created_at": row[7],
            "started_at": row[8],
            "completed_at": row[9],
            "status": row[10],
            "git_hash": row[11],
            "version": row[12]
        }
        for row in rows
    ]


def save_run_config(conn, run_id: int, config: dict) -> None:
    """
    Save run configuration to run_configs table.

    Args:
        conn: SQLite connection
        run_id: Run ID
        config: Configuration dict with all required fields
    """
    conn.execute("""
        INSERT INTO run_configs (
            run_id, symbol, symbols_list, is_batch_mode, timeframe,
            start_date, end_date, lookback_value, lookback_unit,
            initial_capital, leverage, risk_per_trade_pct,
            fee_tier, slippage_model, slippage_pct, params
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_id,
        config.get('symbol'),
        json.dumps(config.get('symbols_list')) if config.get('symbols_list') else None,
        config.get('is_batch_mode', False),
        config.get('timeframe'),
        config.get('start_date'),
        config.get('end_date'),
        config.get('lookback_value'),
        config.get('lookback_unit'),
        config.get('initial_capital', '10000.00'),
        config.get('leverage', 10),
        config.get('risk_per_trade_pct', '0.02'),
        config.get('fee_tier', '0.001'),
        config.get('slippage_model', 'none'),
        config.get('slippage_pct', '0.0'),
        json.dumps(config.get('params', {}))
    ))


def save_run_results(conn, run_id: int, results: dict) -> None:
    """
    Save scalar results to run_results table. Monetary values as TEXT.

    Args:
        conn: SQLite connection
        run_id: Run ID
        results: Results dict with metrics
    """
    conn.execute("""
        INSERT INTO run_results (
            run_id, net_profit, net_profit_pct, gross_profit, gross_loss,
            win_rate, profit_factor, expectancy, max_drawdown_pct, max_drawdown_value,
            max_drawdown_duration_days, volatility, sharpe_ratio, sortino_ratio,
            calmar_ratio, total_trades, winning_trades, losing_trades,
            avg_win, avg_loss, largest_win, largest_loss,
            max_consecutive_wins, max_consecutive_losses, avg_hold_time_hours,
            exit_reasons
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_id,
        results.get('net_profit'),
        results.get('net_profit_pct'),
        results.get('gross_profit'),
        results.get('gross_loss'),
        results.get('win_rate'),
        results.get('profit_factor'),
        results.get('expectancy'),
        results.get('max_drawdown_pct'),
        results.get('max_drawdown_value'),
        results.get('max_drawdown_duration_days'),
        results.get('volatility'),
        results.get('sharpe_ratio'),
        results.get('sortino_ratio'),
        results.get('calmar_ratio'),
        results.get('total_trades'),
        results.get('winning_trades'),
        results.get('losing_trades'),
        results.get('avg_win'),
        results.get('avg_loss'),
        results.get('largest_win'),
        results.get('largest_loss'),
        results.get('max_consecutive_wins'),
        results.get('max_consecutive_losses'),
        results.get('avg_hold_time_hours'),
        json.dumps(results.get('exit_reasons', {}))
    ))


def save_run_timeseries(
    conn,
    run_id: int,
    equity_curve: list,
    drawdown_curve: list = None,
    monthly_returns: dict = None
) -> None:
    """
    Save compressed timeseries to run_timeseries. Uses zlib for BLOBs.

    Args:
        conn: SQLite connection
        run_id: Run ID
        equity_curve: List of equity points
        drawdown_curve: Optional list of drawdown points
        monthly_returns: Optional dict of monthly returns
    """
    # Compress equity curve
    equity_json = json.dumps(equity_curve)
    equity_blob = zlib.compress(equity_json.encode('utf-8'))

    # Compress drawdown curve if provided
    drawdown_blob = None
    if drawdown_curve:
        drawdown_json = json.dumps(drawdown_curve)
        drawdown_blob = zlib.compress(drawdown_json.encode('utf-8'))

    conn.execute("""
        INSERT INTO run_timeseries (run_id, equity_curve, drawdown_curve, monthly_returns)
        VALUES (?, ?, ?, ?)
    """, (
        run_id,
        equity_blob,
        drawdown_blob,
        json.dumps(monthly_returns) if monthly_returns else None
    ))


def save_trades(conn, run_id: int, trades: list[dict]) -> None:
    """
    Batch-insert trades for a run.

    Args:
        conn: SQLite connection
        run_id: Run ID
        trades: List of trade dicts
    """
    for trade in trades:
        conn.execute("""
            INSERT INTO trades (
                run_id, symbol, side, entry_time, exit_time, hold_time_hours,
                entry_price, exit_price, stop_loss_price, tp1_price, tp2_price, tp3_price,
                quantity, size_usd, pnl, pnl_pct, exit_reason, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            trade.get('symbol'),
            trade.get('side'),
            trade.get('entry_time'),
            trade.get('exit_time'),
            trade.get('hold_time_hours'),
            trade.get('entry_price'),
            trade.get('exit_price'),
            trade.get('stop_loss_price'),
            trade.get('tp1_price'),
            trade.get('tp2_price'),
            trade.get('tp3_price'),
            trade.get('quantity'),
            trade.get('size_usd'),
            trade.get('pnl'),
            trade.get('pnl_pct'),
            trade.get('exit_reason'),
            trade.get('note')
        ))
