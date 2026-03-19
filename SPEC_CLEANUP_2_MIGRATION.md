# SPEC Part 2: File-by-File Migration Map

> **Related**: [Overview](SPEC_CLEANUP_1_OVERVIEW.md) · [Refactors](SPEC_CLEANUP_3_REFACTORS.md) · [Tech Debt](SPEC_CLEANUP_4_TECH_DEBT.md) · [Agent Strategy](SPEC_CLEANUP_5_AGENTS.md)

---

## 1. Complete Migration Table

Every Python file and its destination. Files marked **NEW** are created during refactoring (see Part 3).
Files marked **DEPRECATED** move to `deprecated/`.

### app/core/ → app/core/ (stays, with removals)

| Current Path | New Path | Notes |
|-------------|----------|-------|
| `app/core/__init__.py` | `app/core/__init__.py` | Update exports |
| `app/core/interfaces.py` | `app/core/interfaces.py` | **Stays** — centralized contracts |
| `app/core/actions.py` | `app/core/actions.py` | Stays |
| `app/core/analysis_result.py` | `app/core/analysis_result.py` | Stays |
| `app/core/config.py` | `app/core/config.py` | Stays; remove strategy params, add `warmup_candles` to constants |
| `app/core/context.py` | `app/core/context.py` | Stays |
| `app/core/events.py` | `app/core/events.py` | Stays |
| `app/core/exceptions.py` | `app/core/exceptions.py` | Stays |
| `app/core/logging.py` | `app/core/logging.py` | Stays |
| `app/core/snapshots.py` | `app/core/snapshots.py` | Stays |
| `app/core/utils.py` | `app/core/utils.py` | Stays |
| — | `app/core/constants.py` | **NEW**: WARMUP, MAX_CANDLES_IN_RAM, DEFAULT_MAKER_FEE, DEFAULT_TAKER_FEE |
| `app/core/portfolio.py` | `app/trading/portfolio/` | **MOVES** — decomposed (see Part 3) |
| `app/core/engine.py` | `app/trading/engine.py` | **MOVES** |
| `app/core/runner.py` | `app/trading/runner.py` | **MOVES** |
| `app/core/event_source.py` | `app/trading/event_source.py` | **MOVES** |
| `app/core/sl_tp_calculator.py` | `app/trading/sl_tp_calculator.py` | **MOVES** |

### app/strategies/ → app/trading/strategy/

| Current Path | New Path | Notes |
|-------------|----------|-------|
| `app/strategies/__init__.py` | `app/trading/strategy/__init__.py` | Update |
| `app/strategies/base.py` | `app/trading/strategy/base.py` | Move |
| `app/strategies/loader.py` | `app/trading/strategy/loader.py` | Move; update STRATEGY_MAP imports |
| `app/strategies/rsi_momentum.py` | `app/trading/strategy/rsi_momentum.py` | Move; extract shared utils |
| `app/strategies/rsi_no_retest.py` | `app/trading/strategy/rsi_no_retest.py` | Move; extract shared utils |
| `app/strategies/rsi_wma_retest.py` | `app/trading/strategy/rsi_wma_retest.py` | Move; extract shared utils |
| — | `app/trading/strategy/utils/__init__.py` | **NEW** |
| — | `app/trading/strategy/utils/config_helpers.py` | **NEW** |
| — | `app/trading/strategy/utils/trade_state.py` | **NEW** |
| — | `app/trading/strategy/utils/signal_detection.py` | **NEW** |
| — | `app/trading/strategy/utils/sl_tp_builders.py` | **NEW** |

### app/services/execution/ → app/trading/exchange/

| Current Path | New Path | Notes |
|-------------|----------|-------|
| `app/services/execution/__init__.py` | `app/trading/exchange/__init__.py` | Flatten |
| `app/services/execution/exchange_factory.py` | `app/trading/exchange/factory.py` | Move + rename |
| `app/services/execution/cex/__init__.py` | _(removed)_ | Flatten; no cex/ subdir |
| `app/services/execution/cex/binance_adapter.py` | `app/trading/exchange/binance_adapter.py` | Move |
| `app/services/execution/dex/__init__.py` | _(removed)_ | Flatten; no dex/ subdir |
| `app/services/execution/dex/hyperliquid_adapter.py` | `app/trading/exchange/hyperliquid_adapter.py` | Move |
| `app/services/execution/dex/lighter_adapter.py` | `app/trading/exchange/lighter_adapter.py` | Move |
| — | `app/trading/exchange/fill_simulator.py` | **NEW**: shared FillSimulator |

### app/sim/ → app/trading/exchange/sim/

| Current Path | New Path | Notes |
|-------------|----------|-------|
| `app/sim/__init__.py` | `app/trading/exchange/sim/__init__.py` | Move |
| `app/sim/exchange.py` | `app/trading/exchange/sim/sim_exchange.py` | Move + rename |
| `app/sim/state.py` | `app/trading/exchange/sim/sim_state.py` | Move + rename |
| `app/sim/funding.py` | `app/trading/exchange/sim/sim_funding.py` | Move + rename |
| `app/sim/stream_manager.py` | `app/trading/exchange/sim/sim_stream.py` | Move + rename |

### app/services/market_data/ → app/data/

| Current Path | New Path | Notes |
|-------------|----------|-------|
| `app/services/market_data/__init__.py` | `app/data/__init__.py` | Move |
| `app/services/market_data/store.py` | `app/data/store.py` | Move; use constants for MAX_CANDLES |
| `app/services/market_data/stream_manager.py` | `app/data/stream_manager.py` | Move |
| `app/services/market_data/normalizer.py` | `app/data/normalizer.py` | Move |
| `app/services/market_data/live_event_source.py` | `app/data/live_event_source.py` | Move |

### app/utils/ → merged into domains

| Current Path | New Path | Notes |
|-------------|----------|-------|
| `app/utils/__init__.py` | _(removed)_ | Directory eliminated |
| `app/utils/indicators.py` | `app/data/indicators.py` | **MERGED** with crossover_indicators.py |
| `app/utils/crossover_indicators.py` | _(merged)_ | Content merged into `app/data/indicators.py` |
| `app/utils/resampler.py` | `app/data/resampler.py` | Move |

### app/services/notification/ → app/notification/

| Current Path | New Path | Notes |
|-------------|----------|-------|
| `app/services/notification/__init__.py` | `app/notification/__init__.py` | Move |
| `app/services/notification/telegram_notifier.py` | `app/notification/telegram_notifier.py` | Move |
| `app/services/notification/telegram_bot.py` | `app/notification/telegram_bot.py` | Move |
| `app/services/notification/notification_service.py` | `app/notification/notification_service.py` | Move |
| `app/services/notification/notification_worker.py` | `app/notification/notification_worker.py` | Move |
| `app/services/notification/null_notifier.py` | `app/notification/null_notifier.py` | Move |

### app/backtest/ → app/backtest/ (mostly stays)

| Current Path | New Path | Notes |
|-------------|----------|-------|
| `app/backtest/__init__.py` | `app/backtest/__init__.py` | Stays |
| `app/backtest/engine.py` | `app/backtest/engine.py` | Stays; use constants for WARMUP |
| `app/backtest/mock_exchange.py` | `app/backtest/mock_exchange.py` | Stays; refactored to use FillSimulator |
| `app/backtest/backtest.py` | `app/backtest/backtest.py` | Stays (CLI entry point) |
| `app/backtest/backtest_event_source.py` | `app/backtest/event_source.py` | Rename |
| `app/backtest/config_builder.py` | `app/backtest/config_builder.py` | Stays |
| `app/backtest/download_data.py` | `app/backtest/download_data.py` | Stays |
| `app/backtest/download_tick_data.py` | `app/backtest/download_tick_data.py` | Stays |
| `app/backtest/portfolio_engine.py` | `app/backtest/portfolio_engine.py` | Stays |
| `app/backtest/portfolio_event_source.py` | `app/backtest/portfolio_event_source.py` | Stays |
| `app/backtest/reporting.py` | `app/backtest/reporting.py` | Stays |
| — | `app/backtest/service.py` | **NEW**: BacktestService (extracted from routes) |
| `app/backtest/run_batch_analysis.py` | `deprecated/run_batch_analysis.py` | **DEPRECATED** |
| `app/backtest/run_paper_tick_replay.py` | `deprecated/run_paper_tick_replay.py` | **DEPRECATED** |
| `app/backtest/run_portfolio_backtest.py` | `deprecated/run_portfolio_backtest.py` | **DEPRECATED** |

### app/api/ → app/api/ (routes split)

| Current Path | New Path | Notes |
|-------------|----------|-------|
| `app/api/__init__.py` | `app/api/__init__.py` | Stays |
| `app/api/main.py` | `app/api/main.py` | Stays; update route imports |
| `app/api/executor.py` | `app/api/executor.py` | Stays |
| `app/api/schemas.py` | `app/api/schemas.py` | Stays |
| `app/api/export_schema.py` | `app/api/export_schema.py` | Enhanced for TS type generation |
| `app/api/routes/__init__.py` | `app/api/routes/__init__.py` | Stays |
| `app/api/routes/backtest.py` | Split into 3 files below | **SPLIT** |
| — | `app/api/routes/backtest_run.py` | **NEW**: POST /run, DELETE /cancel |
| — | `app/api/routes/backtest_results.py` | **NEW**: GET /results, /timeseries |
| — | `app/api/routes/backtest_stream.py` | **NEW**: GET /progress SSE |
| `app/api/routes/data.py` | `app/api/routes/data.py` | Stays |
| `app/api/routes/history.py` | `app/api/routes/history.py` | Stays |
| `app/api/routes/strategies.py` | `app/api/routes/strategies.py` | Stays |

### app/repository/ → app/repository/ (unchanged)

| Current Path | New Path | Notes |
|-------------|----------|-------|
| All files | Same paths | No structural changes; only import updates if needed |

### Top-level files

| Current Path | New Path | Notes |
|-------------|----------|-------|
| `main.py` | `main.py` | Update imports |
| `config.yaml` | `config.yaml` | Remove strategy params |
| `SPEC.md` | `docs/archive/SPEC_cicd.md` | Archive |
| `SPEC_1.md` | `docs/archive/SPEC_1.md` | Archive |

---

## 2. Migration Phases

Structure-first approach: move files to new locations, update imports, verify. Internal refactors happen in Phase 8+.

### Phase 1: Skeleton & Constants
**Create new directory structure + `__init__.py` files + `constants.py`**

```
Create:
  app/trading/__init__.py
  app/trading/strategy/__init__.py
  app/trading/strategy/utils/__init__.py
  app/trading/portfolio/__init__.py
  app/trading/exchange/__init__.py
  app/trading/exchange/sim/__init__.py
  app/data/__init__.py
  app/notification/__init__.py
  app/core/constants.py
  deprecated/README.md
```

**Verification gate**: `pytest tests/` passes (no functional changes yet)

---

### Phase 2: Move core/ overflow → trading/
**Move engine, runner, event_source, sl_tp_calculator, portfolio out of core/**

Files moved:
- `app/core/engine.py` → `app/trading/engine.py`
- `app/core/runner.py` → `app/trading/runner.py`
- `app/core/event_source.py` → `app/trading/event_source.py`
- `app/core/sl_tp_calculator.py` → `app/trading/sl_tp_calculator.py`
- `app/core/portfolio.py` → `app/trading/portfolio/manager.py` (+ extract `Position` to `models.py`)

Imports to update:
- `main.py` — imports runner/engine
- `app/backtest/engine.py` — imports sl_tp_calculator
- `app/strategies/*.py` — may import from core
- `tests/test_portfolio_short.py`, `tests/test_position_sizing.py`, etc.

**Verification gate**: `pytest tests/` + `python -c "from app.trading.engine import TradingEngine"`

---

### Phase 3: Move strategies/ → trading/strategy/
**Move all strategy files**

Files moved:
- `app/strategies/base.py` → `app/trading/strategy/base.py`
- `app/strategies/loader.py` → `app/trading/strategy/loader.py`
- `app/strategies/rsi_momentum.py` → `app/trading/strategy/rsi_momentum.py`
- `app/strategies/rsi_no_retest.py` → `app/trading/strategy/rsi_no_retest.py`
- `app/strategies/rsi_wma_retest.py` → `app/trading/strategy/rsi_wma_retest.py`
- Remove `app/strategies/` after move

Imports to update:
- `app/api/routes/strategies.py` — STRATEGY_MAP import
- `app/backtest/engine.py` — strategy loader
- `app/backtest/config_builder.py`
- `tests/test_rsi_momentum.py`, `tests/test_stateless_strategy.py`

**Verification gate**: `pytest tests/` + `python -c "from app.trading.strategy.loader import STRATEGY_MAP"`

---

### Phase 4: Move services/execution/ → trading/exchange/
**Flatten exchange adapters from 5-level nesting to 2-level**

Files moved:
- `app/services/execution/cex/binance_adapter.py` → `app/trading/exchange/binance_adapter.py`
- `app/services/execution/dex/hyperliquid_adapter.py` → `app/trading/exchange/hyperliquid_adapter.py`
- `app/services/execution/dex/lighter_adapter.py` → `app/trading/exchange/lighter_adapter.py`
- `app/services/execution/exchange_factory.py` → `app/trading/exchange/factory.py`
- Remove `app/services/execution/`

Imports to update:
- `app/trading/runner.py` — factory import
- `tests/test_binance_adapter.py`, `tests/test_factory.py`, `tests/test_hyperliquid_adapter.py`

**Verification gate**: `pytest tests/` + `python -c "from app.trading.exchange.factory import create_exchange"`

---

### Phase 5: Move sim/ → trading/exchange/sim/
**Move simulation exchange under trading/exchange/**

Files moved:
- `app/sim/exchange.py` → `app/trading/exchange/sim/sim_exchange.py`
- `app/sim/state.py` → `app/trading/exchange/sim/sim_state.py`
- `app/sim/funding.py` → `app/trading/exchange/sim/sim_funding.py`
- `app/sim/stream_manager.py` → `app/trading/exchange/sim/sim_stream.py`
- Remove `app/sim/`

Imports to update:
- `app/trading/exchange/factory.py` — SimExchange import
- `tests/test_sim_exchange.py`, `tests/test_sim_tick_scanner.py`

**Verification gate**: `pytest tests/` + `python -c "from app.trading.exchange.sim.sim_exchange import SimExchange"`

---

### Phase 6: Move services/market_data/ + utils/ → data/
**Consolidate all data-layer code**

Files moved:
- `app/services/market_data/store.py` → `app/data/store.py`
- `app/services/market_data/stream_manager.py` → `app/data/stream_manager.py`
- `app/services/market_data/normalizer.py` → `app/data/normalizer.py`
- `app/services/market_data/live_event_source.py` → `app/data/live_event_source.py`
- `app/utils/indicators.py` + `app/utils/crossover_indicators.py` → `app/data/indicators.py` (merged)
- `app/utils/resampler.py` → `app/data/resampler.py`
- Remove `app/services/market_data/`, `app/utils/`

Imports to update:
- All strategy files — indicator imports
- `app/trading/engine.py` — store, stream imports
- `app/trading/runner.py` — store, stream imports
- Multiple test files

**Verification gate**: `pytest tests/` + `python -c "from app.data.indicators import Indicators"`

---

### Phase 7: Move services/notification/ → notification/
**Flatten notification layer**

Files moved:
- All 5 files from `app/services/notification/` → `app/notification/`
- Remove `app/services/` (now empty)

Imports to update:
- `app/trading/runner.py` — notification imports
- `app/trading/portfolio/manager.py` — telegram imports
- `tests/test_telegram_polling.py`

**Verification gate**: `pytest tests/` + `python -c "from app.notification.telegram_notifier import TelegramNotifier"`

---

### Phase 8: Restructure API routes + deprecate dead code
**Split backtest routes, move deprecated files**

Files changed:
- `app/api/routes/backtest.py` → split into `backtest_run.py`, `backtest_results.py`, `backtest_stream.py`
- `app/api/main.py` — update router imports
- `app/backtest/run_batch_analysis.py` → `deprecated/run_batch_analysis.py`
- `app/backtest/run_paper_tick_replay.py` → `deprecated/run_paper_tick_replay.py`
- `app/backtest/run_portfolio_backtest.py` → `deprecated/run_portfolio_backtest.py`

**Verification gate**: `pytest tests/` + `python -c "from app.api.main import app"`

---

## 3. Import Update Strategy

For each phase, follow this process:

1. **Move file** with `git mv` (preserves history)
2. **Update imports in the moved file** (its own internal imports)
3. **Grep for old import path** across entire codebase: `grep -rn "from app.old_path" app/ tests/ main.py`
4. **Update all consumers**
5. **Run pytest** — fix any remaining import errors
6. **Commit** — one commit per phase for clean `git bisect`

### Import search patterns per phase

```bash
# Phase 2
grep -rn "from app.core.engine\|from app.core.runner\|from app.core.event_source\|from app.core.sl_tp_calculator\|from app.core.portfolio" app/ tests/ main.py

# Phase 3
grep -rn "from app.strategies" app/ tests/ main.py

# Phase 4
grep -rn "from app.services.execution" app/ tests/ main.py

# Phase 5
grep -rn "from app.sim" app/ tests/ main.py

# Phase 6
grep -rn "from app.services.market_data\|from app.utils" app/ tests/ main.py

# Phase 7
grep -rn "from app.services.notification\|from app.services" app/ tests/ main.py
```

---

## 4. Test File Updates

Tests are updated alongside the code they test (Phase N moves code → Phase N updates test imports).

| Test File | Phase | Import Changes |
|-----------|-------|---------------|
| `tests/test_portfolio_short.py` | 2 | `app.core.portfolio` → `app.trading.portfolio.manager` |
| `tests/test_position_sizing.py` | 2 | `app.core.portfolio` → `app.trading.portfolio.position_sizer` |
| `tests/test_soft_sl.py` | 2 | `app.core.portfolio` → `app.trading.portfolio.manager` |
| `tests/test_partial_tp_sl.py` | 2 | `app.core.portfolio` → `app.trading.portfolio.manager` |
| `tests/test_dynamic_tp.py` | 2 | `app.core.portfolio` → `app.trading.portfolio.manager` |
| `tests/test_candle_close_sl.py` | 2 | `app.core.portfolio` → `app.trading.portfolio.manager` |
| `tests/test_rsi_momentum.py` | 3 | `app.strategies` → `app.trading.strategy` |
| `tests/test_stateless_strategy.py` | 3 | `app.strategies` → `app.trading.strategy` |
| `tests/test_binance_adapter.py` | 4 | `app.services.execution.cex` → `app.trading.exchange` |
| `tests/test_factory.py` | 4 | `app.services.execution` → `app.trading.exchange` |
| `tests/test_hyperliquid_adapter.py` | 4 | `app.services.execution.dex` → `app.trading.exchange` |
| `tests/test_sim_exchange.py` | 5 | `app.sim` → `app.trading.exchange.sim` |
| `tests/test_sim_tick_scanner.py` | 5 | `app.sim` → `app.trading.exchange.sim` |
| `tests/test_mock_exchange_short.py` | 6 | Update if mock_exchange imports change |
| `tests/test_normalized_orders.py` | 4-5 | Exchange imports |
| `tests/test_telegram_polling.py` | 7 | `app.services.notification` → `app.notification` |
| `tests/test_api_backtest.py` | 8 | Route imports |
| `tests/test_engine_events.py` | 2 | `app.core.engine` → `app.trading.engine` |
| `tests/test_engine_results.py` | 2 | `app.core.engine` → `app.trading.engine` |

---

*Next: [SPEC Part 3: Internal Refactors →](SPEC_CLEANUP_3_REFACTORS.md)*
