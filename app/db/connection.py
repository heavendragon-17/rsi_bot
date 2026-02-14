"""
SQLite Connection Manager for Backtest Database
================================================
Thread-safe connection manager with WAL mode and foreign key enforcement.
"""
import sqlite3
import os
from contextlib import contextmanager
from typing import Optional

# DB path constant - relative to project root
DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "backtest.db"
)


@contextmanager
def get_connection(db_path: Optional[str] = None):
    """
    Context manager for SQLite connections.
    Uses WAL mode for concurrent reads and enforces foreign keys.

    Args:
        db_path: Optional custom database path. Defaults to data/backtest.db

    Usage:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT ...")
            conn.commit()

    Yields:
        sqlite3.Connection: Database connection with row factory enabled
    """
    path = db_path or DB_PATH
    
    # Ensure data directory exists
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row  # Enable dict-like access to rows
    
    # Enable WAL mode for concurrent reads
    conn.execute("PRAGMA journal_mode=WAL")
    
    # Enforce foreign key constraints
    conn.execute("PRAGMA foreign_keys=ON")
    
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db_size_mb(db_path: Optional[str] = None) -> float:
    """
    Returns the database file size in MB.

    Args:
        db_path: Optional custom database path

    Returns:
        float: Database size in megabytes
    """
    path = db_path or DB_PATH
    
    if not os.path.exists(path):
        return 0.0
    
    size_bytes = os.path.getsize(path)
    return size_bytes / (1024 * 1024)
