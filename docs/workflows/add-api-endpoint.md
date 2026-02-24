# Add an API Endpoint

> Add a new REST or SSE endpoint to the FastAPI backend.
> Reference implementations:
>   - SSE + background job: `app/api/routes/backtest.py`
>   - Simple CRUD: `app/api/routes/strategies.py`

## Prerequisites

- Read `docs/api-reference.md` — understand existing endpoints and conventions
- Read `docs/backtest-engine.md` — understand the SSE pattern if adding a streaming endpoint
- Read `app/api/schemas.py` — existing Pydantic request/response models

## Steps

### 1. Determine which router file to use

| Domain | Existing router file |
|--------|---------------------|
| Backtest run lifecycle | `app/api/routes/backtest.py` |
| Historical run list | `app/api/routes/history.py` |
| Strategy metadata | `app/api/routes/strategies.py` |
| Data download/status | `app/api/routes/data.py` |
| **New domain** | Create `app/api/routes/{domain}.py` |

If adding to an existing domain, add routes to the existing file. If it's a new domain, create a new router file.

### 2. Create the route

**For a new router file** — `app/api/routes/{domain}.py`:

Model on `app/api/routes/strategies.py` (simple) or `app/api/routes/backtest.py` (complex with SSE).

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.repository.backtest.database import SessionLocal
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/api/{domain}", tags=["{domain}"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/")
def list_items(db: Session = Depends(get_db)):
    ...
```

**For SSE endpoints** (long-running background jobs):

Follow the pattern in `app/api/routes/backtest.py`:
1. POST endpoint submits job via `app/api/executor.py` → `submit_backtest(run_id, fn)`
2. GET `/{run_id}/progress` returns `StreamingResponse` consuming from `get_progress_queue(run_id)`
3. The background function publishes events via `publish_event(run_id, event_dict)`

### 3. Register the router in main.py

File: `app/api/main.py`

Add import and registration:
```python
from app.api.routes import backtest, data, history, strategies, your_domain  # add

app.include_router(your_domain.router)  # add
```

### 4. Add request/response schemas

File: `app/api/schemas.py`

Add Pydantic models for request bodies and response models:
```python
class YourRequest(BaseModel):
    field: str
    ...

class YourResponse(BaseModel):
    id: int
    ...
```

### 5. Add DB models if needed

File: `app/repository/backtest/models.py`

If the endpoint requires new tables, add SQLAlchemy ORM models. Design rationale goes in code comments (not in `docs/database.md` — that file is auto-generated).

After adding models:
```bash
python scripts/gen_db_docs.py
```

## Testing

1. Write `tests/test_{domain}_api.py` using FastAPI `TestClient`:
   ```python
   from fastapi.testclient import TestClient
   from app.api.main import app
   client = TestClient(app)
   ```
2. Test happy path (200), not-found (404), and validation errors (422)
3. For SSE endpoints: test the event stream format
4. Run `pytest tests/ -v`
5. Manual smoke test:
   ```bash
   python -m uvicorn app.api.main:app --reload --port 8000
   curl http://localhost:8000/api/{domain}/
   ```

## Documentation Impact

Consult `docs/INDEX.md` → "Code Path → Documentation File" table:

- `app/api/` modified → update **`docs/api-reference.md`**: add the new endpoint with method, path, request schema, response schema, example curl, and error codes
- If `app/repository/` modified → run **`python scripts/gen_db_docs.py`** to regenerate `docs/database.md`
- Design rationale for new DB tables goes in code comments in `app/repository/backtest/models.py`
