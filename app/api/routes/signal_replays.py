"""BTC M5/M15 signal replay and human review routes."""

from __future__ import annotations

import tempfile
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from app.api.schemas import (
    SignalChartResponse,
    SignalForwardMetricResponse,
    SignalHumanOutcome,
    SignalQuality,
    SignalReplayAvailabilityResponse,
    SignalReplayBundleImportResponse,
    SignalReplayListResponse,
    SignalReplayRunDetail,
    SignalReplayRunRequest,
    SignalReplayRunSummary,
    SignalReplaySignalDetail,
    SignalReplayStartResponse,
    SignalReviewResponse,
    SignalReviewUpdate,
)
from app.backtest.signal_replay_bundle import (
    create_signal_review_bundle,
    import_signal_review_bundle,
)
from app.backtest.signal_replay_bundle_format import (
    MAX_ARCHIVE_BYTES,
    SignalReviewBundleError,
)
from app.backtest.signal_replay_service import SignalReplayService
from app.backtest.signal_replay_support import api_datetime, run_summary
from app.repository.backtest.database import SessionLocal
from app.repository.backtest.models import SignalReplayRun, SignalReplaySignal

router = APIRouter(prefix="/api/signal-replays", tags=["signal-replays"])
logger = structlog.get_logger()
_service = SignalReplayService()


def _remove_temporary_file(path: str) -> None:
    Path(path).unlink(missing_ok=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get(
    "/availability",
    response_model=SignalReplayAvailabilityResponse,
)
def get_signal_replay_availability():
    return _service.get_availability()


@router.post("/runs", status_code=201, response_model=SignalReplayStartResponse)
async def start_signal_replay(
    body: SignalReplayRunRequest,
    db: Session = Depends(get_db),
):
    try:
        run_id = await _service.start_run(body.start, body.end, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    logger.info("api_signal_replay_started", run_id=run_id)
    return {"run_id": run_id, "status": "running"}


@router.get("/runs", response_model=list[SignalReplayRunSummary])
def list_signal_replay_runs(
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
):
    _service.reconcile_orphaned_runs(db)
    runs = (
        db.query(SignalReplayRun)
        .order_by(SignalReplayRun.created_at.desc())
        .limit(limit)
        .all()
    )
    return [run_summary(run, db) for run in runs]


@router.get("/runs/{run_id}", response_model=SignalReplayRunDetail)
def get_signal_replay_run(run_id: int, db: Session = Depends(get_db)):
    try:
        return _service.get_run(run_id, db)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get("/runs/{run_id}/bundle")
def download_signal_replay_bundle(run_id: int, db: Session = Depends(get_db)):
    try:
        artifact = create_signal_review_bundle(run_id, db)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except (OSError, SignalReviewBundleError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    logger.info(
        "api_signal_review_bundle_exported",
        run_id=run_id,
        bundle_id=artifact.bundle_id,
    )
    return FileResponse(
        path=artifact.path,
        media_type="application/zip",
        filename=artifact.filename,
        background=BackgroundTask(_remove_temporary_file, str(artifact.path)),
    )


@router.post("/bundles/import", response_model=SignalReplayBundleImportResponse)
async def upload_signal_replay_bundle(
    request: Request,
    db: Session = Depends(get_db),
):
    raw_length = request.headers.get("content-length")
    if raw_length is not None:
        try:
            content_length = int(raw_length)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid Content-Length header"
            ) from None
        if content_length > MAX_ARCHIVE_BYTES:
            raise HTTPException(
                status_code=413, detail="Review bundle exceeds the 1 GiB upload limit"
            )

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="signal-review-upload-", suffix=".zip", delete=False
        ) as handle:
            temp_path = Path(handle.name)
            received = 0
            async for chunk in request.stream():
                received += len(chunk)
                if received > MAX_ARCHIVE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="Review bundle exceeds the 1 GiB upload limit",
                    )
                handle.write(chunk)
        if received == 0:
            raise HTTPException(status_code=400, detail="Review bundle upload is empty")
        result = await run_in_threadpool(import_signal_review_bundle, temp_path, db)
    except HTTPException:
        raise
    except SignalReviewBundleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except OSError as exc:
        raise HTTPException(
            status_code=400, detail=f"Could not store review bundle: {exc}"
        ) from None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    logger.info(
        "api_signal_review_bundle_imported",
        run_id=result.run_id,
        source_run_id=result.source_run_id,
        bundle_id=result.bundle_id,
        duplicate=result.duplicate,
    )
    return {
        "run_id": result.run_id,
        "bundle_id": result.bundle_id,
        "duplicate": result.duplicate,
        "signal_count": result.signal_count,
        "reviewed_count": result.reviewed_count,
        "source_run_id": result.source_run_id,
    }


@router.get("/runs/{run_id}/progress")
async def stream_signal_replay_progress(run_id: int, db: Session = Depends(get_db)):
    return StreamingResponse(
        _service.stream_progress(run_id, db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/signals", response_model=SignalReplayListResponse)
def list_signal_replay_signals(
    timeframe: str | None = None,
    replay_run_id: int | None = None,
    quality: SignalQuality | None = None,
    human_outcome: SignalHumanOutcome | None = None,
    start: str | None = None,
    end: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    try:
        return _service.list_signals(
            db,
            timeframe=timeframe,
            replay_run_id=replay_run_id,
            quality=quality.value if quality else None,
            human_outcome=human_outcome.value if human_outcome else None,
            start_raw=start,
            end_raw=end,
            page=page,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/signals/{signal_id}", response_model=SignalReplaySignalDetail)
def get_signal(signal_id: int, db: Session = Depends(get_db)):
    try:
        return _service.get_signal(signal_id, db)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get("/signals/{signal_id}/chart", response_model=SignalChartResponse)
def get_signal_chart(
    signal_id: int,
    timeframe: str | None = None,
    start: str | None = None,
    end: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        return _service.get_chart(
            signal_id,
            db,
            chart_timeframe=timeframe,
            start_raw=start,
            end_raw=end,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/signals/{signal_id}/forward-metrics", response_model=list[SignalForwardMetricResponse])
def get_signal_forward_metrics(signal_id: int, db: Session = Depends(get_db)):
    try:
        signal = db.query(SignalReplaySignal).filter_by(id=signal_id).first()
        if signal is None:
            raise LookupError("Signal not found")
        return [
            {
                "horizon_minutes": metric.horizon_minutes,
                "price_at_observation": metric.price_at_observation,
                "return_pct": metric.return_pct,
                "mfe_pct": metric.mfe_pct,
                "mae_pct": metric.mae_pct,
                "observed_at": api_datetime(metric.observed_at),
                "complete": metric.complete,
                "warning": metric.warning,
            }
            for metric in signal.forward_metrics
        ]
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.patch("/signals/{signal_id}/review", response_model=SignalReviewResponse)
def update_signal_review(
    signal_id: int,
    body: SignalReviewUpdate,
    db: Session = Depends(get_db),
):
    try:
        return _service.update_review(signal_id, body, db)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
