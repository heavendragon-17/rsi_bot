# Documentation Index

> **For AI agents**: Read this file first to determine which spec file(s) to consult for your task.
> **For humans**: See the [wiki/](../wiki/) folder for getting-started guides and architecture overviews.

---

## AI Agent Spec Files (docs/)

These files are the **canonical specifications** for building and modifying the system. They contain precise implementation details, data flows, API contracts, and architectural decisions.

| File                                           | Covers                                                                                                   | Read when...                                                              |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| [architecture.md](architecture.md)             | System overview, tech stack, 3-layer clean architecture, threading model                                 | Starting any task — provides context for the whole system                 |
| [live-bot.md](live-bot.md)                     | WebSocket streaming, strategy execution, portfolio management, exchange adapters, multi-symbol runner    | Working on the live trading bot (`main.py`, `app/core/`, `app/services/`) |
| [backtest-engine.md](backtest-engine.md)       | Single backtest flow, batch mode, tick-level paper replay, engine internals, data management, SSE bridge | Working on backtest engine (`app/backtest/`, `app/api/`)                  |
| [optimization.md](optimization.md)             | Grid search, walk-forward optimization, sensitivity analysis                                             | Adding or modifying quant optimization features                           |
| [ui-spec.md](ui-spec.md)                       | Navigation, Zustand stores, charts, themes, CSS variables, Pine indicators, export system                | Working on the React frontend (`ui/src/`)                                 |
| [api-reference.md](api-reference.md)           | All REST + SSE endpoints, request/response schemas                                                       | Adding or modifying API endpoints (`app/api/`)                            |
| [error-handling.md](error-handling.md)         | Error flows, error categories, crash recovery, SSE error events                                          | Implementing error handling or debugging failures                         |
| [strategy-reference.md](strategy-reference.md) | Strategy parameters, entry/exit rules, SL/TP logic, config defaults                                      | Tuning strategy params or modifying strategy logic (`app/strategies/`)    |
| [database.md](database.md)                     | SQLite schema (auto-generated from ORM models)                                                           | Working with the database (`app/repository/backtest/models.py`)           |

## Workflows (docs/workflows/)

Step-by-step guides for extending the system. Read the relevant workflow **before** making changes — they document non-obvious registration points and required file touches.

| Workflow                                                     | Use when...                                                     |
| ------------------------------------------------------------ | --------------------------------------------------------------- |
| [add-cex-exchange.md](workflows/add-cex-exchange.md)         | Adding a new CEX via CCXT (Binance, OKX, Bybit, etc.)           |
| [add-dex-exchange.md](workflows/add-dex-exchange.md)         | Adding a new perp DEX with a custom SDK or REST API             |
| [add-strategy.md](workflows/add-strategy.md)                 | Adding a new trading strategy                                   |
| [add-notifier.md](workflows/add-notifier.md)                 | Adding a new notification channel (Discord, Slack, email, etc.) |
| [add-api-endpoint.md](workflows/add-api-endpoint.md)         | Adding a new FastAPI endpoint to the backtest backend           |
| [add-indicator.md](workflows/add-indicator.md)               | Adding new technical indicators to the indicator set            |
| [add-data-source.md](workflows/add-data-source.md)           | Adding a new market data stream or historical data source       |
| [add-backtest-feature.md](workflows/add-backtest-feature.md) | Adding new metrics, optimization modes, or quant features       |

## Key Conventions

- **DATABASE.md is auto-generated** from ORM models via `scripts/gen_db_docs.py`. Do NOT edit it manually. Design rationale lives as comments in `app/repository/backtest/models.py`.
- **CLAUDE.md** at project root contains build commands, environment setup, and quick-reference architecture. It is NOT a substitute for these spec files.
- **Source of truth hierarchy**: Code > docs/ specs > CLAUDE.md. If a spec contradicts the code, the code wins.

## Archived Files (docs/archive/)

Historical specs that have been fully implemented. Kept for reference only — do not use for new work.

| File                | Was                                     | Status                              |
| ------------------- | --------------------------------------- | ----------------------------------- |
| SPEC.md             | FastAPI integration spec (Phases 1-5)   | Fully implemented                   |
| IMPROVE.md          | Architecture improvement spec (PRs 1-8) | Fully implemented                   |
| PLAN-figma-ui-v3.md | Original UI plan (13 tasks)             | Superseded by DOCS.md → split files |
| CSS_VARIABLES.md    | Theme system contract                   | Merged into ui-spec.md              |

## IMPORTANT: Documentation Maintenance

After completing ANY code change (feature, bug fix, refactor — not just workflow-guided tasks), you MUST update documentation:

1. Use the table below to find which doc file covers the code you changed
2. Update that doc file to reflect your changes (new functions, changed behavior, new config keys, etc.)
3. If you added a new extension point (new exchange, strategy, notifier, etc.), follow the matching workflow in `docs/workflows/` first
4. If you modified `app/repository/` models, run `python scripts/gen_db_docs.py`

Skip doc updates only for trivial changes (typo fixes, log message tweaks, comment edits).

### Code Path → Documentation File

| Code path modified           | Doc file to update                                       |
| ---------------------------- | -------------------------------------------------------- |
| `app/core/interfaces.py`     | `docs/architecture.md`                                   |
| `app/services/execution/`    | `docs/live-bot.md`                                       |
| `app/strategies/`            | `docs/strategy-reference.md`                             |
| `app/backtest/`              | `docs/backtest-engine.md`                                |
| `app/api/`                   | `docs/api-reference.md`                                  |
| `app/services/market_data/`  | `docs/live-bot.md`                                       |
| `app/services/notification/` | `docs/live-bot.md`                                       |
| `app/repository/`            | `docs/database.md` (run `python scripts/gen_db_docs.py`) |
| `ui/src/`                    | `docs/ui-spec.md`                                        |
| `app/core/engine.py`         | `docs/backtest-engine.md`                                |
| `config.yaml` schema changes | `docs/architecture.md`                                   |

If you modified `app/core/interfaces.py`, also update `docs/architecture.md` regardless of the primary domain.
