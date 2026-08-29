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
custom_origins = os.getenv("API_CORS_ORIGINS")
allow_origins = custom_origins.split(",") if custom_origins else []
allow_origin_regex = (
    None
    if custom_origins
    else r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
)
allow_methods=["*"], allow_headers=["*"], allow_credentials=True
```

The regex is a development default. Set an exact comma-separated
`API_CORS_ORIGINS` allowlist when the API is placed behind an authenticated
proxy. CORS does not provide authentication or prevent direct API clients.

---

## Executor

Backtests run in a `ThreadPoolExecutor` (not `ProcessPoolExecutor` — processes are used within the executor for grid search parallelism).

Job tracking dicts maintain SSE queues and job state:
- `progress_queues: Dict[str, asyncio.Queue]` — SSE event queues per run_id
- `running_jobs: Dict[str, Future]` — executor futures for cancellation

The executor entry point is `submit_backtest(job_id, fn, *args, **kwargs)`.
`job_id` is the executor's tracking key; worker-specific keyword arguments,
including `run_id`, are forwarded separately to `fn`.

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
python -m uvicorn app.api.main:app --reload --port 8100

# Production
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8100 --workers 1
```

Note: Use `--workers 1` — SQLite does not support concurrent writes from multiple processes.
