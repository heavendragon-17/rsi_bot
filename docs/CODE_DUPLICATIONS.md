# Code Duplications Report

Generated: 2026-03-19

This document lists all code duplications found in the codebase, organized by
category. Each entry includes file paths, line numbers, and code snippets.
Use this as a checklist across multiple sessions.

---

## 1. Fee Constants (`0.0005` / `0.0002`)

**Canonical source:** `app/core/constants.py`

| Status | File | Line | Code |
|--------|------|------|------|
| [x] | `app/core/constants.py` | — | `DEFAULT_TAKER_FEE` / `DEFAULT_MAKER_FEE` (canonical, centralized) |
| [x] | `app/trading/exchange/sim/sim_exchange.py` | — | Imports from constants |
| [x] | `app/backtest/exchange/mock_exchange.py` | — | Imports from constants |
| [x] | `app/backtest/engine/backtest_engine.py` | — | Imports from constants |
| [x] | `app/trading/strategy/rsi_no_retest.py` | — | Uses strategy config dataclass |
| [x] | `app/trading/strategy/rsi_momentum.py` | — | Uses strategy config dataclass |

**Fix:** All files now import from `app.core.constants`. ✅ Resolved during refactoring.

---

## 2. Initial Balance Defaults (INCONSISTENT: 1000 vs 10000)

| Status | File | Line | Value | Code |
|--------|------|------|-------|------|
| [ ] | `app/core/config.py` | 74, 81 | 10000 | `initial_balance: Decimal = Decimal("10000")` |
| [ ] | `app/backtest/exchange/mock_exchange.py` | — | `initial_balance: float = 1000.0` |
| [ ] | `app/backtest/engine/backtest_engine.py` | — | `.get("initial_balance", 1000.0)` |
| [ ] | `app/backtest/runners/portfolio_runner.py` | — | `.get("initial_balance", 10000)` |

**Fix:** Pick one canonical default (probably 10000 from config.py) and import it everywhere.

---

## 3. Leverage Defaults (INCONSISTENT: 1 vs 10)

| Status | File | Line | Value | Code |
|--------|------|------|-------|------|
| [ ] | `app/core/config.py` | 25, 47 | 10 | `leverage: int = 10` |
| [ ] | `app/backtest/config_builder.py` | 17 | 10 | `leverage: int = 10` |
| [ ] | `app/api/schemas.py` | 28 | 10 | `leverage: int = 10` |
| [ ] | `app/backtest/exchange/mock_exchange.py` | — | `leverage: int = 1` |
| [ ] | `app/trading/portfolio/manager.py` | — | `.get("leverage", 1)` |

**Fix:** Use `RiskConfig.leverage` default (10) as canonical. All fallbacks should match.

---

## 4. `load_config()` Function (3 identical copies)

| Status | File | Line | Code |
|--------|------|------|------|
| [x] | `app/backtest/backtest.py` | — | `def load_config(): with open(CONFIG_PATH) ...` |
| [x] | `app/backtest/runners/portfolio_runner.py` | — | Uses `AppConfig.from_yaml()` |
| [x] | `app/backtest/runners/batch_runner.py` | — | Uses `AppConfig.from_yaml()` |

**Canonical alternative:** `AppConfig.from_yaml()` in `app/core/config.py`.

**Fix:** Either use `AppConfig.from_yaml()` or extract a shared `load_raw_config()` into a common module.

---

## 5. CSV Path Construction (`symbol.replace('/', '')`)

23 occurrences across 11 files. No centralized helper.

| Status | File | Line | Variation |
|--------|------|------|-----------|
| [ ] | `app/backtest/data/download.py` | — | `symbol.replace('/', '')` |
| [ ] | `app/backtest/runners/portfolio_runner.py` | — | `symbol.replace('/', '')` |
| [ ] | `app/backtest/runners/batch_runner.py` | — | `symbol.replace('/', '')` |
| [ ] | `app/backtest/data/download_tick.py` | — | `symbol.replace('/', '').upper()` |
| [ ] | `app/backtest/reporting/reporter.py` | — | `symbol.replace("/", "")` |
| [ ] | `app/api/routes/data.py` | — | `symbol.replace("/", "")` |
| [ ] | `app/api/routes/backtest_run.py` | — | `symbol.replace("/", "")` |
| [ ] | `app/trading/exchange/sim/sim_funding.py` | — | `symbol.replace("/", "").upper()` |
| [ ] | `app/trading/exchange/sim/sim_stream.py` | — | `symbol.replace("/", "").lower()` / `.upper()` |
| [ ] | `app/data/normalizer.py` | — | `symbol.upper().replace('/', '')` |
| [ ] | `app/data/stream_manager.py` | — | `.strip().upper().replace("/", "")` |
| [ ] | `app/notification/telegram_bot.py` | — | `symbol.replace("/", "").upper()` |

**Fix:** Create `def sanitize_symbol(symbol: str, case: str = "upper") -> str` in a utils module.

---

## 6. `SCRIPT_DIR` / `PROJECT_ROOT` Boilerplate

Identical 2-line block in every backtest CLI script.

| Status | File | Line | Code |
|--------|------|------|------|
| [ ] | `app/backtest/backtest.py` | — | `SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))` / `PROJECT_ROOT = ...` |
| [ ] | `app/backtest/runners/portfolio_runner.py` | — | same |
| [ ] | `app/backtest/runners/batch_runner.py` | — | same |
| [ ] | `app/backtest/runners/tick_replay.py` | — | same |
| [ ] | `app/backtest/data/download.py` | — | `SCRIPT_DIR` only |
| [ ] | `app/backtest/data/download_tick.py` | — | `SCRIPT_DIR` only |

**Fix:** Create `app/backtest/paths.py` with `SCRIPT_DIR`, `PROJECT_ROOT`, `DATA_DIR`, `CONFIG_PATH`.

---

## 7. `risk_per_trade_pct` Default (`0.02`)

| Status | File | Line | Code |
|--------|------|------|------|
| [ ] | `app/core/config.py` | 45 | `risk_per_trade_pct: Decimal = Decimal("0.02")` |
| [ ] | `app/trading/portfolio/manager.py` | — | `.get("risk_per_trade_pct", 0.02)` |
| [ ] | `app/backtest/config_builder.py` | 18 | `risk_per_trade_pct: float = 0.02` |
| [ ] | `app/api/schemas.py` | 29 | `risk_per_trade_pct: str = "0.02"` |
| [ ] | `app/repository/backtest/models.py` | 86 | `default="0.02"` |

**Fix:** Import default from `app.core.config.RiskConfig`.

---

## 8. Default Timeframe (INCONSISTENT: `5m` vs `15m` vs `1h`)

| Status | File | Line | Value | Code |
|--------|------|------|-------|------|
| [ ] | `app/core/config.py` | 101 | `5m` | `timeframe: str = "5m"` |
| [ ] | `app/trading/runner.py` | — | `15m` | `.get('timeframe', '15m')` |
| [ ] | `app/backtest/engine/backtest_engine.py` | — | `15m` | `.get("timeframe", "15m")` |
| [ ] | `app/backtest/backtest.py` | — | `5m` | `.get('timeframe', '5m')` |
| [ ] | `app/backtest/runners/portfolio_runner.py` | — | `15m` | `.get("timeframe", "15m")` |
| [ ] | `app/backtest/runners/batch_runner.py` | — | `15m` | `.get("timeframe", "15m")` |
| [ ] | `app/trading/strategy/rsi_no_retest.py` | — | `15m` | `.get("timeframe", "15m")` |
| [ ] | `app/trading/strategy/rsi_wma_retest.py` | — | `1h` | `.get("timeframe", "1h")` |

**Fix:** Use `AppConfig.timeframe` default as canonical. Strategy-specific overrides are fine but should be explicit.

---

## 9. Warmup Period Constants (INCONSISTENT: 200 vs 220)

| Status | File | Line | Value | Code |
|--------|------|------|-------|------|
| [ ] | `app/core/config.py` | 102 | 200 | `warmup_candles: int = 200` |
| [x] | `app/core/constants.py` | — | **220** | `WARMUP = 220` (canonical, centralized) |
| [x] | `app/backtest/engine/backtest_engine.py` | — | Imports from constants |

**Fix:** Use one constant. If 220 is intentional (200 + 10% buffer), document it and derive from config.

---

## 10. Data Download/Validation Logic (~30 lines duplicated)

Nearly identical blocks that check CSV existence, count rows, check recency, and auto-download.

| Status | File | Lines | Description |
|--------|------|-------|-------------|
| [x] | `app/backtest/runners/portfolio_runner.py` | — | Uses `DataManager` |
| [x] | `app/backtest/runners/batch_runner.py` | — | Uses `DataManager` |

**Fix:** Extracted into `app/backtest/data/manager.py:DataManager`. ✅ Resolved during refactoring.

---

## 11. `safe_serialize()` JSON Helper

| Status | File | Line | Code |
|--------|------|------|------|
| [ ] | `app/backtest/runners/portfolio_runner.py` | — | 15-line function handling Timestamp, Series, ndarray, NaN, datetime |

Only one copy currently, but likely needed elsewhere. Consider centralizing preemptively.

---

## 12. `_parse_dt()` Datetime Helper

| Status | File | Line | Code |
|--------|------|------|------|
| [ ] | `app/api/routes/backtest_results.py` | — | 10-line function: None check, isinstance datetime, pd.to_datetime fallback |

Only one copy currently. Monitor for duplication.

---

## 13. Audit metric reimplementation (Sharpe / profit factor / win rate) — **INTENTIONAL**

| Status | File | Line | Code |
|--------|------|------|------|
| ✅ INTENTIONAL — DO NOT MERGE | `app/backtest/audit/bootstrap_ci.py` | `_sharpe`, `_profit_factor`, `_win_rate` | One-line numpy reimplementations of three metrics also computed by `app/backtest/statistics/compute_core_metrics`. |

This duplication is by design and must NOT be removed. Three reasons, kept in sync with the module docstring of `bootstrap_ci.py`:

1. **Unit-space safety.** `compute_core_metrics`'s `win_rate` is a percentage in `[0, 100]`; the audit's pass thresholds are written in fraction space `[0, 1]`. A dedicated audit `_win_rate` returns fractions only, removing the cross-module conversion footgun.
2. **Hot-loop cost.** `arch.bootstrap.StationaryBootstrap.apply` calls the metric callable 10,000× per metric. `compute_core_metrics` builds an equity-curve list internally — wasted work in the inner loop when all we need is `mean/std`, `pos-sum/neg-sum`, or a boolean mean.
3. **Independence as a check.** The audit is a check *on* the rest of the system. If a bug ever slips into `compute_core_metrics` (e.g. annualization constant drift, unit flip), the audit must catch it — not inherit it. Two implementations that agree are evidence; one shared implementation can hide its own bug.

---

## Summary by Priority

### Critical (inconsistent values - bugs waiting to happen)
1. **Initial balance**: 1000 vs 10000
2. **Leverage**: 1 vs 10
3. **Timeframe**: 5m vs 15m vs 1h
4. **Warmup**: 200 vs 220

### High (same value duplicated - maintenance burden)
5. **Fee constants**: 7 locations
6. **CSV path construction**: 23 locations
7. **load_config()**: 3 identical copies
8. **risk_per_trade_pct**: 5 locations
9. **SCRIPT_DIR/PROJECT_ROOT**: 6 locations

### Medium (duplicated logic blocks)
10. **Data download/validation**: 2 copies of ~30 lines
11. **safe_serialize**: 1 copy (preemptive)
12. **_parse_dt**: 1 copy (preemptive)
