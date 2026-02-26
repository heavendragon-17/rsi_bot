# ADR 005: structlog over stdlib logging

## Status: Accepted

## Context
The original codebase used `print()` statements for debugging and monitoring. This made it impossible to:
- Filter logs by level or component
- Parse logs programmatically
- Add context (symbol, order_id) consistently

## Decision
Migrate all logging to `structlog` with zero `print()` statements in production code.

```python
import structlog
logger = structlog.get_logger()
logger.info("order_placed", symbol="BTC/USDT", order_id="123", amount=0.1)
```

## Consequences
- **Positive**: Structured key=value format — easy to grep, parse, and analyze
- **Positive**: Consistent context binding (symbol, order_id attached automatically)
- **Positive**: Level-based filtering (debug, info, warning, error)
- **Positive**: Thread-safe by default
- **Negative**: Slightly more verbose than `print()` for quick debugging
- **Negative**: Developers must remember to use `structlog`, not `print()`
- **Rule**: Zero `print()` statements in production code. Enforced by code review.
