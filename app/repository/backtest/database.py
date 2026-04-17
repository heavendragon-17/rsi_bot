"""
SQLAlchemy engine, session factory, and init_db() for the backtest database.

DB file: <project_root>/data/backtest.db
"""

from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.orm import declarative_base, sessionmaker

# <project_root>/data/backtest.db
# __file__ = app/repository/backtest/database.py  → parents[3] = project root
DB_DIR = Path(__file__).parents[3] / "data"
DB_URL = f"sqlite:///{DB_DIR / 'backtest.db'}"

engine = sa.create_engine(
    DB_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)


@event.listens_for(engine, "connect")
def set_sqlite_pragmas(dbapi_connection, _connection_record):
    """Enable WAL mode and foreign-key enforcement on every new connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def _migrate_add_batch_id(eng) -> None:
    """Add batch_id column to runs table if missing. One-time migration."""
    with eng.connect() as conn:
        result = conn.execute(sa.text("PRAGMA table_info(runs)"))
        columns = {row[1] for row in result}
        if "batch_id" not in columns:
            conn.execute(
                sa.text("ALTER TABLE runs ADD COLUMN batch_id INTEGER REFERENCES batches(id)")
            )
            conn.commit()


def _migrate_add_final_balance(eng) -> None:
    """Add final_balance column to run_results table if missing."""
    with eng.connect() as conn:
        result = conn.execute(sa.text("PRAGMA table_info(run_results)"))
        columns = {row[1] for row in result}
        if "final_balance" not in columns:
            conn.execute(sa.text("ALTER TABLE run_results ADD COLUMN final_balance TEXT"))
            conn.commit()


def _migrate_add_dispersion_range(eng) -> None:
    """Add dispersion_range column to run_timeseries table if missing."""
    with eng.connect() as conn:
        result = conn.execute(sa.text("PRAGMA table_info(run_timeseries)"))
        columns = {row[1] for row in result}
        if "dispersion_range" not in columns:
            conn.execute(sa.text("ALTER TABLE run_timeseries ADD COLUMN dispersion_range BLOB"))
            conn.commit()


def _migrate_add_benchmark_curve(eng) -> None:
    """Add benchmark_curve column to run_timeseries table if missing."""
    with eng.connect() as conn:
        result = conn.execute(sa.text("PRAGMA table_info(run_timeseries)"))
        columns = {row[1] for row in result}
        if "benchmark_curve" not in columns:
            conn.execute(sa.text("ALTER TABLE run_timeseries ADD COLUMN benchmark_curve BLOB"))
            conn.commit()


def init_db() -> None:
    """
    Create all tables (idempotent) and seed initial strategy rows.

    Safe to call on every server startup — `create_all` is a no-op when
    tables already exist.
    """
    DB_DIR.mkdir(parents=True, exist_ok=True)

    # Import models so SQLAlchemy registers them with the metadata before
    # create_all is called.
    import app.repository.backtest.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_add_batch_id(engine)
    _migrate_add_final_balance(engine)
    _migrate_add_dispersion_range(engine)
    _migrate_add_benchmark_curve(engine)

    session = SessionLocal()
    try:
        from app.repository.backtest.seed import seed_strategies

        seed_strategies(session)
    finally:
        session.close()
