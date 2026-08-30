"""Application service for database-backed BTC signal review replays."""

from __future__ import annotations

import asyncio
import json
import math
import subprocess
from datetime import UTC, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from app.api import executor
from app.backtest.signal_replay import _default_paths
from app.backtest.signal_replay_analysis import chart_window_from_frame, source_metadata
from app.backtest.signal_replay_data import load_ohlcv_csv
from app.backtest.signal_replay_persistence import DEFINITION_VERSION
from app.backtest.signal_replay_worker import run_signal_replay_worker
from app.repository.backtest.models import (
    SignalForwardMetric,
    SignalReplayRun,
    SignalReplaySignal,
    SignalReview,
)

UTC_PLUS_7 = timezone(timedelta(hours=7), name="UTC+7")
REPLAY_SOURCE_TIMEFRAMES = ("5m", "15m", "1h", "4h")


def parse_boundary(raw: str | None, *, is_end: bool) -> datetime | None:
    """Parse a date or timestamp, interpreting naive values as UTC+7."""

    if raw is None or raw == "":
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(
            "date boundaries must be YYYY-MM-DD or an ISO timestamp"
        ) from exc
    if len(raw) == 10:
        parsed = datetime.combine(parsed.date(), time.min)
        if is_end:
            parsed += timedelta(days=1) - timedelta(microseconds=1)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC_PLUS_7)
    return parsed.astimezone(UTC)


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(UTC).replace(tzinfo=None)


def api_datetime(value: datetime | None) -> str | None:
    """Serialize DB's UTC-naive timestamps as explicit UTC ISO strings."""

    if value is None:
        return None
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat()


def _now_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _availability_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def current_git_hash() -> str | None:
    """Capture the code revision when the API is running from a Git checkout."""

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value or None


def _review_values(review: SignalReview | None) -> dict[str, Any]:
    if review is None:
        return {
            "quality": "UNREVIEWED",
            "human_outcome": "UNSET",
            "note": None,
            "reviewed_at": None,
            "updated_at": None,
            "future_unlocked_at": None,
        }
    return {
        "quality": review.quality,
        "human_outcome": review.human_outcome,
        "note": review.note,
        "reviewed_at": api_datetime(review.reviewed_at),
        "updated_at": api_datetime(review.updated_at),
        "future_unlocked_at": api_datetime(review.future_unlocked_at),
    }


def _metric_values(metric: SignalForwardMetric) -> dict[str, Any]:
    return {
        "horizon_minutes": metric.horizon_minutes,
        "price_at_observation": metric.price_at_observation,
        "return_pct": metric.return_pct,
        "mfe_pct": metric.mfe_pct,
        "mae_pct": metric.mae_pct,
        "observed_at": api_datetime(metric.observed_at),
        "complete": metric.complete,
        "warning": metric.warning,
    }


def run_summary(run: SignalReplayRun, db) -> dict[str, Any]:
    signals = db.query(SignalReplaySignal).filter_by(replay_run_id=run.id)
    m5_count = signals.filter_by(timeframe="5m").count()
    m15_count = signals.filter_by(timeframe="15m").count()
    return {
        "id": run.id,
        "status": run.status,
        "strategy_name": run.strategy_name,
        "definition_version": run.definition_version,
        "git_hash": run.git_hash,
        "symbol": run.symbol,
        "requested_start_at": api_datetime(run.requested_start_at),
        "requested_end_at": api_datetime(run.requested_end_at),
        "created_at": api_datetime(run.created_at),
        "started_at": api_datetime(run.started_at),
        "completed_at": api_datetime(run.completed_at),
        "signal_count": m5_count + m15_count,
        "m5_count": m5_count,
        "m15_count": m15_count,
        "error_message": run.error_message,
    }


def signal_summary(signal: SignalReplaySignal) -> dict[str, Any]:
    review = _review_values(signal.review)
    return {
        "id": signal.id,
        "replay_run_id": signal.replay_run_id,
        "event_id": signal.event_id,
        "sequence": signal.sequence,
        "timeframe": signal.timeframe,
        "trigger_close_at": api_datetime(signal.trigger_close_at),
        "trigger_close_price": signal.trigger_close_price,
        "decision_reason": signal.decision_reason,
        "quality": review["quality"],
        "human_outcome": review["human_outcome"],
        "note_present": bool(review["note"]),
    }


def signal_detail(signal: SignalReplaySignal) -> dict[str, Any]:
    return {
        "id": signal.id,
        "replay_run_id": signal.replay_run_id,
        "event_id": signal.event_id,
        "sequence": signal.sequence,
        "timeframe": signal.timeframe,
        "definition_version": signal.definition_version,
        "trigger_open_at": api_datetime(signal.trigger_open_at),
        "trigger_close_at": api_datetime(signal.trigger_close_at),
        "trigger_close_price": signal.trigger_close_price,
        "trigger_price_ema21": signal.trigger_price_ema21,
        "rsi21": signal.rsi21,
        "rsi_ema9": signal.rsi_ema9,
        "rsi_wma45": signal.rsi_wma45,
        "rsi_spread": signal.rsi_spread,
        "previous_rsi_ema9": signal.previous_rsi_ema9,
        "previous_rsi_wma45": signal.previous_rsi_wma45,
        "h4_close_price": signal.h4_close_price,
        "h4_price_ema21": signal.h4_price_ema21,
        "h4_close_at": api_datetime(signal.h4_close_at),
        "decision_reason": signal.decision_reason,
        "telegram_card": signal.telegram_card,
        "snapshot": signal.snapshot,
        "review": _review_values(signal.review),
        "forward_metrics": [_metric_values(metric) for metric in signal.forward_metrics],
    }


class SignalReplayService:
    """Coordinates replay jobs and exposes review-oriented query operations."""

    def get_availability(self) -> dict[str, Any]:
        """Inspect the canonical replay inputs and return their common range."""

        sources: list[dict[str, Any]] = []
        starts: list[datetime] = []
        ends: list[datetime] = []
        for timeframe, path in zip(
            REPLAY_SOURCE_TIMEFRAMES,
            _default_paths(),
            strict=True,
        ):
            if not path.is_file():
                sources.append(
                    {
                        "timeframe": timeframe,
                        "available": False,
                        "row_count": 0,
                        "available_start": None,
                        "available_end": None,
                        "source_modified_at": None,
                        "error": f"Missing {path.name}",
                    }
                )
                continue
            try:
                frame = load_ohlcv_csv(path, timeframe)
                metadata = source_metadata(path, frame, timeframe)
                available_start = _availability_datetime(
                    metadata["available_start"]
                )
                available_end = _availability_datetime(metadata["available_end"])
                if available_start is None or available_end is None:
                    raise ValueError("CSV contains no candles")
                starts.append(available_start)
                ends.append(available_end)
                sources.append(
                    {
                        "timeframe": timeframe,
                        "available": True,
                        "row_count": metadata["row_count"],
                        "available_start": metadata["available_start"],
                        "available_end": metadata["available_end"],
                        "source_modified_at": metadata["source_modified_at"],
                        "error": None,
                    }
                )
            except (OSError, ValueError) as exc:
                sources.append(
                    {
                        "timeframe": timeframe,
                        "available": False,
                        "row_count": 0,
                        "available_start": None,
                        "available_end": None,
                        "source_modified_at": None,
                        "error": f"{path.name}: {exc}",
                    }
                )

        ready = len(starts) == len(REPLAY_SOURCE_TIMEFRAMES)
        common_start = max(starts) if ready else None
        common_end = min(ends) if ready else None
        if common_start is not None and common_end is not None:
            ready = common_start <= common_end
        return {
            "ready": ready,
            "common_start_at": common_start.isoformat() if ready else None,
            "common_end_at": common_end.isoformat() if ready else None,
            "sources": sources,
        }

    def reconcile_orphaned_runs(self, db) -> None:
        """Fail running DB rows whose in-memory executor job no longer exists."""

        orphaned = (
            db.query(SignalReplayRun)
            .filter_by(status="running")
            .order_by(SignalReplayRun.created_at.asc())
            .all()
        )
        changed = False
        for run in orphaned:
            if executor.get_progress_queue(run.id) is not None:
                continue
            run.status = "failed"
            run.error_message = (
                "Replay was interrupted before completion. Start a new replay."
            )
            run.completed_at = _now_utc_naive()
            changed = True
        if changed:
            db.commit()

    async def start_run(self, start_raw: str | None, end_raw: str | None, db) -> int:
        self.reconcile_orphaned_runs(db)
        active_run = (
            db.query(SignalReplayRun)
            .filter_by(status="running")
            .order_by(SignalReplayRun.created_at.desc())
            .first()
        )
        if active_run is not None:
            raise ValueError(f"Signal replay #{active_run.id} is already running")

        availability = self.get_availability()
        if not availability["ready"]:
            errors = [
                source["error"]
                for source in availability["sources"]
                if source["error"]
            ]
            raise ValueError(
                "Signal replay data is not ready: " + "; ".join(errors)
            )
        available_start = _availability_datetime(availability["common_start_at"])
        available_end = _availability_datetime(availability["common_end_at"])
        if available_start is None or available_end is None:
            raise ValueError("Signal replay data has no common available range")

        start_at = parse_boundary(start_raw, is_end=False) or available_start
        end_at = parse_boundary(end_raw, is_end=True) or available_end
        if start_at is not None and end_at is not None and start_at > end_at:
            raise ValueError("start must be before or equal to end")
        if start_at < available_start or end_at > available_end:
            start_label = available_start.astimezone(UTC_PLUS_7).isoformat()
            end_label = available_end.astimezone(UTC_PLUS_7).isoformat()
            raise ValueError(
                "Replay range must stay inside the available data range "
                f"{start_label} to {end_label}"
            )

        now = _now_utc_naive()
        run = SignalReplayRun(
            status="running",
            strategy_name="btc_rsi_cross_alert",
            definition_version=DEFINITION_VERSION,
            git_hash=current_git_hash(),
            symbol="BTC/USDT",
            requested_start_at=_utc_naive(start_at),
            requested_end_at=_utc_naive(end_at),
            created_at=now,
            started_at=now,
            source_metadata={},
            counters={},
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        loop = asyncio.get_running_loop()
        executor.create_progress_queue(run.id)
        progress_cb = executor.make_progress_callback(run.id, loop)
        try:
            executor.submit_backtest(
                run.id,
                run_signal_replay_worker,
                run_id=run.id,
                start_at=start_at,
                end_at=end_at,
                loop=loop,
                progress_cb=progress_cb,
                publish_event_fn=executor.publish_event,
                cleanup_fn=executor.cleanup_job,
            )
        except Exception as exc:
            run.status = "failed"
            run.error_message = f"{type(exc).__name__}: {exc}"
            run.completed_at = _now_utc_naive()
            db.commit()
            executor.cleanup_job(run.id)
            raise
        return run.id

    async def stream_progress(self, run_id: int, db=None):
        """Reuse the existing SSE queue consumer for replay jobs."""

        if executor.get_progress_queue(run_id) is None:
            run = db.query(SignalReplayRun).filter_by(id=run_id).first() if db is not None else None
            if run is None:
                yield f"event: error\ndata: {json.dumps({'message': 'Signal replay run not found'})}\n\n"
            elif run.status == "failed":
                yield f"event: error\ndata: {json.dumps({'message': run.error_message or 'Signal replay failed'})}\n\n"
            elif run.status == "running":
                yield f"event: error\ndata: {json.dumps({'message': 'Replay was interrupted before completion. Start a new replay.'})}\n\n"
            else:
                yield f"event: complete\ndata: {json.dumps({'run_id': run_id, 'status': run.status})}\n\n"
            return

        from app.backtest.service import BacktestService

        async for event in BacktestService().stream_progress(run_id):
            yield event

    def get_run(self, run_id: int, db) -> dict[str, Any]:
        run = db.query(SignalReplayRun).filter_by(id=run_id).first()
        if run is None:
            raise LookupError("Signal replay run not found")
        return {
            "run": run_summary(run, db),
            "source_metadata": run.source_metadata or {},
            "counters": run.counters or {},
        }

    def list_signals(
        self,
        db,
        *,
        timeframe: str | None,
        replay_run_id: int | None,
        quality: str | None,
        human_outcome: str | None,
        start_raw: str | None,
        end_raw: str | None,
        page: int,
        limit: int,
    ) -> dict[str, Any]:
        start_at = parse_boundary(start_raw, is_end=False)
        end_at = parse_boundary(end_raw, is_end=True)
        query = db.query(SignalReplaySignal)
        if timeframe:
            if timeframe not in {"5m", "15m"}:
                raise ValueError("timeframe must be 5m or 15m")
            query = query.filter(SignalReplaySignal.timeframe == timeframe)
        if replay_run_id is not None:
            query = query.filter(SignalReplaySignal.replay_run_id == replay_run_id)
        if quality or human_outcome:
            query = query.join(SignalReview, isouter=True)
        if quality:
            query = query.filter(SignalReview.quality == quality)
        if human_outcome:
            query = query.filter(SignalReview.human_outcome == human_outcome)
        if start_at:
            query = query.filter(SignalReplaySignal.trigger_close_at >= _utc_naive(start_at))
        if end_at:
            query = query.filter(SignalReplaySignal.trigger_close_at <= _utc_naive(end_at))

        total = query.count()
        pages = max(1, math.ceil(total / limit))
        offset = (page - 1) * limit
        signals = (
            query.order_by(
                SignalReplaySignal.trigger_close_at.desc(),
                SignalReplaySignal.id.desc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )
        return {
            "signals": [signal_summary(signal) for signal in signals],
            "total": total,
            "page": page,
            "pages": pages,
        }

    def get_signal(self, signal_id: int, db) -> dict[str, Any]:
        signal = db.query(SignalReplaySignal).filter_by(id=signal_id).first()
        if signal is None:
            raise LookupError("Signal not found")
        return signal_detail(signal)

    def get_chart(
        self,
        signal_id: int,
        db,
        *,
        chart_timeframe: str | None,
        start_raw: str | None,
        end_raw: str | None,
    ) -> dict[str, Any]:
        signal = db.query(SignalReplaySignal).filter_by(id=signal_id).first()
        if signal is None:
            raise LookupError("Signal not found")
        run = db.query(SignalReplayRun).filter_by(id=signal.replay_run_id).first()
        if run is None:
            raise LookupError("Replay run not found")
        requested_timeframe = chart_timeframe or signal.timeframe
        if requested_timeframe not in REPLAY_SOURCE_TIMEFRAMES:
            raise ValueError("chart timeframe must be 5m, 15m, 1h, or 4h")
        metadata = (run.source_metadata or {}).get(requested_timeframe, {})
        csv_path_raw = metadata.get("path")
        csv_path = Path(csv_path_raw) if csv_path_raw else None
        allow_future = signal.review is not None and signal.review.quality != "UNREVIEWED"
        start_at = parse_boundary(start_raw, is_end=False)
        end_at = parse_boundary(end_raw, is_end=True)
        signal_time = signal.trigger_close_at.replace(tzinfo=UTC)
        if csv_path is None or not csv_path.is_file():
            return {
                "signal_id": signal_id,
                "timeframe": requested_timeframe,
                "candles": [],
                "available_start": metadata.get("available_start"),
                "available_end": metadata.get("available_end"),
                "requested_start": start_raw,
                "requested_end": end_raw,
                "has_before": False,
                "has_after": False,
                "future_allowed": allow_future,
                "signal_time": signal_time.isoformat(),
                "anchor_time": None,
                "warning": (
                    f"{requested_timeframe.upper()} replay source is unavailable "
                    "for this dataset."
                ),
            }
        try:
            frame = load_ohlcv_csv(csv_path, requested_timeframe)
            current_source = source_metadata(csv_path, frame, requested_timeframe)
            candles, chart_metadata = chart_window_from_frame(
                frame,
                requested_timeframe,
                trigger_close=signal_time,
                start_at=start_at,
                end_at=end_at,
                allow_future=allow_future,
            )
            source_warnings: list[str] = []
            for key in ("row_count", "available_start", "available_end", "source_modified_at"):
                if metadata.get(key) and metadata.get(key) != current_source.get(key):
                    source_warnings.append(f"Current CSV {key.replace('_', ' ')} differs from the replay source.")
            if source_warnings:
                warnings = [warning for warning in (chart_metadata.get("warning"), *source_warnings) if warning]
                chart_metadata["warning"] = " ".join(dict.fromkeys(warnings))
        except (LookupError, ValueError) as exc:
            return {
                "signal_id": signal_id,
                "timeframe": requested_timeframe,
                "candles": [],
                "available_start": metadata.get("available_start"),
                "available_end": metadata.get("available_end"),
                "requested_start": start_raw,
                "requested_end": end_raw,
                "has_before": False,
                "has_after": False,
                "future_allowed": allow_future,
                "signal_time": signal_time.isoformat(),
                "anchor_time": None,
                "warning": str(exc),
            }
        return {
            "signal_id": signal_id,
            "timeframe": requested_timeframe,
            "candles": candles,
            **chart_metadata,
        }

    def update_review(self, signal_id: int, patch, db) -> dict[str, Any]:
        signal = db.query(SignalReplaySignal).filter_by(id=signal_id).first()
        if signal is None:
            raise LookupError("Signal not found")
        review = signal.review
        if review is None:
            review = SignalReview(signal_id=signal_id, quality="UNREVIEWED", human_outcome="UNSET")
            db.add(review)
            db.flush()

        fields = patch.model_fields_set
        if "quality" in fields and patch.quality is not None:
            review.quality = patch.quality.value
            if review.quality == "UNREVIEWED":
                review.human_outcome = "UNSET"
                review.reviewed_at = None
                review.future_unlocked_at = None
            else:
                reviewed_at = _now_utc_naive()
                review.reviewed_at = reviewed_at
                review.future_unlocked_at = reviewed_at
        if "human_outcome" in fields and patch.human_outcome is not None:
            if patch.human_outcome.value != "UNSET" and review.quality == "UNREVIEWED":
                raise ValueError("Save a quality label before recording a human outcome")
            review.human_outcome = patch.human_outcome.value
        if "note" in fields:
            review.note = patch.note
        review.updated_at = _now_utc_naive()
        db.commit()
        db.refresh(review)
        return _review_values(review)
