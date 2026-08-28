# RSI Bot — Phase 2 Backend Spec

> **Historical implementation spec (April 2026):** Retained for provenance;
> use `docs/INDEX.md` for current backend documentation.

## Scope

Batch mode (N independent runs via single API call), portfolio mode (single balance across all symbols), server-side presets CRUD.

**Prerequisite:** Phase 1 complete — single backtest works end-to-end.

**Key principle:** Route all modes through existing `POST /api/backtest/run` with `mode` discriminator. Wrap existing `BatchRunner` for parallel execution — don't reimplement.

---

## Stage 2A: Batch Mode via Existing Endpoint

### Three Modes — All Through `POST /api/backtest/run`

| Mode | Request | Backend Implementation |
|------|---------|----------------------|
| **Single** | `mode=single`, `symbol="BTC/USDT"` | Phase 1 flow (exists) |
| **Batch** | `mode=batch`, `symbols=["BTC/USDT", "ETH/USDT"]` | Wraps existing `BatchRunner` with `ProcessPoolExecutor` |
| **Portfolio** | `mode=portfolio`, `symbols=["BTC/USDT", "ETH/USDT"]` | Existing `_portfolio_worker` in `service.py` (exists) |

No separate `POST /api/backtest/batch` endpoint — `BacktestService.start_run()` already routes by `mode`.

### Add Batch Mode to `BacktestService.start_run()` [MODIFY]

**File:** `app/backtest/service.py`

**Diff — add batch case to `_resolve_mode()` and `_build_worker()`:**

```diff
  @staticmethod
  def _resolve_mode(req: BacktestRequest) -> BacktestMode:
      if req.mode is not None:
          return req.mode
-     return BacktestMode.PORTFOLIO if req.symbols else BacktestMode.SINGLE
+     if req.symbols:
+         return BacktestMode.BATCH if req.mode == BacktestMode.BATCH else BacktestMode.PORTFOLIO
+     return BacktestMode.SINGLE

  def _build_worker(self, *, mode, req, run_id, loop, progress_cb, strategy_class, csv_path):
      if mode == BacktestMode.PORTFOLIO:
          return self._portfolio_worker(req, run_id, loop, progress_cb)
+     if mode == BacktestMode.BATCH:
+         return self._batch_worker(req, run_id, loop, progress_cb)
      return self._single_worker(req, run_id, loop, progress_cb, strategy_class, csv_path)
```

### Batch Worker — Wraps Existing `BatchRunner`

**File:** `app/backtest/workers.py` [MODIFY — add batch_worker]

The existing `BatchRunner` in `app/backtest/runners/batch_runner.py` already uses `ProcessPoolExecutor` for parallel execution. The API worker wraps it.

```python
def batch_worker(
    *,
    req,
    run_id: int,
    loop,
    progress_cb,
    publish_event_fn,
):
    """Worker fn for batch backtest. Wraps existing BatchRunner."""
    from app.backtest.runners.batch_runner import BatchRunner

    try:
        # Download data for all symbols if missing (with file lock)
        for symbol in req.symbols:
            csv_path = _csv_path(symbol, req.timeframe)
            download_if_missing(
                csv_path=csv_path,
                symbol=symbol,
                timeframe=req.timeframe,
                start_date=req.start_date,
                end_date=req.end_date,
                run_id=run_id,
                loop=loop,
                publish_event_fn=publish_event_fn,
            )

        # Build config dict for BatchRunner
        config = {
            "strategy": req.strategy,
            "strategy_params": req.params,
            "bot": {"timeframe": req.timeframe},
            "risk": {
                "leverage": req.leverage,
                "risk_per_trade_pct": float(req.risk_per_trade_pct),
            },
        }

        runner = BatchRunner(
            symbols=req.symbols,
            config=config,
            strategy_name=req.strategy,
            timeframe=req.timeframe,
            balance=float(req.initial_capital),
        )

        max_workers = req.max_workers or min(4, len(req.symbols))
        batch_results = runner.run(
            max_workers=max_workers,
            progress_cb=progress_cb,
        )

        # Persist aggregated results
        persist_results(run_id, _aggregate_batch_results(batch_results))
        publish_event_fn(run_id, loop, "complete", {
            "run_id": run_id,
            "status": "completed",
        })

    except Exception as err:
        logger.error("batch_worker_error", run_id=run_id, error=str(err))
        mark_failed(run_id, str(err))
        publish_event_fn(run_id, loop, "error", {
            "run_id": run_id,
            "message": str(err),
        })
```

**Note:** The SSE events use the same `progress` / `complete` / `error` event types as single mode. The `BatchRunner.run()` already calls the progress callback with `{"pct": ...}` after each symbol completes.

---

## Stage 2B: Portfolio Mode [EXISTS — VERIFY]

Portfolio mode already works via `BacktestService._portfolio_worker()` in `service.py`. It calls `_run_portfolio_backtest()` from `portfolio_runner.py`.

### Dynamic Progress Split

**Current problem:** The portfolio worker hardcodes 50% download / 50% backtest. When data is cached, progress jumps 0→50% instantly.

**Fix — in `workers.py` `portfolio_worker()`:**

```python
def portfolio_worker(*, req, run_id, loop, progress_cb, publish_event_fn):
    # Check which symbols need download
    symbols_needing_download = [
        s for s in req.symbols
        if not os.path.exists(_csv_path(s, req.timeframe))
    ]
    needs_download = len(symbols_needing_download) > 0

    # Dynamic split: download gets 30% only if needed, otherwise backtest gets 100%
    download_weight = 0.3 if needs_download else 0.0
    backtest_weight = 1.0 - download_weight

    # Phase 1: Download (only if needed)
    if needs_download:
        for i, symbol in enumerate(symbols_needing_download):
            download_if_missing(...)
            pct = int((i + 1) / len(symbols_needing_download) * download_weight * 100)
            publish_event_fn(run_id, loop, "download_progress", {"pct": pct, "symbol": symbol})
        publish_event_fn(run_id, loop, "download_complete", {"symbol": "all"})

    # Phase 2: Run portfolio engine
    base_pct = int(download_weight * 100)
    results = _run_portfolio_backtest(
        ...,
        progress_cb=lambda data: progress_cb({
            "pct": base_pct + int(data.get("pct", 0) * backtest_weight),
        }),
    )
    # ... persist and emit complete
```

---

## Stage 2C: Server-Side Presets

### New DB Table: `presets`

**File:** `app/repository/backtest/models.py` [MODIFY — add model]

```python
class Preset(Base):
    __tablename__ = "presets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    strategy = Column(Text, nullable=False, index=True)
    config = Column(JSON, nullable=False)  # {symbol, timeframe, leverage, params: {...}}
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("name", "strategy", name="uq_preset_name_strategy"),
    )
```

**Migration note:** The project uses `Base.metadata.create_all()` on startup, which auto-creates new tables. The `Preset` table will be created automatically on next server start. No Alembic needed.

### CRUD Routes

**File:** `app/api/routes/presets.py` [NEW]

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import PresetCreate, PresetResponse, PresetUpdate
from app.repository.backtest.database import SessionLocal
from app.repository.backtest.models import Preset

router = APIRouter(prefix="/api/presets", tags=["presets"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=list[PresetResponse])
def list_presets(strategy: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Preset)
    if strategy:
        query = query.filter(Preset.strategy == strategy)
    return query.order_by(Preset.updated_at.desc()).all()


@router.post("", status_code=201, response_model=PresetResponse)
def create_preset(body: PresetCreate, db: Session = Depends(get_db)):
    preset = Preset(name=body.name, strategy=body.strategy, config=body.config)
    db.add(preset)
    db.commit()
    db.refresh(preset)
    return preset


@router.put("/{preset_id}", response_model=PresetResponse)
def update_preset(preset_id: int, body: PresetUpdate, db: Session = Depends(get_db)):
    preset = db.query(Preset).filter_by(id=preset_id).first()
    if not preset:
        raise HTTPException(404, "Preset not found")
    if body.name is not None:
        preset.name = body.name
    if body.config is not None:
        preset.config = body.config
    db.commit()
    db.refresh(preset)
    return preset


@router.delete("/{preset_id}", status_code=204)
def delete_preset(preset_id: int, db: Session = Depends(get_db)):
    preset = db.query(Preset).filter_by(id=preset_id).first()
    if not preset:
        raise HTTPException(404, "Preset not found")
    db.delete(preset)
    db.commit()
```

### Pydantic Schemas

**File:** `app/api/schemas.py` [MODIFY — add preset schemas]

```python
class PresetCreate(BaseModel):
    name: str
    strategy: str
    config: dict[str, Any]  # {symbol, timeframe, leverage, params: {...}}

class PresetUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None

class PresetResponse(BaseModel):
    id: int
    name: str
    strategy: str
    config: dict[str, Any]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
```

### Register Routes

**File:** `app/api/main.py` [MODIFY — add include_router]

```diff
+ from app.api.routes.presets import router as presets_router

  app.include_router(...)  # existing routers
+ app.include_router(presets_router)
```

---

## Stage 2D: Batch DB Schema

### New Table: `batches`

**File:** `app/repository/backtest/models.py` [MODIFY — add model]

```python
class Batch(Base):
    __tablename__ = "batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(Text, default="running")  # running, completed, partial, failed
    total_symbols = Column(Integer)
    completed_symbols = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    runs = relationship("Run", back_populates="batch")
```

### Add `batch_id` FK to `Run` Table

**File:** `app/repository/backtest/models.py` [MODIFY]

```diff
  class Run(Base):
      # ... existing columns ...
+     batch_id = Column(Integer, ForeignKey("batches.id"), nullable=True)

      strategy = relationship("Strategy", back_populates="runs")
+     batch = relationship("Batch", back_populates="runs")
      config = relationship("RunConfig", ...)
      # ... rest unchanged
```

### Migration for Existing `runs` Table

`create_all()` does **not** add columns to existing tables. A one-time migration is needed:

**File:** `app/repository/backtest/database.py` [MODIFY — add migration helper]

```python
def _migrate_add_batch_id(engine) -> None:
    """Add batch_id column to runs table if missing. One-time migration."""
    with engine.connect() as conn:
        # Check if column exists (SQLite-specific)
        result = conn.execute(sa.text("PRAGMA table_info(runs)"))
        columns = {row[1] for row in result}
        if "batch_id" not in columns:
            conn.execute(sa.text("ALTER TABLE runs ADD COLUMN batch_id INTEGER REFERENCES batches(id)"))
            conn.commit()
```

Call from `init_db()`:

```diff
  def init_db() -> None:
      DB_DIR.mkdir(parents=True, exist_ok=True)
      import app.repository.backtest.models  # noqa: F401
      Base.metadata.create_all(bind=engine)
+     _migrate_add_batch_id(engine)

      session = SessionLocal()
      # ... seed_strategies ...
```

---

## Implementation Order

```
2A    Add batch mode to start_run() + batch_worker    ~3 hours
2B    Dynamic progress split for portfolio worker     ~1 hour
2C    Presets DB table + CRUD routes                  ~2 hours
2D    Batch DB schema + migration helper              ~1.5 hours
                                              Total: ~7.5 hours
```

**Note:** Reduced from 10h — batch endpoint eliminated (uses existing route), portfolio worker already exists.

---

## Files Changed

| File | Change |
|------|--------|
| `app/backtest/service.py` | MODIFY — add batch case to `_resolve_mode()` / `_build_worker()` |
| `app/backtest/workers.py` | MODIFY — add `batch_worker()`, update `portfolio_worker()` with dynamic progress |
| `app/api/routes/presets.py` | NEW — preset CRUD routes |
| `app/api/schemas.py` | MODIFY — add `PresetCreate`, `PresetUpdate`, `PresetResponse` |
| `app/repository/backtest/models.py` | MODIFY — add `Preset`, `Batch` models, `Run.batch_id` FK + relationship |
| `app/repository/backtest/database.py` | MODIFY — add `_migrate_add_batch_id()` to `init_db()` |
| `app/api/main.py` | MODIFY — register preset router |

**Files NOT changed (already working):**
| File | Reason |
|------|--------|
| `app/api/routes/backtest_run.py` | Still routes to `BacktestService.start_run()` — no change |
| `app/backtest/runners/batch_runner.py` | `BatchRunner` used as-is via wrapper |
| `app/backtest/runners/portfolio_runner.py` | `_run_portfolio_backtest` used as-is |
