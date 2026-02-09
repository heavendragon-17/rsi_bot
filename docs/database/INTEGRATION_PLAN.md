# Database Integration Plan

> **Document Type:** Integration Patterns  
> **Agent:** database-architect  
> **Reference:** `docs/DATABASE.md` (CTO-approved schema - DO NOT DUPLICATE)

---

## 1. Schema Validation ✅

The existing `docs/DATABASE.md` schema has been validated against UI requirements:

| UI Feature | Required Table | Status | Notes |
|------------|----------------|--------|-------|
| Run backtest | `runs`, `run_results` | ✅ Exists | Full coverage |
| Store trades | `trades` | ✅ Exists | TEXT precision |
| Equity curves | `run_timeseries` | ✅ Exists | BLOB + zlib |
| Strategy configs | `strategies`, `run_configs` | ✅ Exists | JSON storage |
| Grid Search | `runs.grid_search_parent_id` | ✅ Exists | Self-referential FK |
| Compare runs | `comparisons` | ✅ Exists | run_a, run_b FKs |
| Tagging | `tags` | ✅ Exists | Many-to-one |
| Themes | `themes` | ✅ Exists | N-theme scalable |
| Version control | `runs.git_hash`, `runs.version` | ✅ Exists | Audit trail |
| Simulation costs | `run_configs.fee_tier`, `slippage_model` | ✅ Exists | CTO requirement |

**Result:** No schema modifications required.

---

## 2. Python Repository Layer

### Directory Structure

```
app/repository/
├── __init__.py           # Exports all repositories
├── db.py                 # Connection manager
├── runs_repo.py          # Runs + run_configs + run_results
├── trades_repo.py        # Trades operations
├── timeseries_repo.py    # BLOB compression/decompression
├── strategies_repo.py    # Strategies + configs
├── themes_repo.py        # Theme CRUD
└── comparisons_repo.py   # Comparison operations
```

### Connection Manager

```python
# app/repository/db.py
import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent.parent.parent / "data" / "backtest.db"

def get_connection() -> sqlite3.Connection:
    """Get database connection with row factory."""
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
```

### Decimal Handling Pattern

> Reference: `docs/DATABASE.md` lines 392-417

```python
# app/repository/decimal_utils.py
from decimal import Decimal
from typing import Any, Dict

def to_db(value: Decimal) -> str:
    """Convert Decimal to TEXT for SQLite storage."""
    return str(value)

def from_db(value: str) -> Decimal:
    """Convert TEXT from SQLite to Decimal."""
    return Decimal(value) if value else Decimal("0")

def row_to_dict(row: sqlite3.Row, decimal_fields: list) -> Dict[str, Any]:
    """Convert Row to dict with Decimal conversion for specified fields."""
    result = dict(row)
    for field in decimal_fields:
        if field in result and result[field]:
            result[field] = from_db(result[field])
    return result
```

### BLOB Compression Pattern

> Reference: `docs/DATABASE.md` lines 421-488

```python
# app/repository/timeseries_repo.py
import zlib
import json
from typing import List, Dict, Any

def compress_timeseries(data: List[Dict]) -> bytes:
    """Compress JSON list to BLOB for storage."""
    json_str = json.dumps(data)
    return zlib.compress(json_str.encode('utf-8'))

def decompress_timeseries(blob: bytes) -> List[Dict]:
    """Decompress BLOB to JSON list."""
    if not blob:
        return []
    json_str = zlib.decompress(blob).decode('utf-8')
    return json.loads(json_str)

def save_timeseries(cursor, run_id: int, equity: List, drawdown: List = None):
    """Save compressed time-series to run_timeseries table."""
    cursor.execute("""
        INSERT INTO run_timeseries (run_id, equity_curve, drawdown_curve)
        VALUES (?, ?, ?)
    """, (
        run_id,
        compress_timeseries(equity),
        compress_timeseries(drawdown) if drawdown else None
    ))

def load_timeseries(cursor, run_id: int) -> Dict[str, Any]:
    """Load and decompress time-series from database."""
    cursor.execute("""
        SELECT equity_curve, drawdown_curve, monthly_returns
        FROM run_timeseries WHERE run_id = ?
    """, (run_id,))
    row = cursor.fetchone()
    
    if not row:
        return {'equity_curve': [], 'drawdown_curve': [], 'monthly_returns': {}}
    
    return {
        'equity_curve': decompress_timeseries(row[0]),
        'drawdown_curve': decompress_timeseries(row[1]),
        'monthly_returns': json.loads(row[2]) if row[2] else {}
    }
```

---

## 3. CLI Manager Implementation

> Reference: `docs/DATABASE.md` lines 493-504

### Commands

```bash
# Initialize database with schema
python cli/db_manager.py init

# Run migrations (if schema changes)
python cli/db_manager.py migrate

# Seed default strategies and themes
python cli/db_manager.py seed
```

### Implementation Plan

```python
# cli/db_manager.py
import argparse
import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent.parent / "docs" / "DATABASE.md"
DB_PATH = Path(__file__).parent.parent / "data" / "backtest.db"

def extract_sql_from_markdown(md_path: Path) -> str:
    """Extract SQL from DATABASE.md code blocks."""
    content = md_path.read_text()
    # Parse ```sql ... ``` blocks
    # Return combined SQL statements
    ...

def init_db():
    """Create database with schema from DATABASE.md."""
    DB_PATH.parent.mkdir(exist_ok=True)
    sql = extract_sql_from_markdown(SCHEMA_PATH)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(sql)
    conn.close()
    print(f"✅ Database created: {DB_PATH}")

def seed_db():
    """Insert default strategies and themes from DATABASE.md."""
    # Strategies and themes are in the same SQL file
    # Already included in schema (INSERT INTO statements)
    print("✅ Default data seeded")

def main():
    parser = argparse.ArgumentParser(description="Database manager")
    parser.add_argument("command", choices=["init", "migrate", "seed"])
    args = parser.parse_args()
    
    if args.command == "init":
        init_db()
    elif args.command == "seed":
        seed_db()
    elif args.command == "migrate":
        print("No pending migrations")
```

---

## 4. Query Patterns for UI

### Dashboard List (Fast - No BLOB)

```python
def get_recent_runs(limit: int = 50) -> List[Dict]:
    """Get recent runs for dashboard list."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT r.id, s.name as strategy_name, 
                   rr.net_profit_pct, rr.sharpe_ratio, rr.win_rate,
                   rc.symbol, rc.timeframe,
                   r.created_at, r.status
            FROM runs r
            JOIN strategies s ON r.strategy_id = s.id
            JOIN run_results rr ON r.id = rr.run_id
            JOIN run_configs rc ON r.id = rc.run_id
            WHERE r.status = 'completed'
            ORDER BY r.created_at DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]
```

### Lazy Load Chart Data (On Click)

```python
def get_run_chart_data(run_id: int) -> Dict:
    """Load chart data only when user clicks a run."""
    with get_cursor() as cursor:
        return load_timeseries(cursor, run_id)
```

### Filter by Strategy/Symbol

```python
def filter_runs(strategy: str = None, symbol: str = None) -> List[Dict]:
    """Filter runs by criteria."""
    query = """
        SELECT r.id, s.name, rr.net_profit_pct
        FROM runs r
        JOIN strategies s ON r.strategy_id = s.id
        JOIN run_results rr ON r.id = rr.run_id
        JOIN run_configs rc ON r.id = rc.run_id
        WHERE r.status = 'completed'
    """
    params = []
    
    if strategy:
        query += " AND s.name = ?"
        params.append(strategy)
    if symbol:
        query += " AND rc.symbol = ?"
        params.append(symbol)
    
    query += " ORDER BY r.created_at DESC"
    
    with get_cursor() as cursor:
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
```

---

## 5. Cross-Reference

| Document | Purpose |
|----------|---------|
| [DATABASE.md](../DATABASE.md) | CTO-approved schema (source of truth) |
| [API_CONTRACTS.md](../backend/API_CONTRACTS.md) | How UI calls these repositories |
| [SECURITY_RULES.md](../constraints/SECURITY_RULES.md) | Write access boundaries |
