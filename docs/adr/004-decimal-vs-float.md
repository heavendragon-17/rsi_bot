# ADR 004: Decimal in Live, float64 in Backtest

## Status: Accepted

## Context
Financial calculations need precision. `Decimal` provides exact arithmetic but is 20-40% slower than `float64` for the math-heavy backtest loop.

## Decision
- **Live trading**: All prices use Python `Decimal` for financial precision
- **Backtest engine**: `MockExchange` uses `float64` for performance
- **Database**: Money stored as `TEXT`, parsed with `Decimal` on read
- **MarketDataStore**: Dual columns — `close` (float64 for pandas math) and `close_dec` (Decimal for precision)

## Consequences
- **Positive**: Live trading has exact arithmetic (no floating-point surprises at exchange precision boundaries)
- **Positive**: Backtest is 20-40% faster per run (significant for grid search with 200+ runs)
- **Positive**: `float64` has 15-16 significant digits — more than sufficient for simulation
- **Negative**: Two code paths for numeric types — must be careful about which to use where
- **Negative**: Conversion overhead at boundaries (strategy produces Decimal actions, MockExchange uses float)
- **Rule**: Never mix Decimal and float in the same arithmetic operation
