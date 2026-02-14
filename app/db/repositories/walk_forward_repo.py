"""
Walk-Forward Repository
=======================
CRUD operations for walk_forward_results table.
"""
from typing import Optional


def save_result(conn, run_id: int, session_id: str, result: dict) -> int:
    """
    Insert one row into walk_forward_results.

    Args:
        conn: SQLite connection
        run_id: Parent run ID
        session_id: Session ID
        result: Dict with window_index, is_start_date, is_end_date, oos_start_date, oos_end_date,
                best_param, best_param_value, is_metric_value, oos_return_pct, is_positive

    Returns:
        int: Inserted row ID
    """
    cursor = conn.execute("""
        INSERT INTO walk_forward_results (
            run_id, session_id, window_index,
            is_start_date, is_end_date, oos_start_date, oos_end_date,
            best_param, best_param_value, is_metric_value, oos_return_pct,
            is_positive
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_id,
        session_id,
        result.get("window_index"),
        result.get("is_start_date"),
        result.get("is_end_date"),
        result.get("oos_start_date"),
        result.get("oos_end_date"),
        result.get("best_param"),
        result.get("best_param_value"),
        result.get("is_metric_value"),
        result.get("oos_return_pct"),
        result.get("is_positive"),
    ))
    return cursor.lastrowid


def save_results_batch(conn, run_id: int, session_id: str, results: list[dict]) -> None:
    """
    Batch insert all walk-forward results for a run.

    Args:
        conn: SQLite connection
        run_id: Parent run ID
        session_id: Session ID
        results: List of result dicts
    """
    conn.executemany("""
        INSERT INTO walk_forward_results (
            run_id, session_id, window_index,
            is_start_date, is_end_date, oos_start_date, oos_end_date,
            best_param, best_param_value, is_metric_value, oos_return_pct,
            is_positive
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (
            run_id,
            session_id,
            r.get("window_index"),
            r.get("is_start_date"),
            r.get("is_end_date"),
            r.get("oos_start_date"),
            r.get("oos_end_date"),
            r.get("best_param"),
            r.get("best_param_value"),
            r.get("is_metric_value"),
            r.get("oos_return_pct"),
            r.get("is_positive"),
        )
        for r in results
    ])


def get_results(conn, run_id: int) -> list[dict]:
    """
    Return all walk-forward results for a run, ordered by window_index.

    Args:
        conn: SQLite connection
        run_id: Run ID

    Returns:
        list[dict]: List of result dicts
    """
    cursor = conn.execute("""
        SELECT id, run_id, session_id, window_index,
               is_start_date, is_end_date, oos_start_date, oos_end_date,
               best_param, best_param_value, is_metric_value, oos_return_pct,
               is_positive
        FROM walk_forward_results
        WHERE run_id = ?
        ORDER BY window_index
    """, (run_id,))

    return [
        {
            "id": row[0],
            "run_id": row[1],
            "session_id": row[2],
            "window_index": row[3],
            "is_start_date": row[4],
            "is_end_date": row[5],
            "oos_start_date": row[6],
            "oos_end_date": row[7],
            "best_param": row[8],
            "best_param_value": row[9],
            "is_metric_value": row[10],
            "oos_return_pct": row[11],
            "is_positive": bool(row[12]),
        }
        for row in cursor.fetchall()
    ]


def get_results_by_session(conn, session_id: str) -> list[dict]:
    """
    Return all walk-forward results across all runs in a session.

    Args:
        conn: SQLite connection
        session_id: Session ID

    Returns:
        list[dict]: List of result dicts
    """
    cursor = conn.execute("""
        SELECT id, run_id, session_id, window_index,
               is_start_date, is_end_date, oos_start_date, oos_end_date,
               best_param, best_param_value, is_metric_value, oos_return_pct,
               is_positive
        FROM walk_forward_results
        WHERE session_id = ?
        ORDER BY run_id, window_index
    """, (session_id,))

    return [
        {
            "id": row[0],
            "run_id": row[1],
            "session_id": row[2],
            "window_index": row[3],
            "is_start_date": row[4],
            "is_end_date": row[5],
            "oos_start_date": row[6],
            "oos_end_date": row[7],
            "best_param": row[8],
            "best_param_value": row[9],
            "is_metric_value": row[10],
            "oos_return_pct": row[11],
            "is_positive": bool(row[12]),
        }
        for row in cursor.fetchall()
    ]
