# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added
- Deterministic repository-local Markdown link validation in pre-commit and CI
- Frontend build and deployment-shell validation in the main CI workflow
- Frontend high/critical dependency audit gate and secure lockfile upgrades
- Dependabot coverage for GitHub Actions, Python, and npm dependencies
- Prioritized infrastructure hardening roadmap
- Enterprise documentation restructure: numbered folder hierarchy in `docs/` for AI agents
- `.env.example` with all environment variables documented
- `SECURITY.md` security policy
- `CHANGELOG.md` (this file)
- `docs/00_onboarding/` — AI agent bootstrap guide
- `docs/06_quant_research/` — Quant research pipeline docs
- `docs/09_portfolio_and_reconciliation/` — Portfolio tracking and known gaps
- `docs/12_deployment_and_ops/` — Deployment and operations guides
- `docs/13_runbooks_and_postmortems/` — Incident response runbooks
- `docs/15_debugging/` — Structured debug guides with decision trees
- `docs/adr/` — Architecture Decision Records

### Changed
- Hardened tag promotion and VPS deployment with exact-ref CI, least-privilege
  workflow permissions, immutable action pins, fail-closed position checks,
  candidate health identity checks, and verified rollback attempts
- Standardized supported runtime documentation and container builds on Python
  3.13; the container now runs as a non-root user
- Reconciled active setup, API, strategy, deployment, and UI documentation;
  moved obsolete root specifications into `docs/archive/root/`
- Removed generated `ui/build/` assets and their commit-back workflow; frontend
  output is now ignored and deterministically rebuilt from the npm lockfile
- Reorganized flat `docs/` files into numbered folder structure
- Enhanced `docs/INDEX.md` with task-based routing table
- Updated `CLAUDE.md` to reference new folder structure
- Updated `README.md` with expanded documentation links
- BTC RSI alert cards now include the chart candle locator and the complete
  point-in-time M5/M15 indicator and price-filter checks.

## [1.2.6] - 2026-08-28

### Fixed
- Updated Binance Futures combined WebSocket consumers to use the current
  `/market/stream` endpoint so live kline and simulation tick callbacks receive
  market data again.

## [1.2.4] - 2026-08-27

### Changed
- Routed BTC RSI M5 alerts to Telegram topic `1147` and M15 alerts to topic `1003`; the ordinary `rsi_no_retest` signal strategy is disabled in the checked-in signal configuration.

## [1.2.3] - 2026-08-27

### Added
- Signal-mode Telegram `/topics` command listing configured strategy topic names and IDs, including inactive entries and the debug topic

### Changed
- Refined BTC RSI alert timeframe checking and worker integration

---

## Historical Milestones

> Retroactive documentation of major changes. See `docs/archive/IMPROVE.md` and `docs/archive/SPEC.md` for full details.

### Architecture Improvements (PRs 1-8)

#### PR8 — Typed Configuration System
- Frozen dataclass config with `__post_init__` validation
- `AppConfig.from_yaml()` loading with type safety

#### PR7 — Normalized Order Vocabulary
- Unified order types: `market`, `limit`, `stop_market`, `stop_limit`, `trailing_stop`
- All exit orders use `reduceOnly=True`
- SL = `stop_market` (not `limit`)

#### PR6 — Stateless Strategy Pattern
- `analyze(symbol, df, position=PositionSnapshot, context=ContextSnapshot) → AnalysisResult`
- Runner stores context per symbol, passes on each call
- Actions: `OpenPosition`, `ClosePosition`, `MoveSL`, `PartialClose`, `DoNothing`

#### PR5 — PortfolioManager as Sole Execution Path
- Removed `BinanceSignalExecutor`
- All order execution flows through `PortfolioManager`

#### PR4 — Clean Interface Hierarchy
- 3-layer architecture: Data Ingestion → Core Logic → Execution
- All interfaces in `app/core/interfaces.py`

#### PR3 — Exchange Factory + DEX Auto-Discovery
- Factory creates adapters based on `config.yaml` mode
- DEX adapters auto-discovered via `importlib`

#### PR2 — BinanceAdapter CCXT Wrapper
- Replaced raw API calls with CCXT
- Paper mode via `set_sandbox_mode(True)`

#### PR1 — structlog Migration
- Replaced all `print()` with structured logging
- Zero print statements policy

### FastAPI Integration (SPEC Phases 1-5)

#### Phase 5 — Optimization Suite
- Grid search with heatmap visualization
- Walk-forward optimization with robustness verdict
- Sensitivity analysis with tornado charts

#### Phase 4 — Batch Mode + Multi-Symbol
- Unified simulation engine for batch backtests
- Multi-symbol data synchronization
- Capital allocation across symbols

#### Phase 3 — Trade Detail Charts
- TradingView Lightweight Charts integration
- Entry/exit markers, SL/TP lines, equity curve

#### Phase 2 — Run History + Comparison
- SQLite storage for backtest results
- Run comparison (2-run detailed, N-run metrics table)
- Pagination and filtering

#### Phase 1 — Core Backtest UI
- React frontend + FastAPI backend
- SSE for real-time progress
- ProcessPoolExecutor for parallel backtests
