# RSI Bot — Phase 1 Backend Spec

## Scope

Make the single-mode backtest work end-to-end: strategy auto-seed, param schema endpoint, inline data download with typed SSE events, verified result persistence.

---

## Stage 1A: Strategy Infrastructure

### 1A.1 — Auto-Seed Strategies

**Problem:** If a user selects a strategy that exists in `STRATEGY_MAP` but isn't in the DB `strategies` table, the backtest fails.

**Solution:** On app startup AND on each backtest request, check if the strategy exists in DB. If not, insert it.

**File:** `app/api/routes/backtest.py` (or a startup hook)

```python
# app/backtest/strategy_registry.py
from app.trading.strategy.rsi_no_retest import RsiNoRetestStrategy, RsiNoRetestConfig
from app.trading.strategy.rsi_momentum import RsiMomentumStrategy, RsiMomentumConfig

STRATEGY_MAP = {
    "rsi_no_retest": {
        "class": RsiNoRetestStrategy,
        "config_class": RsiNoRetestConfig,
        "description": "RSI No-Retest Long/Short Strategy",
    },
    "rsi_momentum": {
        "class": RsiMomentumStrategy,
        "config_class": RsiMomentumConfig,
        "description": "RSI Momentum Short-Only Strategy",
    },
}

def ensure_strategies_seeded(db: Session):
    """Insert any strategies from STRATEGY_MAP that are missing from DB."""
    existing = {s.name for s in db.query(Strategy.name).all()}
    for name, meta in STRATEGY_MAP.items():
        if name not in existing:
            config_cls = meta["config_class"]
            defaults = {f.name: f.default for f in dataclasses.fields(config_cls)
                       if f.default is not dataclasses.MISSING}
            strategy = Strategy(
                name=name,
                description=meta.get("description", ""),
                default_config=defaults,
            )
            db.add(strategy)
    db.commit()
```

**Call site:** FastAPI startup event:
```python
@app.on_event("startup")
def seed_strategies():
    db = SessionLocal()
    try:
        ensure_strategies_seeded(db)
    finally:
        db.close()
```

---

### 1A.2 — Param Schema Endpoint

**File:** `app/api/routes/strategies.py`

**Change `GET /api/strategies` response** to include `param_schema`:

```python
@router.get("/api/strategies")
def list_strategies(db: Session = Depends(get_db)):
    strategies = db.query(Strategy).all()
    results = []
    for s in strategies:
        meta = STRATEGY_MAP.get(s.name, {})
        config_cls = meta.get("config_class")
        schema = config_cls.param_schema() if config_cls and hasattr(config_cls, 'param_schema') else {}
        results.append(StrategyInfo(
            id=s.id,
            name=s.name,
            description=s.description or meta.get("description", ""),
            default_config=s.default_config or {},
            param_schema=schema,
        ))
    return results
```

**Add `param_schema` to Pydantic response schema:**
```python
# app/api/schemas.py
class StrategyInfo(BaseModel):
    id: int
    name: str
    description: str | None
    default_config: dict
    param_schema: dict = {}  # ← NEW
```

**See `spec_strategy_schema.md` for the `param_schema()` classmethod implementation.**

---

## Stage 1B: Inline Data Download + SSE

### 1B.1 — Modify Backtest Run Handler

**File:** `app/api/routes/backtest.py`

**Current flow:**
1. Receive `BacktestRequest`
2. Look up data file path
3. If missing → return 400
4. Build config, submit to executor
5. Stream progress via SSE

**New flow:**
1. Receive `BacktestRequest`
2. Look up data file path
3. **If missing → download inline, emitting SSE events**
4. Build config, submit to executor
5. Stream progress via SSE

```python
@router.post("/api/backtest/run", status_code=201)
async def start_backtest(req: BacktestRequest, db: Session = Depends(get_db)):
    # 1. Validate strategy
    if req.strategy not in STRATEGY_MAP:
        raise HTTPException(400, f"Unknown strategy: {req.strategy}")

    # 2. Auto-seed if needed
    ensure_strategy_exists(db, req.strategy)

    # 3. Create Run record (status=running)
    run = create_run_record(db, req)

    # 4. Submit to executor — the worker handles download + backtest
    executor.submit(run_backtest_worker, run.id, req)

    return {"run_id": run.id, "status": "running"}
```

### 1B.2 — Worker Function with Inline Download

**File:** `app/backtest/service.py` (or new `app/backtest/worker.py`)

```python
def run_backtest_worker(run_id: int, req: BacktestRequest):
    """Runs in ThreadPoolExecutor. Handles download + backtest + persistence."""
    progress_bus = get_progress_bus(run_id)  # SSE event emitter

    try:
        # Phase 1: Check & Download Data
        data_path = resolve_data_path(req.symbol, req.timeframe)

        if not data_path.exists():
            progress_bus.emit("download_progress", {
                "pct": 0, "symbol": req.symbol,
                "candles_fetched": 0, "candles_total": 0
            })

            download_data_with_progress(
                symbol=req.symbol,
                timeframe=req.timeframe,
                start_date=req.start_date,
                end_date=req.end_date,
                on_progress=lambda fetched, total: progress_bus.emit(
                    "download_progress",
                    {"pct": int(fetched / total * 100) if total else 0,
                     "symbol": req.symbol,
                     "candles_fetched": fetched,
                     "candles_total": total}
                )
            )

            progress_bus.emit("download_complete", {
                "symbol": req.symbol
            })

        # Phase 2: Run Backtest
        config = build_backtest_config(req)
        engine = BacktestEngine(config)

        engine.run(
            progress_callback=lambda candle, total: progress_bus.emit(
                "progress",
                {"pct": int(candle / total * 100),
                 "candle": candle, "total": total}
            )
        )

        # Phase 3: Persist Results
        results = engine.compute_results()
        persist_results(run_id, results, engine)

        progress_bus.emit("complete", {"run_id": run_id, "status": "completed"})

    except Exception as e:
        mark_failed(run_id, str(e))
        progress_bus.emit("error", {"message": str(e), "code": "BACKTEST_ERROR"})
```

### 1B.3 — Download with Progress Callback

**File:** `app/backtest/data/download.py`

The existing `download_data()` function fetches in 1000-candle pages. Add a `on_progress` callback:

```python
def download_data_with_progress(
    symbol: str,
    timeframe: str,
    start_date: str = None,
    end_date: str = None,
    on_progress: callable = None,
):
    """Wrapper around download_data that emits progress after each page."""
    # Calculate total candles needed
    total_candles = calculate_candle_limit(start_date, end_date, timeframe)
    fetched = 0

    # Use existing download logic but with page callback
    # ... (modify the pagination loop in download_data to call on_progress)

    # After each 1000-candle page:
    fetched += len(new_candles)
    if on_progress:
        on_progress(fetched, total_candles)
```

**Note:** The existing `download_data()` already handles pagination. The change is adding the callback hook inside the `while` loop that fetches pages.

---

## Stage 1B.4 — Progress Bus (SSE Event Emitter)

**File:** `app/api/progress.py` (new)

The SSE `/progress` endpoint needs to receive events from the worker thread. Use an in-memory dict of asyncio Queues (or threading Events):

```python
import asyncio
from collections import defaultdict
from typing import Any

_progress_queues: dict[int, list[asyncio.Queue]] = defaultdict(list)

class ProgressBus:
    def __init__(self, run_id: int):
        self.run_id = run_id

    def emit(self, event_type: str, data: dict):
        """Called from worker thread. Puts event into all subscriber queues."""
        for queue in _progress_queues.get(self.run_id, []):
            try:
                queue.put_nowait({"event": event_type, "data": data})
            except asyncio.QueueFull:
                pass  # Drop if queue full (client too slow)

    @staticmethod
    def subscribe(run_id: int) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize=100)
        _progress_queues[run_id].append(queue)
        return queue

    @staticmethod
    def unsubscribe(run_id: int, queue: asyncio.Queue):
        if run_id in _progress_queues:
            _progress_queues[run_id].remove(queue)
            if not _progress_queues[run_id]:
                del _progress_queues[run_id]

def get_progress_bus(run_id: int) -> ProgressBus:
    return ProgressBus(run_id)
```

**SSE endpoint using the bus:**

```python
@router.get("/api/backtest/{run_id}/progress")
async def stream_progress(run_id: int):
    queue = ProgressBus.subscribe(run_id)

    async def event_generator():
        try:
            while True:
                msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                event_type = msg["event"]
                data = json.dumps(msg["data"])
                yield f"event: {event_type}\ndata: {data}\n\n"

                if event_type in ("complete", "error"):
                    break
        except asyncio.TimeoutError:
            yield f"event: heartbeat\ndata: {{}}\n\n"
        finally:
            ProgressBus.unsubscribe(run_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
```

---

## Stage 1C: Verify Result Persistence

### Checklist — `persist_results()` must save:

| Field | Source | Frontend expects |
|-------|--------|-----------------|
| `net_profit` | `engine.results["net_profit"]` | `results.net_profit` (string) |
| `net_profit_pct` | computed | `results.net_profit_pct` (float) |
| `win_rate` | computed | `results.win_rate` (float) |
| `profit_factor` | computed | `results.profit_factor` (float) |
| `max_drawdown_pct` | computed | `results.max_drawdown_pct` (float) |
| `max_drawdown_value` | computed | `results.max_drawdown_value` (string) |
| `sharpe_ratio` | computed | `results.sharpe_ratio` (float) |
| `sortino_ratio` | computed | `results.sortino_ratio` (float) |
| `calmar_ratio` | computed | `results.calmar_ratio` (float) |
| `volatility` | computed | `results.volatility` (float) |
| `expectancy` | computed | `results.expectancy` (string) |
| `max_consecutive_wins` | computed | `results.max_consecutive_wins` (int) |
| `winning_trades` | computed | `results.winning_trades` (int) |
| `losing_trades` | computed | `results.losing_trades` (int) |
| `total_trades` | computed | `results.total_trades` (int) |
| `avg_win` | computed | `results.avg_win` (string) |
| `avg_loss` | computed | `results.avg_loss` (string) |
| `largest_win` | computed | `results.largest_win` (string) |
| `largest_loss` | computed | `results.largest_loss` (string) |
| `exit_reasons` | aggregated | `results.exit_reasons` (dict) |

**Action items:**
1. Check `compute_results()` in `BacktestEngine` — does it compute ALL of the above?
2. Check `persistence.py` — does `persist_results()` save all fields to `RunResult`?
3. Check `GET /api/backtest/{id}` — does the response serialize all fields from `RunResult`?

### Missing fields likely:
- `exit_reasons` — needs to be aggregated from trades and stored (either in `RunResult` JSON or computed at query time)
- `max_consecutive_wins` — needs computation
- `volatility` — needs computation
- `calmar_ratio` — needs computation
- `expectancy` — needs computation

**Recommendation:** Add a `metrics_json` TEXT column to `RunResult` for flexible metrics storage, OR compute these on-the-fly in the API handler from the trades list.

---

## Stage 1D: Verify Timeseries Format

The frontend `mapApiToResults()` expects:

```typescript
// Equity curve
equityCurve: timeseries.equity_curve.map(p => ({
  time: String(p["date"] ?? p["time"] ?? ""),
  value: typeof p["balance"] === "string" ? parseFloat(p["balance"]) : p["balance"],
}))

// Drawdown curve
underwaterCurve: timeseries.drawdown_curve.map(p => ({
  time: String(p["date"] ?? p["time"] ?? ""),
  value: -(typeof p["drawdown"] === "number" ? p["drawdown"] : parseFloat(p["drawdown"])),
}))
```

**Check `persistence.py`:** The zlib-compressed JSON must use keys `date` + `balance` (not `time` + `equity`), and `date` + `drawdown`.

If current format differs, either:
- Fix backend to match frontend expectations, OR
- Add a normalization layer in the API handler

---

## Implementation Order

```
1A.1  Auto-seed strategies on startup          ~30 min
1A.2  param_schema() on config dataclasses     ~2 hours
1A.2  GET /api/strategies returns schema       ~30 min
1B.1  Modify backtest run handler              ~1 hour
1B.2  Worker with inline download              ~2 hours
1B.3  download_data progress callback          ~1 hour
1B.4  Progress bus (SSE event emitter)         ~2 hours
1C    Verify/fix result persistence            ~2 hours
1D    Verify/fix timeseries format             ~1 hour
                                        Total: ~12 hours
```

---

## Files Changed

| File | Change |
|------|--------|
| `app/backtest/strategy_registry.py` | NEW — strategy map + auto-seed |
| `app/trading/strategy/utils/schema_helper.py` | NEW — schema generation |
| `app/trading/strategy/rsi_no_retest.py` | Add `PARAM_METADATA`, `param_schema()` |
| `app/trading/strategy/rsi_momentum.py` | Add `PARAM_METADATA`, `param_schema()` |
| `app/api/routes/backtest.py` | Inline download flow, auto-seed check |
| `app/api/routes/strategies.py` | Return `param_schema` |
| `app/api/schemas.py` | Add `param_schema` to `StrategyInfo` |
| `app/api/progress.py` | NEW — ProgressBus for SSE |
| `app/backtest/service.py` | Worker function with download + backtest |
| `app/backtest/data/download.py` | Add progress callback to download loop |
| `app/backtest/engine/backtest_engine.py` | Verify `compute_results()` completeness |
| `app/backtest/persistence.py` | Verify all metrics saved |
| `app/main.py` | Add startup event for strategy seeding |
