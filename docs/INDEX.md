# Documentation Index

> **For AI agents**: Read this file first to determine which folder(s) to consult for your task.
> **For humans**: See the [wiki/](../wiki/) folder for getting-started guides and architecture overviews.

---

## Quick Navigation by Task

| I need to... | Read these folders | Key files |
|---|---|---|
| Bootstrap / first time in this repo | [00_onboarding](00_onboarding/) | [onboarding.md](00_onboarding/onboarding.md) |
| Understand the architecture | [02_architecture](02_architecture/) | [system-overview.md](02_architecture/system-overview.md) |
| Set up the environment or config | [03_setup_and_installation](03_setup_and_installation/) | [configuration.md](03_setup_and_installation/configuration.md) |
| Work on data ingestion or WebSocket | [05_data_pipeline](05_data_pipeline/) | [live-data-flow.md](05_data_pipeline/live-data-flow.md) |
| Research a new trading signal | [06_quant_research](06_quant_research/) | [research-workflow.md](06_quant_research/research-workflow.md) |
| Add or modify a strategy | [07_trading_strategies](07_trading_strategies/), [workflows/](workflows/) | [strategy-pattern.md](07_trading_strategies/strategy-pattern.md), [add-strategy.md](workflows/add-strategy.md) |
| Work on order execution or exchange adapters | [08_execution_and_oms](08_execution_and_oms/), [workflows/](workflows/) | [portfolio-manager.md](08_execution_and_oms/portfolio-manager.md), [add-cex-exchange.md](workflows/add-cex-exchange.md) |
| Work on notifications / Telegram | [08_execution_and_oms](08_execution_and_oms/), [workflows/](workflows/) | [notifications.md](08_execution_and_oms/notifications.md), [add-notifier.md](workflows/add-notifier.md) |
| Understand portfolio or reconciliation | [09_portfolio_and_reconciliation](09_portfolio_and_reconciliation/) | [position-tracking.md](09_portfolio_and_reconciliation/position-tracking.md) |
| Work on the React frontend (backtest UI) | [10_frontend_dashboard](10_frontend_dashboard/) | [ui-architecture.md](10_frontend_dashboard/ui-architecture.md) |
| Work on tests or the backtest engine | [11_testing_and_backtesting](11_testing_and_backtesting/) | [backtest-engine.md](11_testing_and_backtesting/backtest-engine.md), [testing-strategy.md](11_testing_and_backtesting/testing-strategy.md) |
| Deploy or operate the live bot | [12_deployment_and_ops](12_deployment_and_ops/) | [deployment-checklist.md](12_deployment_and_ops/deployment-checklist.md) |
| Handle or prepare for incidents | [13_runbooks_and_postmortems](13_runbooks_and_postmortems/) | [runbook-template.md](13_runbooks_and_postmortems/runbook-template.md) |
| Add or modify API endpoints | [14_api_reference](14_api_reference/), [workflows/](workflows/) | [rest-endpoints.md](14_api_reference/rest-endpoints.md), [add-api-endpoint.md](workflows/add-api-endpoint.md) |
| Debug an issue | [15_debugging](15_debugging/) | [debug-decision-trees.md](15_debugging/debug-decision-trees.md) |
| Enforcement rules, CI/CD, hooks | [16_enforcement](16_enforcement/) | [enforcement.md](16_enforcement/enforcement.md) |
| Understand a past architectural decision | [adr/](adr/) | [README.md](adr/README.md) |

---

## AI Agent Spec Folders

| Folder | Covers | Read when... |
|--------|--------|-------------|
| [00_onboarding/](00_onboarding/) | Agent bootstrap: reading order, conventions, do/don't rules, context budget guidance | **First time in this repo** — read once, then skip |
| [02_architecture/](02_architecture/) | System overview, 3-layer architecture, data types, threading model | Starting any task — provides context for the whole system |
| [03_setup_and_installation/](03_setup_and_installation/) | Environment setup, config.yaml schema, .env vars, exchange modes | Setting up or modifying configuration |
| [05_data_pipeline/](05_data_pipeline/) | WebSocket streaming, CSV downloads, DataFrame schemas, data normalization | Working on data ingestion (`app/data/`) |
| [06_quant_research/](06_quant_research/) | Research workflow, recommended stack, signal evaluation, notebook conventions | Researching new trading signals or strategies |
| [07_trading_strategies/](07_trading_strategies/) | Stateless analyze() pattern, strategy params, entry/exit rules, SL/TP logic | Working on strategies (`app/trading/strategy/`) |
| [08_execution_and_oms/](08_execution_and_oms/) | Order lifecycle, PortfolioManager flow, exchange adapters | Working on execution (`app/trading/exchange/`, `app/trading/portfolio/`) |
| [09_portfolio_and_reconciliation/](09_portfolio_and_reconciliation/) | Position tracking, PnL calculation, capital allocation, known gaps | Working on position/portfolio logic |
| [10_frontend_dashboard/](10_frontend_dashboard/) | React UI architecture, Zustand stores, charts, themes | Working on the frontend (`ui/src/`) |
| [11_testing_and_backtesting/](11_testing_and_backtesting/) | Testing strategy, backtest engine, optimization (grid/walk-forward/sensitivity) | Working on tests or backtest (`tests/`, `app/backtest/`). Backtest sub-packages: `engine/`, `exchange/`, `runners/`, `statistics/`, `reporting/`, `data/` |
| [12_deployment_and_ops/](12_deployment_and_ops/) | Deployment checklist, monitoring, security, production config | Deploying or operating the live bot |
| [13_runbooks_and_postmortems/](13_runbooks_and_postmortems/) | Incident response runbooks, postmortem templates | Handling or preparing for production incidents |
| [14_api_reference/](14_api_reference/) | REST endpoints, SSE events, API config | Working on the FastAPI backend (`app/api/`) |
| [15_debugging/](15_debugging/) | Debug decision trees, log interpretation, common issues | Diagnosing any issue |
| [16_enforcement/](16_enforcement/) | Enforcement rules, CI/CD pipeline, pre-commit hooks, adding new rules | Working on linting, CI, or code quality enforcement |

---

## Workflows (docs/workflows/)

Step-by-step guides for extending the system. Read the relevant workflow **before** making changes — they document non-obvious registration points and required file touches.

| Workflow | Use when... |
|----------|-------------|
| [add-strategy.md](workflows/add-strategy.md) | Adding a new trading strategy |
| [add-cex-exchange.md](workflows/add-cex-exchange.md) | Adding a new CEX via CCXT (Binance, OKX, Bybit, etc.) |
| [add-dex-exchange.md](workflows/add-dex-exchange.md) | Adding a new perp DEX with a custom SDK or REST API |
| [add-notifier.md](workflows/add-notifier.md) | Adding a new notification channel (Discord, Slack, email, etc.) |
| [add-api-endpoint.md](workflows/add-api-endpoint.md) | Adding a new FastAPI endpoint to the backtest backend |
| [add-indicator.md](workflows/add-indicator.md) | Adding new technical indicators to the indicator set |
| [add-data-source.md](workflows/add-data-source.md) | Adding a new market data stream or historical data source |
| [add-backtest-feature.md](workflows/add-backtest-feature.md) | Adding new metrics, optimization modes, or quant features |

---

## Architecture Decision Records (docs/adr/)

Records of significant architectural decisions with context, rationale, and consequences. See [adr/README.md](adr/README.md) for the index.

---

## Key Conventions

- **agent-workflow.md** stays at `docs/` root — **MUST READ before every task**
- **database.md is auto-generated** from ORM models via `scripts/gen_db_docs.py`. Do NOT edit it manually.
- **CLAUDE.md** at project root contains build commands and quick-reference. Not a substitute for these specs.
- **Source of truth hierarchy**: Code > docs/ specs > CLAUDE.md

---

## IMPORTANT: Documentation Maintenance

After completing ANY code change (feature, bug fix, refactor), you MUST update documentation:

1. Use the table below to find which doc folder covers the code you changed
2. Update the relevant file(s) to reflect your changes
3. If you added a new extension point, follow the matching `docs/workflows/add-*.md` first
4. If you modified `app/repository/` models, run `python scripts/gen_db_docs.py`

Skip doc updates only for trivial changes (typo fixes, log message tweaks, comment edits).

### Code Path → Documentation Folder

| Code path modified | Doc folder to update |
|---|---|
| `app/core/interfaces.py` | `02_architecture/` |
| `app/core/config.py` | `03_setup_and_installation/configuration.md` |
| `app/data/` | `05_data_pipeline/` |
| `app/trading/strategy/` | `07_trading_strategies/` |
| `app/trading/exchange/` | `08_execution_and_oms/` |
| `app/trading/portfolio/` | `08_execution_and_oms/` + `09_portfolio_and_reconciliation/` |
| `app/backtest/` | `11_testing_and_backtesting/` |
| `app/api/` | `14_api_reference/` |
| `app/notification/` | [`08_execution_and_oms/notifications.md`](08_execution_and_oms/notifications.md) |
| `app/repository/` | `14_api_reference/` (run `python scripts/gen_db_docs.py`) |
| `ui/src/` | `10_frontend_dashboard/` |
| `config.yaml` schema changes | `03_setup_and_installation/configuration.md` |
| `tests/` | `11_testing_and_backtesting/` |

If you modified `app/core/interfaces.py`, also update `02_architecture/` regardless of the primary domain.

---

## Archived Files (docs/archive/)

Historical specs that have been fully implemented. Kept for reference only — do not use for new work.

| File | Was | Status |
|------|-----|--------|
| SPEC.md | FastAPI integration spec (Phases 1-5) | Fully implemented |
| IMPROVE.md | Architecture improvement spec (PRs 1-8) | Fully implemented |
| PLAN-figma-ui-v3.md | Original UI plan (13 tasks) | Superseded |
| pine-indicators.md | Custom indicator library spec | Archived (feature removed) |
| CSS_VARIABLES.md | Theme system contract | Merged into ui-spec |
