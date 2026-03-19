# Code Duplications Report

Generated: 2026-03-19

This document lists all code duplications found in the codebase, organized by
category. Each entry includes file paths, line numbers, and code snippets.
Use this as a checklist across multiple sessions.

---

## 1. Fee Constants (`0.0005` / `0.0002`)

**Canonical source:** `app/core/actions.py:37-38`

| Status | File | Line | Code |
|--------|------|------|------|
| [ ] | `app/core/actions.py` | 37-38 | `DEFAULT_TAKER_FEE = 0.0005` / `DEFAULT_MAKER_FEE = 0.0002` (canonical) |
| [ ] | `app/sim/exchange.py` | 44-45 | `TAKER_FEE = Decimal("0.0005")` / `MAKER_FEE = Decimal("0.0002")` |
| [ ] | `app/backtest/mock_exchange.py` | 52 | `taker_fee: float = 0.0` (different default!) |
| [ ] | `app/backtest/engine.py` | 67-68 | `.get("taker_fee", DEFAULT_TAKER_FEE)` (imports canonical) |
| [ ] | `app/backtest/run_portfolio_backtest.py` | 187-188 | `.get("taker_fee", 0.0005)` (hardcoded, should import) |
| [ ] | `app/strategies/rsi_no_retest.py` | 146-147 | `.get("taker_fee", 0.0005)` (hardcoded, should import) |
| [ ] | `app/strategies/rsi_momentum.py` | 77-78 | `taker_fee: float = DEFAULT_TAKER_FEE` (imports canonical) |

**Fix:** All files should import `DEFAULT_TAKER_FEE` / `DEFAULT_MAKER_FEE` from `app.core.actions`.

---

## 2. Initial Balance Defaults (INCONSISTENT: 1000 vs 10000)

| Status | File | Line | Value | Code |
|--------|------|------|-------|------|
| [ ] | `app/core/config.py` | 74, 81 | 10000 | `initial_balance: Decimal = Decimal("10000")` |
| [ ] | `app/backtest/mock_exchange.py` | 52 | **1000** | `initial_balance: float = 1000.0` |
| [ ] | `app/backtest/engine.py` | 63 | **1000** | `.get("initial_balance", 1000.0)` |
| [ ] | `app/backtest/run_portfolio_backtest.py` | 183 | 10000 | `.get("initial_balance", 10000)` |

**Fix:** Pick one canonical default (probably 10000 from config.py) and import it everywhere.

---

## 3. Leverage Defaults (INCONSISTENT: 1 vs 10)

| Status | File | Line | Value | Code |
|--------|------|------|-------|------|
| [ ] | `app/core/config.py` | 25, 47 | 10 | `leverage: int = 10` |
| [ ] | `app/backtest/config_builder.py` | 17 | 10 | `leverage: int = 10` |
| [ ] | `app/api/schemas.py` | 28 | 10 | `leverage: int = 10` |
| [ ] | `app/backtest/mock_exchange.py` | 52 | **1** | `leverage: int = 1` |
| [ ] | `app/core/portfolio.py` | 107 | **1** | `.get("leverage", 1)` |

**Fix:** Use `RiskConfig.leverage` default (10) as canonical. All fallbacks should match.

---

## 4. `load_config()` Function (3 identical copies)

| Status | File | Line | Code |
|--------|------|------|------|
| [ ] | `app/backtest/backtest.py` | 27-29 | `def load_config(): with open(CONFIG_PATH) ...` |
| [ ] | `app/backtest/run_portfolio_backtest.py` | 42-44 | `def load_config(): with open(CONFIG_PATH) ...` |
| [ ] | `app/backtest/run_batch_analysis.py` | 35-37 | `def load_config(): with open(CONFIG_PATH) ...` |

**Canonical alternative:** `AppConfig.from_yaml()` in `app/core/config.py`.

**Fix:** Either use `AppConfig.from_yaml()` or extract a shared `load_raw_config()` into a common module.

---

## 5. CSV Path Construction (`symbol.replace('/', '')`)

23 occurrences across 11 files. No centralized helper.

| Status | File | Line | Variation |
|--------|------|------|-----------|
| [ ] | `app/backtest/download_data.py` | 58 | `symbol.replace('/', '')` |
| [ ] | `app/backtest/run_portfolio_backtest.py` | 112, 171 | `symbol.replace('/', '')` |
| [ ] | `app/backtest/run_batch_analysis.py` | 259 | `symbol.replace('/', '')` |
| [ ] | `app/backtest/download_tick_data.py` | 53, 71, 88, 185 | `symbol.replace('/', '').upper()` |
| [ ] | `app/backtest/reporting.py` | 118, 871, 888 | `symbol.replace("/", "")` |
| [ ] | `app/api/routes/data.py` | 34, 99 | `symbol.replace("/", "")` |
| [ ] | `app/api/routes/backtest.py` | 61, 78 | `symbol.replace("/", "")` |
| [ ] | `app/sim/funding.py` | 152 | `symbol.replace("/", "").upper()` |
| [ ] | `app/sim/stream_manager.py` | 33, 60 | `symbol.replace("/", "").lower()` / `.upper()` |
| [ ] | `app/services/market_data/normalizer.py` | 33 | `symbol.upper().replace('/', '')` |
| [ ] | `app/services/market_data/stream_manager.py` | 74 | `.strip().upper().replace("/", "")` |
| [ ] | `app/services/notification/telegram_bot.py` | 212, 232 | `symbol.replace("/", "").upper()` |

**Fix:** Create `def sanitize_symbol(symbol: str, case: str = "upper") -> str` in a utils module.

---

## 6. `SCRIPT_DIR` / `PROJECT_ROOT` Boilerplate

Identical 2-line block in every backtest CLI script.

| Status | File | Line | Code |
|--------|------|------|------|
| [ ] | `app/backtest/backtest.py` | 13-14 | `SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))` / `PROJECT_ROOT = ...` |
| [ ] | `app/backtest/run_portfolio_backtest.py` | 15-16 | same |
| [ ] | `app/backtest/run_batch_analysis.py` | 14-15 | same |
| [ ] | `app/backtest/run_paper_tick_replay.py` | 44-45 | same |
| [ ] | `app/backtest/download_data.py` | 13 | `SCRIPT_DIR` only |
| [ ] | `app/backtest/download_tick_data.py` | 20 | `SCRIPT_DIR` only |

**Fix:** Create `app/backtest/paths.py` with `SCRIPT_DIR`, `PROJECT_ROOT`, `DATA_DIR`, `CONFIG_PATH`.

---

## 7. `risk_per_trade_pct` Default (`0.02`)

| Status | File | Line | Code |
|--------|------|------|------|
| [ ] | `app/core/config.py` | 45 | `risk_per_trade_pct: Decimal = Decimal("0.02")` |
| [ ] | `app/core/portfolio.py` | 102 | `.get("risk_per_trade_pct", 0.02)` |
| [ ] | `app/backtest/config_builder.py` | 18 | `risk_per_trade_pct: float = 0.02` |
| [ ] | `app/api/schemas.py` | 29 | `risk_per_trade_pct: str = "0.02"` |
| [ ] | `app/repository/backtest/models.py` | 86 | `default="0.02"` |

**Fix:** Import default from `app.core.config.RiskConfig`.

---

## 8. Default Timeframe (INCONSISTENT: `5m` vs `15m` vs `1h`)

| Status | File | Line | Value | Code |
|--------|------|------|-------|------|
| [ ] | `app/core/config.py` | 101 | `5m` | `timeframe: str = "5m"` |
| [ ] | `app/core/runner.py` | 69 | `15m` | `.get('timeframe', '15m')` |
| [ ] | `app/backtest/engine.py` | 51 | `15m` | `.get("timeframe", "15m")` |
| [ ] | `app/backtest/backtest.py` | 82 | `5m` | `.get('timeframe', '5m')` |
| [ ] | `app/backtest/run_portfolio_backtest.py` | 311 | `15m` | `.get("timeframe", "15m")` |
| [ ] | `app/backtest/run_batch_analysis.py` | 855 | `15m` | `.get("timeframe", "15m")` |
| [ ] | `app/strategies/rsi_no_retest.py` | 130-132 | `15m` | `.get("timeframe", "15m")` |
| [ ] | `app/strategies/rsi_wma_retest.py` | 71 | `1h` | `.get("timeframe", "1h")` |

**Fix:** Use `AppConfig.timeframe` default as canonical. Strategy-specific overrides are fine but should be explicit.

---

## 9. Warmup Period Constants (INCONSISTENT: 200 vs 220)

| Status | File | Line | Value | Code |
|--------|------|------|-------|------|
| [ ] | `app/core/config.py` | 102 | 200 | `warmup_candles: int = 200` |
| [ ] | `app/backtest/engine.py` | 42 | **220** | `WARMUP = 220` |
| [ ] | `app/backtest/run_paper_tick_replay.py` | 68 | **220** | `WARMUP = 220` |

**Fix:** Use one constant. If 220 is intentional (200 + 10% buffer), document it and derive from config.

---

## 10. Data Download/Validation Logic (~30 lines duplicated)

Nearly identical blocks that check CSV existence, count rows, check recency, and auto-download.

| Status | File | Lines | Description |
|--------|------|-------|-------------|
| [ ] | `app/backtest/run_portfolio_backtest.py` | 115-156 | Full download-if-missing block |
| [ ] | `app/backtest/run_batch_analysis.py` | 272-314 | Same logic, copy-pasted |

**Fix:** Extract into `app/backtest/data_utils.py:ensure_data_available(symbol, timeframe, limit)`.

---

## 11. `safe_serialize()` JSON Helper

| Status | File | Line | Code |
|--------|------|------|------|
| [ ] | `app/backtest/run_portfolio_backtest.py` | 266-280 | 15-line function handling Timestamp, Series, ndarray, NaN, datetime |

Only one copy currently, but likely needed elsewhere. Consider centralizing preemptively.

---

## 12. `_parse_dt()` Datetime Helper

| Status | File | Line | Code |
|--------|------|------|------|
| [ ] | `app/api/routes/backtest.py` | 441-450 | 10-line function: None check, isinstance datetime, pd.to_datetime fallback |

Only one copy currently. Monitor for duplication.

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
