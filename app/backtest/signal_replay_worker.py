"""Background worker for database-backed BTC signal replay runs."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import structlog

from app.backtest.signal_replay import (
    _default_paths,
    run_btc_alert_replay,
)
from app.backtest.signal_replay_analysis import source_metadata
from app.backtest.signal_replay_data import load_ohlcv_csv
from app.backtest.signal_replay_persistence import build_signal_rows
from app.repository.backtest.database import SessionLocal
from app.repository.backtest.models import SignalReplayRun

logger = structlog.get_logger()


def _counts_payload(result) -> dict[str, Any]:
    counts = asdict(result.counts)
    counts.update(
        {
            "candidates": result.counts.candidates,
            "not_ready": result.counts.not_ready,
            "rejected": result.counts.rejected,
            "warmup_skipped": result.counts.warmup_skipped,
            "signals": len(result.signals),
            "m5_signals": sum(signal.timeframe == "5m" for signal in result.signals),
            "m15_signals": sum(signal.timeframe == "15m" for signal in result.signals),
        }
    )
    return counts


def _utc_naive(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None)


def run_signal_replay_worker(
    *,
    run_id: int,
    start_at: datetime | None,
    end_at: datetime | None,
    loop,
    progress_cb,
    publish_event_fn,
    cleanup_fn,
) -> None:
    """Execute replay, metrics, and persistence in one isolated worker."""

    db = SessionLocal()
    source_facts: dict[str, Any] = {}
    try:
        run = db.query(SignalReplayRun).filter_by(id=run_id).first()
        if run is None:
            raise LookupError(f"Signal replay run {run_id} not found")

        m5_path, m15_path, h1_path, h4_path = _default_paths()
        m5_frame = load_ohlcv_csv(m5_path, "5m")
        m15_frame = load_ohlcv_csv(m15_path, "15m")
        h1_frame = load_ohlcv_csv(h1_path, "1h")
        h4_frame = load_ohlcv_csv(h4_path, "4h")
        source_facts = {
            "5m": source_metadata(m5_path, m5_frame, "5m"),
            "15m": source_metadata(m15_path, m15_frame, "15m"),
            "1h": source_metadata(h1_path, h1_frame, "1h"),
            "4h": source_metadata(h4_path, h4_frame, "4h"),
        }
        progress_cb({
            "pct": 10,
            "phase": "load",
            "candle": 0,
            "total": len(m5_frame) + len(m15_frame) + len(h1_frame) + len(h4_frame),
        })

        result = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            h1_path=h1_path,
            start_utc7=start_at,
            end_utc7=end_at,
            write_output=False,
        )
        progress_cb(
            {
                "pct": 72,
                "phase": "signals",
                "candle": result.counts.candidates,
                "total": result.counts.candidates,
            }
        )

        run.source_metadata = source_facts
        run.counters = _counts_payload(result)

        def report_metric_progress(completed: int, total: int) -> None:
            fraction = completed / total if total else 1.0
            progress_cb(
                {
                    "pct": 72 + fraction * 18,
                    "phase": "metrics",
                    "candle": completed,
                    "total": total,
                }
            )

        rows = build_signal_rows(
            result,
            replay_run_id=run_id,
            m5_frame=m5_frame,
            m15_frame=m15_frame,
            on_progress=report_metric_progress,
        )
        progress_cb(
            {
                "pct": 92,
                "phase": "saving",
                "candle": len(rows),
                "total": len(rows),
            }
        )
        db.add_all(rows)
        run.status = "completed"
        run.completed_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()
        progress_cb(
            {
                "pct": 100,
                "phase": "complete",
                "candle": len(rows),
                "total": len(rows),
            }
        )
        publish_event_fn(
            run_id,
            loop,
            "complete",
            {
                "run_id": run_id,
                "status": "completed",
                "signal_count": len(rows),
                "m5_count": sum(row.timeframe == "5m" for row in rows),
                "m15_count": sum(row.timeframe == "15m" for row in rows),
            },
        )
    except Exception as err:
        error_message = f"{type(err).__name__}: {err}"
        db.rollback()
        failed = db.query(SignalReplayRun).filter_by(id=run_id).first()
        if failed is not None:
            failed.status = "failed"
            failed.source_metadata = source_facts
            failed.error_message = error_message
            failed.completed_at = datetime.now(UTC).replace(tzinfo=None)
            db.commit()
        logger.error("signal_replay_worker_error", run_id=run_id, error=error_message)
        publish_event_fn(
            run_id,
            loop,
            "error",
            {"run_id": run_id, "message": error_message},
        )
    finally:
        db.close()
        cleanup_fn(run_id)
