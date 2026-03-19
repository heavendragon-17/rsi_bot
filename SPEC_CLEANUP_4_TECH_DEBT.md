# SPEC Part 4: Tech Debt Inventory

> **Related**: [Overview](SPEC_CLEANUP_1_OVERVIEW.md) · [Migration](SPEC_CLEANUP_2_MIGRATION.md) · [Refactors](SPEC_CLEANUP_3_REFACTORS.md) · [Agent Strategy](SPEC_CLEANUP_5_AGENTS.md)

Full inventory of technical debt discovered during codebase analysis. Items are categorized by severity and mapped to remediation phases.

---

## Severity Definitions

| Severity | Meaning |
|----------|---------|
| **HIGH** | Causes bugs, data inconsistency, or blocks future work. Fix during this cleanup. |
| **MEDIUM** | Code smell or maintainability issue. Fix opportunistically during restructure. |
| **LOW** | Cosmetic or minor. Fix if touching the file anyway. |

---

## HIGH Severity (8 items)

### H1: Fee Constant Drift
**Files**: `app/core/actions.py:37-38`, `app/sim/exchange.py:44-45`, `app/strategies/rsi_no_retest.py:146-147`, `app/backtest/run_portfolio_backtest.py:187-188`
**Problem**: `DEFAULT_TAKER_FEE` defined as `0.0005` in `actions.py`, redefined as `Decimal("0.0005")` in `sim/exchange.py`, and hardcoded as `0.0005` in `rsi_no_retest.py` and `run_portfolio_backtest.py`. If one changes, others won't. Also, `taker_fee` vs `TAKER_FEE` naming inconsistency.
**Fix**: Centralize all fee constants in `app/core/constants.py`. All files import from there.

### H2: WARMUP Magic Number in 3 Places
**Files**: `app/backtest/engine.py:42`, `app/backtest/run_paper_tick_replay.py:68`, `app/core/config.py:102`
**Problem**: `WARMUP = 220` in engine, `WARMUP = 220` in replay (with comment "match BacktestEngine.WARMUP"), `warmup_candles: int = 200` in config (different default!). The config default is 200 but engine uses 220.
**Fix**: Single constant in `app/core/constants.py`. Config default should match.

### H3: Bare Except Clauses
**Files**: `app/backtest/run_batch_analysis.py:213`, `app/backtest/run_batch_analysis.py:957`
**Problem**: `except:` catches everything including `KeyboardInterrupt` and `SystemExit`. Silent failure.
**Fix**: File is being deprecated. If kept, change to `except Exception:` with logging.

### H4: God File — run_batch_analysis.py (962 lines)
**File**: `app/backtest/run_batch_analysis.py`
**Problem**: 962 lines, bare excepts, combines batch orchestration, parameter sweeps, result aggregation, and reporting in one file. No tests.
**Fix**: Move to `deprecated/`. If functionality is needed later, rewrite as proper batch service.

### H5: PortfolioManager God Class (769 lines)
**File**: `app/core/portfolio.py`
**Problem**: Single class handles 5+ responsibilities. See Refactor 1 in Part 3.
**Fix**: Decompose per Refactor 1 spec.

### H6: MockExchange God Class (879 lines)
**File**: `app/backtest/mock_exchange.py`
**Problem**: Single class handles order matching, fill simulation, position tracking, margin calculation, liquidation, funding fees, and SL/TP triggers.
**Fix**: Extract FillSimulator per Refactor 2 spec.

### H7: Strategy Config Loaded from Both YAML and Dataclass
**Files**: `app/strategies/rsi_no_retest.py:130-148`, `app/strategies/rsi_wma_retest.py` (similar)
**Problem**: `rsi_no_retest` reads fee params from `risk_cfg` dict (YAML-derived) while also having a config dataclass. `rsi_momentum` reads entirely from its dataclass. Inconsistent pattern.
**Fix**: All strategies use their frozen config dataclass as single source. Remove YAML strategy params.

### H8: Duplicate Symbol Normalization
**Files**: `app/backtest/mock_exchange.py:29` (`_base_asset()`), `app/services/market_data/normalizer.py:29` (`_normalize_symbol()`), `app/services/notification/telegram_bot.py:209-230` (inline), `app/services/market_data/stream_manager.py:55-82` (inline)
**Problem**: 4 separate implementations of "BTC/USDT" → "BTC" / "BTCUSDT" → "BTC" symbol parsing. Slightly different behavior in edge cases.
**Fix**: Add `normalize_symbol()` and `base_asset()` to `app/core/utils.py`. All files import from there.

---

## MEDIUM Severity (21 items)

### M1: Duplicate `load_dotenv()` Pattern
**Files**: `app/services/execution/cex/binance_adapter.py:24-29`, `app/services/execution/dex/hyperliquid_adapter.py:28-33`, `app/backtest/run_paper_tick_replay.py:49-50`
**Problem**: Each exchange adapter loads `.env` independently with identical try/except pattern.
**Fix**: Load `.env` once at application entry point (`main.py`). Adapters just read `os.environ`.

### M2: `MAX_CANDLES_IN_RAM` Hardcoded
**File**: `app/services/market_data/store.py:13`
**Problem**: `MAX_CANDLES_IN_RAM = 6000` — single hardcoded value, not configurable.
**Fix**: Move to `app/core/constants.py`.

### M3: AppConfig `to_legacy_dict()` Burden
**File**: `app/core/config.py:170+`
**Problem**: `to_legacy_dict()` exists to support components not yet updated to use typed config. Perpetuates dict-based config access.
**Fix**: After restructure, update all consumers to use typed config directly. Remove `to_legacy_dict()`.

### M4: Missing Type Hints in MockExchange
**File**: `app/backtest/mock_exchange.py`
**Problem**: Several methods lack return type annotations. Internal state uses mixed `float`/`Decimal`.
**Fix**: Add type hints during FillSimulator extraction.

### M5: Indicator Silent Fallback
**Files**: `app/utils/indicators.py`, `app/utils/crossover_indicators.py`
**Problem**: If indicator computation fails (e.g., insufficient data), some methods return NaN silently rather than raising. Strategy may trade on NaN data.
**Fix**: Add explicit validation in merged indicator module. Raise `ValueError` on insufficient data.

### M6: Inconsistent Error Handling in Exchange Adapters
**Files**: `app/services/execution/cex/binance_adapter.py`, `app/services/execution/dex/hyperliquid_adapter.py`, `app/services/execution/dex/lighter_adapter.py`
**Problem**: Different adapters catch different exception types and handle errors differently. Some log, some raise, some silently return None.
**Fix**: Standardize: all adapters catch exchange-specific exceptions and wrap in `ExchangeError` from `app/core/exceptions.py`.

### M7: Backtest Reporting (897 lines)
**File**: `app/backtest/reporting.py`
**Problem**: Large file mixing metric computation, HTML generation, and chart rendering. Not a god class but doing too much.
**Fix**: Consider splitting into `metrics.py` (computation) and `reporting.py` (rendering) if touching this file.

### M8: run_paper_tick_replay.py (553 lines)
**File**: `app/backtest/run_paper_tick_replay.py`
**Problem**: Experimental file mixing replay logic, data loading, and live simulation. Uses `WARMUP=220` hardcoded.
**Fix**: Move to `deprecated/`.

### M9: run_portfolio_backtest.py (317 lines)
**File**: `app/backtest/run_portfolio_backtest.py`
**Problem**: Standalone script duplicating backtest engine logic with slight variations.
**Fix**: Move to `deprecated/`.

### M10: Queue Size Hardcoded
**File**: `app/services/notification/notification_worker.py`
**Problem**: Notification queue size likely hardcoded.
**Fix**: Move to constants or make configurable.

### M11: Test Coverage Gaps — Portfolio
**Problem**: No dedicated tests for: position sizing edge cases (zero balance, max position limit), SL/TP ladder with 0-distance SL, notification dispatch failure handling.
**Fix**: Add tests during Portfolio decomposition (each component gets its own test file).

### M12: Test Coverage Gaps — API
**Problem**: Only `test_api_backtest.py` exists. No tests for data routes, history routes, strategy routes.
**Fix**: Add basic route tests during API restructure.

### M13: Test Coverage Gaps — Indicators
**Problem**: No dedicated indicator tests. Indicator correctness is only tested implicitly through strategy tests.
**Fix**: Add `tests/test_indicators.py` during indicator merge.

### M14: Test Coverage Gaps — Config
**Problem**: `test_config.py` and `test_config_validation.py` exist but may not cover the new config structure after strategy params are removed.
**Fix**: Update config tests during config cleanup.

### M15: Test Coverage Gaps — Notification
**Problem**: Only `test_telegram_polling.py`. No tests for notification worker, null notifier, or notification service.
**Fix**: Add basic tests during notification move.

### M16: Late Imports in Exchange Adapters
**Files**: `app/services/execution/cex/binance_adapter.py:24`, `app/services/execution/dex/hyperliquid_adapter.py:28`
**Problem**: `from dotenv import load_dotenv` inside `__init__` method. Non-standard pattern.
**Fix**: Top-level import after .env loading is centralized.

### M17: SimExchange State Complexity
**File**: `app/sim/state.py`
**Problem**: `SimOrder`, `SimPosition`, `SimTradeState` — parallel data model to `Position` in portfolio. Two representations of the same concept.
**Fix**: During FillSimulator extraction, consider unifying position models where possible.

### M18: Percentage Calculations Scattered
**Problem**: TP close percentages calculated differently in portfolio (Decimal-based) vs strategy (float-based). Potential precision mismatch.
**Fix**: Standardize: Decimal in live path, float in backtest (acceptable per conventions).

### M19: Strategy Loader Hardcoded Map
**File**: `app/strategies/loader.py`
**Problem**: `STRATEGY_MAP` is a hardcoded dict. Adding a strategy requires editing this file.
**Fix**: Low priority. Could use entry points or auto-discovery, but current approach is explicit and fine for 3 strategies.

### M20: Unused `app/services/__init__.py` After Move
**Problem**: After moving all subdirs out of `app/services/`, the directory and its `__init__.py` become empty.
**Fix**: Delete `app/services/` entirely after Phase 7.

### M21: Backtest Engine Duplicate Config Building
**Files**: `app/backtest/engine.py:55-75`, `app/backtest/config_builder.py`
**Problem**: `BacktestEngine.__init__` reads risk_cfg dict manually. `config_builder.py` also builds config for API-triggered backtests. Two entry points with slightly different config handling.
**Fix**: Unify through `config_builder.py` for all backtest entry points.

---

## LOW Severity (4 items)

### L1: HTTP Status Magic Numbers
**File**: `app/api/routes/backtest.py`
**Problem**: `HTTPException(status_code=404, ...)` — status codes as magic numbers rather than `status.HTTP_404_NOT_FOUND`.
**Fix**: Use `fastapi.status` constants. Fix during route split.

### L2: Truncation Magic Number
**File**: `app/services/notification/telegram_notifier.py`
**Problem**: Message truncation at hardcoded character limit.
**Fix**: Extract to constant if touching this file.

### L3: Inconsistent Naming
**Problem**: Mix of `snake_case` file names (`mock_exchange.py`) and abbreviations (`sl_tp_calculator.py`). Some files use full names, others abbreviate.
**Fix**: Accept current naming. Not worth the import churn to rename.

### L4: Empty `__init__.py` Files
**Problem**: Several `__init__.py` files are empty or have minimal exports.
**Fix**: Add appropriate `__all__` exports during restructure to make imports cleaner.

---

## Remediation Phases

### Phase A: During Structure Migration (Parts 2, Phases 1-8)
Fix these while moving files:
- **H1**: Fee constant centralization (Phase 1 — create constants.py)
- **H2**: WARMUP centralization (Phase 1)
- **H8**: Symbol normalization dedup (Phase 6)
- **M1**: Centralize dotenv loading (Phase 4)
- **M2**: MAX_CANDLES_IN_RAM (Phase 1)
- **M16**: Late imports cleanup (Phase 4)
- **M20**: Delete empty services/ (Phase 7)
- **L1**: HTTP status constants (Phase 8)
- **L4**: __init__.py exports (all phases)

### Phase B: During Internal Refactors (Part 3)
Fix these during the relevant refactor:
- **H5**: Portfolio decomposition → Refactor 1
- **H6**: MockExchange → Refactor 2
- **H7**: Strategy config inconsistency → Refactor 5
- **M3**: Remove to_legacy_dict() → Refactor 5
- **M4**: Type hints → Refactor 2
- **M5**: Indicator validation → Refactor 3
- **M6**: Error handling standardization → Refactor 2
- **M17**: Position model unification → Refactor 2
- **M18**: Percentage precision → Refactor 1
- **M21**: Config building unification → Refactor 4

### Phase C: Post-Refactor (Cleanup Pass)
Fix these after structure is stable:
- **H3**: Bare excepts (file deprecated, so auto-fixed)
- **H4**: God file deprecated
- **M7**: Reporting split (optional, only if needed)
- **M8**, **M9**: Deprecated files moved
- **M10**: Queue size constant
- **M11-M15**: Test coverage gaps (ongoing)
- **M19**: Strategy loader (leave as-is)
- **L2**, **L3**: Cosmetic fixes

---

## Tech Debt Metrics

| Category | Count | Fixed During Cleanup | Remaining |
|----------|-------|---------------------|-----------|
| HIGH | 8 | 8 (all) | 0 |
| MEDIUM | 21 | 17 | 4 (M7, M10, M15, M19) |
| LOW | 4 | 2 | 2 (L2, L3) |
| **Total** | **33** | **27** | **6** |

Post-cleanup, 6 items remain as acceptable tech debt — none are HIGH severity.

---

*Next: [SPEC Part 5: Multi-Agent Execution Strategy →](SPEC_CLEANUP_5_AGENTS.md)*
