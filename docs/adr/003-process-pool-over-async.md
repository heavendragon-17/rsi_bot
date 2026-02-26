# ADR 003: ProcessPoolExecutor over Async for Backtests

## Status: Accepted

## Context
Grid search requires running 100-200+ backtests. Python's GIL prevents true parallelism with `ThreadPoolExecutor`. Options:
- `asyncio` with async backtest engine
- `ThreadPoolExecutor` (GIL-bound)
- `ProcessPoolExecutor` (separate processes, no GIL)

## Decision
Use `ProcessPoolExecutor` for backtest parallelism. Each backtest runs in a separate process with no shared state.

## Consequences
- **Positive**: True parallelism — 8-12× speedup on 8-core machines for grid search
- **Positive**: No shared state between runs — inherently safe
- **Positive**: Crash isolation — one failed run doesn't affect others
- **Negative**: Requires `multiprocessing.Queue` → polling thread → `asyncio.Queue` bridge for SSE events
- **Negative**: Higher memory usage (each process loads full CSV)
- **Negative**: Serialization overhead for process startup
- **Trade-off**: Strategy's stateful context (2-candle SL pattern, partial TP tracking) makes async/vectorized approaches incompatible
