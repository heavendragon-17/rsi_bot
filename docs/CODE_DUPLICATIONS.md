# Code Duplication and Default-Drift Register

Last revalidated: 2026-08-28

This is a technical-debt register, not an instruction to merge every similar
piece of code. Revalidate behavior and unit semantics before refactoring.

## Highest-value open items

| Area | Current evidence | Risk | Suggested next step |
|---|---|---|---|
| Initial balance defaults | Typed config and most runners use `10000`; `MockExchange`, `BacktestEngine`, and one batch-runner fallback still use `1000` | Direct callers can get different capital and incomparable results | Define one backtest default in a dependency-light module and add a consistency test |
| Timeframe defaults | Typed config uses `5m`; several runners use `15m`; `rsi_wma_retest` has an explicit `1h` strategy fallback | Missing config produces context-dependent behavior | Separate the application default from explicit strategy defaults; reject missing runner inputs where possible |
| Warmup values | `AppConfig.warmup_candles` defaults to `200`; `app.core.constants.WARMUP` is `220` | Different entry points can begin analysis on different candles | Name the 20-candle buffer or derive the engine warmup from config |
| Leverage defaults | Typed risk/config builder/API use `10`; direct `MockExchange()` construction uses `1` | Tests and ad-hoc backtests can differ from configured runs | Require leverage at the exchange boundary or use a shared constant |
| Symbol-to-filename conversion | Slash removal and case conversion remain spread across data, API, backtest, notification, and simulation code | Naming changes can break cache/data lookup in only one path | Expand the existing audit symbol helper into a neutral shared utility with compatibility tests |
| CLI path bootstrapping | Backtest scripts repeat project-root and data-path setup | Launch behavior depends on current working directory | Prefer `python -m` entry points and `pathlib` helpers |

The repeated `risk_per_trade_pct` values are currently aligned at `0.02`, but
they use different types for YAML, Pydantic, ORM, and computation. Treat that
as a schema-boundary concern rather than deduplicating the representations
blindly.

## Resolved or intentionally retained

- Fee defaults are centralized in `app/core/constants.py`.
- Portfolio and batch data preparation share `app/backtest/data/manager.py`.
- Most backtest construction flows through `app/backtest/config_builder.py`.
- Bootstrap audit metrics in `app/backtest/audit/bootstrap_ci.py` intentionally
  remain independent from production statistics. They use different unit
  conventions, avoid hot-loop allocation, and provide an independent check.

## Maintenance rule

When fixing an item, add a regression test that compares all relevant entry
points, then update or remove its row here. File/line references are omitted on
purpose because they age quickly; use `rg` to re-establish the live call sites.
