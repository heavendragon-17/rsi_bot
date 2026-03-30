# RSI Bot — Phase 1 Backend Spec

## Scope

Make the single-mode backtest work end-to-end: param schema on strategies endpoint, inline data download with typed SSE events, verified result persistence.

**Key principle:** Build on existing infrastructure. Do NOT recreate `executor.py`, `seed.py`, `BacktestService`, or `stream_progress()`.

---

## Stage 1A: Strategy Infrastructure

### 1A.1 — Update `seed.py` to Use CONFIG_CLASS

**File:** `app/repository/backtest/seed.py` [EXISTS — MODIFY]

**Current state:** `seed_strategies()` already iterates `STRATEGY_MAP`, checks DB, inserts missing. Uses `getattr(cls, "DEFAULT_CONFIG", {})` for defaults.

**Change:** Extract defaults from `CONFIG_CLASS` frozen dataclass fields (source of truth) instead of `DEFAULT_CONFIG` dict.

```python
# app/repository/backtest/seed.py — updated
import dataclasses
from app.repository.backtest.models import Strategy
from app.trading.strategy.loader import STRATEGY_MAP

STRATEGY_DESCRIPTIONS = {
    "rsi_no_retest": "RSI strategy without retest confirmation",
    "rsi_wma_retest": "RSI strategy requiring WMA45 retest",
    "rsi_momentum": "RSI momentum strategy (short entries only)",
}

def seed_strategies(session) -> None:
    """Insert default strategies if they don't already exist."""
    for name, strategy_cls in STRATEGY_MAP.items():
        if session.query(Strategy).filter_by(name=name).first() is None:
            config_cls = getattr(strategy_cls, "CONFIG_CLASS", None)
            if config_cls:
                defaults = {
                    f.name: f.default
                    for f in dataclasses.fields(config_cls)
                    if f.default is not dataclasses.MISSING
                       and f.name not in ("METADATA", "UI_GROUPS")
                }
            else:
                defaults = getattr(strategy_cls, "DEFAULT_CONFIG", {})

            session.add(Strategy(
                name=name,
                description=STRATEGY_DESCRIPTIONS.get(name, name),
                default_config=defaults,
            ))
            session.commit()
```

**Startup hook:** Already exists in `app/api/main.py` via `lifespan` context manager — calls `init_db()` + `seed_strategies()`. **No changes needed to `main.py`.**

---

### 1A.2 — Param Schema on Strategies Endpoint

**File:** `app/api/routes/strategies.py` [EXISTS — MODIFY]

Add `param_schema` to the response using `STRATEGY_MAP[name].CONFIG_CLASS.param_schema()`:

```python
from app.trading.strategy.loader import STRATEGY_MAP

@router.get("/api/strategies")
def list_strategies(db: Session = Depends(get_db)):
    strategies = db.query(Strategy).all()
    results = []
    for s in strategies:
        strategy_cls = STRATEGY_MAP.get(s.name)
        config_cls = getattr(strategy_cls, "CONFIG_CLASS", None) if strategy_cls else None
        schema = config_cls.param_schema() if config_cls and hasattr(config_cls, "param_schema") else {}
        results.append(StrategyInfo(
            id=s.id,
            name=s.name,
            description=s.description or "",
            default_config=s.default_config or {},
            param_schema=schema,
        ))
    return results
```

**File:** `app/api/schemas.py` [EXISTS — MODIFY]

```python
class StrategyInfo(BaseModel):
    id: int
    name: str
    description: str | None
    default_config: dict[str, Any]
    param_schema: dict[str, Any] = {}  # ← NEW
```

**See `spec_strategy_schema.md` for `SchemaConfigMixin` and `param_schema()` implementation.**

---

## Stage 1B: Inline Data Download + SSE

### 1B.1 — Move Data Check into Worker Thread

**File:** `app/backtest/service.py` [EXISTS — MODIFY]

**Current flow in `BacktestService.start_run()`:**
1. Validate strategy
2. Check CSV file exists → raises `FileNotFoundError` (400) if missing
3. Create Run + RunConfig rows
4. Submit to executor

**New flow:**
1. Validate strategy (keep)
2. ~~Check CSV file~~ → **Remove the `FileNotFoundError` check for single mode**
3. Create Run + RunConfig rows (keep)
4. Submit to executor → **worker handles download if needed**

```python
# In BacktestService.start_run() — remove these lines:
# csv_path = _csv_path(req.symbol, req.timeframe)
# if not os.path.exists(csv_path):
#     raise FileNotFoundError(...)

# Instead, pass csv_path to worker — let it download if missing
csv_path = _csv_path(req.symbol, req.timeframe) if not is_portfolio else None
```

### 1B.2 — Worker with Inline Download

**File:** `app/backtest/workers.py` [NEW]

Extract worker functions from `service.py` into a dedicated module. This keeps `service.py` under 400 lines and isolates the worker concern.

```python
"""
Backtest worker functions — run in ThreadPoolExecutor.

Extracted from service.py to keep file sizes under 400 lines.
Handles inline download + backtest execution + result persistence.
"""
from __future__ import annotations

import os
from typing import Any

import structlog

from app.backtest.config_builder import build_backtest_config
from app.backtest.data.inline_download import download_if_missing
from app.backtest.persistence import mark_failed, persist_results

logger = structlog.get_logger()


def single_worker(
    *,
    req,
    run_id: int,
    loop,
    progress_cb,
    publish_event_fn,
    strategy_class,
    csv_path: str,
):
    """Worker fn for single-symbol backtest. Called from ThreadPoolExecutor."""
    from app.backtest.engine.backtest_engine import BacktestEngine

    try:
        # Phase 1: Download data if CSV missing (with file lock)
        download_if_missing(
            csv_path=csv_path,
            symbol=req.symbol,
            timeframe=req.timeframe,
            start_date=req.start_date,
            end_date=req.end_date,
            run_id=run_id,
            loop=loop,
            publish_event_fn=publish_event_fn,
        )

        # Phase 2: Run backtest
        engine_config = build_backtest_config(
            symbol=req.symbol,
            timeframe=req.timeframe,
            strategy_name=req.strategy,
            initial_balance=float(req.initial_capital),
            leverage=req.leverage,
            risk_per_trade_pct=float(req.risk_per_trade_pct),
            params=req.params,
        )
        engine = BacktestEngine(csv_path, strategy_class, engine_config)
        results = engine.run(on_progress=progress_cb)

        # Phase 3: Persist
        persist_results(run_id, results)
        publish_event_fn(run_id, loop, "complete", {"run_id": run_id, "status": "completed"})

    except Exception as err:
        logger.error("backtest_worker_error", run_id=run_id, error=str(err))
        mark_failed(run_id, str(err))
        publish_event_fn(run_id, loop, "error", {"run_id": run_id, "message": str(err)})


def portfolio_worker(
    *,
    req,
    run_id: int,
    loop,
    progress_cb,
    publish_event_fn,
):
    """Worker fn for portfolio backtest. Called from ThreadPoolExecutor."""
    from app.backtest.runners.portfolio_runner import _run_portfolio_backtest

    try:
        results = _run_portfolio_backtest(
            symbols=req.symbols,
            strategy_name=req.strategy,
            timeframe=req.timeframe,
            start_date=req.start_date,
            end_date=req.end_date,
            initial_capital=float(req.initial_capital),
            leverage=req.leverage,
            risk_per_trade_pct=float(req.risk_per_trade_pct),
            fee_tier=req.fee_tier,
            slippage_model=req.slippage_model,
            slippage_pct=float(req.slippage_pct),
            params=req.params,
            progress_cb=progress_cb,
        )
        persist_results(run_id, results)
        publish_event_fn(run_id, loop, "complete", {"run_id": run_id, "status": "completed"})

    except Exception as err:
        logger.error("portfolio_worker_error", run_id=run_id, error=str(err))
        mark_failed(run_id, str(err))
        publish_event_fn(run_id, loop, "error", {"run_id": run_id, "message": str(err)})
```

**Update `service.py`:** Replace `_single_worker()` and `_portfolio_worker()` methods with imports from `workers.py`.

### 1B.3 — Inline Download with File Lock

**File:** `app/backtest/data/inline_download.py` [NEW]

Isolated module for the inline download concern. Uses `fcntl.flock()` for concurrent safety.

```python
"""
Inline data download — downloads CSV if missing, with file lock + SSE progress.

Used by backtest workers when data file doesn't exist.
"""
from __future__ import annotations

import fcntl
import os
from typing import Any, Callable

import structlog

from app.backtest.data.download import download_data

logger = structlog.get_logger()


def download_if_missing(
    *,
    csv_path: str,
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    run_id: int,
    loop,
    publish_event_fn: Callable,
) -> None:
    """Download data file if it doesn't exist. Thread-safe via file lock."""
    if os.path.exists(csv_path):
        return

    lock_path = f"{csv_path}.lock"
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)

    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            # Double-check after acquiring lock (another worker may have finished)
            if os.path.exists(csv_path):
                return

            publish_event_fn(run_id, loop, "download_progress", {
                "pct": 0, "symbol": symbol,
                "candles_fetched": 0, "candles_total": 0,
            })

            # Use existing download_data() — add progress callback
            download_data(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                on_progress=lambda fetched, total: publish_event_fn(
                    run_id, loop, "download_progress", {
                        "pct": int(fetched / total * 100) if total else 0,
                        "symbol": symbol,
                        "candles_fetched": fetched,
                        "candles_total": total,
                    }
                ),
            )

            publish_event_fn(run_id, loop, "download_complete", {
                "symbol": symbol,
            })

        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
```

### 1B.4 — Add Progress Callback to `download_data()`

**File:** `app/backtest/data/download.py` [EXISTS — MODIFY]

The existing `download_data()` fetches in 1000-candle pages. Add an optional `on_progress` callback parameter:

```python
def download_data(
    symbol: str,
    timeframe: str,
    start_date: str = None,
    end_date: str = None,
    on_progress: callable = None,  # ← NEW: called after each page
):
    # ... existing pagination loop ...

    # After each 1000-candle page fetch, add:
    fetched += len(new_candles)
    if on_progress:
        on_progress(fetched, total_candles)
```

**Note:** The existing SSE infrastructure (`executor.py`) handles all event routing. The worker calls `executor.publish_event()` — no new ProgressBus needed.

---

## Stage 1C: Verify Result Persistence [ALREADY COMPLETE]

All fields are already present and working. Verified against actual code:

### `RunResult` model — all columns exist (`app/repository/backtest/models.py:96-127`)

All 22 metrics fields already defined: `net_profit`, `net_profit_pct`, `gross_profit`, `gross_loss`, `win_rate`, `profit_factor`, `expectancy`, `max_drawdown_pct`, `max_drawdown_value`, `max_drawdown_duration_days`, `volatility`, `sharpe_ratio`, `sortino_ratio`, `calmar_ratio`, `total_trades`, `winning_trades`, `losing_trades`, `avg_win`, `avg_loss`, `largest_win`, `largest_loss`, `max_consecutive_wins`, `max_consecutive_losses`, `avg_hold_time_hours`, `exit_reasons`.

### `persist_results()` — maps all fields (`app/backtest/persistence.py:27-111`)

Already writes `RunResult`, `RunTimeseries` (zlib-compressed equity/drawdown), and `Trade` rows.

### `_build_results_dict()` — serializes all fields (`app/backtest/service.py:334-362`)

Already outputs all 22 fields in the API response.

**Action:** Verify only — no code changes needed. Run a test backtest and confirm the API returns all fields.

---

## Stage 1D: Verify Timeseries Format

The frontend `mapApiToResults()` expects:

```typescript
// Equity curve — expects "date" key + "balance" key
equityCurve: timeseries.equity_curve.map(p => ({
  time: String(p["date"] ?? p["time"] ?? ""),
  value: typeof p["balance"] === "string" ? parseFloat(p["balance"]) : p["balance"],
}))

// Drawdown curve — expects "date" key + "drawdown" key
underwaterCurve: timeseries.drawdown_curve.map(p => ({
  time: String(p["date"] ?? p["time"] ?? ""),
  value: -(typeof p["drawdown"] === "number" ? p["drawdown"] : parseFloat(p["drawdown"])),
}))
```

**Action:** Check `persistence.py` zlib output keys. The `RunTimeseries` model comment says `zlib(JSON[{date, balance}])` — verify the actual `compute_results()` output uses these keys. If different, add a normalization step in `_build_results_dict()` or the timeseries handler.

---

## Implementation Order

```
1A.1  Update seed.py to use CONFIG_CLASS         ~30 min
1A.2  Add param_schema to strategies endpoint    ~1 hour
      (incl. StrategyInfo schema change)
1B.1  Remove FileNotFoundError from start_run()  ~15 min
1B.2  Extract workers.py from service.py         ~2 hours
1B.3  Create inline_download.py (file lock)      ~1.5 hours
1B.4  Add on_progress callback to download.py    ~1 hour
1C    Verify result persistence (test run)        ~1 hour
1D    Verify timeseries format (test run)         ~30 min
                                          Total: ~8 hours
```

**Note:** Reduced from original 12h estimate — Stages 1B.4 (ProgressBus) and 1C (missing fields) are eliminated since the infrastructure already exists.

---

## Files Changed

| File | Change |
|------|--------|
| `app/repository/backtest/seed.py` | MODIFY — use `CONFIG_CLASS` for defaults |
| `app/api/routes/strategies.py` | MODIFY — return `param_schema` |
| `app/api/schemas.py` | MODIFY — add `param_schema` to `StrategyInfo` |
| `app/backtest/service.py` | MODIFY — remove CSV check, delegate workers to `workers.py` |
| `app/backtest/workers.py` | NEW — extracted worker functions |
| `app/backtest/data/inline_download.py` | NEW — download with file lock + SSE |
| `app/backtest/data/download.py` | MODIFY — add `on_progress` callback |

**Files NOT changed (already working):**
| File | Reason |
|------|--------|
| `app/api/executor.py` | Progress queues + thread-safe callbacks already complete |
| `app/api/routes/backtest_run.py` | Route handler already delegates to `BacktestService` |
| `app/api/routes/backtest_stream.py` | SSE endpoint already works |
| `app/backtest/persistence.py` | All metrics fields already persisted |
| `app/backtest/engine/backtest_engine.py` | `compute_results()` already complete |
| `app/api/main.py` | `lifespan` hook already calls `seed_strategies()` |
