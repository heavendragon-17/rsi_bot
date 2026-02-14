"""
Session Repository
==================
CRUD operations for sessions table.
"""
import uuid
import json
from datetime import datetime
from typing import Optional


def create_session(
    conn,
    mode_type: str,
    strategy_id: int,
    config_snapshot: dict,
    git_hash: str = None,
    notes: str = None
) -> str:
    """
    Create a new session. Returns the session_id (UUID string).
    Auto-generates: id (UUID), created_at, last_accessed, status='active'.

    Args:
        conn: SQLite connection
        mode_type: "single" | "batch"
        strategy_id: Foreign key to strategies table
        config_snapshot: Full configuration dict at session creation
        git_hash: Optional git commit hash
        notes: Optional user notes

    Returns:
        str: Session ID (UUID format: "sess_abc123...")
    """
    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    now = datetime.now().isoformat()

    conn.execute("""
        INSERT INTO sessions (id, mode_type, strategy_id, created_at, last_accessed, 
                             status, config_snapshot, git_hash, notes)
        VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
    """, (session_id, mode_type, strategy_id, now, now, 
          json.dumps(config_snapshot), git_hash, notes))

    return session_id


def get_session(conn, session_id: str) -> Optional[dict]:
    """
    Get a single session by ID. Returns None if not found.

    Args:
        conn: SQLite connection
        session_id: Session ID to retrieve

    Returns:
        dict: Session data with parsed JSON fields, or None
    """
    cursor = conn.execute("""
        SELECT id, mode_type, strategy_id, created_at, last_accessed,
               status, config_snapshot, git_hash, notes
        FROM sessions
        WHERE id = ?
    """, (session_id,))

    row = cursor.fetchone()
    if not row:
        return None

    return {
        "id": row[0],
        "mode_type": row[1],
        "strategy_id": row[2],
        "created_at": row[3],
        "last_accessed": row[4],
        "status": row[5],
        "config_snapshot": json.loads(row[6]) if row[6] else {},
        "git_hash": row[7],
        "notes": row[8]
    }


def list_sessions(
    conn,
    mode_type: str = None,
    status: str = None,
    limit: int = 50,
    offset: int = 0
) -> list[dict]:
    """
    List sessions with optional filters, ordered by created_at DESC.

    Args:
        conn: SQLite connection
        mode_type: Optional filter by mode ("single" | "batch")
        status: Optional filter by status ("active" | "archived")
        limit: Maximum number of results
        offset: Pagination offset

    Returns:
        list[dict]: List of session dicts
    """
    query = """
        SELECT id, mode_type, strategy_id, created_at, last_accessed,
               status, config_snapshot, git_hash, notes
        FROM sessions
        WHERE 1=1
    """
    params = []

    if mode_type:
        query += " AND mode_type = ?"
        params.append(mode_type)

    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()

    return [
        {
            "id": row[0],
            "mode_type": row[1],
            "strategy_id": row[2],
            "created_at": row[3],
            "last_accessed": row[4],
            "status": row[5],
            "config_snapshot": json.loads(row[6]) if row[6] else {},
            "git_hash": row[7],
            "notes": row[8]
        }
        for row in rows
    ]


def archive_session(conn, session_id: str) -> bool:
    """
    Set session status to 'archived'. Returns True if updated.

    Args:
        conn: SQLite connection
        session_id: Session ID to archive

    Returns:
        bool: True if session was found and updated
    """
    cursor = conn.execute("""
        UPDATE sessions
        SET status = 'archived'
        WHERE id = ?
    """, (session_id,))

    return cursor.rowcount > 0


def update_last_accessed(conn, session_id: str) -> None:
    """
    Update last_accessed to current timestamp.

    Args:
        conn: SQLite connection
        session_id: Session ID to update
    """
    now = datetime.now().isoformat()
    conn.execute("""
        UPDATE sessions
        SET last_accessed = ?
        WHERE id = ?
    """, (now, session_id))


def delete_session(conn, session_id: str) -> bool:
    """
    Hard-delete a session and ALL related data (cascading).
    Used by cleanup policy. Returns True if deleted.

    Args:
        conn: SQLite connection
        session_id: Session ID to delete

    Returns:
        bool: True if session was found and deleted
    """
    # SQLite doesn't support CASCADE DELETE by default, so we need to manually delete
    # First delete all runs and their related data
    cursor = conn.execute("SELECT id FROM runs WHERE session_id = ?", (session_id,))
    run_ids = [row[0] for row in cursor.fetchall()]

    for run_id in run_ids:
        # Delete trades
        conn.execute("DELETE FROM trades WHERE run_id = ?", (run_id,))
        # Delete tags
        conn.execute("DELETE FROM tags WHERE run_id = ?", (run_id,))
        # Delete run_configs
        conn.execute("DELETE FROM run_configs WHERE run_id = ?", (run_id,))
        # Delete run_results
        conn.execute("DELETE FROM run_results WHERE run_id = ?", (run_id,))
        # Delete run_timeseries
        conn.execute("DELETE FROM run_timeseries WHERE run_id = ?", (run_id,))
        # Delete quant results
        conn.execute("DELETE FROM grid_search_results WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM walk_forward_results WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM sensitivity_results WHERE run_id = ?", (run_id,))

    # Delete runs
    conn.execute("DELETE FROM runs WHERE session_id = ?", (session_id,))

    # Delete session
    cursor = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    return cursor.rowcount > 0
