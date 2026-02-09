import sqlite3
from pathlib import Path
from contextlib import contextmanager

# Define DB path relative to this file
# app/db/connection.py -> app/db/ -> app/ -> root -> data/backtest.db
DB_PATH = Path(__file__).parent.parent.parent / "data" / "backtest.db"

def get_connection() -> sqlite3.Connection:
    """Get database connection with row factory."""
    # Ensure directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

@contextmanager
def get_cursor():
    """Context manager for cursor with auto-commit."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
