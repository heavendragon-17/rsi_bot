"""
FastAPI Server for Backtest API
================================
Local REST API for backtest results and quant tools.
Runs on localhost:8765 with CORS enabled for UI dev server.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.db.schema import init_db, seed_defaults


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    init_db()
    seed_defaults()
    yield


app = FastAPI(
    title="RSI Bot Backtest API",
    version="0.1.0",
    description="Local REST API for backtest results and quant analysis",
    lifespan=lifespan
)

# CORS middleware for local UI dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite default
        "http://localhost:3000",  # Alternative
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}


# Include route modules
from app.api.routes import sessions, backtest, grid_search
app.include_router(sessions.router, prefix="/api")
app.include_router(backtest.router, prefix="/api")
app.include_router(grid_search.router, prefix="/api")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.api.server:app", host="0.0.0.0", port=8765, reload=True)
