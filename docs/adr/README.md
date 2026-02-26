# Architecture Decision Records

> Records of significant architectural decisions with context, rationale, and consequences.

## Format

Each ADR follows:
- **Status**: Accepted / Superseded / Deprecated
- **Context**: What problem or need prompted the decision
- **Decision**: What was decided
- **Consequences**: Trade-offs, implications, what this enables and limits

## Index

| # | Title | Status |
|---|-------|--------|
| [001](001-stateless-strategy.md) | Stateless Strategy Pattern | Accepted |
| [002](002-sqlite-over-postgres.md) | SQLite over Postgres for Backtest Storage | Accepted |
| [003](003-process-pool-over-async.md) | ProcessPoolExecutor over Async for Backtests | Accepted |
| [004](004-decimal-vs-float.md) | Decimal in Live, float64 in Backtest | Accepted |
| [005](005-structlog.md) | structlog over stdlib logging | Accepted |
