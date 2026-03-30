# RSI Bot — Phase 2 Backend Spec

## Scope

Batch mode (N independent runs via single API call), portfolio mode (single balance across all symbols), server-side presets CRUD.

**Prerequisite:** Phase 1 complete — single backtest works end-to-end.

---

## Stage 2A: Batch Endpoint

### Three Modes Clarification

| Mode | Description | Backend Implementation |
|------|-------------|----------------------|
| **Single** | 1 symbol, 1 run | Existing flow from Phase 1 |
| **Batch** | N symbols, N independent runs, each with its own balance | `batch_runner.py` already exists for CLI (`python -m app.backtest.runners.batch_runner`) — wrap in API endpoint |
| **Portfolio** | N symbols, 1 shared balance, multiplexed chronologically | `PortfolioEngine` — single run with interleaved candles |

### `POST /api/backtest/batch`

**File:** `app/api/routes/backtest.py`

```python
@router.post("/api/backtest/batch", status_code=201)
async def start_batch(req: BatchRequest, db: Session = Depends(get_db)):
    """
    Starts N independent backtests — one per symbol.
    Returns a batch_id + individual run_ids.
    Progress streamed via GET /api/backtest/batch/{batch_id}/progress
    """
    if not req.symbols or len(req.symbols) == 0:
        raise HTTPException(400, "No symbols provided")

    # Create parent batch record
    batch = Batch(status="running", total_symbols=len(req.symbols))
    db.add(batch)
    db.flush()

    # Create individual run records
    run_ids = []
    for symbol in req.symbols:
        run = create_run_record(db, req, symbol=symbol, batch_id=batch.id)
        run_ids.append(run.id)
    db.commit()

    # Submit to executor
    executor.submit(run_batch_worker, batch.id, run_ids, req)

    return {"batch_id": batch.id, "run_ids": run_ids, "status": "running"}
```

### Pydantic Schema:

```python
class BatchRequest(BaseModel):
    symbols: list[str]
    timeframe: str
    strategy: str
    start_date: str
    end_date: str
    initial_capital: str = "10000.00"  # per symbol
    leverage: int = 10
    risk_per_trade_pct: str = "0.02"
    params: dict = {}
```

### Batch Worker:

```python
# app/backtest/workers/batch_worker.py

def run_batch_worker(batch_id: int, run_ids: list[int], req: BatchRequest):
    """Runs N backtests sequentially (or limited parallelism)."""
    progress_bus = get_progress_bus(batch_id)
    completed = 0

    for i, (run_id, symbol) in enumerate(zip(run_ids, req.symbols)):
        try:
            # Run single backtest (reuse Phase 1 worker logic)
            run_single_backtest(run_id, symbol, req, progress_callback=lambda pct: (
                progress_bus.emit("batch_progress", {
                    "pct": int(((completed + pct / 100) / len(run_ids)) * 100),
                    "symbol": symbol,
                    "symbol_pct": pct,
                    "completed": completed,
                    "total": len(run_ids),
                })
            ))
            completed += 1

            progress_bus.emit("batch_symbol_complete", {
                "symbol": symbol,
                "run_id": run_id,
                "completed": completed,
                "total": len(run_ids),
            })

        except Exception as e:
            progress_bus.emit("error", {
                "message": f"Failed on {symbol}: {str(e)}",
                "symbol": symbol,
            })

    progress_bus.emit("batch_complete", {
        "batch_id": batch_id,
        "completed": completed,
        "total": len(run_ids),
        "run_ids": run_ids,
    })
```

### Batch Progress SSE:

```
GET /api/backtest/batch/{batch_id}/progress
```

SSE events:
| Event | Payload |
|-------|---------|
| `batch_progress` | `{pct, symbol, symbol_pct, completed, total}` |
| `batch_symbol_complete` | `{symbol, run_id, completed, total}` |
| `batch_complete` | `{batch_id, completed, total, run_ids}` |
| `error` | `{message, symbol}` |

---

## Stage 2B: Portfolio Endpoint

### `POST /api/backtest/run` (with `symbols` array)

The existing `BacktestRequest` already has a `symbols` field. When `symbols` is provided (and `symbol` is null), use portfolio mode.

**File:** `app/api/routes/backtest.py`

```python
@router.post("/api/backtest/run", status_code=201)
async def start_backtest(req: BacktestRequest, db: Session = Depends(get_db)):
    # Detect mode
    if req.symbols and len(req.symbols) > 1:
        # Portfolio mode
        run = create_run_record(db, req, symbol=",".join(req.symbols))
        executor.submit(run_portfolio_worker, run.id, req)
    elif req.symbol:
        # Single mode (Phase 1)
        run = create_run_record(db, req, symbol=req.symbol)
        executor.submit(run_single_worker, run.id, req)
    else:
        raise HTTPException(400, "Provide symbol or symbols")

    return {"run_id": run.id, "status": "running"}
```

### Portfolio Worker:

```python
def run_portfolio_worker(run_id: int, req: BacktestRequest):
    """Runs PortfolioEngine with all symbols under single balance."""
    progress_bus = get_progress_bus(run_id)

    try:
        # Download data for all symbols (inline)
        for i, symbol in enumerate(req.symbols):
            data_path = resolve_data_path(symbol, req.timeframe)
            if not data_path.exists():
                progress_bus.emit("download_progress", {
                    "pct": int(i / len(req.symbols) * 50),  # download = 50%
                    "symbol": symbol,
                })
                download_data_with_progress(symbol, req.timeframe, req.start_date, req.end_date)
                progress_bus.emit("download_complete", {"symbol": symbol})

        # Run portfolio engine
        config = build_portfolio_config(req)
        engine = PortfolioEngine(config)

        engine.run(
            progress_callback=lambda candle, total: progress_bus.emit(
                "progress",
                {"pct": 50 + int(candle / total * 50), "candle": candle, "total": total}
            )
        )

        results = engine.compute_results()
        persist_results(run_id, results, engine)
        progress_bus.emit("complete", {"run_id": run_id, "status": "completed"})

    except Exception as e:
        mark_failed(run_id, str(e))
        progress_bus.emit("error", {"message": str(e)})
```

---

## Stage 2C: Server-Side Presets

### New DB Table: `presets`

```python
# app/repository/backtest/models.py

class Preset(Base):
    __tablename__ = "presets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    strategy = Column(String, nullable=False, index=True)
    config = Column(JSON, nullable=False)  # Full config snapshot
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("name", "strategy", name="uq_preset_name_strategy"),
    )
```

### CRUD Routes

**File:** `app/api/routes/presets.py`

```python
@router.get("/api/presets")
def list_presets(strategy: str = None, db: Session = Depends(get_db)):
    query = db.query(Preset)
    if strategy:
        query = query.filter(Preset.strategy == strategy)
    return query.order_by(Preset.updated_at.desc()).all()

@router.post("/api/presets", status_code=201)
def create_preset(body: PresetCreate, db: Session = Depends(get_db)):
    preset = Preset(name=body.name, strategy=body.strategy, config=body.config)
    db.add(preset)
    db.commit()
    db.refresh(preset)
    return preset

@router.put("/api/presets/{preset_id}")
def update_preset(preset_id: int, body: PresetUpdate, db: Session = Depends(get_db)):
    preset = db.query(Preset).get(preset_id)
    if not preset:
        raise HTTPException(404, "Preset not found")
    if body.name: preset.name = body.name
    if body.config: preset.config = body.config
    db.commit()
    return preset

@router.delete("/api/presets/{preset_id}", status_code=204)
def delete_preset(preset_id: int, db: Session = Depends(get_db)):
    preset = db.query(Preset).get(preset_id)
    if not preset:
        raise HTTPException(404, "Preset not found")
    db.delete(preset)
    db.commit()
```

### Pydantic Schemas:

```python
class PresetCreate(BaseModel):
    name: str
    strategy: str
    config: dict  # {symbol, timeframe, leverage, params: {...}}

class PresetUpdate(BaseModel):
    name: str | None = None
    config: dict | None = None

class PresetResponse(BaseModel):
    id: int
    name: str
    strategy: str
    config: dict
    created_at: str
    updated_at: str
```

---

## Stage 2D: Batch DB Schema (Optional)

For tracking batch runs as a group:

```python
class Batch(Base):
    __tablename__ = "batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String, default="running")  # running, completed, partial, failed
    total_symbols = Column(Integer)
    completed_symbols = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

# Add batch_id FK to Run table:
class Run(Base):
    # ... existing columns ...
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=True)
```

---

## Implementation Order

```
2A    Batch endpoint + batch worker           ~4 hours
2B    Portfolio worker                         ~3 hours
2C    Presets DB table + CRUD                  ~2 hours
2D    Batch DB schema (optional)               ~1 hour
                                        Total: ~10 hours
```

## Files Changed

| File | Change |
|------|--------|
| `app/api/routes/backtest.py` | Batch endpoint, portfolio detection |
| `app/api/routes/presets.py` | NEW — preset CRUD |
| `app/api/schemas.py` | BatchRequest, PresetCreate/Update/Response |
| `app/backtest/workers/batch_worker.py` | NEW — batch orchestration |
| `app/backtest/workers/portfolio_worker.py` | NEW — portfolio engine wrapper |
| `app/repository/backtest/models.py` | Preset table, Batch table, Run.batch_id |
| `app/main.py` | Register preset routes |
