"""
Grid Search Repository
======================
CRUD operations for grid_search_results table.
"""
import json
from typing import Optional


def save_result(conn, run_id: int, session_id: str, result: dict) -> int:
    """
    Insert one row into grid_search_results.

    Args:
        conn: SQLite connection
        run_id: Parent run ID
        session_id: Session ID
        result: Dict with x_param, x_value, y_param, y_value + metrics

    Returns:
        int: Inserted row ID
    """
    cursor = conn.execute("""
        INSERT INTO grid_search_results (
            run_id, session_id, x_param, x_value, y_param, y_value,
            net_pnl, net_pnl_pct, sharpe_ratio, profit_factor, win_rate,
            max_drawdown_pct, trade_count, calmar_ratio, sortino_ratio,
            above_threshold
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_id,
        session_id,
        result.get("x_param"),
        result.get("x_value"),
        result.get("y_param"),
        result.get("y_value"),
        result.get("net_pnl"),
        result.get("net_pnl_pct"),
        result.get("sharpe_ratio"),
        result.get("profit_factor"),
        result.get("win_rate"),
        result.get("max_drawdown_pct"),
        result.get("trade_count"),
        result.get("calmar_ratio"),
        result.get("sortino_ratio"),
        result.get("above_threshold", False),
    ))
    return cursor.lastrowid


def save_results_batch(conn, run_id: int, session_id: str, results: list[dict]) -> None:
    """
    Batch insert all grid search results for a run.

    Args:
        conn: SQLite connection
        run_id: Parent run ID
        session_id: Session ID
        results: List of result dicts
    """
    conn.executemany("""
        INSERT INTO grid_search_results (
            run_id, session_id, x_param, x_value, y_param, y_value,
            net_pnl, net_pnl_pct, sharpe_ratio, profit_factor, win_rate,
            max_drawdown_pct, trade_count, calmar_ratio, sortino_ratio,
            above_threshold
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (
            run_id,
            session_id,
            r.get("x_param"),
            r.get("x_value"),
            r.get("y_param"),
            r.get("y_value"),
            r.get("net_pnl"),
            r.get("net_pnl_pct"),
            r.get("sharpe_ratio"),
            r.get("profit_factor"),
            r.get("win_rate"),
            r.get("max_drawdown_pct"),
            r.get("trade_count"),
            r.get("calmar_ratio"),
            r.get("sortino_ratio"),
            r.get("above_threshold", False),
        )
        for r in results
    ])


def get_results(conn, run_id: int) -> list[dict]:
    """
    Return all grid search results for a run, ordered by x_value then y_value.

    Args:
        conn: SQLite connection
        run_id: Run ID

    Returns:
        list[dict]: List of result dicts
    """
    cursor = conn.execute("""
        SELECT id, run_id, session_id, x_param, x_value, y_param, y_value,
               net_pnl, net_pnl_pct, sharpe_ratio, profit_factor, win_rate,
               max_drawdown_pct, trade_count, calmar_ratio, sortino_ratio,
               above_threshold
        FROM grid_search_results
        WHERE run_id = ?
        ORDER BY x_value, y_value
    """, (run_id,))

    return [
        {
            "id": row[0],
            "run_id": row[1],
            "session_id": row[2],
            "x_param": row[3],
            "x_value": row[4],
            "y_param": row[5],
            "y_value": row[6],
            "net_pnl": row[7],
            "net_pnl_pct": row[8],
            "sharpe_ratio": row[9],
            "profit_factor": row[10],
            "win_rate": row[11],
            "max_drawdown_pct": row[12],
            "trade_count": row[13],
            "calmar_ratio": row[14],
            "sortino_ratio": row[15],
            "above_threshold": bool(row[16]),
        }
        for row in cursor.fetchall()
    ]


def get_results_by_session(conn, session_id: str) -> list[dict]:
    """
    Return all grid search results across all runs in a session.

    Args:
        conn: SQLite connection
        session_id: Session ID

    Returns:
        list[dict]: List of result dicts
    """
    cursor = conn.execute("""
        SELECT id, run_id, session_id, x_param, x_value, y_param, y_value,
               net_pnl, net_pnl_pct, sharpe_ratio, profit_factor, win_rate,
               max_drawdown_pct, trade_count, calmar_ratio, sortino_ratio,
               above_threshold
        FROM grid_search_results
        WHERE session_id = ?
        ORDER BY run_id, x_value, y_value
    """, (session_id,))

    return [
        {
            "id": row[0],
            "run_id": row[1],
            "session_id": row[2],
            "x_param": row[3],
            "x_value": row[4],
            "y_param": row[5],
            "y_value": row[6],
            "net_pnl": row[7],
            "net_pnl_pct": row[8],
            "sharpe_ratio": row[9],
            "profit_factor": row[10],
            "win_rate": row[11],
            "max_drawdown_pct": row[12],
            "trade_count": row[13],
            "calmar_ratio": row[14],
            "sortino_ratio": row[15],
            "above_threshold": bool(row[16]),
        }
        for row in cursor.fetchall()
    ]
