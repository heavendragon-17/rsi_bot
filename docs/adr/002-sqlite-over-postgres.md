# ADR 002: SQLite over Postgres for Backtest Storage

## Status: Accepted

## Context
The backtest UI needs a database to store run history, results, and trade data. Options considered:
- PostgreSQL: full-featured, concurrent writes, network-accessible
- SQLite: zero configuration, embedded, single-file

## Decision
Use SQLite (`data/backtest.db`) with SQLAlchemy ORM.

## Consequences
- **Positive**: Zero setup — database auto-created on first run
- **Positive**: Single file — easy to backup, share, or delete
- **Positive**: No external service dependency
- **Positive**: Good read performance for the query patterns (paginated history, run detail)
- **Negative**: No concurrent writes — must use `--workers 1` with uvicorn
- **Negative**: No network access — can't share database across machines
- **Negative**: Money stored as TEXT (Decimal precision) — no native decimal type
- **Trade-off**: Timeseries data zlib-compressed in BLOB columns (saves ~80% storage, adds decompress step on read)
