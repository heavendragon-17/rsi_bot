# SPEC Enforce 1: Foundation — Fix Baseline + pyproject.toml + Basic CI

> **Status**: Draft
> **Date**: 2026-03-22
> **Scope**: Zero-tolerance baseline, project tooling config, GitHub Actions CI skeleton
> **Related specs**: [Toolstack](SPEC_ENFORCE_2_TOOLSTACK.md) · [Rules](SPEC_ENFORCE_3_RULES.md) · [Coverage & Docs](SPEC_ENFORCE_4_COVERAGE_DOCS.md)

---

## 1. Problem Statement

The codebase has 73+ coding rules but only 7 are enforced via `scripts/arch_lint.py` + Claude Code hooks. There is **no CI/CD pipeline**, **no pre-commit framework**, and **no standard Python tooling** (ruff, mypy, bandit). Human developers have zero automated enforcement. The AI agent only catches arch_lint violations locally.

**Current violations**: 10 (1 import boundary, 8 file size, 1 class count)

**Goal**: Fix all 10 violations to reach zero baseline, then establish CI infrastructure so violations can never be re-introduced.

---

## 2. Decision Log

All decisions from the interview that apply to this PR:

| # | Topic | Decision | Rationale |
|---|-------|----------|-----------|
| 1 | CI platform | GitHub Actions | Already using GitHub |
| 2 | Baseline violations | Fix all before CI goes live | Zero tolerance policy |
| 3 | Scan scope | Full repo (not just changed files) | Completeness over speed |
| 4 | Python version | 3.11 (match production) | Single version, no matrix |
| 5 | CI triggers | PRs + main branch pushes | Safety without excess compute |
| 6 | Caching | pip + pre-commit + mypy | Speed up CI runs |
| 7 | Violation surfacing | PR comment with summary | Fast developer feedback |
| 8 | Branch protection | Require CI pass to merge | Automated gate, no human review |
| 9 | pytest.ini | Migrate to pyproject.toml | Single config file |

---

## 3. Fix 10 Baseline Violations

### 3.1 Import Boundary Violation (1)

**File**: `app/trading/exchange/factory.py:27`
**Violation**: `from app.backtest.mock_exchange import MockExchange` — trading/ imports backtest/
**Fix**: Move import inside the `if mode == "mock":` block (lazy import pattern, already used for SimExchange and BinanceAdapter in the same file).

```python
# Before (line 27, top-level)
from app.backtest.mock_exchange import MockExchange

# After (inside create_exchange(), line ~121)
if mode == "mock":
    from app.backtest.mock_exchange import MockExchange
    ...
```

### 3.2 File Size Violations (8 files)

Each file must be split to stay under 400 lines. Splits follow the Single Responsibility Principle.

#### 3.2.1 `app/backtest/reporting.py` (898 lines → 3 files)

| New File | Content | Est. Lines |
|----------|---------|------------|
| `reporting.py` (keep) | `BacktestReporter` class: `__init__`, `generate_report()`, `_export_csv()`, delegates to html builder | ~100 |
| `reporting_html.py` (new) | `generate_html_report()` function: HTML structure, CSS, JS, chart data rendering. Extracted from `_generate_html_report()` (786 lines) | ~550 |
| `reporting_styles.py` (new) | CSS constants, color palettes, badge styles, responsive breakpoints as string constants | ~250 |

**Approach**: The 786-line `_generate_html_report()` method is the problem. Extract the HTML generation into a standalone function in `reporting_html.py`. Extract all CSS/style strings into `reporting_styles.py` as constants. The main class becomes a thin orchestrator.

#### 3.2.2 `app/backtest/engine.py` (739 lines → 3 files)

| New File | Content | Est. Lines |
|----------|---------|------------|
| `engine.py` (keep) | `BacktestEngine`: `__init__`, `run()`, `_handle_candle_close()`, `compute_results()`, `_close_open_positions()`, `_sync_executed_orders_to_portfolio()`, `_prepare_dataframe()` | ~250 |
| `engine_metrics.py` (new) | Static metric functions: `build_round_trips()`, `create_round_trip()`, `get_highest_exit_reason()`, `calculate_metrics()`, `max_consecutive()`, `calculate_drawdown()`, `calculate_risk_metrics()`, `calculate_monthly_returns()` | ~300 |
| `engine_curves.py` (new) | Equity/drawdown curve builders: `build_equity_curve_dated()`, `build_drawdown_curve_dated()` | ~80 |

**Approach**: All static methods (already marked `@staticmethod`) move to `engine_metrics.py` as module-level functions. Engine imports and calls them.

#### 3.2.3 `app/backtest/mock_exchange.py` (505 lines → 2 files)

| New File | Content | Est. Lines |
|----------|---------|------------|
| `mock_exchange.py` (keep) | `MockExchange`: IExchange interface methods, `__init__`, properties, order routing | ~250 |
| `mock_exchange_executor.py` (new) | `MockOrderExecutor`: `execute_order()` (87 lines PnL/margin logic), `check_liquidation()` (33 lines), `update_stop_loss()` (32 lines), `_calc_hold_duration()` | ~200 |

**Approach**: Extract the heavy `_execute_order()` and liquidation/SL logic into a dedicated executor class. MockExchange delegates to it.

#### 3.2.4 `app/trading/runner.py` (417 lines → 2 files)

| New File | Content | Est. Lines |
|----------|---------|------------|
| `runner.py` (keep) | `MultiSymbolRunner`: `__init__`, `start()`, `stop()`, `wait()`, `get_status()`, `_signal_handler()`, `_log_status()` | ~200 |
| `runner_loop.py` (new) | `run_symbol_loop()` function (113 lines main trading loop), `action_to_signal()` helper (18 lines), `cleanup_on_startup()` (47 lines) | ~200 |

**Approach**: Extract the 113-line `_run_symbol_loop()` and startup helpers into module-level functions. Runner calls them with explicit parameters.

#### 3.2.5 `app/trading/exchange/lighter_adapter.py` (411 lines → 2 files)

| New File | Content | Est. Lines |
|----------|---------|------------|
| `lighter_adapter.py` (keep) | `LighterAdapter`: `__init__`, `_get_client()`, `_run_async()`, symbol mapping, `create_order()`, `cancel_order()`, `set_leverage()`, `fetch_ohlcv()` | ~200 |
| `lighter_queries.py` (new) | `fetch_balance()` (64 lines), `fetch_order()` (33 lines), `fetch_positions()` (66 lines) — all async query wrappers | ~200 |

**Approach**: Move read-only query methods to a separate module. Adapter imports and delegates.

#### 3.2.6 `app/trading/exchange/sim/sim_exchange.py` (447 lines → 2 files)

| New File | Content | Est. Lines |
|----------|---------|------------|
| `sim_exchange.py` (keep) | `SimExchange`: IExchange interface, `__init__`, `create_order()`, sim hooks (`on_kline_open`, `on_tick`), `_order_to_dict()` | ~200 |
| `sim_fill_handler.py` (new) | Fill execution: `execute_fill_from_order()`, `execute_fill_from_result()`, `open_position_locked()`, `close_position_locked()`, notification capture, position linking helpers | ~250 |

**Approach**: Extract all fill/execution logic into a `SimFillHandler` class. SimExchange delegates fill operations to it.

#### 3.2.7 `app/trading/strategy/rsi_momentum.py` (414 lines → 3 files)

| New File | Content | Est. Lines |
|----------|---------|------------|
| `rsi_momentum.py` (keep) | `RsiMomentumConfig` dataclass, `RsiMomentumStrategy`: `__init__`, `analyze()` orchestrator | ~120 |
| `rsi_momentum_entry.py` (new) | `check_entry()` function (168 lines): signal validation (alignment, crossover, spread, divergence), SL/TP computation, returns `OpenPosition` | ~170 |
| `rsi_momentum_exit.py` (new) | `manage_exit()` function (83 lines): lock-profit trigger, candle-close SL, returns `MoveSL`/`ClosePosition` | ~100 |

**Approach**: Extract the 168-line `_check_entry()` and 83-line `_manage_exit()` into module-level functions. Strategy's `analyze()` becomes a thin dispatcher.

#### 3.2.8 `app/trading/strategy/rsi_no_retest.py` (573 lines → 3 files)

| New File | Content | Est. Lines |
|----------|---------|------------|
| `rsi_no_retest.py` (keep) | `RsiNoRetestConfig` dataclass, `RsiNoRetestStrategy`: `__init__`, `analyze()` state machine dispatcher | ~150 |
| `rsi_no_retest_entry.py` (new) | Entry state machine (SCANNING → CONFIRMING): `detect_reclaim()`, `pullback_filter()`, RSI spread confirmation, SL/TP computation | ~200 |
| `rsi_no_retest_exit.py` (new) | Exit management: pending candle SL, lock-profit trigger, candle-close SL, `compute_sl()`, `compute_price_at_rr()` | ~180 |

**Approach**: The 275-line `analyze()` is a state machine. Split by state: entry logic (SCANNING/CONFIRMING with no position) goes to `_entry.py`, exit logic (position open) goes to `_exit.py`. Calculator helpers go with exit (they're used for SL moves).

### 3.3 Class Count Violation (1)

**File**: `app/core/interfaces.py` — 4 classes: `IIndicators`, `IExchange`, `IPortfolio`, `INotifier`
**Issue**: arch_lint counts these as "real classes" because they have 3+ methods.
**Fix**: Update `scripts/arch_lint.py` to exempt **pure ABCs** (classes where ALL non-dunder methods are `@abstractmethod`). These are contracts, not implementations — they belong together per Decision #8 in SPEC_CLEANUP_1.

```python
# In check_class_count(), add after is_dataclass/is_enum checks:
is_pure_abc = all(
    isinstance(n, ast.FunctionDef) and
    any(isinstance(d, ast.Name) and d.id == "abstractmethod"
        for d in n.decorator_list)
    for n in node.body
    if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")
)
if is_dataclass or is_enum or is_pure_abc:
    continue
```

---

## 4. Create `pyproject.toml`

Migrate `pytest.ini` config and add tool configurations. This becomes the single source of truth for all Python tooling.

```toml
[project]
name = "rsi-bot"
requires-python = ">=3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
pythonpath = ["."]
markers = [
    "slow: marks tests as slow",
    "integration: requires external services",
]

[tool.coverage.run]
source = ["app"]
omit = ["app/__pycache__/*"]

[tool.coverage.report]
show_missing = true
fail_under = 0

[tool.ruff]
target-version = "py311"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP"]
ignore = ["E501"]

[tool.ruff.lint.isort]
known-first-party = ["app"]

[tool.mypy]
python_version = "3.11"
check_untyped_defs = false
disallow_untyped_defs = false
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true

[tool.bandit]
targets = ["app"]
exclude_dirs = ["tests", "scripts"]
skips = ["B101"]
```

**Delete**: `pytest.ini` (migrated to pyproject.toml)

---

## 5. Create `.github/workflows/ci.yml`

Initial CI with 3 jobs. Expanded in later PRs.

```yaml
name: CI

on:
  push:
    branches: [mua-tren-the-nang]
  pull_request:
    branches: [mua-tren-the-nang]

jobs:
  arch-lint:
    name: Architecture Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Run architecture lint
        run: python scripts/arch_lint.py
      - name: Post violation summary
        if: failure() && github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const { execSync } = require('child_process');
            const output = execSync('python scripts/arch_lint.py 2>&1 || true').toString();
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: `## Architecture Lint Failed\n\n\`\`\`\n${output}\n\`\`\``
            });

  ruff:
    name: Ruff Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install ruff
      - name: Ruff check
        run: ruff check app/ tests/ scripts/
      - name: Post ruff summary
        if: failure() && github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const { execSync } = require('child_process');
            const output = execSync('ruff check app/ tests/ scripts/ 2>&1 || true').toString();
            const truncated = output.substring(0, 3000);
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: `## Ruff Lint Failed\n\n\`\`\`\n${truncated}\n\`\`\``
            });

  tests:
    name: Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        run: pytest tests/ -v --tb=short
```

---

## 6. Verification Checklist

After this PR is complete:

- [ ] `python scripts/arch_lint.py` exits 0 (zero violations)
- [ ] All 8 oversized files are under 400 lines
- [ ] `app/trading/exchange/factory.py` no longer has top-level backtest import
- [ ] `pyproject.toml` exists with pytest, ruff, mypy, bandit, coverage config
- [ ] `pytest.ini` is deleted
- [ ] `.github/workflows/ci.yml` exists with arch-lint, ruff, tests jobs
- [ ] `pytest tests/` passes (all existing tests)
- [ ] No new files violate any arch_lint rule

---

## 7. Files Changed Summary

### New Files (15)
| File | Source |
|------|--------|
| `pyproject.toml` | New |
| `.github/workflows/ci.yml` | New |
| `app/backtest/reporting_html.py` | Split from reporting.py |
| `app/backtest/reporting_styles.py` | Split from reporting.py |
| `app/backtest/engine_metrics.py` | Split from engine.py |
| `app/backtest/engine_curves.py` | Split from engine.py |
| `app/backtest/mock_exchange_executor.py` | Split from mock_exchange.py |
| `app/trading/runner_loop.py` | Split from runner.py |
| `app/trading/exchange/lighter_queries.py` | Split from lighter_adapter.py |
| `app/trading/exchange/sim/sim_fill_handler.py` | Split from sim_exchange.py |
| `app/trading/strategy/rsi_momentum_entry.py` | Split from rsi_momentum.py |
| `app/trading/strategy/rsi_momentum_exit.py` | Split from rsi_momentum.py |
| `app/trading/strategy/rsi_no_retest_entry.py` | Split from rsi_no_retest.py |
| `app/trading/strategy/rsi_no_retest_exit.py` | Split from rsi_no_retest.py |

### Modified Files (10)
| File | Change |
|------|--------|
| `scripts/arch_lint.py` | Add pure-ABC exemption to class count rule |
| `app/trading/exchange/factory.py` | Lazy import MockExchange |
| `app/backtest/reporting.py` | Extract to reporting_html.py + reporting_styles.py |
| `app/backtest/engine.py` | Extract metrics to engine_metrics.py + engine_curves.py |
| `app/backtest/mock_exchange.py` | Extract executor to mock_exchange_executor.py |
| `app/trading/runner.py` | Extract loop to runner_loop.py |
| `app/trading/exchange/lighter_adapter.py` | Extract queries to lighter_queries.py |
| `app/trading/exchange/sim/sim_exchange.py` | Extract fills to sim_fill_handler.py |
| `app/trading/strategy/rsi_momentum.py` | Extract entry/exit to separate files |
| `app/trading/strategy/rsi_no_retest.py` | Extract entry/exit to separate files |

### Deleted Files (1)
| File | Reason |
|------|--------|
| `pytest.ini` | Migrated to pyproject.toml |
