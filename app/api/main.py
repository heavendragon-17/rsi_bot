"""
FastAPI entry point.

Run with:
    python -m app.api.main                           # uses API_PORT env (default 8100)
    API_PORT=9000 python -m app.api.main             # override the port
    uvicorn app.api.main:app --reload --port 8100    # or via uvicorn CLI
"""

from __future__ import annotations

import os
import traceback
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    backtest_results,
    backtest_run,
    backtest_stream,
    data,
    history,
    presets,
    settings,
    strategies,
    trade_chart,
)
from app.repository.backtest.database import SessionLocal, init_db
from app.repository.backtest.seed import seed_strategies

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialise DB and seed strategies on server start."""
    from app.core.logging import setup_logging

    setup_logging(level="INFO", log_file="backtest_api.log")
    init_db()
    db = SessionLocal()
    try:
        seed_strategies(db)
    finally:
        db.close()
    logger.info("backtest_api_ready")
    yield


app = FastAPI(
    title="RSI Bot Backtest API",
    version="1.0.0",
    description="FastAPI backend for the RSI Bot backtest UI",
    lifespan=lifespan,
)

# CORS — allow any localhost / 127.0.0.1 port so the UI can move freely when
# the default port is taken. Override in production via API_CORS_ORIGINS.
_custom_origins = os.getenv("API_CORS_ORIGINS")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_custom_origins.split(",") if _custom_origins else [],
    allow_origin_regex=(
        None if _custom_origins else r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    ),
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
app.include_router(settings.router)
app.include_router(trade_chart.router)


# ── Global exception handler ───────────────────────────────────────────────
# Catches ALL unhandled exceptions and returns a proper JSON response.
# Without this, unhandled 500s bypass CORS middleware and the browser
# blocks the response entirely, hiding the real error from the developer.
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    logger.error(
        "unhandled_exception",
        method=request.method,
        url=str(request.url),
        error=str(exc),
        traceback="".join(tb),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": type(exc).__name__},
    )


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "app.api.main:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8100")),
        reload=True,
        log_level="info",
    )
