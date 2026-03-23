# SPEC Part 1: Cleanup & Reorganization — Overview

> **Status**: Draft
> **Date**: 2026-03-19
> **Scope**: Full codebase reorganization of `rsi_bot` (78 Python files, 15,350 lines)
> **Related specs**: [Migration](SPEC_CLEANUP_2_MIGRATION.md) · [Refactors](SPEC_CLEANUP_3_REFACTORS.md) · [Tech Debt](SPEC_CLEANUP_4_TECH_DEBT.md) · [Agent Strategy](SPEC_CLEANUP_5_AGENTS.md)

---

## 1. Problem Statement

The codebase has grown organically and accumulated structural debt:

- **God classes**: `PortfolioManager` (769 lines), `MockExchange` (879 lines), `run_batch_analysis.py` (962 lines)
- **Misplaced files**: exchange adapters split across `app/services/execution/` and `app/core/`, Telegram handler buried in `app/services/notification/`, sim exchange isolated in `app/sim/`
- **Duplicate logic**: 3 RSI strategies share config dataclasses, TradeState serialization, crossover detection; 2 indicator files (`indicators.py` 273 lines + `crossover_indicators.py` 225 lines) compute identical RSI/EMA9/WMA45 with different column names. Down cross (SHORT entry) and up cross (LONG setup) use the same detection logic — no reason for separate classes
- **Scattered config**: strategy parameters in `config.yaml`, hardcoded magic numbers (`WARMUP=220` in 3 places, `MAX_CANDLES_IN_RAM=6000`), fee defaults scattered across 4 files
- **Mixed concerns**: backtest API routes (491 lines) contain business logic, SSE streaming, and HTTP handling in one file
- **Deep nesting**: `app/services/execution/cex/binance_adapter.py` is 5 levels deep

---

## 2. Goals

1. **Flat, navigable structure** — find any module in ≤2 directory levels
2. **Single responsibility** — no file >400 lines, no god classes
3. **DRY** — shared strategy logic extracted, one indicator module, centralized constants
4. **Clean boundaries** — interfaces in `core/`, implementations in domain dirs
5. **Safe migration** — incremental moves, tests pass after each step
6. **Updated documentation** — docs and wiki reflect new structure as changes land

### Non-Goals

- Full frontend rewrite (only API contract sync)
- New features or strategy changes
- Performance optimization
- CI/CD pipeline changes

---

## 3. Decision Log

All decisions were made through a detailed interview. This is the authoritative reference.

| # | Topic | Decision | Rationale |
|---|-------|----------|-----------|
| 1 | Strategy duplication | **Keep separate, share utils** via `app/trading/strategy/utils/` | Strategies may diverge; shared utils prevent copy-paste without forcing inheritance |
| 2 | PortfolioManager (769 lines) | **Full decomposition** → TradeExecutor, PositionSizer, SLTPManager, NotificationDispatcher | Each concern testable independently; execution path clearer |
| 3 | Indicators (2 files, overlapping) | **Consolidate into one `Indicators` class** — absorb `CrossoverIndicators` methods (`detect_crossover`, `check_alignment`, `detect_bearish_divergence`) into `Indicators`. Down cross = SHORT entry, up cross = LONG setup. Delete `CrossoverIndicators`. | Same RSI/EMA9/WMA45 logic and params; crossover direction param handles both sides |
| 4 | MockExchange / SimExchange | **Pluggable FillSimulator** with wick-based + tick-based modes | Shared order matching, divergent fill logic made explicit |
| 5 | Backtest API (491 lines) | **Service layer + split routes** | Business logic in service, thin route handlers per domain |
| 6 | Config strategy params | **Move into strategy code**; YAML keeps general config only | Breaking change allowed; each strategy owns its parameters |
| 7 | Directory layout | **Coarser grouping**, singular nouns | Balance between flat and organized |
| 8 | Interfaces location | **Stay centralized** in `app/core/interfaces.py` | Single source of truth for system contracts |
| 9 | Dead code | **Soft deprecate** to top-level `deprecated/` | Recoverable; delete in follow-up after confirming nothing breaks. Note: `run_batch_analysis.py`, `run_paper_tick_replay.py`, `run_portfolio_backtest.py` are NOT dead code — they are core backtest runners used by the UI and are refactored, not deprecated |
| 10 | Import migration | **Incremental moves** — one module at a time, test after each | Safest for a live trading bot |
| 11 | Execution order | **Structure first**, then internal refactors | Establishes clean layout before deep changes |
| 12 | Backtest coupling | **Shared codebase** with live bot | Strategies, models, interfaces reused; only execution differs |
| 13 | `app/utils/` | **Merge into domains**, eliminate the directory | Indicators → `app/data/`, resampler → `app/data/`, logging → `app/core/` |
| 14 | API contracts | **Auto-generate TypeScript** types from Python Pydantic models | Single source of truth in Python |
| 15 | Documentation | **Update alongside** each code change | Prevents docs from drifting during multi-step refactor |
| 16 | Frontend scope | **Backend + API contracts** only | Frontend cleanup is independent work |
| 17 | Breaking changes | **Allowed** with migration notes | Solo project; clean break > backward compat |

---

## 4. Target Directory Layout

```
app/
├── __init__.py
├── core/                          # Layer 0: Contracts & shared models
│   ├── __init__.py
│   ├── interfaces.py              # IExchange, IStrategy, IDataProvider, etc.
│   ├── actions.py                 # OpenPosition, ClosePosition, SIDE_BUY, etc.
│   ├── analysis_result.py         # AnalysisResult
│   ├── config.py                  # AppConfig (general: exchange, risk, symbols)
│   ├── constants.py               # NEW: WARMUP, MAX_CANDLES_IN_RAM, fee defaults
│   ├── context.py                 # SCANNING, CONFIRMING states
│   ├── events.py                  # SignalEvent
│   ├── exceptions.py              # ExchangeError, InsufficientFundsError, etc.
│   ├── logging.py                 # structlog setup
│   ├── snapshots.py               # PositionSnapshot, ContextSnapshot
│   └── utils.py                   # to_decimal, shared tiny helpers
│
├── trading/                       # Layer 1-3: Live trading domain
│   ├── __init__.py
│   ├── strategy/                  # Layer 2: Core logic
│   │   ├── __init__.py
│   │   ├── base.py                # BaseStrategy ABC
│   │   ├── loader.py              # STRATEGY_MAP, dynamic loading
│   │   ├── rsi_momentum.py        # Short setup strategy
│   │   ├── rsi_no_retest.py       # Long setup strategy
│   │   ├── rsi_wma_retest.py      # Long setup strategy (WMA variant)
│   │   └── utils/                 # NEW: shared strategy utilities
│   │       ├── __init__.py
│   │       ├── config_helpers.py  # Config dataclass merge/override logic
│   │       ├── trade_state.py     # TradeState serialization/deserialization
│   │       ├── signal_detection.py# Crossover signal detection wrappers
│   │       └── sl_tp_builders.py  # SL/TP ladder calculation helpers
│   │
│   ├── portfolio/                 # Layer 3: Execution (decomposed)
│   │   ├── __init__.py
│   │   ├── manager.py             # PortfolioManager (slim orchestrator)
│   │   ├── trade_executor.py      # NEW: Entry/exit orchestration
│   │   ├── position_sizer.py      # NEW: Risk-based position sizing
│   │   ├── sl_tp_manager.py       # NEW: SL/TP placement, trailing, moves
│   │   ├── notification_dispatch.py # NEW: Telegram + logging dispatch
│   │   └── models.py              # Position dataclass (from portfolio.py)
│   │
│   ├── exchange/                  # Layer 3: Exchange adapters
│   │   ├── __init__.py
│   │   ├── factory.py             # exchange_factory (creates adapter by mode)
│   │   ├── fill_simulator.py      # NEW: shared FillSimulator base
│   │   ├── binance_adapter.py     # BinanceAdapter (live/paper/testnet)
│   │   ├── hyperliquid_adapter.py # HyperliquidAdapter
│   │   ├── lighter_adapter.py     # LighterAdapter
│   │   └── sim/                   # Simulation-specific
│   │       ├── __init__.py
│   │       ├── sim_exchange.py    # SimExchange (paper trading)
│   │       ├── sim_state.py       # SimOrder, SimPosition, SimTradeState
│   │       ├── sim_funding.py     # Funding rate simulation
│   │       └── sim_stream.py      # Sim stream manager
│   │
│   ├── engine.py                  # Live trading engine (from core/engine.py)
│   ├── runner.py                  # Bot runner (from core/runner.py)
│   ├── event_source.py            # Live event source (from core/event_source.py)
│   └── sl_tp_calculator.py        # SLTPCalculator (from core/sl_tp_calculator.py)
│
├── data/                          # Data ingestion & storage
│   ├── __init__.py
│   ├── store.py                   # MarketDataStore
│   ├── stream_manager.py          # BinanceStreamManager (WebSocket)
│   ├── normalizer.py              # DataNormalizer (raw → OHLCV)
│   ├── indicators.py              # MERGED: all indicator functions
│   └── resampler.py               # Timeframe resampling
│
├── backtest/                      # Backtest domain
│   ├── __init__.py
│   ├── engine.py                  # BacktestEngine
│   ├── mock_exchange.py           # MockExchange (uses FillSimulator wick mode)
│   ├── event_source.py            # BacktestEventSource
│   ├── portfolio_engine.py        # Portfolio backtest engine
│   ├── portfolio_event_source.py  # Portfolio event source
│   ├── reporting.py               # Backtest report generation
│   ├── config_builder.py          # Build config from API request
│   ├── service.py                 # NEW: BacktestService (business logic)
│   ├── download_data.py           # OHLCV data downloader
│   ├── download_tick_data.py      # Tick data downloader
│   ├── runners/                   # REFACTORED: backtest execution modes
│   │   ├── __init__.py
│   │   ├── batch_runner.py        # Multi-symbol parallel backtest orchestration
│   │   ├── portfolio_runner.py    # Unified multi-symbol portfolio backtest
│   │   └── tick_replay.py         # Tick-level simulation with SimExchange
│   ├── export.py                  # NEW: CSV/JSON signal export utilities
│   ├── data_manager.py            # NEW: data download/validation (deduped)
│   ├── batch_report.py            # NEW: BatchHtmlGenerator (from run_batch_analysis)
│   └── enrichment.py              # NEW: _enrich_round_trips + shared helpers
│   # Future directories (planned):
│   # ├── optimization/            # Parameter sweeps, genetic algorithms, AI strategy finder
│   # └── statistics/              # Monte Carlo, probability analysis, confidence intervals
│
├── api/                           # FastAPI backend
│   ├── __init__.py
│   ├── main.py                    # FastAPI app factory
│   ├── executor.py                # ProcessPoolExecutor management
│   ├── schemas.py                 # Pydantic request/response models
│   ├── export_schema.py           # NEW: auto-generate TypeScript types
│   └── routes/
│       ├── __init__.py
│       ├── backtest_run.py        # POST /run, DELETE /cancel (split)
│       ├── backtest_results.py    # GET /results, /timeseries (split)
│       ├── backtest_stream.py     # GET /progress SSE (split)
│       ├── data.py                # Data routes
│       ├── history.py             # History routes
│       └── strategies.py          # Strategy listing routes
│
├── notification/                  # Notification services
│   ├── __init__.py
│   ├── telegram_notifier.py       # TelegramNotifier
│   ├── telegram_bot.py            # Telegram bot command handler
│   ├── notification_service.py    # Notification orchestration
│   ├── notification_worker.py     # Async notification worker
│   └── null_notifier.py           # No-op notifier for testing
│
└── repository/                    # Database layer (unchanged)
    ├── __init__.py
    ├── db_connect.py
    ├── order_repo.py
    └── backtest/
        ├── __init__.py
        ├── database.py
        ├── models.py
        └── seed.py

deprecated/                        # Soft-deprecated code (top-level)
└── (only truly dead code goes here — backtest runners are NOT deprecated)
```

---

## 5. Architecture Diagram (Post-Refactor)

```
┌─────────────────────────────────────────────────────────────┐
│                        main.py                               │
│              ┌────────────┴────────────┐                     │
│         Live Trading              Backtest UI                │
│              │                        │                      │
│   ┌──────────▼──────────┐   ┌────────▼────────┐            │
│   │  trading/runner.py   │   │  api/main.py     │            │
│   │  trading/engine.py   │   │  api/routes/*    │            │
│   └──────────┬──────────┘   └────────┬────────┘            │
│              │                        │                      │
│   ┌──────────▼──────────────────────▼──────────┐           │
│   │              core/interfaces.py              │           │
│   │   IStrategy  IExchange  IDataProvider        │           │
│   └──┬────────────┬──────────────┬──────────────┘           │
│      │            │              │                            │
│  ┌───▼───┐  ┌────▼────┐  ┌─────▼─────┐                    │
│  │trading/│  │trading/ │  │  data/     │                    │
│  │strategy│  │exchange │  │  store     │                    │
│  │  *.py  │  │ + sim/  │  │  stream    │                    │
│  └───┬───┘  └────┬────┘  │  indicators│                    │
│      │           │        └─────┬─────┘                     │
│  ┌───▼───────────▼──────────────▼───┐                      │
│  │    trading/portfolio/             │                       │
│  │  TradeExecutor → PositionSizer    │                       │
│  │  SLTPManager  → NotifDispatcher   │                       │
│  └──────────────┬───────────────────┘                       │
│                 │                                            │
│         ┌───────▼───────┐                                   │
│         │ notification/  │                                   │
│         │ telegram_*.py  │                                   │
│         └───────────────┘                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Breaking Changes

These changes break backward compatibility. All are intentional.

| Change | Impact | Migration |
|--------|--------|-----------|
| Strategy params removed from `config.yaml` | Anyone with custom `config.yaml` must remove strategy-specific keys | Document which keys moved; strategy code has defaults |
| All `app.*` import paths change | Every Python file's imports update | Handled incrementally; no external consumers |
| `PortfolioManager` API changes | Direct callers must use new decomposed classes | `manager.py` remains as thin orchestrator for backward compat |
| `app/utils/` removed | Imports from `app.utils.indicators` etc. must change | Redirected to `app.data.indicators` |
| Deprecated files moved | Scripts referencing old paths break | Files in `deprecated/` with README explaining status |

---

## 7. Success Criteria

- [ ] All 27 existing test files pass
- [ ] `python -c "from app.core import interfaces; from app.trading import engine"` — no circular imports
- [ ] Bot starts in mock mode without errors
- [ ] Short backtest runs end-to-end successfully
- [ ] No file in `app/` exceeds 400 lines (god classes decomposed)
- [ ] `app/utils/` directory no longer exists
- [ ] All docs and wiki pages reference correct file paths
- [ ] TypeScript types auto-generated from Pydantic models

---

*Next: [SPEC Part 2: Migration Map →](SPEC_CLEANUP_2_MIGRATION.md)*
