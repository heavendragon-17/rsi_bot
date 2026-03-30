"""
FastAPI entry point.

Run with:
    python -m app.api.main
    # or
    uvicorn app.api.main:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import backtest_results, backtest_run, backtest_stream, data, history, presets, strategies
from app.repository.backtest.database import SessionLocal, init_db
from app.repository.backtest.seed import seed_strategies


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialise DB and seed strategies on server start."""
    init_db()
    db = SessionLocal()
    try:
        seed_strategies(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="RSI Bot Backtest API",
    version="1.0.0",
    description="FastAPI backend for the RSI Bot backtest UI",
    lifespan=lifespan,
)

# CORS — allow local Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(backtest_run.router)
app.include_router(backtest_results.router)
app.include_router(backtest_stream.router)
app.include_router(history.router)
app.include_router(strategies.router)
app.include_router(data.router)
app.include_router(presets.router)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "app.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
