# API Configuration

> FastAPI app setup, CORS, executor configuration, and database initialization.

---

## FastAPI App (`app/api/main.py`)

```python
app = FastAPI(title="RSI Bot Backtest API", version="1.0.0")
```

### Lifespan Startup
1. `init_db()` — creates SQLite tables if not exist
2. `seed_strategies(db)` — inserts strategy rows (if not already present)

### Routers

| Router | Prefix | Module |
|--------|--------|--------|
| backtest (run) | `/api/backtest` | `app/api/routes/backtest_run.py` |
| backtest (results) | `/api/backtest` | `app/api/routes/backtest_results.py` |
| backtest (stream) | `/api/backtest` | `app/api/routes/backtest_stream.py` |
| history | `/api/history` | `app/api/routes/history.py` |
| strategies | `/api/strategies` | `app/api/routes/strategies.py` |
| data | `/api/data` | `app/api/routes/data.py` |

### CORS

```python
origins = ["http://localhost:3000", "http://localhost:5173"]
allow_methods=["*"], allow_headers=["*"], allow_credentials=True
```

---

## Executor

Backtests run in a `ThreadPoolExecutor` (not `ProcessPoolExecutor` — processes are used within the executor for grid search parallelism).

Job tracking dicts maintain SSE queues and job state:
- `progress_queues: Dict[str, asyncio.Queue]` — SSE event queues per run_id
- `running_jobs: Dict[str, Future]` — executor futures for cancellation

---

## Database

- **Engine**: SQLite at `data/backtest.db`
- **ORM**: SQLAlchemy with declarative models in `app/repository/backtest/models.py`
- **Schema docs**: Auto-generated via `python scripts/gen_db_docs.py`
- **Tables**: runs, run_configs, run_results, run_timeseries, strategies, tags, trades
- **Key patterns**: TEXT for money, zlib BLOB for timeseries compression, cascade deletes

---

## Running

```bash
# Development (with auto-reload)
python -m uvicorn app.api.main:app --reload --port 8000

# Production
python -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Note: Use `--workers 1` — SQLite does not support concurrent writes from multiple processes.
