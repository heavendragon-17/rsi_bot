# ADR 001: Stateless Strategy Pattern

## Status: Accepted

## Context
The original strategy implementation (`rsi_wma_retest`) stored mutable state on `self` (context transitions, entry prices, SL levels). This caused:
- Test pollution: state leaked between test runs unless carefully reset
- Threading bugs: shared strategy instance across symbols was unsafe
- Hard to reason about: state changes scattered across method calls

## Decision
Adopt a stateless `analyze()` pattern where strategies receive all state as parameters and return new state:

```python
analyze(symbol, df, position=PositionSnapshot, context=ContextSnapshot) -> AnalysisResult
```

- `ContextSnapshot` carries the strategy's state machine (SCANNING/CONFIRMING) and metadata
- `PositionSnapshot` provides read-only position data from PortfolioManager
- `AnalysisResult` returns actions and a new `ContextSnapshot`
- The `Engine` owns the `contexts` dict and passes/stores contexts

## Consequences
- **Positive**: Tests are isolated (pass context as param, no global state)
- **Positive**: Thread-safe by design (no shared mutable state)
- **Positive**: Easy to serialize/log state transitions
- **Positive**: Engine can reset context independently (e.g., on position close)
- **Negative**: Legacy `rsi_wma_retest` not yet migrated (still uses old API)
- **Negative**: Slightly more verbose (must pass context in/out)
