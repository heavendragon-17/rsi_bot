# AI Agent Onboarding

> Bootstrap guide for AI agents (Claude Code, Gemini, Cursor, Copilot) working in this repository. Read this after `CLAUDE.md`, before starting any task.

---

## Reading Order

```
1. CLAUDE.md              → Quick-reference: commands, architecture summary, conventions
2. docs/INDEX.md          → Smart routing table: find the right spec for your task
3. docs/agent-workflow.md → Mandatory workflow rules (plan mode, verification, code quality)
4. [Domain spec]          → The specific docs/NN_folder/ for your task (see INDEX.md)
5. [Workflow guide]       → If extending the system, read docs/workflows/add-*.md
```

**Do NOT read every doc file.** Use `INDEX.md` to find only what you need. The full docs are ~3,000+ lines; reading everything wastes context.

---

## Context Budget Guidance

### Backend-Only Tasks (live bot, strategies, exchange adapters)
**Read**: `02_architecture/`, `07_trading_strategies/` or `08_execution_and_oms/`, `15_debugging/`
**Skip**: `10_frontend_dashboard/`, `14_api_reference/` (unless touching the API layer)

### Frontend-Only Tasks (React UI, charts, themes)
**Read**: `10_frontend_dashboard/`, `14_api_reference/`
**Skip**: `05_data_pipeline/`, `07_trading_strategies/`, `08_execution_and_oms/`, `09_portfolio_and_reconciliation/`

### Backtest Engine Tasks
**Read**: `11_testing_and_backtesting/`, `05_data_pipeline/`, `14_api_reference/`
**Skip**: `07_trading_strategies/` (unless modifying strategy interface), `10_frontend_dashboard/` (unless modifying UI)

### Bug Fixes
**Read**: `15_debugging/debug-decision-trees.md` first, then the relevant domain folder
**Skip**: Everything not related to the bug's domain

### New Feature / Extension
**Read**: The relevant `docs/workflows/add-*.md` guide first, then the domain folder it references

---

## Key Conventions Checklist

Before writing any code, internalize these rules:

### Financial Precision
- [ ] All prices use `Decimal` in live trading code
- [ ] `float64` is acceptable only in backtest engine (`MockExchange`, `BacktestEngine`)
- [ ] Database stores money as `TEXT`, parsed with Python `Decimal`

### Order Safety
- [ ] All exit orders (TP, SL) use `reduceOnly=True` in params
- [ ] SL = `stop_market` (NOT `limit`), TP = `limit`
- [ ] Order vocabulary: `market`, `limit`, `stop_market`, `stop_limit`, `trailing_stop`

### Logging
- [ ] Use `structlog` everywhere — zero `print()` statements in production code
- [ ] `import structlog; logger = structlog.get_logger()`
- [ ] Log with structured fields: `logger.info("order_placed", symbol=symbol, order_id=oid)`

### Strategy Pattern
- [ ] Strategies are **stateless**: `analyze(symbol, df, position, context) → AnalysisResult`
- [ ] State lives in `ContextSnapshot`, not on the strategy instance
- [ ] Actions: `OpenPosition`, `ClosePosition`, `MoveSL`, `PartialClose`, `DoNothing`

### Testing
- [ ] Always patch `Indicators.last` explicitly to avoid global state pollution
- [ ] Pass `context=ContextSnapshot(state="CONFIRMING")` in tests, don't mutate strategy
- [ ] Run `python -m pytest tests/ -v` before marking any task complete

---

## Do / Don't Rules

### DO
- Enter plan mode for any non-trivial task (3+ steps or architectural decisions)
- Use subagents to keep the main context window clean
- Run tests and verify correctness before marking tasks done
- Update documentation after code changes (see `INDEX.md` → Documentation Maintenance)
- Use `PortfolioManager` as the sole execution path — never bypass it
- Follow the typed config system (`AppConfig.from_yaml`)

### DON'T
- Don't amend existing commits — create new commits
- Don't skip git hooks (`--no-verify`, `--no-gpg-sign`)
- Don't use `print()` — use `structlog`
- Don't store mutable state on strategy instances — use `ContextSnapshot`
- Don't create `limit` orders for SL — always use `stop_market`
- Don't bypass `PortfolioManager` by calling exchange methods directly
- Don't hard-code API keys or secrets in code — use `.env`
- Don't edit `docs/14_api_reference/database.md` manually — run
  `python scripts/gen_db_docs.py`

---

## Project Quick Facts

| Fact | Value |
|------|-------|
| Language | Python 3.13 (backend), TypeScript/React (frontend) |
| Main branch | `mua-tren-the-nang` |
| Exchange | Binance USDT-M Futures (primary), Lighter DEX (secondary) |
| Config | `config.yaml` + `.env` |
| Database | SQLite (`data/backtest.db`) |
| Logging | `structlog` |
| Tests | `pytest` (`tests/` directory) |
| Frontend build | Vite |
| API | FastAPI + SSE |

---

## Architecture at a Glance

```
WebSocket (BinanceStreamManager) → MarketDataStore → Strategy.analyze() → Actions → PortfolioManager → Exchange → Telegram
```

```
React/Zustand → FastAPI REST + SSE → ProcessPoolExecutor → BacktestEngine → SQLite
```

For detailed architecture, see `docs/02_architecture/system-overview.md`.
