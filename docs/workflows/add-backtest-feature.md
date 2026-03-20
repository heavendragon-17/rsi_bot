# Add a Backtest Feature

> Add a new metric, optimization mode, or quant analysis feature to the backtest system.
> Reference implementations:
>   - Engine: `app/trading/engine.py`, `app/backtest/event_source.py`
>   - API (SSE pattern): `app/api/routes/backtest.py`, `app/api/executor.py`
>   - Optimization spec: `docs/optimization.md`
>   - UI stores: `ui/src/stores/backtestStore.ts`

## Prerequisites

- Read `docs/backtest-engine.md` — understand the full single-backtest flow
- Read `docs/optimization.md` — understand grid search and walk-forward patterns
- Read `docs/api-reference.md` — understand existing endpoints and SSE protocol
- Determine your feature type — then follow the appropriate branch below

---

## Branch A: New Metric

> Add a new performance metric (e.g., Omega ratio, Calmar ratio, Kelly fraction) to backtest results.

### A1. Compute in the engine

File: `app/backtest/backtest_engine.py`

Find the method that computes metrics after the backtest completes. Add the new metric to the results dict:

```python
results["risk_metrics"]["omega_ratio"] = self._compute_omega(returns)
```

Keep the computation in a separate private method for testability.

### A2. Persist to the database

File: `app/repository/backtest/models.py`

Add a new column to `RunResult` if the metric should be persisted. If it's a complex metric (multi-value), consider storing as JSON in an existing column.

File: `app/api/routes/backtest.py`

In the results persistence logic, read the new metric from the results dict and write to the DB. In the detail endpoint, expose it in the response.

### A3. Display in the UI

File: `ui/src/` — find the results dashboard component.

Add a metric card following existing patterns. The metric value comes from the `GET /api/backtest/{run_id}` response.

---

## Branch B: New Optimization Mode

> Add a new parameter sweep or optimization method (e.g., Monte Carlo simulation, Bayesian optimization, sensitivity analysis).

### B1. Create the optimization runner

File: `app/backtest/{name}_optimizer.py`

The runner:
- Accepts a config (strategy params, parameter space definition, data path)
- Runs `BacktestEngine.run()` in a loop or via `ProcessPoolExecutor`
- Reports progress via a callback or queue
- Returns aggregated results

Model on the grid search pattern described in `docs/optimization.md`.

### B2. Create the API route

File: `app/api/routes/{name}.py`

Follow the SSE pattern from `app/api/routes/backtest.py`:

1. **POST endpoint**: Validate request → create DB parent row → submit job to executor (`app/api/executor.py` → `submit_backtest(run_id, fn)`) → return `{"run_id": ..., "status": "running"}`
2. **GET SSE endpoint**: `/{run_id}/progress` returns `StreamingResponse` consuming from `get_progress_queue(run_id)` → yields `data: {...}\n\n` events
3. **GET detail endpoint**: `/{run_id}` returns completed results from DB
4. **DELETE endpoint**: `/{run_id}` cancels a running job

### B3. Register the router

File: `app/api/main.py`

```python
from app.api.routes import ..., your_name
app.include_router(your_name.router)
```

### B4. Add DB models

File: `app/repository/backtest/models.py`

Add tables for optimization-specific results (e.g., parameter combinations, aggregated metrics). Run:
```bash
python scripts/gen_db_docs.py
```

### B5. Add the UI

**Zustand store** — `ui/src/stores/{name}Store.ts`:

Follow existing store patterns. The store needs:
- Config state (parameter space, optimization settings)
- Results state (best params, all runs, progress)
- `run()` action: POST to new endpoint, connect SSE stream for progress
- `reset()` action

**UI components**:
- Add a tab/section to the navigation for the new optimization mode
- Add a configuration panel for mode-specific settings
- Add a results visualization (table, chart, or heatmap)

---

## Branch C: New Engine Mode

> Add a new backtest execution mode (e.g., multi-timeframe, portfolio-level, replay mode).

### C1. Extend or subclass the Engine

File: `app/trading/engine.py` (base) or create a new subclass

The base `Engine` processes events from an `IEventSource` and dispatches to handlers. You can:
- **Subclass `Engine`**: Override `_handle_candle_close()` or add new event handlers
- **Create a sibling**: If the execution model is fundamentally different

### C2. Create a new event source if needed

File: `app/backtest/{name}_event_source.py`

Implement `IEventSource` from `app/trading/event_source.py`. Model on `app/backtest/event_source.py`.

The `IEventSource` interface requires:
- `events()` → `Iterator[EngineEvent]`: yields events in chronological order
- `stop()`: signals to stop iteration

### C3. Integrate with the API

Follow the same API pattern as Branch B (SSE route + executor). The API routes call your new engine/event-source combination instead of the standard `BacktestEngine`.

---

## Testing

**Branch A (new metric):**
1. Unit test the metric calculation function with known inputs/expected outputs
2. Integration test: run a full backtest on test data, assert the metric is present in the results dict and has a reasonable value
3. Run `pytest tests/ -v`

**Branch B (new optimization mode):**
1. Unit test the optimizer with a tiny parameter grid (2x2 — must complete fast)
2. Test SSE event sequence: progress events followed by a complete event
3. Test DB persistence: parent row updated, child runs created
4. Test cancellation: DELETE stops the running job
5. Run `pytest tests/ -v`

**Branch C (new engine mode):**
1. Unit test the new event source with synthetic data
2. Integration test: full engine run with the new event source, verify trade output format matches existing
3. Run `pytest tests/ -v`

## Documentation Impact

Consult `docs/INDEX.md` → "Code Path → Documentation File" table:

- `app/trading/engine.py` or `app/backtest/` modified → update **`docs/backtest-engine.md`**
- New optimization mode → update **`docs/optimization.md`** with the new mode's specification
- `app/api/` modified → update **`docs/api-reference.md`** with the new endpoints
- `app/repository/` modified → run **`python scripts/gen_db_docs.py`**
- `ui/src/` modified → update **`docs/ui-spec.md`**: add the new Zustand store to the stores table, document the new mode tab
