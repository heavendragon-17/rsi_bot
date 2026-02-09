# Phase 1: Database Layer

> **Phase Type:** Backend | **Estimated Time:** 1 hour | **Depends On:** Phase 0

---

## 🎯 Objective

Create the SQLite database layer with models and repository pattern.

---

## 📖 Required Reading

Before starting, read:
- `.agent-guide/knowledge/DATABASE_SCHEMA.md`
- `docs/DATABASE.md` (authoritative schema)

---

## ✅ Tasks

### Task 1.1: Create Database Package

Create `app/db/__init__.py`:
```python
from .models import Base, Run, RunResult, Trade, Theme
from .repository import BacktestRepository
from .init_db import init_database
```

### Task 1.2: Create SQLAlchemy Models

Create `app/db/models.py` with these tables:

**Table: runs**
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | Primary key, autoincrement |
| strategy_name | TEXT | |
| symbol | TEXT | |
| timeframe | TEXT | |
| start_date | TEXT | ISO format |
| end_date | TEXT | ISO format |
| created_at | TEXT | ISO timestamp |
| config_json | TEXT | JSON string of parameters |

**Table: run_results**
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | Primary key |
| run_id | INTEGER | Foreign key → runs.id |
| total_profit | TEXT | Use TEXT for Decimal precision |
| win_rate | REAL | |
| total_trades | INTEGER | |
| profit_factor | REAL | |
| max_drawdown | TEXT | |
| sharpe_ratio | REAL | |
| metrics_json | TEXT | Additional metrics as JSON |

**Table: run_timeseries**
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | Primary key |
| run_id | INTEGER | Foreign key → runs.id |
| equity_curve | BLOB | Compressed with zlib |
| drawdown_curve | BLOB | Compressed with zlib |

**Table: trades**
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | Primary key |
| run_id | INTEGER | Foreign key → runs.id |
| entry_time | TEXT | |
| exit_time | TEXT | |
| entry_price | TEXT | Decimal |
| exit_price | TEXT | Decimal |
| quantity | TEXT | |
| side | TEXT | 'long' or 'short' |
| pnl | TEXT | Decimal |
| exit_reason | TEXT | 'tp', 'sl', 'signal', 'timeout' |

**Table: themes**
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | Primary key |
| name | TEXT | Unique |
| is_active | INTEGER | Boolean (0/1) |
| colors_json | TEXT | Theme color definitions |

### Task 1.3: Create Repository

Create `app/db/repository.py` with class `BacktestRepository`:

**Methods to implement:**
- `save_run(run_data: dict) -> int` - Save run and return ID
- `get_run(run_id: int) -> dict` - Get run by ID
- `get_all_runs() -> list[dict]` - Get all runs
- `get_run_results(run_id: int) -> dict` - Get results for run
- `save_run_results(run_id: int, results: dict)` - Save results
- `get_trades(run_id: int) -> list[dict]` - Get trades for run
- `save_trades(run_id: int, trades: list[dict])` - Save trades
- `get_timeseries(run_id: int) -> dict` - Decompress and return
- `save_timeseries(run_id: int, equity: list, drawdown: list)` - Compress and save
- `get_themes() -> list[dict]` - Get all themes
- `get_active_theme() -> dict` - Get active theme
- `set_active_theme(theme_name: str)` - Set active theme

**Important:**
- Use `zlib.compress()` / `zlib.decompress()` for timeseries
- Use `Decimal` for monetary values, convert to `str` for SQLite
- Use context managers for database connections

### Task 1.4: Create Database Initialization

Create `app/db/init_db.py`:

```python
def init_database(db_path: str = "data/backtest.db"):
    """Create database and tables if they don't exist."""
    # Create data/ directory if needed
    # Create tables using SQLAlchemy
    # Insert default themes if themes table is empty
```

**Default themes to insert:**
- "dark" (default active)
- "light"
- "midnight"

### Task 1.5: Create Data Directory

Ensure `data/` folder exists at project root for the SQLite database.

---

## 🔍 Verification Checkpoint

Create a test script or run Python interactively:

```python
from app.db import init_database, BacktestRepository

# Initialize database
init_database()

# Test repository
repo = BacktestRepository()

# Save a test run
run_id = repo.save_run({
    "strategy_name": "test",
    "symbol": "BTCUSDT",
    "timeframe": "1h",
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "config_json": "{}"
})

# Verify it was saved
run = repo.get_run(run_id)
assert run is not None
print("Database layer working!")
```

**Expected:**
- `data/backtest.db` file created
- All tables exist
- CRUD operations work

---

## 📤 Report Template

```
## Phase 1 Complete: Database Layer

### Created Files:
- app/db/__init__.py
- app/db/models.py (5 tables)
- app/db/repository.py (BacktestRepository class)
- app/db/init_db.py

### Verification:
- Database created: ✅ / ❌
- Tables exist: ✅ / ❌
- CRUD test passed: ✅ / ❌

### Database Location:
- data/backtest.db

Awaiting "proceed" command for Phase 2.
```

---

## ⏭️ Next Phase

After user approval, proceed to `PHASE_2_BRIDGE.md`
